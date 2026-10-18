import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from agent.lifecycle import Lifecycle
from agent.readonly import ReadOnlyAgent,SingleInstance

class SensitiveError(Exception):
    def __str__(self):raise AssertionError('Exception stringification is forbidden')

class WorkerFailureTests(unittest.TestCase):
    def test_safe_diagnostic_never_formats_exception_or_records_message_locals(self):
        with TemporaryDirectory() as folder:
            lifecycle=Lifecycle(folder)
            try:raise SensitiveError('inert-secret-fixture-never-record')
            except SensitiveError as error:lifecycle.record_worker_failure('upload',error)
            data=json.loads((Path(folder)/'last-worker-failure.json').read_text())
            self.assertEqual('SensitiveError',data['failure']['exceptionType'])
            self.assertEqual('upload',data['failure']['worker'])
            self.assertTrue(data['failure']['frames'])
            self.assertNotIn('inert-secret-fixture-never-record',json.dumps(data))
            self.assertEqual({'file','function','line'},set(data['failure']['frames'][0]))

    def run_failure(self,folder,diagnostic_failure=False):
        agent=ReadOnlyAgent('https://fixture.ts.net','inert-secret-fixture-never-record',folder)
        def fail():raise SensitiveError('inert-secret-fixture-never-record')
        agent.heartbeat_loop=fail
        agent.collection_loop=lambda:agent.stop.wait(10)
        agent.upload_loop=lambda:agent.stop.wait(10)
        agent.demand_loop=lambda:agent.stop.wait(10)
        original=__import__('agent.lifecycle',fromlist=['atomic_json']).atomic_json
        def write(path,value):
            if diagnostic_failure and Path(path).name=='last-worker-failure.json':raise PermissionError('fixture disk denial')
            return original(path,value)
        with patch('agent.lifecycle.atomic_json',side_effect=write),patch.object(agent,'home',side_effect=AssertionError('No home HTTP')):
            with self.assertRaisesRegex(RuntimeError,'Agent worker failed'):agent.run()
        with SingleInstance(Path(folder)/'agent.lock'):pass
        status=json.loads((Path(folder)/'agent-runtime.json').read_text())
        self.assertEqual('failed',status['phase']);self.assertEqual('heartbeat',status['workerFailure']['worker'])
        self.assertEqual('SensitiveError',status['workerFailure']['exceptionType'])
        self.assertNotIn('inert-secret-fixture-never-record',json.dumps(status))
        return status

    def test_worker_failure_is_persisted_and_lock_is_released(self):
        with TemporaryDirectory() as folder:
            status=self.run_failure(folder)
            self.assertTrue(status['workerFailurePersisted'])
            self.assertTrue((Path(folder)/'last-worker-failure.json').exists())

    def test_diagnostic_write_denial_still_stops_without_unsafe_traceback(self):
        with TemporaryDirectory() as folder:
            status=self.run_failure(folder,True)
            self.assertFalse(status['workerFailurePersisted'])
            self.assertFalse((Path(folder)/'last-worker-failure.json').exists())
