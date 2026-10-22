"""Synthetic negative controls; these tests never certify real batch evidence."""
import copy
import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from tools.shadow_compare import batch_review,campaign_review
from tools.shadow_capture import CaptureError

class ReviewGateTests(unittest.TestCase):
 def fixture(self,batch='fixture-batch'):
  a={'batchId':batch,'sourceIdentity':batch+'-start','observedAt':'2026-10-22T10:00:00+08:00','expectedTaskIds':['one','two'],'realBatchEvidence':True,'dependencyClosureVerified':True}
  b={'batchId':batch,'sourceIdentity':batch+'-end','observedAt':'2026-10-22T11:00:00+08:00','completeTaskIds':['one','two'],'realBatchEvidence':True,'dependencyClosureVerified':True}
  rows=[{'module':m,'batchId':batch,'sourceIdentity':batch+'-'+m,'candidateSourceIdentity':batch+'-'+m,'observedAt':'2026-10-22T10:30:00+08:00','taskIds':['one','two'],'observedTriggerIds':[batch+'-trigger-'+m],'realBatchEvidence':True,'dependencyClosureVerified':True,'comparable':True,'caseCount':2,'mismatchCount':0,'timelineAccuracyAccepted':True} for m in ['R1','R2','R3','R5']]
  return a,b,rows
 def review(self,a,b,rows):return batch_review(rows,batch_id=a['batchId'],started_evidence=a,completed_evidence=b)
 def test_complete_synthetic_claims_only_ready_for_human_review(self):
  r=self.review(*self.fixture());self.assertTrue(r['readyForHumanReview'],r);self.assertFalse(r['realShadowPassed']);self.assertFalse(r['switchAccepted'])
 def test_reverse_equal_and_naive_boundary_times_rejected(self):
  for at in ['2026-10-22T09:00:00+08:00','2026-10-22T10:00:00+08:00','2026-10-22T11:00:00']:
   a,b,rows=self.fixture();b['observedAt']=at;r=self.review(a,b,rows);self.assertIn('batch_boundary_time_invalid',r['blockers'])
 def test_timezone_offsets_compare_as_instants(self):
  a,b,rows=self.fixture()
  for row in rows:row['observedAt']='2026-10-22T02:30:00Z'
  self.assertTrue(self.review(a,b,rows)['readyForHumanReview'])
 def test_samples_outside_batch_or_unknown_tasks_are_not_accepted(self):
  for field,value,reason in [('observedAt','2026-10-22T11:01:00+08:00','comparison_outside_batch_window'),('taskIds',['not-this-batch'],'comparison_task_identity_unproven')]:
   a,b,rows=self.fixture();rows[0][field]=value;r=self.review(a,b,rows);self.assertFalse(r['readyForHumanReview']);self.assertIn(reason,r['modules']['R1']['blockers'])
 def test_r1_and_r2_require_every_expected_task(self):
  for index in [0,1]:
   a,b,rows=self.fixture();rows[index]['taskIds']=['one'];r=self.review(a,b,rows);self.assertIn('complete_task_coverage_missing',r['modules'][rows[index]['module']]['blockers'])
 def test_real_operation_need_not_target_every_task(self):
  a,b,rows=self.fixture();rows[2]['taskIds']=['one'];rows[3]['taskIds']=['two'];self.assertTrue(self.review(a,b,rows)['readyForHumanReview'])
 def test_reused_snapshot_and_trigger_cannot_inflate_windows(self):
  a,b,rows=self.fixture();rows.append(copy.deepcopy(rows[0]));r=self.review(a,b,rows);self.assertIn('comparison_snapshot_reused',r['modules']['R1']['blockers']);self.assertEqual(1,r['modules']['R1']['actualTriggers'])
  a,b,rows=self.fixture();rows[3]['observedTriggerIds']=rows[2]['observedTriggerIds'];r=self.review(a,b,rows);self.assertIn('trigger_reused_across_comparisons',r['modules']['R5']['blockers'])
 def test_duplicate_task_ids_and_missing_live_boundary_are_rejected(self):
  a,b,rows=self.fixture();a['expectedTaskIds']=['one','one'];b['completeTaskIds']=['one','one'];a['realBatchEvidence']=False;r=self.review(a,b,rows);self.assertIn('complete_batch_tasks_not_observed',r['blockers']);self.assertIn('batch_boundary_real_evidence_missing',r['blockers'])
 def test_no_cleanup_trigger_keeps_r5_pending(self):
  a,b,rows=self.fixture();rows.pop();r=self.review(a,b,rows);self.assertEqual('not-accepted',r['modules']['R5']['status']);self.assertFalse(r['readyForHumanReview'])
 def test_duplicate_batch_does_not_become_two_batches(self):
  r=self.review(*self.fixture());c=campaign_review([r,r]);self.assertEqual(1,c['readyBatchCount']);self.assertFalse(c['readyForHumanReview']);self.assertEqual(0,c['acceptedRealBatchCount'])
 def test_different_batch_ids_cannot_reuse_same_snapshot(self):
  first=self.review(*self.fixture());second=self.review(*self.fixture('fixture-other'));second['comparisonSourceIdentities'][0]=first['comparisonSourceIdentities'][0];c=campaign_review([first,second]);self.assertIn('snapshot_reused_across_batches',c['blockers'])
 def test_two_distinct_synthetic_claims_still_never_grant_switch(self):
  c=campaign_review([self.review(*self.fixture()),self.review(*self.fixture('fixture-other'))]);self.assertEqual(2,c['readyBatchCount']);self.assertTrue(c['readyForHumanReview']);self.assertEqual(0,c['acceptedRealBatchCount']);self.assertFalse(c['switchAccepted'])
 def test_empty_modules_cannot_bypass_review(self):
  with self.assertRaises(CaptureError):campaign_review([],required_modules=[])
  with self.assertRaises(CaptureError):batch_review([],batch_id='fixture',started_evidence={},completed_evidence={},required_modules=[])
 def test_modified_review_summary_rejected(self):
  first=self.review(*self.fixture());second=self.review(*self.fixture('fixture-other'));second['completedAt']='2026-10-22T12:00:00+08:00';c=campaign_review([first,second]);self.assertIn('batch_review_hash_mismatch',c['blockers']);self.assertFalse(c['readyForHumanReview'])
 def test_cli_report_and_two_batch_campaign_leave_acceptance_false(self):
  from tools.shadow_evidence import main
  with TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
   root=Path(folder);outputs=[]
   for name in ['fixture-a','fixture-b']:
    a,b,rows=self.fixture(name);source=root/(name+'.input.json');output=root/(name+'.review.json');source.write_text(json.dumps({'reports':rows,'batchId':name,'startedEvidence':a,'completedEvidence':b}),encoding='utf-8');self.assertEqual(0,main(['review-batch','--input',str(source),'--out',str(output)]));outputs.append(output)
   out=root/'campaign.json';self.assertEqual(0,main(['review-campaign','--batch-review',str(outputs[0]),'--batch-review',str(outputs[1]),'--out',str(out)]));result=json.loads(out.read_text());self.assertTrue(result['readyForHumanReview']);self.assertEqual(0,result['acceptedRealBatchCount'])
   with self.assertRaises(CaptureError):main(['review-campaign','--batch-review',str(outputs[0]),'--out',str(out)])
 def test_cli_credential_descriptor_rejected_without_output(self):
  from tools.shadow_evidence import main
  with TemporaryDirectory() as folder:
   root=Path(folder);source=root/'input.json';output=root/'review.json';source.write_text(json.dumps({'password':'synthetic-do-not-copy'}),encoding='utf-8')
   with self.assertRaises(CaptureError):main(['review-batch','--input',str(source),'--out',str(output)])
   self.assertFalse(output.exists())
