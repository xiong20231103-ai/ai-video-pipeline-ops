"""Window-budget fixes for aligned capture; synthetic roots and databases only."""
import copy,sqlite3,unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from agent.core import snapshot as snapshot_module
from agent.core.snapshot import SnapshotError,capture,rows_sha256
from tools import shadow_capture
from tools.shadow_capture import CaptureError,aligned_capture

ROOT=Path(__file__).resolve().parents[1]
LEGACY='a'*64


class DriveRootAliasTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def capture(self,aliases):
        return capture(self.root/'snap',facts={'pathAliases':aliases},frozen_at='2026-10-23T00:00:00+00:00',legacy_sha256=LEGACY)

    def test_drive_root_is_a_valid_capture_root(self):
        snap=self.capture({'E:\\':'final','E:\\音频':'audio'})
        self.assertEqual({'E:\\':'final','E:\\音频':'audio'},snap.manifest['facts']['pathAliases'])

    def test_relative_or_drive_relative_alias_is_still_rejected(self):
        for alias in ('final','E:','E:relative'):
            with self.subTest(alias=alias),self.assertRaisesRegex(SnapshotError,'invalid_path_alias'):
                self.capture({alias:'final'})


class RowsHashCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'ops.db'
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,payload TEXT)')
            db.execute("INSERT INTO events VALUES(1,'first')");db.commit()
        snapshot_module._ROWS_HASHES.clear()

    def test_closed_copy_is_read_once(self):
        reads=[]
        real=snapshot_module.sqlite_rows
        with patch.object(snapshot_module,'sqlite_rows',side_effect=lambda path:reads.append(path) or real(path)):
            first=rows_sha256(self.db);second=rows_sha256(self.db)
        self.assertEqual(first,second);self.assertEqual(1,len(reads))

    def test_live_wal_is_reread_and_sees_uncheckpointed_rows(self):
        before=rows_sha256(self.db)
        with closing(sqlite3.connect(self.db)) as writer:
            writer.execute('PRAGMA wal_autocheckpoint=0')
            writer.execute("INSERT INTO events VALUES(2,'second')");writer.commit()
            self.assertGreater(self.db.with_name('ops.db-wal').stat().st_size,0)
            self.assertNotEqual(before,rows_sha256(self.db))
            with self.assertRaisesRegex(SnapshotError,'closed_database'):rows_sha256(self.db,rows={})

    def test_changed_bytes_never_reuse_an_old_hash(self):
        before=rows_sha256(self.db)
        with closing(sqlite3.connect(self.db)) as writer:
            writer.execute("INSERT INTO events VALUES(2,'second')");writer.commit()
            writer.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.assertNotEqual(before,rows_sha256(self.db))


class AlignedWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.live=self.root/'live';(self.live/'metadata').mkdir(parents=True)
        self.state=self.live/'state.json';self.state.write_text('{"items":[]}',encoding='utf-8')
        for i in range(5):(self.live/'metadata'/f'handoff-{i}.json').write_text('{"done":true}',encoding='utf-8')
        self.source=self.root/'app.py'
        self.source.write_text((ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
        self.plan={'schema':1,'roots':{'workbench':str(self.live)},
                   'files':{'workbench/state.json':{'root':'workbench','path':'state.json'}},
                   'trees':{'workbench/metadata':{'root':'workbench','path':'metadata'}}}

    def capture(self):
        return aligned_capture(self.plan,self.root/'snapshot',source_path=self.source,
                               process_probe=lambda:{'processRecords':[],'processIds':[]},http_probe=lambda:{})

    def test_privacy_refusal_still_happens_after_the_window(self):
        self.state.write_text('{"password":"fixture-secret"}',encoding='utf-8')
        with self.assertRaises((CaptureError,SnapshotError)):self.capture()
        self.assertFalse((self.root/'snapshot').exists())

    def test_small_file_hashing_is_capped_in_aligned_capture(self):
        with patch.object(shadow_capture,'WINDOW_HASH_SECONDS',0):snap=self.capture()
        nodes=snap.manifest['facts']['filesystem']
        self.assertTrue(all(nodes[f'workbench/metadata/handoff-{i}.json']['hashPending'] for i in range(5)))
        self.assertEqual(b'{"items":[]}',snap.read('workbench/state.json'))


if __name__=='__main__':unittest.main()
