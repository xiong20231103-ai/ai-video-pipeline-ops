import base64,hashlib,hmac,http.client,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from cloud.feishu_notifications import FeishuSender,sign,validate_settings,message
from cloud.notification_settings import load,runtime_settings
from cloud.notification_setup import save,phone_acceptance

def settings():return {'schema':1,'provider':'feishu','enabled':False,'legacy_notifications_disabled':False,'webhook':'https://open.feishu.cn/open-apis/bot/v2/hook/00000000-0000-0000-0000-000000000000','signing_secret':'fixture-secret','keyword':'fixture-keyword','quiet_start':0,'quiet_end':8}
def batch():return {'id':'fixture-delivery','kind':'task_failed','events':[{'eventKey':'a'*64,'identity':{'project':'fixture'},'phase':'import','message':r'failure E:\private\hidden.mp4 token=hidden','needsManualReview':True}]}
class Response(io.BytesIO):
 def __init__(self,body=b'{"code":0}',code=200,length=None):
  super().__init__(body);self.code=code;self.headers={'Content-Length':str(len(body) if length is None else length)}
class Transport:
 def __init__(self,response):self.response=response;self.calls=[]
 def open(self,request,timeout):self.calls.append((request,timeout));return self.response
class FeishuTests(unittest.TestCase):
 def test_official_signature_empty_message(self):
  expected=base64.b64encode(hmac.new(b'100\nfixture-secret',b'',hashlib.sha256).digest()).decode()
  self.assertEqual(expected,sign(100,'fixture-secret'))
 def test_payload_signature_keyword_all_event_keys_and_redaction(self):
  transport=Transport(Response());sender=FeishuSender(settings(),transport,clock=lambda:100)
  self.assertEqual('sent',sender(batch())['state']);request,timeout=transport.calls[0];payload=json.loads(request.data)
  self.assertEqual('POST',request.method);self.assertEqual(10,timeout);self.assertEqual('100',payload['timestamp']);self.assertEqual(sign(100,'fixture-secret'),payload['sign'])
  text=payload['content']['text'];self.assertIn('fixture-keyword',text);self.assertIn('a'*64,text);self.assertNotIn('hidden',text);self.assertNotIn('fixture-secret',text)
 def test_provider_responses_are_classified_without_private_body(self):
  for body,code,state in [(b'{"code":0}',200,'sent'),(b'{"StatusCode":0}',200,'sent'),(b'{"code":19021,"msg":"secret"}',200,'rejected'),(b'{"code":0}',302,'rejected'),(b'private',503,'unknown'),(b'[]',200,'unknown'),(b'{',200,'unknown'),(b'{}',200,'unknown')]:
   answer=FeishuSender(settings(),Transport(Response(body,code)))(batch());self.assertEqual(state,answer['state']);self.assertNotIn('secret',json.dumps(answer))
 def test_truncated_success_never_acknowledged(self):
  answer=FeishuSender(settings(),Transport(Response(length=99)))(batch());self.assertEqual('unknown',answer['state'])
 def test_transport_exception_never_leaks_url_or_retries(self):
  transport=Transport(None)
  with patch.object(transport,'open',side_effect=http.client.IncompleteRead(b'private',4)) as call:
   self.assertEqual({'state':'unknown','error_code':'transport_uncertain'},FeishuSender(settings(),transport)(batch()));self.assertEqual(1,call.call_count)
 def test_webhook_and_settings_strictly_validated(self):
  for url in ('http://open.feishu.cn/open-apis/bot/v2/hook/'+'x'*20,'https://other.invalid/open-apis/bot/v2/hook/'+'x'*20,settings()['webhook']+'?secret=x',settings()['webhook'].replace('https://','https://user@')):
   with self.assertRaises(ValueError):validate_settings({**settings(),'webhook':url})
 def test_no_signing_fields_when_signature_disabled(self):
  transport=Transport(Response());FeishuSender({**settings(),'signing_secret':''},transport)(batch());self.assertNotIn('sign',json.loads(transport.calls[0][0].data))
 def test_settings_default_disabled_and_legacy_off_required(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'notifications.json';self.assertEqual(({'enabled':False},None),runtime_settings(path))
   path.write_text(json.dumps(settings()));path.chmod(0o600);self.assertIsNone(runtime_settings(path)[1])
   path.write_text(json.dumps({**settings(),'enabled':True}));self.assertIsNone(runtime_settings(path)[1])
   path.write_text(json.dumps({**settings(),'enabled':True,'legacy_notifications_disabled':True}));public,sender=runtime_settings(path)
   self.assertTrue(public['enabled']);self.assertIsNotNone(sender);self.assertNotIn('webhook',public);self.assertNotIn('signing_secret',public)
 def test_save_backup_rollback_prepared_before_atomic_replace(self):
  # Windows and Linux both exercise real temp-file replacement; OS ownership is
  # patched only for portable fixtures, never the production setup command.
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'notifications.json';path.write_text(json.dumps(settings()));backups=root/'backups'
   import os
   replace=os.replace
   def replace_checked(source,target):
    folders=list(backups.iterdir());self.assertEqual(1,len(folders));self.assertTrue((folders[0]/'rollback.sh').exists());self.assertEqual(settings(),json.loads((folders[0]/'settings.before.json').read_text()));replace(source,target)
   with patch('cloud.notification_setup.os.replace',side_effect=replace_checked),patch('cloud.notification_setup.private_owner'):
    answer=save({**settings(),'keyword':'new'},path,backups)
   self.assertTrue(answer['savedPrivately']);self.assertEqual('new',load(path)['keyword']);self.assertNotIn('fixture-secret',json.dumps(answer));self.assertNotIn('00000000',json.dumps(answer))
 def test_phone_probe_uses_isolated_cache_and_two_real_sender_calls(self):
  calls=[]
  class Sender:
   def __init__(self,*args,**kwargs):pass
   def __call__(self,b):calls.append(b);return {'state':'sent','receipt':'fixture'}
  with patch('cloud.notification_setup.FeishuSender',Sender):answer=phone_acceptance(settings())
  self.assertEqual(['home_offline','recovered'],[b['kind'] for b in calls]);self.assertEqual(2,answer['messagesAccepted']);self.assertFalse(answer['realHomeContacted'])
 def test_status_requires_login_and_never_contains_private_config(self):
  from cloud.app import create_app,HASHER,COOKIE
  from cloud.store import Store
  from fastapi.testclient import TestClient
  with tempfile.TemporaryDirectory() as directory:
   store=Store(Path(directory)/'console.db');user=store.register('fixture-user','fixture-password-hash',2);token,_=store.new_session(user)
   config={'origin':'https://console.fixture.ts.net','agent_token_sha256':'a'*64,'invite_hash':HASHER.hash('fixture-invite')}
   application=create_app(config,store,Path(__file__).parents[1]/'static');client=TestClient(application,base_url=config['origin'])
   self.assertEqual(401,client.get('/console/notifications').status_code);client.cookies.set(COOKIE,token)
   response=client.get('/console/notifications');self.assertEqual(200,response.status_code)
   self.assertFalse(response.json()['enabled']);self.assertNotIn('webhook',response.text);self.assertNotIn('signing_secret',response.text)
if __name__=='__main__':unittest.main()
