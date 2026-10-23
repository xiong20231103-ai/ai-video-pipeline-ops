import json,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from agent.core.snapshot import capture
from tools.shadow_capture import CaptureError
from tools.shadow_store import put_snapshot,materialize_snapshot,usage
from tools.shadow_store_compact import plan_compaction,apply_compaction,main
from tools.shadow_sqlite_snapshot import sqlite_page_size

LEGACY='a'*64
CAP=256*1024*1024


class PageStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.db=self.root/'live.db';self.store=self.root/'store';self.count=0
        with sqlite3.connect(self.db) as conn:
            conn.execute('PRAGMA page_size=4096');conn.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,payload TEXT)')
            conn.executemany('INSERT INTO events VALUES(?,?)',((i,'x'*900) for i in range(4000)))
        conn.close()

    def snapshot(self):
        self.count+=1
        return capture(self.root/f'snap{self.count}',databases={'repository/data/ops.db':self.db},facts={},
                       frozen_at=f'2026-10-23T00:00:{self.count:02d}+00:00',legacy_sha256=LEGACY)

    def update_one_row(self,value):
        with sqlite3.connect(self.db) as conn:conn.execute('UPDATE events SET payload=? WHERE id=1234',(value,))
        conn.close()

    def test_one_changed_row_stores_about_one_page_not_64kib(self):
        self.assertEqual(4096,sqlite_page_size(self.db))
        put_snapshot(self.snapshot(),self.store,approved_total_bytes=CAP)
        self.update_one_row('y'*900)
        second=put_snapshot(self.snapshot(),self.store,approved_total_bytes=CAP)
        # Changed data page + header page + one listing segment + the index.
        self.assertLess(second['newBytes'],64*1024)
        index=json.loads(next(p for p in (self.store/'snapshots').iterdir()).read_bytes())
        entry=index['files']['repository/data/ops.db']
        self.assertEqual(4096,entry['pageSize']);self.assertTrue(entry['segments'])

    def test_page_store_restores_exact_database_bytes(self):
        snap=self.snapshot();stored=put_snapshot(snap,self.store,approved_total_bytes=CAP)
        restored=materialize_snapshot(self.store,stored['sourceIdentity'],self.root/'restored')
        self.assertEqual((snap.root/'repository/data/ops.db').read_bytes(),(restored.root/'repository/data/ops.db').read_bytes())

    def test_corrupt_listing_segment_refuses_restore(self):
        stored=put_snapshot(self.snapshot(),self.store,approved_total_bytes=CAP)
        index=json.loads((self.store/'snapshots'/(stored['sourceIdentity']+'.json')).read_bytes())
        segment=index['files']['repository/data/ops.db']['segments'][0]
        (self.store/'objects'/segment).write_bytes(b'not-a-listing')
        with self.assertRaisesRegex(CaptureError,'corrupt'):
            materialize_snapshot(self.store,stored['sourceIdentity'],self.root/'restored')


class CompactionTests(PageStoreTests):
    def three_snapshots(self):
        ids=[]
        for value in ('a','b','c'):
            self.update_one_row(value*900)
            ids.append(put_snapshot(self.snapshot(),self.store,approved_total_bytes=CAP)['sourceIdentity'])
        return ids

    def verdict(self,snapshots,conclusion='accepted'):
        path=self.root/'verdict.json'
        path.write_text(json.dumps({'schema':1,'batchId':'10.22-resume','conclusion':conclusion,'snapshots':snapshots}),encoding='utf-8')
        return path

    def test_dry_run_changes_nothing(self):
        first,middle,last=self.three_snapshots()
        before={p.relative_to(self.store).as_posix():p.read_bytes() for p in self.store.rglob('*') if p.is_file()}
        plan=plan_compaction(self.store,self.verdict([first,middle,last]),drop=[middle],keep=[first,last])
        self.assertGreater(plan['bytesFreed'],0)
        self.assertEqual(before,{p.relative_to(self.store).as_posix():p.read_bytes() for p in self.store.rglob('*') if p.is_file()})

    def test_apply_frees_space_and_kept_snapshots_still_restore_exactly(self):
        first,middle,last=self.three_snapshots()
        expected={i:materialize_snapshot(self.store,i,self.root/('before-'+i[:8])).root.joinpath('repository/data/ops.db').read_bytes() for i in (first,last)}
        used=usage(self.store)
        record=apply_compaction(self.store,plan_compaction(self.store,self.verdict([first,middle,last]),drop=[middle],keep=[first,last]))
        self.assertLess(usage(self.store),used);self.assertEqual(['10.22-resume'],[p.name for p in (self.store/'retired').iterdir()])
        self.assertTrue((self.store/'retired'/'10.22-resume'/(middle+'.json')).exists())
        self.assertNotIn('_unreferenced',record)
        for identity,body in expected.items():
            restored=materialize_snapshot(self.store,identity,self.root/('after-'+identity[:8]))
            self.assertEqual(body,(restored.root/'repository/data/ops.db').read_bytes())

    def test_snapshots_outside_the_batch_keep_their_objects(self):
        first,middle,last=self.three_snapshots()
        # The verdict only covers the batch; the store also holds `last` from elsewhere.
        apply_compaction(self.store,plan_compaction(self.store,self.verdict([first,middle,last]),drop=[middle],keep=[first]))
        materialize_snapshot(self.store,last,self.root/'other')

    def test_refusals(self):
        first,middle,last=self.three_snapshots()
        verdict=self.verdict([first,middle])
        for kwargs,code in [({'drop':[middle],'keep':[]},'key_snapshot_required'),
                            ({'drop':[],'keep':[first]},'nothing_to_compact'),
                            ({'drop':[middle],'keep':[middle]},'both_kept_and_dropped'),
                            ({'drop':[last],'keep':[first]},'does_not_cover'),
                            ({'drop':['../x'],'keep':[first]},'identity_invalid')]:
            with self.subTest(code=code),self.assertRaisesRegex(CaptureError,code):plan_compaction(self.store,verdict,**kwargs)
        with self.assertRaisesRegex(CaptureError,'verdict_invalid'):
            plan_compaction(self.store,self.verdict([first,middle],conclusion='pending'),drop=[middle],keep=[first])

    def test_busy_writer_or_capture_lock_refuses_apply(self):
        first,middle,last=self.three_snapshots()
        plan=plan_compaction(self.store,self.verdict([first,middle,last]),drop=[middle],keep=[first])
        (self.store/'.writer.lock').write_text('owner')
        with self.assertRaisesRegex(CaptureError,'writer_busy'):apply_compaction(self.store,plan)
        self.assertEqual('owner',(self.store/'.writer.lock').read_text());(self.store/'.writer.lock').unlink()
        (self.root/'.capture-writer.lock').write_text('capture')
        with self.assertRaisesRegex(CaptureError,'capture_writer_busy'):apply_compaction(self.store,plan)
        self.assertTrue((self.store/'snapshots'/(middle+'.json')).exists())

    def test_cli_defaults_to_dry_run(self):
        first,middle,last=self.three_snapshots();verdict=self.verdict([first,middle,last])
        self.assertEqual(0,main(['--store',str(self.store),'--verdict',str(verdict),'--drop',middle,'--keep',first]))
        self.assertTrue((self.store/'snapshots'/(middle+'.json')).exists())


if __name__=='__main__':unittest.main()
