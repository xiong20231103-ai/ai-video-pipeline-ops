import hashlib,json,tempfile,unittest
from pathlib import Path
from tools.shadow_evidence_audit import audit_passive,source_identity
from agent.core.snapshot import canonical

class ShadowAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'objects').mkdir();(self.root/'samples').mkdir()
        self.batch='formal-batch-123';self.task=self.batch+'-01'
    def add(self,value=None,**flags):
        body=canonical(value or {'items':{self.task:{'taskId':self.task,'batchId':self.batch,'pipelineStatus':'completed','completed':4,'expectedCount':4}}})
        digest=hashlib.sha256(body).hexdigest();(self.root/'objects'/digest).write_bytes(body)
        sample={'schema':1,'mode':'passive-evidence','observedAt':'2026-10-21T12:00:00+08:00','productionWrites':False,'businessRequests':0,'files':[{'root':'WB','relative':'status.json','sha256':digest,'bytes':len(body)}],'budgetHit':False,'quotaExhausted':False,'errorCounts':{},**flags}
        path=self.root/'samples'/('sample'+str(len(list((self.root/'samples').iterdir())))+'.json');path.write_bytes(canonical(sample))
        return digest,path,sample
    def test_observation_never_becomes_a_shadow_pass(self):
        self.add();r=audit_passive(self.root,self.batch)
        self.assertIn(self.task,r['observedProjects']);self.assertFalse(r['comparable']);self.assertFalse(r['realShadowPassed']);self.assertFalse(r['switchAccepted'])
        self.assertIn('offline candidate replay',r['blockers'])
    def test_missing_and_changed_objects_rejected(self):
        digest,_,_=self.add();(self.root/'objects'/digest).write_bytes(b'changed')
        r=audit_passive(self.root,self.batch);self.assertNotIn(self.task,r['observedProjects']);self.assertTrue(r['errors'])
    def test_false_real_pass_claim_in_sample_is_ignored(self):
        self.add(comparable=True,realShadowPassed=True,switchAccepted=True)
        self.assertFalse(audit_passive(self.root,self.batch)['realShadowPassed'])
    def test_budget_and_quota_are_reported_as_blockers(self):
        self.add(budgetHit=True,quotaExhausted=True)
        self.assertIn('capture_truncated',audit_passive(self.root,self.batch)['blockers'])
    def test_foreign_batch_not_attributed_by_date(self):
        self.add({'taskId':'other','batchId':'other-batch','date':'10.15'})
        r=audit_passive(self.root,self.batch);self.assertEqual({},r['observedProjects']);self.assertIn('batch_not_observed',r['blockers'])
    def test_timezone_and_window_must_be_explicit(self):
        self.add()
        with self.assertRaisesRegex(ValueError,'timezone'):audit_passive(self.root,self.batch,since='2026-10-21T00:00:00')
        r=audit_passive(self.root,self.batch,since='2026-10-22T00:00:00+08:00');self.assertIn('no_samples_in_window',r['blockers'])
    def test_source_change_is_not_silently_normalized(self):
        self.add();p=self.root/'source.txt';p.write_text('old')
        expected=source_identity(p);p.write_text('new')
        r=audit_passive(self.root,self.batch,source=p,expected_source=expected)
        self.assertIn('production_source_not_candidate_baseline',r['blockers'])
    def test_secret_object_is_never_echoed(self):
        self.add({'password':'do-not-report'})
        r=audit_passive(self.root,self.batch);self.assertNotIn('do-not-report',json.dumps(r));self.assertTrue(r['errors'])
    def test_duplicate_reference_is_not_comparable(self):
        _,p,s=self.add();s['files']*=2;p.write_bytes(canonical(s))
        self.assertTrue(audit_passive(self.root,self.batch)['errors'])
    def test_cli_no_overwrite_or_evidence_write(self):
        from tools.shadow_audit import main
        self.add();out=self.root.parent/(self.root.name+'-report.json');self.addCleanup(lambda:out.unlink(missing_ok=True))
        args=['--evidence',str(self.root),'--batch-id',self.batch,'--out',str(out)]
        self.assertEqual(0,main(args))
        with self.assertRaises(ValueError):main(args)
        with self.assertRaises(ValueError):main(args[:-1]+[str(self.root/'report.json')])

    def test_audit_budget_is_explicit_and_never_a_pass(self):
        from unittest.mock import patch
        self.add()
        with patch('tools.shadow_evidence_audit.time.monotonic',side_effect=[0,31,32]):
            r=audit_passive(self.root,self.batch)
        self.assertTrue(r['auditBudgetHit']);self.assertIn('audit_time_budget_reached',r['blockers'])
        self.assertFalse(r['realShadowPassed'])
