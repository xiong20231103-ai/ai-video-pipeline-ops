"""End-to-end ASGI fixture traffic; home transport is never contacted."""
import base64,hashlib,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from fastapi.testclient import TestClient
from cloud.app import create_app,HASHER,COOKIE
from cloud.store import Store
from cloud.commands import CommandQueue

LEDGER='a'*32
class RouteTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=Store(Path(self.temp.name)/'console.db')
  self.config={'origin':'https://fixture.ts.net','agent_token_sha256':hashlib.sha256(b'fixture-agent').hexdigest(),'invite_hash':HASHER.hash('fixture-invite'),'command_queue_enabled':True,'h3_target_contract':True}
  self.app=create_app(self.config,self.store);self.q=self.app.state.commands
  self.client=TestClient(self.app,base_url=self.config['origin'],client=('127.0.0.1',12345))
  self.store.register('fixture-user',HASHER.hash('fixture-password'),2);token,self.csrf=self.store.new_session(self.store.user('fixture-user')['id']);self.client.cookies.set(COOKIE,token)
  self.headers={'Origin':self.config['origin'],'X-CSRF-Token':self.csrf,'X-Client-Request-ID':'fixture-request-123456'}
  self.agent={'Authorization':'Bearer fixture-agent'}
  self.tailnet={'X-Forwarded-Proto':'https','X-Forwarded-For':'100.100.1.2','Content-Type':'application/json','X-Client-Request-ID':'fixture-public-123456'}
  self.q.advertise({'enabled':True,'protocol':1,'ledgerId':LEDGER});self.store.heartbeat('healthy')
 def test_console_csrf_and_closed_route_then_claim_finish_and_reload(self):
  self.assertEqual(403,self.client.post('/api/controls/upload/rescan',json={}).status_code)
  self.assertEqual(400,self.client.post('/api/controls/testing/reset',json={},headers=self.headers).status_code)
  row=self.client.post('/api/controls/upload/rescan',json={},headers=self.headers);self.assertEqual(202,row.status_code,row.text)
  identifier=row.json()['cloudCommandId'];self.assertFalse(row.json()['downstreamCancellationGuaranteed'])
  self.assertEqual(401,self.client.get('/agent/commands?ledgerId='+LEDGER+'&wait=0').status_code)
  job=self.client.get('/agent/commands?ledgerId='+LEDGER+'&wait=0',headers=self.agent).json()['item'];self.assertEqual(identifier,job['id'])
  self.assertEqual(200,self.client.post('/agent/commands/'+identifier+'/start',headers=self.agent,json={'lease':job['lease'],'ledgerId':LEDGER}).status_code)
  result={'kind':'http','httpStatus':422,'bodyBase64':base64.b64encode(' {"detail":"fixture校验错误"}\n'.encode()).decode(),'contentType':'application/json'}
  self.assertEqual(200,self.client.post('/agent/results',headers=self.agent,json={'id':identifier,'lease':job['lease'],'ledgerId':LEDGER,'result':result}).status_code)
  reopened=create_app(self.config,Store(self.store.path));other=TestClient(reopened,base_url=self.config['origin']);other.cookies.update(self.client.cookies)
  receipt=other.get('/console/commands/request/fixture-request-123456').json();self.assertEqual(result,receipt['result']);self.assertEqual(identifier,receipt['cloudCommandId'])
 def test_public_submitter_only_serve_no_secret_and_lost_ack_lookup(self):
  data={'batchId':'fixture-batch','tasks':[{'taskId':'fixture-task'}]}
  self.assertEqual(403,self.client.post('/api/batches',json=data).status_code)
  self.assertEqual(403,self.client.post('/api/batches',json=data,headers={**self.tailnet,'X-Forwarded-For':'203.0.113.1'}).status_code)
  self.assertEqual(403,self.client.post('/api/batches',json=data,headers={**self.tailnet,'Origin':'https://foreign.invalid'}).status_code)
  # Complete the inert fixture immediately; preserve the exact legacy bytes/status.
  def enqueue(*args,**kwargs):
   row=original(*args,**kwargs);job=self.q.claim(LEDGER);self.q.permit(job['id'],job['lease'],LEDGER)
   self.q.finish(job['id'],job['lease'],LEDGER,{'kind':'http','httpStatus':422,'bodyBase64':base64.b64encode(b'{"detail":"fixture invalid"}\n').decode(),'contentType':'application/json'})
   return self.q.get(row['cloudCommandId'])
  original=self.q.enqueue
  with patch.object(self.q,'enqueue',side_effect=enqueue):
   response=self.client.post('/api/batches/validate',json=data,headers=self.tailnet)
  self.assertEqual(422,response.status_code,response.text);self.assertEqual(b'{"detail":"fixture invalid"}\n',response.content)
  self.client.cookies.clear()
  result=self.client.get('/api/submission-requests/fixture-public-123456',headers=self.tailnet);self.assertEqual(200,result.status_code,result.text)
  self.assertEqual('completed',result.json()['state']);self.assertEqual(401,self.client.get('/api/dashboard',headers=self.tailnet).status_code)
  self.assertEqual(403,self.client.get('/api/submissions/'+result.json()['cloudCommandId']).status_code)
 def test_disabled_legacy_agent_never_enables_commands_and_ledger_change_pauses(self):
  response=self.client.post('/agent/heartbeat',headers=self.agent,json={'engineState':'healthy'});self.assertTrue(response.json()['executionAccepted']);self.assertFalse(self.q.capability())
  self.client.post('/agent/heartbeat',headers=self.agent,json={'engineState':'healthy','execution':{'enabled':True,'protocol':1,'ledgerId':'b'*32}})
  health=self.client.get('/console/status').json();self.assertTrue(health['agentOnline']);self.assertTrue(health['commandsPaused']);self.assertFalse(health['canContinue'])
 def test_cancel_lost_ack_tombstone_prevents_late_post(self):
  self.assertEqual(200,self.client.post('/console/commands/request/fixture-request-123456/cancel',headers=self.headers).status_code)
  self.assertEqual(409,self.client.post('/api/controls/upload/rescan',json={},headers=self.headers).status_code)
 def test_unclaimed_result_or_header_injection_is_rejected(self):
  row=self.client.post('/api/controls/upload/rescan',json={},headers=self.headers).json()
  self.assertEqual(400,self.client.post('/agent/results',headers=self.agent,json={'id':row['cloudCommandId'],'result':{'kind':'unknown','reason':'transport_uncertain'}}).status_code)
  job=self.q.claim(LEDGER);self.q.permit(job['id'],job['lease'],LEDGER)
  self.assertEqual(400,self.client.post('/agent/results',headers=self.agent,json={'id':job['id'],'lease':job['lease'],'ledgerId':LEDGER,'result':{'kind':'http','httpStatus':200,'bodyBase64':'e30=','contentType':'application/json\r\nFake: value'}}).status_code)

 def test_public_lost_ack_cancel_requires_login_csrf_and_same_tailnet_identity(self):
  headers={**self.headers,**self.tailnet}
  self.assertEqual(200,self.client.post('/console/submission-requests/fixture-public-123456/cancel',headers=headers).status_code)
  self.client.cookies.clear()
  answer=self.client.get('/api/submission-requests/fixture-public-123456',headers=self.tailnet)
  self.assertEqual(200,answer.status_code);self.assertTrue(answer.json()['cancelledBeforeReceipt'])
  self.assertEqual(409,self.client.post('/api/batches',headers=self.tailnet,json={'batchId':'fixture','tasks':[{}]}).status_code)

 def test_active_business_status_refreshes_after_five_seconds_but_terminal_does_not(self):
  self.store.push({'target':'/api/control-commands/fixture-active','version':1,'status':200,'body':{'state':'recovering','commandId':'fixture-active'}})
  self.store.push({'target':'/api/control-commands/fixture-done','version':1,'status':200,'body':{'state':'completed','commandId':'fixture-done'}})
  clock=self.store.clock;self.store.clock=lambda:clock()+6
  answer=self.client.get('/api/control-commands/fixture-active');self.assertEqual('recovering',answer.json()['state']);self.assertEqual('true',answer.headers['X-Cache-Refresh-Pending'])
  terminal=self.client.get('/api/control-commands/fixture-done');self.assertEqual('false',terminal.headers['X-Cache-Refresh-Pending'])
  self.assertEqual(['/api/control-commands/fixture-active'],[item['target'] for item in self.store.claim_reads()])
