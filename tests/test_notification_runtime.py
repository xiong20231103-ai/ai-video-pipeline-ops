import json,tempfile,unittest
from pathlib import Path
from cloud.store import Store
from cloud.notification_runtime import NotificationWorker
from contracts.cache import cache_key
from test_notification_contract import summary
class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=1_800_000_000
  self.store=Store(Path(self.temp.name)/'console.db',clock=lambda:self.now);self.sent=[]
  def sender(batch):self.sent.append(batch);return {'state':'sent','receipt':'fixture-accepted'}
  self.worker=NotificationWorker(self.store,{'enabled':True,'quiet_start':0,'quiet_end':0},sender)
 def put(self,body,version=1,scan_age=0,age=0):
  with self.store.db(True) as db:
   db.execute('INSERT OR REPLACE INTO responses VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cache_key('GET','/api/dashboard/summary'),version,200,json.dumps(body),'fixture',self.now-age,self.now,'',json.dumps({'scanAgeSeconds':scan_age}),'',self.now))
 def test_no_home_polling_and_initial_existing_failure_baseline(self):
  self.put(summary());self.worker.tick();self.assertEqual([],self.sent)
  self.now+=5;self.worker.tick();self.assertEqual([],self.sent)
 def test_fresh_new_failure_sends_once_across_restart(self):
  b=summary('running');b['currentProjectStatus']['errors']=[];self.put(b);self.worker.tick()
  self.now+=10;self.put(summary(),version=2);self.worker.tick();self.worker.tick()
  self.assertEqual(1,len(self.sent));self.assertEqual('task_failed',self.sent[0]['kind'])
  self.assertEqual({'sent':1},self.worker.ledger.status()['events'])
 def test_offline_at_300_seconds_not_45_busy_is_not_offline(self):
  self.store.heartbeat('busy');self.worker.tick()
  self.now+=46;self.worker.tick();self.assertEqual([],self.sent)
  self.now+=255;self.worker.tick();self.assertEqual(1,len(self.sent));self.assertEqual('home_offline',self.sent[0]['kind'])
  self.now+=5;self.worker.tick();self.assertEqual(1,len(self.sent))
 def test_engine_unavailable_is_distinct_from_agent_offline(self):
  self.store.heartbeat('healthy');self.worker.tick()
  self.now+=5;self.store.heartbeat('unavailable');self.worker.tick()
  self.now+=61;self.store.heartbeat('unavailable');self.worker.tick()
  self.assertEqual('engine_unavailable',self.sent[0]['kind']);self.assertNotIn('home_offline',[b['kind'] for b in self.sent])
 def test_offline_recovery_starts_new_episode(self):
  self.store.heartbeat('healthy');self.worker.tick();self.now+=301;self.worker.tick()
  self.now+=5;self.store.heartbeat('healthy');self.worker.tick()
  self.now+=601;self.worker.tick();self.assertEqual(2,len(self.sent))
 def test_stale_snapshot_never_generates_manual_continue(self):
  self.put({'currentProjectStatus':{}});self.worker.tick();self.now+=10;self.put(summary(),2,scan_age=70);self.worker.tick()
  self.assertNotIn('manual_attention',[b['kind'] for b in self.sent])
 def test_disabled_worker_does_not_initialize_or_send(self):
  self.worker.config['enabled']=False;self.put(summary());self.worker.tick()
  self.assertIsNone(self.worker.ledger.baseline());self.assertEqual([],self.sent)
 def test_provider_absent_keeps_pending_and_exposes_status(self):
  self.worker.sender=None;self.worker.tick();self.put(summary());self.worker.tick()
  self.assertFalse(self.worker.status()['providerConfigured']);self.assertEqual({'pending':1},self.worker.status()['events'])
 def test_uncertain_send_is_not_retried(self):
  self.worker.tick();self.put(summary());self.worker.sender=lambda _:(_ for _ in ()).throw(OSError('fixture'))
  self.worker.tick();self.worker.tick()
  self.assertEqual({'unknown':1},self.worker.status()['events'])
 def test_source_clock_rollback_does_not_trigger_false_offline(self):
  self.store.heartbeat('healthy');self.worker.tick();self.now-=500;self.worker.tick();self.assertEqual([],self.sent)
if __name__=='__main__':unittest.main()
