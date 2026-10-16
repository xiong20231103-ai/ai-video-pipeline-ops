import unittest
from contracts.shadow import RULES,pending_ledger,switch_blockers

class ShadowGateTests(unittest.TestCase):
    def test_review_all_77_rules_present_including_draft_partial_failure(self):
        ids={item['id'] for item in RULES}
        self.assertEqual(77,len(ids))
        self.assertIn('R5-D08',ids)
        self.assertIn('RC-12',ids)
        self.assertIn('R4-30',ids)

    def test_empty_or_simulated_zero_differences_never_authorize_switch(self):
        report=pending_ledger()
        self.assertTrue(switch_blockers(report,[item['id'] for item in RULES]))
        report.update(sourceIdentity='frozen',candidateSourceIdentity='frozen')
        report['rules']=[{'ruleId':'R4-01','status':'passed','caseCount':1,'mismatchCount':0}]
        self.assertTrue(switch_blockers(report,['R4-01']))

    def test_unaligned_window_or_any_missing_rule_blocks_real_batch(self):
        report={'mode':'real-shadow','fullBatchId':'fixture-complete','sourceIdentity':'a','candidateSourceIdentity':'b',
                'rules':[{'ruleId':'R4-01','status':'passed','caseCount':1,'mismatchCount':0}]}
        self.assertTrue(switch_blockers(report,['R4-01']))
        report['candidateSourceIdentity']='a'
        self.assertTrue(switch_blockers(report,['R4-01','R4-02']))
        self.assertEqual([],switch_blockers(report,['R4-01']))
