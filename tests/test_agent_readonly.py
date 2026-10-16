import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from agent.readonly import Ledger,ReadOnlyAgent,SingleInstance

class ReadOnlyAgentTests(unittest.TestCase):
    def test_ledger_versions_persist_and_canonicalize_effective_queries(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'agent.db'; ledger=Ledger(path)
            ledger.enqueue('/api/dashboard?date=10.16&batchId=b',200,{'state':'first'})
            Ledger(path).enqueue('/api/dashboard?batchId=b&date=10.16',200,{'state':'later'})
            payload=ledger.next(); self.assertEqual(2,payload['version']); self.assertEqual('later',payload['body']['state'])
            ledger.acknowledge(payload['target'],1); self.assertIsNotNone(ledger.next())
            ledger.acknowledge(payload['target'],2); self.assertIsNone(ledger.next())
    def test_304_compaction_never_drops_unacknowledged_base(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db'); body={'updatedAt':'frozen','state':'running'}
            ledger.enqueue('/api/dashboard/summary',200,body,'fixture-etag')
            ledger.enqueue('/api/dashboard/summary',304,body,'fixture-etag')
            self.assertEqual(200,ledger.next()['status']); self.assertEqual(body,ledger.next()['body'])
    def test_local_clock_delay_is_preserved_without_cloud_clock_comparison(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db')
            with patch('agent.readonly.time.time',return_value=100),patch('agent.readonly.time.monotonic',return_value=500):
                ledger.enqueue('/api/dashboard',200,{})
            with patch('agent.readonly.time.time',return_value=3700),patch('agent.readonly.time.monotonic',return_value=4100):
                self.assertEqual(3600,ledger.next()['captureAgeSeconds'])
    def test_single_instance_prevents_second_home_executor(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'agent.lock'
            with SingleInstance(path):
                with self.assertRaises(RuntimeError):
                    with SingleInstance(path): pass
    def test_agent_only_uses_fixed_loopback_home_routes(self):
        with TemporaryDirectory() as folder:
            instance=ReadOnlyAgent('https://fixture.ts.net','inert-fixture-value',folder)
            for target in ['https://foreign.invalid/api/dashboard','/api/controls/tasks/create','/api/controls/testing/reset']:
                with self.assertRaises(ValueError): instance.home(target)
            with self.assertRaises(ValueError): ReadOnlyAgent('http://fixture.ts.net','inert-fixture-value',folder)
