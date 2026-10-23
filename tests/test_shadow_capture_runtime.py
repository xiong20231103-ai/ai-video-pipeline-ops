import json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from tools.shadow_agent_observer import AgentReadObserver
from tools.shadow_capture_runtime import CapturePublisher
from tools.shadow_replay_worker import compare_ready
from tools.shadow_capture import CaptureError

ROOT=Path(__file__).resolve().parents[1]
class CaptureRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.live=self.root/'live';self.live.mkdir();(self.live/'state.json').write_text('{"items":[]}',encoding='utf-8')
        src=self.root/'source-app';src.mkdir();self.source=src/'app.py';self.source.write_text((ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8'),encoding='utf-8')
        self.plan={'schema':1,'roots':{'workbench':str(self.live)},'files':{'workbench/state.json':{'root':'workbench','path':'state.json'}},'facts':{'scan':False}}
        self.observer=AgentReadObserver({(8766,'/api/health'):'receiver:/api/health'})
        self.complete();self.tick=100
        self.publisher=CapturePublisher(self.plan,self.source,self.root/'evidence',self.observer,lambda:{'processRecords':[]},approved_total_bytes=32*1024*1024,max_capture_bytes=1024,min_interval_seconds=30,clock=lambda:self.tick)
    def complete(self):
        a=self.observer.begin(8766,'/api/health');self.observer.complete(a,200,b'{"ok":true}')
    def test_full_capture_and_retained_exact_bytes(self):
        before=(self.live/'state.json').read_bytes();result=self.publisher.tick();self.assertEqual('captured',result['state'],result)
        identity=result['lastSourceIdentity'];self.assertTrue((self.root/'evidence/ready'/(identity+'.json')).exists())
        self.assertEqual(before,(self.live/'state.json').read_bytes());self.assertFalse(result['realShadowPassed']);self.assertEqual(0,result['businessRequests'])
    def test_missing_http_rejected_before_writes(self):
        self.observer.begin(8766,'/api/health');self.assertEqual('blocked',self.publisher.tick()['state']);self.assertFalse(self.publisher.root.exists())
    def test_full_capacity_retains_old_evidence(self):
        self.publisher.cap=100;self.publisher.root.mkdir();old=self.publisher.root/'old';old.write_bytes(b'keep')
        self.assertEqual('capture_capacity_exhausted',self.publisher.tick()['lastCode']);self.assertEqual(b'keep',old.read_bytes())
    def test_source_overlap_refused(self):
        with self.assertRaises(CaptureError):CapturePublisher(self.plan,self.source,self.live/'evidence',self.observer,lambda:{},approved_total_bytes=100)
    def test_observer_error_is_fixed_code_no_secret_or_path(self):
        self.observer.observation=lambda:(_ for _ in ()).throw(RuntimeError('secret-canary'))
        result=self.publisher.tick();self.assertEqual('capture_rejected',result['lastCode']);self.assertNotIn('secret-canary',json.dumps(result))
    def test_stop_before_first_cycle_does_not_collect(self):
        stop=threading.Event();stop.set();self.publisher.loop(stop);self.assertEqual(0,self.publisher.status()['published'])
    def test_stale_observed_http_blocks_capture(self):
        self.observer.completed_at={key:0 for key in self.observer.values}
        self.assertEqual('blocked',self.publisher.tick()['state'])
        self.assertFalse(self.publisher.root.exists())
    def test_plan_is_copied_not_changed_by_caller(self):
        self.plan['files'].clear()
        self.assertIn('workbench/state.json',self.publisher.plan['files'])
    def test_rate_limit_no_duplicate_capture(self):
        self.publisher.tick();self.assertEqual(1,self.publisher.tick()['published'])
    def test_directory_failure_ratio_counts_attempted_cycles_not_rate_limited_ticks(self):
        self.assertIsNone(self.publisher.status()['directoryChangeFailureRatio'])
        with patch('tools.shadow_capture_runtime.aligned_capture',side_effect=CaptureError('directory_changed_in_window')):
            result=self.publisher.tick()
        self.assertEqual(1,result['directoryChangeFailureRatio']);self.assertEqual(1,result['captureAttempts'])
        self.publisher.tick();self.assertEqual(1,self.publisher.status()['captureAttempts'])
        self.tick+=31
        result=self.publisher.tick()
        self.assertEqual('captured',result['state']);self.assertEqual(.5,result['directoryChangeFailureRatio'])
    def test_read_change_rejects_and_does_not_publish(self):
        old=self.publisher.process_probe;calls=[]
        def probe():
            calls.append(1)
            if len(calls)==2:(self.live/'state.json').write_text('{"items":[1]}',encoding='utf-8')
            return old()
        self.publisher.process_probe=probe;result=self.publisher.tick();self.assertEqual('blocked',result['state']);self.assertFalse((self.publisher.root/'ready').exists())
    def captured(self):
        result=self.publisher.tick();identity=result['lastSourceIdentity'];marker=self.publisher.root/'ready'/(identity+'.json');return identity,marker
    def test_same_process_replay_is_rejected(self):
        identity,_=self.captured()
        with self.assertRaisesRegex(CaptureError,'separate_replay_process'):compare_ready(self.publisher.root,identity,self.source,module='R1',targets=['/api/health'],approved_scratch_bytes=17*1024*1024,retained_limit_bytes=64*1024*1024)
    def test_offline_report_preserves_incomplete_and_never_accepts(self):
        identity,marker=self.captured();v=json.loads(marker.read_bytes());v['emitterPid']=os.getpid()+100;marker.write_text(json.dumps(v),encoding='utf-8')
        # Real strict replay of an intentionally incomplete fixture must not pass.
        result=compare_ready(self.publisher.root,identity,self.source,module='R1',targets=['/api/health'],approved_scratch_bytes=17*1024*1024,retained_limit_bytes=64*1024*1024)
        self.assertFalse(result['comparable']);self.assertFalse(result['realShadowPassed']);self.assertTrue((self.publisher.root/'reports/R1'/(identity+'.json')).exists())
        with self.assertRaisesRegex(CaptureError,'report_already_exists'):compare_ready(self.publisher.root,identity,self.source,module='R1',targets=['/api/health'],approved_scratch_bytes=17*1024*1024,retained_limit_bytes=64*1024*1024)
    def test_offline_quota_and_write_modules_rejected(self):
        identity,marker=self.captured();v=json.loads(marker.read_bytes());v['emitterPid']=os.getpid()+100;marker.write_text(json.dumps(v),encoding='utf-8')
        for module,budget in [('R1',1),('R3',17*1024*1024)]:
            with self.assertRaises(CaptureError):compare_ready(self.publisher.root,identity,self.source,module=module,targets=['/api/health'],approved_scratch_bytes=budget,retained_limit_bytes=64*1024*1024)
if __name__=='__main__':unittest.main()
