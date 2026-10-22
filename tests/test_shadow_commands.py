import copy,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from agent.core.replay import make_fixture
from tools.shadow_commands import compare_recorded_command
ROOT=Path(__file__).resolve().parents[1]
class RecordedCommandTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8');self.profile=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))['running'];roots=['repository','workbench','voice','capcut','downloads','generation','final','drafts','audio','pending-delete','localappdata','appdata','home'];self.profile['facts'].update(scan=False,dependencyClosure=True,completeDirectoryRoots=roots,filesystem={n:{'kind':'directory','size':0,'mtimeNs':0} for n in roots})
  self.record={'schema':1,'commandId':'fixture-command','batchId':'fixture-batch','taskId':'fixture-task','observedAt':self.profile['frozenAt'],'target':'/api/controls/tasks/fixture-task/replenish','body':{'urls':'https://example.invalid/replacement','startNow':False},'ports':[{'port':'http','method':'POST','target':'receiver:/api/tasks/replenish/fixture-task','body':{'urls':'https://example.invalid/replacement','startNow':False},'status':200,'response':{'ok':True,'taskId':'fixture-child'}}],'receipt':{'status':200,'body':{'ok':True,'taskId':'fixture-child'}}};self.path='workbench/handoff/operations/fixture.json'
 def run_case(self,record=None):
  profile=copy.deepcopy(self.profile);profile['files'][self.path]=record or self.record;snapshot=make_fixture(profile,self.source,self.root/'snap');return compare_recorded_command(self.source,snapshot,self.root/'replay',self.path)
 def test_real_adapters_compare_target_body_and_actual_receipt_without_post(self):
  r=self.run_case();self.assertTrue(r['comparable'],r);self.assertEqual(0,r['mismatchCount'],r);self.assertEqual(1,r['caseCount']);self.assertFalse(r['realBatchEvidence']);self.assertFalse(r['switchAccepted'])
 def test_wrong_target_or_missing_recorded_port_cannot_be_zero_difference(self):
  self.record['ports'][0]['target']='receiver:/api/tasks/replenish/wrong-task';r=self.run_case();self.assertFalse(r['comparable']);self.assertIsNone(r['mismatchCount']);self.assertEqual('incomplete',r['status'])
 def test_actual_receipt_disagreement_is_reported_even_when_both_replays_match(self):
  self.record['receipt']['body']['taskId']='different-child';r=self.run_case();self.assertTrue(r['comparable'],r);self.assertGreater(r['mismatchCount'],0);self.assertEqual('different',r['status'])
 def test_recorded_http_rejection_is_compared_without_retry(self):
  self.record['ports'][0].update(status=400,response={'detail':'fixture count mismatch'});self.record['receipt']={'status':400,'body':{'detail':'fixture count mismatch'}};r=self.run_case();self.assertTrue(r['comparable'],r);self.assertEqual(0,r['mismatchCount'],r)
 def test_unconsumed_port_and_missing_receipt_refuse(self):
  self.record['ports'].append(copy.deepcopy(self.record['ports'][0]));r=self.run_case();self.assertFalse(r['comparable']);self.assertIsNone(r['mismatchCount'])
