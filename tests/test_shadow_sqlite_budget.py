import tempfile
import unittest
from tools.shadow_sqlite_budget import experiment


class BudgetExperimentTests(unittest.TestCase):
    def test_small_synthetic_measurement_never_claims_production_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            result=experiment(root,target_bytes=64*1024,rounds=4)
        self.assertEqual(4,len(result['measuredRounds']))
        self.assertEqual(3,len(result['forecastScenarios']))
        self.assertGreater(result['measuredRounds'][0]['newChunkBytes'],0)
        self.assertFalse(result['productionBudgetVerified'])
        self.assertFalse(result['installationPermitted'])
    def test_experiment_size_and_workload_are_bounded(self):
        for args in [{'target_bytes':-1},{'rounds':3},{'target_bytes':2**31}]:
            with self.assertRaises(ValueError):experiment('.',**args)


if __name__=='__main__':unittest.main()
