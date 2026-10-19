"""Real loopback HTTP + SQLite command protocol. NEVER contacts a home service."""
import base64,json,sys,threading,unittest,urllib.error,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud.store import Store
from cloud.commands import CommandQueue
from agent.execution import ExecutionWorker,ExecutionLedger
from contracts.commands import canonical

class FixtureReceiver(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*args):pass
 def do_POST(self):
  length=int(self.headers['Content-Length']);body=json.loads(self.rfile.read(length));self.server.received.append((self.path,body))
  code=422 if self.path.endswith('/validate') else 200
  raw=('{"detail":"合成合同校验错误"}\n' if code==422 else '{"ok":true,"commandId":"fixture-local","state":"persisted"}\n').encode()
  self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)+(30 if self.server.truncate else 0)));self.end_headers();self.wfile.write(raw);self.wfile.flush()
  if self.server.truncate:self.close_connection=True
class MappedTransport:
 def __init__(self,port):self.port=port;self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 def open(self,request,timeout):
  from urllib.parse import urlsplit
  parsed=urlsplit(request.full_url)
  assert request.method=='POST' and parsed.port in (8765,8766)
  assert parsed.hostname==('127.0.0.1' if parsed.port==8766 else '100.92.17.9')
  # Replace the destination BEFORE opening any socket. Only this fixture port is used.
  fixture=urllib.request.Request('http://127.0.0.1:'+str(self.port)+parsed.path,data=request.data,headers=dict(request.header_items()),method='POST')
  return self.opener.open(fixture,timeout=timeout)
class TransportIntegration(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),FixtureReceiver);self.server.received=[];self.server.truncate=False
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close_server)
  self.store=Store(root/'console.db');self.queue=CommandQueue(self.store,True,True);self.agent=SimpleNamespace(state_dir=root/'agent',stop=threading.Event(),lifecycle=SimpleNamespace(stop_request=lambda:None),transport=MappedTransport(self.server.server_port))
  self.agent.state_dir.mkdir();(self.agent.state_dir/'command-settings.json').write_text('{"schema":1,"enabled":true}')
  self.worker=ExecutionWorker(self.agent);self.queue.advertise(self.worker.capability());self.store.heartbeat('healthy');self.agent.cloud=self.cloud
 def close_server(self):self.server.shutdown();self.server.server_close();self.thread.join(2)
 def cloud(self,path,data=None):
  if path.endswith('/start'):return self.queue.permit(path.split('/')[3],data['lease'],data['ledgerId'])
  if path=='/agent/results':return self.queue.finish(data['id'],data['lease'],data['ledgerId'],data['result'])
  raise AssertionError('Unexpected cloud fixture path')
 def run_job(self,path,body):
  row=self.queue.enqueue('fixture-user','fixture-'+str(len(self.server.received)).zfill(16),path,body)
  job=self.queue.claim(self.worker.ledger.identity);self.assertIsNotNone(job);self.worker.process(job);self.worker.flush()
  return self.queue.get(row['cloudCommandId'])
 def test_every_enabled_family_uses_one_http_post_and_exact_error_bytes(self):
  routes=[('/api/controls/tasks/create',{'templateId':'fixture','urls':['https://example.invalid/fixture']}),('/api/controls/tasks/fixture/replenish',{'urls':['https://example.invalid/fixture'],'startNow':False}),('/api/controls/tasks/fixture/start',{}),('/api/controls/tasks/fixture/cancel',{}),('/api/controls/upload/rescan',{}),('/api/controls/upload/verify-history',{}),('/api/batches/validate',{'batchId':'fixture','tasks':[{}]}),('/api/batches',{'batchId':'fixture','tasks':[{}]})]
  for target,body in routes:
   with self.subTest(target=target):
    receipt=self.run_job(target,body);self.assertEqual('completed',receipt['state']);self.assertEqual(422 if target.endswith('/validate') else 200,receipt['result']['httpStatus'])
    if target.endswith('/validate'):self.assertEqual('{"detail":"合成合同校验错误"}\n'.encode(),base64.b64decode(receipt['result']['bodyBase64']))
  self.assertEqual(len(routes),len(self.server.received))
  expected={'batchId':'fixture-b','taskId':'fixture-t','attemptId':'fixture-a'}
  self.store.push({'target':'/api/dashboard/summary','version':1,'status':200,'body':{'autoRecovery':{'enabled':False,'state':'paused'},'currentTaskBox':{'batchId':expected['batchId'],'current':{'taskId':expected['taskId'],'attemptId':expected['attemptId']}}},'sourceHealth':{'scanAgeSeconds':0}})
  self.run_job('/api/control-commands',{'clientRequestId':'fixture-safe-continue','expectedTarget':expected});self.assertEqual(expected,self.server.received[-1][1]['expectedTarget'])
 def test_truncated_real_response_becomes_unknown_and_restart_never_reposts(self):
  self.server.truncate=True;receipt=self.run_job('/api/controls/upload/rescan',{})
  self.assertEqual('unknown',receipt['state']);self.assertEqual(1,len(self.server.received))
  reopened=ExecutionWorker(self.agent);self.assertEqual(self.worker.ledger.identity,reopened.ledger.identity);self.assertIsNone(self.queue.claim(reopened.ledger.identity));self.assertEqual(1,len(self.server.received))
 def test_lost_result_ack_survives_restart_and_repeats_only_cloud_upload(self):
  row=self.queue.enqueue('fixture','fixture-upload-123456','/api/controls/upload/rescan',{});job=self.queue.claim(self.worker.ledger.identity);self.worker.process(job)
  def lost(path,data=None):self.cloud(path,data);raise OSError('synthetic ACK lost after cloud commit')
  self.agent.cloud=lost
  with self.assertRaises(OSError):self.worker.flush()
  self.agent.cloud=self.cloud;reopened=ExecutionWorker(self.agent);self.assertTrue(reopened.flush());self.assertEqual('completed',self.queue.get(row['cloudCommandId'])['state']);self.assertEqual(1,len(self.server.received));self.assertIsNone(reopened.ledger.pending())
if __name__=='__main__':unittest.main(verbosity=2)
