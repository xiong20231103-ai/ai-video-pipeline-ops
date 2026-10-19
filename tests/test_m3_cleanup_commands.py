import base64,json,unittest
from unittest.mock import patch
import test_command_queue as queue_fixture
LEDGER=queue_fixture.LEDGER
import test_command_routes as route_fixture
import test_execution_ledger as execution_fixture
from contracts.commands import command
from contracts.cache import cache_key
from cloud.commands import CommandError,CommandQueue

P='/api/controls/cloud-cleanup/'
class CleanupQueueTests(unittest.TestCase):
 enqueue=queue_fixture.QueueTests.enqueue
 claim=queue_fixture.QueueTests.claim
 start=queue_fixture.QueueTests.start
 finish=queue_fixture.QueueTests.finish
 def setUp(self):
  queue_fixture.QueueTests.setUp(self);self.queue.cleanup=True
  self.queue.advertise({'enabled':True,'protocol':1,'ledgerId':LEDGER,'cleanupProtocol':1})
  self.store.push({'target':'/api/dashboard/summary','version':1,'status':200,'body':{},'sourceHealth':{'scanAgeSeconds':0}})
  self.store.push({'target':P+'capabilities','version':1,'status':200,'body':{'protocol':1,'retentionDays':3,'forbiddenDraftRootProtected':True}})
  self.preview={'kind':'audio','ids':['server-object-1'],'includeUnknown':False}
 def preview_result(self):
  row=self.queue.enqueue('fixture-actor','preview-request-123456',P+'preview',self.preview);job=self.claim();self.start(job)
  value={**self.preview,'ticket':'opaque-fixture-ticket','snapshotToken':'fixture-snapshot','expiresAt':1120,'deletableCount':1}
  self.finish(job,{'kind':'http','httpStatus':200,'bodyBase64':base64.b64encode(json.dumps(value).encode()).decode(),'contentType':'application/json'})
  return {**value,'confirm':'RECYCLE_SELECTED_AUDIO_FILES'}
 def execute(self,body,actor='fixture-actor',rid='execute-request-123456'):
  return self.queue.enqueue(actor,rid,P+'execute',{k:v for k,v in body.items() if k!='deletableCount'})
 def test_capabilities_old_agent_disabled_default_stale_and_unsafe_root(self):
  self.assertTrue(self.queue.health()['canCleanup'])
  for tweak in ('disabled','old-agent','unsafe-dashboard','stale'):
   with self.subTest(tweak=tweak):
    if tweak=='disabled':self.queue.cleanup=False
    elif tweak=='old-agent':self.queue.cleanup=True;self.queue.advertise({'enabled':True,'protocol':1,'ledgerId':LEDGER})
    elif tweak=='unsafe-dashboard':
     self.queue.advertise({'enabled':True,'protocol':1,'ledgerId':LEDGER,'cleanupProtocol':1})
     self.store.push({'target':P+'capabilities','version':2,'status':200,'body':{'protocol':1,'retentionDays':3,'forbiddenDraftRootProtected':False}})
    else:self.now[0]+=61;self.store.heartbeat('healthy')
    self.assertFalse(self.queue.health()['canCleanup'])
    with self.assertRaises(CommandError):self.queue.enqueue('fixture-actor','preview-fail-123456',P+'preview',self.preview)
 def test_preview_owner_selection_confirmation_and_expiry_fail_closed(self):
  body=self.preview_result()
  for modified,actor in ((body,'other-actor'),({**body,'ids':['different-object']},'fixture-actor'),({**body,'ticket':'forged'},'fixture-actor')):
   with self.assertRaisesRegex(CommandError,'account_or_selection'):self.execute(modified,actor)
  with self.assertRaises(ValueError):self.execute({**body,'confirm':'yes'})
  self.now[0]=1121;self.store.heartbeat('healthy')
  with self.assertRaises(CommandError):self.execute(body)
 def test_same_id_no_duplicate_long_cleanup_not_reissued_or_replaced(self):
  body=self.preview_result();row=self.execute(body)
  self.assertEqual(row['cloudCommandId'],self.execute(body)['cloudCommandId']);job=self.claim();self.start(job)
  self.now[0]+=121;self.store.heartbeat('healthy')
  self.assertEqual('sent',self.queue.get(job['id'])['state']);self.assertIsNone(self.queue.claim(LEDGER))
  self.now[0]+=840;self.store.heartbeat('healthy')
  self.assertEqual('unknown',self.queue.get(job['id'])['state']);self.assertIsNone(self.queue.claim(LEDGER));self.assertFalse(self.queue.health()['canCleanup'])
 def test_expired_between_queue_claim_and_send_never_receives_permit(self):
  body=self.preview_result();row=self.execute(body);job=self.claim();self.now[0]=1121;self.store.heartbeat('healthy')
  with self.assertRaises(CommandError):self.start(job)
  self.assertEqual('expired',self.queue.get(row['cloudCommandId'])['state'])
 def test_contract_only_new_paths_object_ids_and_no_paths(self):
  for change in ({'paths':['E:/x']},{'ids':['E:\\secret']},{'kind':'pending','ids':['x']},{'kind':'audio','includeUnknown':True},{'ids':['x'+str(i) for i in range(2001)]}):
   with self.subTest(change=change),self.assertRaises(ValueError):command(P+'preview',{**self.preview,**change})
  for old in ('/api/controls/audio-files/recycle','/api/controls/pending-delete/empty'):
   with self.assertRaises(ValueError):command(old,{})
  self.assertEqual(['unidentified:hash'],command(P+'preview',{'kind':'drafts','ids':['','unidentified:hash','unidentified:hash']})['body']['ids'])
  self.assertEqual(900,command(P+'execute',{'kind':'pending','ids':[],'includeUnknown':False,'ticket':'t','snapshotToken':'s','expiresAt':1100,'confirm':'EMPTY_PENDING_DELETE_NOW'})['timeoutSeconds'])

