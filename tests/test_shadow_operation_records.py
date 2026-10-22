import base64,json,unittest
from tools.shadow_operation_records import command_from_completed_receipt
from tools.shadow_capture import CaptureError
class ReceiptAdapterTests(unittest.TestCase):
 def job(self):return {'id':'fixture-command','target':'/api/controls/tasks/fixture-task/replenish','body':{'urls':'https://example.invalid/replacement','startNow':False}}
 def reply(self,status=200,body=None):return {'kind':'http','httpStatus':status,'bodyBase64':base64.b64encode(json.dumps(body or {'ok':True,'taskId':'fixture-child'}).encode()).decode()}
 def test_observed_forwarded_reply_retains_original_ids_and_body(self):
  job=self.job();r=command_from_completed_receipt(job,self.reply(),batch_id='fixture-batch',task_id='fixture-task',observed_at='2026-10-22T12:00:00+08:00');self.assertEqual('fixture-command',r['commandId']);self.assertEqual(job['body'],r['ports'][0]['body']);self.assertEqual('receiver:/api/tasks/replenish/fixture-task',r['ports'][0]['target'])
 def test_wrong_task_ambiguous_result_native_launch_and_credentials_are_refused(self):
  for case in ['wrong-task','unknown','native','private']:
   with self.subTest(case=case):
    job=self.job();reply=self.reply();task='fixture-task'
    if case=='wrong-task':task='another-task'
    elif case=='unknown':reply=self.reply(503,{'detail':'unavailable'})
    elif case=='native':job['target']='/api/controls/upload/rescan'
    else:reply=self.reply(200,{'accessToken':'private-canary'})
    with self.assertRaises((CaptureError,ValueError)):command_from_completed_receipt(job,reply,batch_id='fixture-batch',task_id=task,observed_at='2026-10-22T12:00:00+08:00')
