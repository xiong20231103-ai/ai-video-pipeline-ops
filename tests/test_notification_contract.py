"""Synthetic snapshot/notification persistence only; no external messages."""
import copy,json,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from cloud.store import Store
from cloud.notification_facts import current_facts,completion_facts,public_text,source_fresh
from cloud.notification_ledger import NotificationLedger

def summary(state='blocked'):
 identity={'batchId':'fixture-batch','canonicalTaskId':'fixture-task','attemptId':'fixture-attempt','project':'fixture-project'}
 return {'currentProjectStatus':{'identity':identity,'state':state,'stages':[],'errors':[{'component':'capcut','phase':'import','errorCode':'FIXTURE_IMPORT_FAILED','status':'failed','message':'fixture failure','attemptId':'fixture-attempt'}]},'currentTaskBox':{'batchId':'fixture-batch','current':{'taskId':'fixture-task'}},'controls':{'continue':{'allowed':True,'continueCanRetry':True,'stale':False,'state':'failed'}},'autoRecovery':{'state':'paused'}}
class FactsTests(unittest.TestCase):
 def test_task_failure_and_manual_attention_require_current_identity(self):
  b=summary();items=current_facts(b);self.assertEqual({'task_failed'},{i['kind'] for i in items});self.assertTrue(items[0]['needsManualReview'])
  b['currentTaskBox']['current']['taskId']='other';self.assertEqual([],current_facts(b))
 def test_allowed_alone_never_means_click_continue(self):
  b=summary('running');b['currentProjectStatus']['errors']=[];self.assertEqual([],current_facts(b))
  for change in ({'continueCanRetry':False},{'stale':True},{'state':'executing'}):
   b=summary();b['controls']['continue'].update(change);self.assertNotIn('manual_attention',[i['kind'] for i in current_facts(b)])
 def test_running_auto_recovery_or_task_or_cloud_command_blocks_manual_notice(self):
  b=summary();self.assertNotIn('manual_attention',[i['kind'] for i in current_facts(b,cloud_inflight=True)])
  b['autoRecovery']['state']='recovering';self.assertNotIn('manual_attention',[i['kind'] for i in current_facts(b)])
  b=summary();b['currentProjectStatus']['stages']=[{'taskScoped':True,'status':'running'}];self.assertNotIn('manual_attention',[i['kind'] for i in current_facts(b)])
 def test_login_errors_never_claim_continue_is_solution(self):
  b=summary();b['currentProjectStatus']['errors'][0]['errorCode']='VOICE_LOGIN_REQUIRED'
  self.assertNotIn('manual_attention',[i['kind'] for i in current_facts(b)])
  self.assertFalse(any(i.get('needsManualReview') for i in current_facts(b)))
 def test_blocked_without_failure_can_request_manual_review(self):
  b=summary();b['currentProjectStatus']['errors']=[];self.assertEqual(['manual_attention'],[i['kind'] for i in current_facts(b)])
 def test_cleanup_only_completed_warning_is_not_failure(self):
  b=summary('completed');e=b['currentProjectStatus']['errors'][0];e['phase']='cleanup';self.assertEqual([],current_facts(b))
 def test_upload_failure_remains_separate_from_production_completion(self):
  b=summary('completed');b['currentProjectStatus']['errors'][0]['component']='upload'
  self.assertEqual(['task_failed'],[i['kind'] for i in current_facts(b)])
 def test_gap_deduplicates_generic_workbench_failure(self):
  b=summary();b['currentTaskBox']['current'].update(gapActive=True,missingCount=3)
  b['currentProjectStatus']['errors'][0]['component']='workbench'
  kinds=[i['kind'] for i in current_facts(b)];self.assertIn('download_gap',kinds);self.assertNotIn('task_failed',kinds)
 def test_stale_source_and_future_clocks_not_fresh(self):
  row={'status':200,'last_success':90,'source_health':json.dumps({'scanAgeSeconds':8})}
  self.assertTrue(source_fresh(row,100,60));self.assertFalse(source_fresh(row,100,15));self.assertFalse(source_fresh(row,80,60))
  row['source_health']='{}';self.assertFalse(source_fresh(row,100,60))
 def test_distinct_attempt_or_error_is_distinct_key(self):
  a=current_facts(summary())[0]['baseKey'];b=summary();b['currentProjectStatus']['errors'][0]['attemptId']='another'
  self.assertNotEqual(a,current_facts(b)[0]['baseKey'])
 def test_no_dates_or_aggregate_failed_counts_used(self):
  self.assertEqual([],current_facts({'overview':{'failed':50},'pipeline':{'failed':1}}))
 def test_redacts_secret_urls_tokens_and_paths(self):
  result=public_text('https://secret.invalid/?key=fixture-secret Bearer abc.def token=fixture-secret E:\\private\\secret.mp4')
  for forbidden in ('fixture-secret','abc.def','secret.mp4','secret.invalid'):self.assertNotIn(forbidden,result)
 def test_only_valid_counted_receipts_prove_production_completion(self):
  b={'taskBoxes':{'items':[{'batchId':'batch','totalVideos':21,'completedVideos':21,'projectCount':1,'completedProjects':1,'completionReceipt':{'status':'completed_verified','receiptHash':'a'*64,'completedAt':datetime.fromtimestamp(200,timezone.utc).isoformat(),'uploadStatus':'upload_pending'}}]}}
  items=completion_facts(b,baseline_at=100,now=300);self.assertEqual(1,len(items));self.assertFalse(items[0]['historical']);self.assertIn('不代表上传完成',items[0]['message'])
  self.assertTrue(completion_facts(b,baseline_at=250,now=300)[0]['historical'])
  b['taskBoxes']['items'][0]['completedVideos']=20;self.assertEqual([],completion_facts(b,baseline_at=100,now=300))

class LedgerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=100
  self.store=Store(Path(self.temp.name)/'console.db',clock=lambda:self.now);self.ledger=NotificationLedger(self.store)
  self.item=current_facts(summary())[0]
 def test_first_enable_baseline_persists_across_restart(self):
  self.assertTrue(self.ledger.initialize([('current',1,[self.item])]))
  reopened=NotificationLedger(self.store);self.assertFalse(reopened.initialize([]));reopened.observe('current',2,[self.item])
  self.assertIsNone(reopened.prepare());self.assertEqual({'baseline':1},reopened.status()['events'])
 def test_same_failure_once_new_episode_after_real_clear(self):
  self.ledger.initialize([('current',1,[])])
  self.ledger.observe('current',2,[self.item]);batch=self.ledger.prepare();self.assertEqual(1,len(batch['events']))
  self.ledger.finish(batch['id'],'sent',receipt='provider-accepted')
  self.ledger.observe('current',3,[self.item]);self.assertIsNone(self.ledger.prepare())
  self.ledger.observe('current',4,[]);self.ledger.observe('current',5,[self.item]);self.assertIsNone(self.ledger.prepare())
  self.now+=601;self.assertIsNotNone(self.ledger.prepare())
 def test_history_backfill_is_suppressed_and_receipt_never_reannounced(self):
  self.ledger.initialize([]);item={**self.item,'kind':'batch_completed','once':True,'historical':True}
  self.ledger.observe('completion',1,[item]);self.ledger.observe('completion',2,[]);self.ledger.observe('completion',3,[{**item,'historical':False}])
  self.assertIsNone(self.ledger.prepare());self.assertEqual({'baseline':1},self.ledger.status()['events'])
 def test_merge_preserves_distinct_tasks_and_all_event_keys(self):
  self.ledger.initialize([]);items=[]
  for n in range(3):
   b=summary();b['currentProjectStatus']['errors'][0]['errorCode']='ERROR_'+str(n);items.append(current_facts(b)[0])
  self.ledger.observe('current',1,items);batch=self.ledger.prepare()
  self.assertEqual(3,len(batch['events']));self.assertEqual(3,len({i['eventKey'] for i in batch['events']}))
 def test_quiet_events_are_deferred_not_dropped(self):
  self.ledger.initialize([]);self.ledger.observe('current',1,[self.item]);self.assertIsNone(self.ledger.prepare(quiet=True))
  self.assertIsNotNone(self.ledger.prepare(quiet=False))
 def test_critical_offline_can_send_during_quiet_hours(self):
  self.ledger.initialize([]);self.ledger.observe('health',1,[{**self.item,'kind':'home_offline','severity':'critical'}]);self.assertIsNotNone(self.ledger.prepare(quiet=True))
 def test_restart_during_external_send_records_unknown_never_repeats(self):
  self.ledger.initialize([]);self.ledger.observe('current',1,[self.item]);self.assertIsNotNone(self.ledger.prepare())
  reopened=NotificationLedger(self.store);self.assertIsNone(reopened.prepare());self.assertEqual({'unknown':1},reopened.status()['deliveries'])
 def test_out_of_order_source_never_clears_current_episode(self):
  self.ledger.initialize([('current',3,[self.item])]);self.ledger.observe('current',2,[]);self.ledger.observe('current',4,[self.item])
  self.assertIsNone(self.ledger.prepare());self.assertEqual({'baseline':1},self.ledger.status()['events'])
if __name__=='__main__':unittest.main()