class CleanupRoutesTests(unittest.TestCase):
 setUp=route_fixture.RouteTests.setUp
 def test_m3_requires_csrf_new_agent_and_feature_switch(self):
  data={'kind':'drafts','ids':['draft-id'],'includeUnknown':False}
  self.assertEqual(403,self.client.post(P+'preview',json=data).status_code)
  self.assertEqual(409,self.client.post(P+'preview',json=data,headers=self.headers).status_code)
  self.q.cleanup=True
  self.assertEqual(409,self.client.post(P+'preview',json=data,headers=self.headers).status_code)
 def test_asgi_preview_execute_account_binding_and_partial_receipt(self):
  import time
  self.q.cleanup=True;self.q.advertise({'enabled':True,'protocol':1,'ledgerId':LEDGER,'cleanupProtocol':1})
  for target,body in [('/api/dashboard/summary',{}),(P+'capabilities',{'protocol':1,'retentionDays':3,'forbiddenDraftRootProtected':True})]:self.store.push({'target':target,'version':1,'status':200,'body':body,'sourceHealth':{'scanAgeSeconds':0}})
  payload={'kind':'audio','ids':['audio-1','audio-blocked'],'includeUnknown':False}
  response=self.client.post(P+'preview',json=payload,headers=self.headers);self.assertEqual(202,response.status_code,response.text)
  job=self.q.claim(LEDGER);self.q.permit(job['id'],job['lease'],LEDGER)
  preview={**payload,'ticket':'fixture-ticket','snapshotToken':'snapshot-token','expiresAt':int(time.time())+122}
  def finish(job,body):self.q.finish(job['id'],job['lease'],LEDGER,{'kind':'http','httpStatus':200,'bodyBase64':base64.b64encode(json.dumps(body).encode()).decode(),'contentType':'application/json'})
  finish(job,preview)
  execute={**preview,'confirm':'RECYCLE_SELECTED_AUDIO_FILES'};headers={**self.headers,'X-Client-Request-ID':'asgi-execute-123456'}
  # IDs must remain the original set, including protected objects.
  self.assertEqual(409,self.client.post(P+'execute',json={**execute,'ids':['audio-1']},headers=headers).status_code)
  accepted=self.client.post(P+'execute',json=execute,headers=headers);self.assertEqual(202,accepted.status_code,accepted.text)
  self.assertEqual(accepted.json()['cloudCommandId'],self.client.post(P+'execute',json=execute,headers=headers).json()['cloudCommandId'])
  job=self.q.claim(LEDGER);self.q.permit(job['id'],job['lease'],LEDGER);result={'state':'partial','moved':1,'blocked':[{'id':'audio-blocked','reason':'active'}]};finish(job,result)
  receipt=self.client.get('/console/commands/'+job['id']).json();self.assertEqual(result,json.loads(base64.b64decode(receipt['result']['bodyBase64'])))
 def test_heartbeat_top_level_capability_preserves_old_execution_contract(self):
  execution={'enabled':True,'protocol':1,'ledgerId':LEDGER}
  response=self.client.post('/agent/heartbeat',headers=self.agent,json={'engineState':'healthy','execution':execution,'cleanupProtocol':1})
  self.assertEqual(200,response.status_code)
  with self.store.db() as db:self.assertEqual(1,db.execute('SELECT protocol FROM cleanup_executor').fetchone()[0])
  self.client.post('/agent/heartbeat',headers=self.agent,json={'engineState':'healthy','execution':execution})
  with self.store.db() as db:self.assertEqual(0,db.execute('SELECT protocol FROM cleanup_executor').fetchone()[0])

class CleanupExecutionTests(unittest.TestCase):
 setUp=execution_fixture.ExecutionTests.setUp
 worker=execution_fixture.ExecutionTests.worker
 def test_ticket_expiry_checked_immediately_before_home_post(self):
  worker,agent=self.worker();body={'kind':'pending','ids':[],'includeUnknown':False,'ticket':'t','snapshotToken':'s','expiresAt':1001,'confirm':'EMPTY_PENDING_DELETE_NOW'}
  self.job.update(command(P+'execute',body))
  def permit(*args):worker.clock=lambda:1002;return {'sendPermitted':True}
  agent.cloud.side_effect=permit
  with patch.object(worker,'home_post') as home:worker.process(self.job);home.assert_not_called()
  self.assertEqual('not_sent',json.loads(self.ledger.pending()['result'])['kind'])
