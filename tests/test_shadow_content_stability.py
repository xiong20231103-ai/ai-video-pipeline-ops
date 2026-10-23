"""Content-aware windows on synthetic roots only; never imports production app."""
from contextlib import contextmanager
import hashlib,json,os,threading,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.shadow_capture import (aligned_capture,measure_directory_stability,validate_plan,
    _inventory,_stat,_read,recheck_state,ChangeReport,SmallReadBudget,CaptureError)

ROOT=Path(__file__).resolve().parents[1]


@contextmanager
def repeated_replacement(paths,content=b'{"ready":true}'):
    stop=threading.Event();condition=threading.Condition();version=[0];errors=[]
    def run():
        try:
            while not stop.wait(.2):
                for path in paths:
                    temporary=path.with_name(path.name+'.tmp')
                    temporary.write_bytes(content);os.replace(temporary,path)
                with condition:version[0]+=1;condition.notify_all()
        except Exception as error:
            errors.append(type(error).__name__)
            with condition:condition.notify_all()
    thread=threading.Thread(target=run,daemon=True);thread.start()
    def next_version():
        with condition:
            wanted=version[0]+1
            if not condition.wait_for(lambda:version[0]>=wanted or errors,timeout=10):raise AssertionError('fixture writer timeout')
            if errors:raise AssertionError('fixture writer failed')
    try:yield next_version
    finally:
        stop.set();thread.join(10)
        if thread.is_alive() or errors:raise AssertionError('fixture writer did not exit cleanly')


class ContentStabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.live=self.root/'live';self.tree=self.live/'metadata';self.tree.mkdir(parents=True)
        self.state=self.live/'workbench.ready.json';self.state.write_bytes(b'{"ready":true}')
        self.small=self.tree/'handoff.json';self.small.write_bytes(b'{"ready":true}')
        self.source=self.root/'app.py';self.source.write_bytes((ROOT/'contracts/legacy-app-f78db5a.txt').read_bytes())
        self.plan=dict(schema=1,roots={'workbench':str(self.live)},
            files={'workbench/workbench.ready.json':dict(root='workbench',path='workbench.ready.json')},
            trees={'workbench/metadata':dict(root='workbench',path='metadata')})
    def capture(self,between=lambda:None):
        calls=[]
        def reply():
            calls.append(1)
            if len(calls)==2:between()
            return {}
        return aligned_capture(self.plan,self.root/'snapshot',source_path=self.source,process_probe=lambda:{},http_probe=reply)

    def test_repeated_atomic_same_content_json_succeeds_and_records_rewrite(self):
        with repeated_replacement([self.state,self.small]) as next_version:
            snapshot=self.capture(between=next_version)
        facts=snapshot.manifest['facts'];proof=facts['captureProof']
        self.assertTrue(facts['filesystem']['workbench/metadata/handoff.json']['rewrittenSameContent'])
        self.assertGreaterEqual(proof['stabilityChanges']['rewrittenSameContentCount'],2)
        self.assertEqual(b'{"ready":true}',snapshot.read('workbench/workbench.ready.json'))

    def test_directory_probe_uses_same_replacement_policy(self):
        with repeated_replacement([self.small]) as next_version:
            report=measure_directory_stability(self.plan,self.root/'probe',between=next_version)
        self.assertEqual(0,report['directoryChangeFailedRounds']);self.assertEqual(0,report['unmeasurableRounds'])
        self.assertGreaterEqual(report['rewrittenSameContentCount'],3)
        self.assertTrue(all(row['within20Seconds'] for row in report['windows']))

    def test_changed_heartbeat_content_rejects_state_window(self):
        def changed():self.state.write_bytes(b'{"ready":null}')
        with self.assertRaisesRegex(CaptureError,'state_changed_in_window'):self.capture(between=changed)
        self.assertFalse((self.root/'snapshot').exists())

    def test_declared_volatile_heartbeat_keeps_first_read_and_reports_update(self):
        self.plan['volatileFiles']=['workbench/workbench.ready.json']
        def changed():self.state.write_bytes(b'{"ready":true,"at":2}')
        snapshot=self.capture(between=changed)
        self.assertEqual(b'{"ready":true}',snapshot.read('workbench/workbench.ready.json'))
        changes=snapshot.manifest['facts']['captureProof']['stabilityChanges']
        self.assertEqual(1,changes['changeCounts'].get('volatile-update'))
        self.assertIn({'path':'workbench/workbench.ready.json','type':'volatile-update'},changes['changes'])

    def test_volatile_heartbeat_removal_still_rejects_window(self):
        self.plan['volatileFiles']=['workbench/workbench.ready.json']
        with self.assertRaisesRegex(CaptureError,'state_changed_in_window'):self.capture(between=self.state.unlink)

    def test_volatile_list_must_name_whitelisted_state_files_only(self):
        for bad in ['workbench/workbench.ready.json',['workbench/metadata'],['other.json'],
                    ['workbench/workbench.ready.json']*2,[f'f{i}' for i in range(9)]]:
            with self.subTest(bad=bad),self.assertRaisesRegex(CaptureError,'volatile_files_invalid'):
                validate_plan({**self.plan,'volatileFiles':bad},self.root/'check')

    def test_volatile_read_accepts_a_settled_new_version(self):
        changes=ChangeReport();original=_stat(self.state);calls=[]
        real=_stat
        def stat(path):
            # The first post-read stat reports a newer heartbeat than was opened.
            calls.append(path)
            if len(calls)==1:self.state.write_bytes(b'{"ready":true,"at":3}')
            return real(path)
        with patch('tools.shadow_capture._stat',side_effect=stat):
            body,info=_read(self.state,1024,changes=changes,logical_path='hb',volatile=True)
        self.assertEqual(b'{"ready":true,"at":3}',body)
        self.assertEqual({'volatile-update':1},changes.report()['changeCounts'])
        self.assertNotEqual(original,info)

    def test_changed_tree_small_file_is_pending_without_rejecting_window(self):
        snapshot=self.capture(between=lambda:self.small.write_bytes(b'{"ready":null}'))
        node=snapshot.manifest['facts']['filesystem']['workbench/metadata/handoff.json']
        self.assertTrue(node['hashPending']);self.assertEqual('writing_or_changed',node['hashState'])
        changes=snapshot.manifest['facts']['captureProof']['stabilityChanges']
        self.assertIn({'path':'workbench/metadata/handoff.json','type':'content-change'},changes['changes'])

    def test_directory_timestamp_only_is_preserved_not_failed(self):
        stamp=self.tree.stat().st_mtime_ns+1000000000
        snapshot=self.capture(between=lambda:os.utime(self.tree,ns=(stamp,stamp)))
        node=snapshot.manifest['facts']['filesystem']['workbench/metadata']
        self.assertEqual(stamp,node['mtimeNs'])
        self.assertIn({'path':'workbench/metadata','type':'stat-only'},snapshot.manifest['facts']['captureProof']['stabilityChanges']['changes'])

    def test_add_delete_or_type_change_is_directory_failure(self):
        for operation in ('add','delete','type'):
            with self.subTest(operation=operation):
                if operation=='add':change=lambda:(self.tree/'new.json').write_text('{}')
                elif operation=='delete':change=lambda:self.small.unlink()
                else:
                    def change():self.small.unlink();self.small.mkdir()
                with self.assertRaisesRegex(CaptureError,'directory_changed_in_window'):self.capture(between=change)
                if self.small.is_dir():self.small.rmdir()
                self.small.write_bytes(b'{"ready":true}')
                if (self.tree/'new.json').exists():(self.tree/'new.json').unlink()

    def test_lock_records_existence_without_reading_or_comparing_timestamps(self):
        lock=self.tree/'project.json.lock';lock.write_bytes(b'not evidence')
        original=Path.open
        def opened(path,*args,**kwargs):
            if path==lock:raise AssertionError('lock content must not be read')
            return original(path,*args,**kwargs)
        stamp=lock.stat().st_mtime_ns+1000000000
        with patch.object(Path,'open',opened):
            snapshot=self.capture(between=lambda:os.utime(lock,ns=(stamp,stamp)))
        self.assertEqual({'kind':'file','exists':True,'metadataPolicy':'existence-only'},snapshot.manifest['facts']['filesystem']['workbench/metadata/project.json.lock'])

    def test_small_file_budget_bounds_all_reads_and_preserves_pending(self):
        _,bindings=validate_plan(self.plan,self.root/'probe');budget=SmallReadBudget(20)
        before,_=_inventory(self.plan,bindings,100,0,small_budget=budget)
        self.assertEqual(14,budget.used)
        self.small.write_bytes(b'{"ready":null}')
        after,_=_inventory(self.plan,bindings,100,0,small_budget=budget)
        self.assertTrue(after['workbench/metadata/handoff.json']['hashPending'])
        self.assertLessEqual(budget.used,20)
        with self.assertRaises(CaptureError):SmallReadBudget(32*1024*1024+1)

    def test_media_and_large_json_changes_do_not_read_content(self):
        media=self.tree/'output.mp4';media.write_bytes(b'fake')
        large=self.tree/'large.json';large.write_bytes(b'x'*(1024*1024+1))
        original=Path.open
        def opened(path,*args,**kwargs):
            if path in (media,large):raise AssertionError('media/large content must not be read')
            return original(path,*args,**kwargs)
        def changed():
            for path in (media,large):
                stamp=path.stat().st_mtime_ns+1000000000;os.utime(path,ns=(stamp,stamp))
        with patch.object(Path,'open',opened):snapshot=self.capture(between=changed)
        for name in ('output.mp4','large.json'):
            self.assertTrue(snapshot.manifest['facts']['filesystem']['workbench/metadata/'+name]['hashPending'])

    def test_change_diagnostics_are_bounded_and_never_contain_file_bodies(self):
        def added():
            for i in range(70):(self.tree/('new-%02d.json'%i)).write_text('PRIVATE-BODY-CANARY')
        report=measure_directory_stability(self.plan,self.root/'probe',between=added)
        self.assertEqual(50,len(report['changes']));self.assertTrue(report['changesTruncated'])
        self.assertNotIn('PRIVATE-BODY-CANARY',json.dumps(report))
        self.assertTrue(all(set(row)=={'path','type'} for row in report['changes']))

    def test_expired_window_is_unmeasurable_and_limit_cannot_be_increased(self):
        ticks=[0]
        def between():ticks[0]+=21
        report=measure_directory_stability(self.plan,self.root/'probe',between=between,clock=lambda:ticks[0])
        self.assertEqual(3,report['unmeasurableRounds']);self.assertIsNone(report['directoryChangeFailureRatio'])
        for limit in (21,0,True,float('nan'),float('inf')):
            with self.assertRaisesRegex(CaptureError,'capture_window_limit'):
                aligned_capture(self.plan,self.root/'snapshot',source_path=self.source,process_probe=lambda:{},http_probe=lambda:{},max_window_seconds=limit)

    def test_forty_dates_are_measured_in_bounded_synthetic_windows(self):
        for i in range(40):
            folder=self.tree/('date-%02d'%i);folder.mkdir()
            (folder/'handoff.json').write_bytes(b'{"done":true}')
            for j in range(20):(folder/('video-%02d.mp4'%j)).write_bytes(b'synthetic-media')
        report=measure_directory_stability(self.plan,self.root/'probe',max_entries=2000)
        self.assertEqual(0,report['unmeasurableRounds']);self.assertEqual(0,report['directoryChangeFailedRounds'])
        self.assertLess(report['maxWindowSeconds'],20)
        print('Synthetic content-window timings: '+json.dumps(report['windows']))


if __name__=='__main__':unittest.main()
