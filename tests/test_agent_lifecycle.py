import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
from agent.lifecycle import Lifecycle,STOP_FILE,MAINTENANCE_FILE,STATUS_FILE,atomic_json,request_identity
from agent.readonly import ReadOnlyAgent,SingleInstance,main
from deploy.agent_source_update import begin_stop,wait_stopped,finish,UpdateError

class AgentLifecycleTests(unittest.TestCase):
    def test_empty_manual_stop_and_maintenance_are_fail_closed(self):
        with TemporaryDirectory() as folder:
            state=Path(folder); lifecycle=Lifecycle(state)
            self.assertIsNone(lifecycle.stop_request())
            (state/STOP_FILE).write_text('')
            self.assertEqual('manual',lifecycle.stop_request())
            (state/STOP_FILE).unlink()
            atomic_json(state/MAINTENANCE_FILE,{'requestId':'abc123'})
            self.assertEqual('abc123',lifecycle.stop_request())

    def test_stop_before_start_does_not_read_credentials_or_poll_home(self):
        with TemporaryDirectory() as folder:
            state=Path(folder)/'OpsAgent';state.mkdir()
            atomic_json(state/STOP_FILE,{'requestId':'abc123'})
            # There is deliberately no private config to read.
            with patch.dict(os.environ,{'LOCALAPPDATA':folder}): main()
            status=json.loads((state/STATUS_FILE).read_text())
            self.assertEqual('stopped',status['phase']);self.assertEqual('abc123',status['stopRequestId'])

    def test_running_stop_ack_and_lock_release_with_no_network(self):
        with TemporaryDirectory() as folder:
            state=Path(folder);instance=ReadOnlyAgent('https://fixture.ts.net','inert-fixture-value',state)
            instance.heartbeat_loop=lambda:instance.stop.wait(10)
            instance.collection_loop=lambda:instance.stop.wait(10)
            instance.upload_loop=lambda:instance.stop.wait(10)
            instance.demand_loop=lambda:instance.stop.wait(10)
            with patch.object(instance,'home',side_effect=AssertionError('No home request allowed')):
                runner=threading.Thread(target=instance.run);runner.start()
                deadline=time.monotonic()+5
                while not (state/STATUS_FILE).exists():
                    self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                began=time.monotonic();begin_stop(state,'abc123');result=wait_stopped(state,'abc123')
                runner.join(3);self.assertFalse(runner.is_alive())
                self.assertLess(time.monotonic()-began,3)
                self.assertTrue(result['lockFree']);self.assertTrue(result['cooperativeAck'])
                with SingleInstance(state/'agent.lock'): pass
            status=json.loads((state/STATUS_FILE).read_text())
            self.assertNotIn('token',json.dumps(status).lower());self.assertNotIn('cloud_origin',status)
            finish(state,'abc123');self.assertFalse((state/STOP_FILE).exists());self.assertFalse((state/MAINTENANCE_FILE).exists())

    def test_other_maintenance_owner_is_never_overwritten_or_removed(self):
        with TemporaryDirectory() as folder:
            state=Path(folder);begin_stop(state,'abc123')
            with self.assertRaises(UpdateError):begin_stop(state,'def456')
            with self.assertRaises(UpdateError):finish(state,'def456')
            self.assertEqual('abc123',request_identity(state/STOP_FILE))

    def test_busy_lock_stop_timeout_leaves_code_and_maintenance_untouched(self):
        with TemporaryDirectory() as folder:
            state=Path(folder);begin_stop(state,'abc123')
            with SingleInstance(state/'agent.lock'):
                with self.assertRaises(UpdateError) as caught:wait_stopped(state,'abc123',timeout=.1)
            self.assertEqual('graceful_stop_timeout_no_code_replaced',caught.exception.code)
            self.assertEqual('abc123',request_identity(state/MAINTENANCE_FILE))
