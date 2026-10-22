import copy,json,sqlite3,unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from agent.core.replay import make_fixture
from agent.core.snapshot import capture,canonical
from tools.shadow_compare import compare_reads,compare_history,batch_review
ROOT=Path(__file__).resolve().parents[1]
class WindowCompareTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8');self.profile=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))['running']
 def test_unclosed_snapshot_is_a_blocker_not_a_zero_difference(self):
  snapshot=make_fixture(self.profile,self.source,self.root/'snap');r=compare_reads(self.source,snapshot,self.root/'replay',['/api/health']);self.assertFalse(r['comparable']);self.assertIsNone(r['mismatchCount']);self.assertEqual(0,r['caseCount'])
 def test_even_identical_replay_errors_are_not_passes(self):
  profile=copy.deepcopy(self.profile);profile['facts']['dependencyClosure']=True;snapshot=make_fixture(profile,self.source,self.root/'snap')
  with patch('tools.shadow_compare.replay',side_effect=ValueError('private-canary-must-not-log')):r=compare_reads(self.source,snapshot,self.root/'replay',['/api/health'])
  self.assertFalse(r['comparable']);self.assertIsNone(r['mismatchCount']);self.assertNotIn('private-canary',json.dumps(r))
 def test_read_mutation_is_counted_not_erased(self):
  profile=copy.deepcopy(self.profile);profile['facts']['dependencyClosure']=True;snapshot=make_fixture(profile,self.source,self.root/'snap')
  old={'responses':{'/api/health':{'status':200,'body':{'taskCount':3}}}};new={'responses':{'/api/health':{'status':200,'body':{'taskCount':2}}}}
  with patch('tools.shadow_compare.replay',return_value=old),patch.dict('tools.shadow_compare.READ_MODULES',R1=lambda *args:new):r=compare_reads(self.source,snapshot,self.root/'replay',['/api/health'])
  self.assertEqual(1,r['mismatchCount']);self.assertEqual('different',r['status']);self.assertFalse(r['realShadowPassed'])
 def test_real_read_adapters_run_under_closed_synthetic_inventory(self):
  profile=copy.deepcopy(self.profile)
  roots=['repository','workbench','voice','capcut','downloads','generation','final','drafts','audio','pending-delete','localappdata','appdata','home']
  profile['facts'].update(dependencyClosure=True,completeDirectoryRoots=roots,filesystem={name:{'kind':'directory','size':0,'mtimeNs':0} for name in roots})
  snapshot=make_fixture(profile,self.source,self.root/'snap')
  r=compare_reads(self.source,snapshot,self.root/'replay',['/api/health','/api/project-gaps'])
  self.assertTrue(r['comparable'],r);self.assertEqual(0,r['mismatchCount'],r);self.assertEqual(2,r['caseCount'])
 def test_history_roundtrip_compares_source_bytes_and_rows_but_not_fake_duration_acceptance(self):
  db=self.root/'ops.db'
  with closing(sqlite3.connect(db)) as con:con.execute('CREATE TABLE tasks(task_id TEXT PRIMARY KEY,state TEXT)');con.execute('INSERT INTO tasks VALUES(?,?)',('fixture-video','Completed'));con.commit()
  state=self.root/'source.json';state.write_bytes(canonical({'items':{'fixture-task':{'completed':1}}}))
  snapshot=capture(self.root/'snap',files={'workbench/handoff/download/project_status.json':state},databases={'repository/data/ops.db':db},facts={'historyResetGeneration':'fixture-reset'},frozen_at='2026-10-22T12:00:00+08:00',legacy_sha256=__import__('hashlib').sha256(self.source.encode()).hexdigest())
  r=compare_history(snapshot,self.root/'replay',source_id='fixture-home',sequence=1)
  self.assertEqual('lossless-source-match',r['status']);self.assertEqual(0,r['mismatchCount']);self.assertEqual(2,r['caseCount']);self.assertFalse(r['timelineAccuracyAccepted']);self.assertFalse(r['realShadowPassed'])
 def test_history_without_database_is_incomplete_not_zero_rows_pass(self):
  snapshot=make_fixture(self.profile,self.source,self.root/'snap');r=compare_history(snapshot,self.root/'history',source_id='fixture-home',sequence=1);self.assertFalse(r['comparable']);self.assertIsNone(r['mismatchCount'])
class BatchReviewTests(unittest.TestCase):
 def boundaries(self):return {'batchId':'fixture-batch','sourceIdentity':'fixture-start','observedAt':'2026-10-22T10:00:00+08:00','expectedTaskIds':['one']},{'batchId':'fixture-batch','sourceIdentity':'fixture-end','observedAt':'2026-10-22T11:00:00+08:00','completeTaskIds':['one']}
 def test_missing_actual_operations_stay_pending_even_when_isolated_zero(self):
  a,b=self.boundaries();rows=[{'module':m,'batchId':'fixture-batch','caseCount':10,'mismatchCount':0,'comparable':True,'sourceIdentity':'same','candidateSourceIdentity':'same'} for m in ['R1','R2','R3','R5']];r=batch_review(rows,batch_id='fixture-batch',started_evidence=a,completed_evidence=b)
  self.assertFalse(r['readyForHumanReview']);self.assertEqual('not-accepted',r['modules']['R5']['status']);self.assertEqual(0,r['modules']['R5']['actualTriggers']);self.assertFalse(r['switchAccepted'])
 def test_zero_cases_missing_identity_and_partial_batch_never_pass(self):
  a,b=self.boundaries();b['completeTaskIds']=[];r=batch_review([],batch_id='fixture-batch',started_evidence=a,completed_evidence=b);self.assertIn('complete_batch_tasks_not_observed',r['blockers']);self.assertFalse(r['realShadowPassed'])
