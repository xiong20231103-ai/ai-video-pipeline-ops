import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app


TARGET = {
    "batchId": "box-1", "taskId": "box-1-05", "productionDate": "10.15",
    "manifestId": "capcut-m1", "attemptId": "attempt-1", "runGroupId": "run-1",
    "batchKind": "formal", "selectedProjects": [], "snapshotUpdatedAt": "",
}


class FakeRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def post(body):
    # Drive the coroutine directly: the isolated runner blocks the socket pair
    # an asyncio event loop needs on Windows, and nothing here really awaits.
    coroutine = app.create_control_command(FakeRequest(body))
    try:
        coroutine.send(None)
    except StopIteration as finished:
        return finished.value
    coroutine.close()
    raise RuntimeError("create_control_command unexpectedly suspended")


class ContinueContractTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.target = dict(TARGET)
        self.enqueued = []

        def fake_enqueue(target, client_request_id=""):
            command = {**target, "commandId": f"continue-{len(self.enqueued)}",
                       "clientRequestId": client_request_id, "state": "persisted"}
            self.enqueued.append(command)
            app.write_control_command(command)
            return command

        for patcher in (
            patch("app.require_control_permission"),
            patch("app.CONTROL_COMMAND_DIR", Path(self.folder.name) / "commands"),
            patch("app._current_continue_target", side_effect=lambda: dict(self.target)),
            patch("app.enqueue_control_command", side_effect=fake_enqueue),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_legacy_call_without_target_still_enqueues(self):
        result = post({"clientRequestId": "req-1"})
        self.assertEqual("box-1-05", result["taskId"])
        self.assertEqual(1, len(self.enqueued))

    def test_matching_expected_target_enqueues(self):
        post({"clientRequestId": "req-1", "expectedTarget": {
            "batchId": "box-1", "taskId": "box-1-05", "attemptId": "attempt-1"}})
        self.assertEqual(1, len(self.enqueued))

    def test_changed_attempt_is_rejected_without_enqueue(self):
        with self.assertRaises(app.HTTPException) as error:
            post({"clientRequestId": "req-1", "expectedTarget": {
                "taskId": "box-1-05", "attemptId": "attempt-0"}})
        self.assertEqual(409, error.exception.status_code)
        self.assertIn("尝试", error.exception.detail)
        self.assertEqual([], self.enqueued)

    def test_changed_project_is_rejected(self):
        with self.assertRaises(app.HTTPException) as error:
            post({"expectedTarget": {"taskId": "box-1-04"}})
        self.assertEqual(409, error.exception.status_code)
        self.assertIn("项目", error.exception.detail)

    def test_blank_expected_fields_are_ignored(self):
        post({"expectedTarget": {"taskId": "box-1-05", "manifestId": "", "runGroupId": None}})
        self.assertEqual(1, len(self.enqueued))

    def test_malformed_expected_target_is_400(self):
        for body in ({"expectedTarget": "box-1"},
                     {"expectedTarget": {"taskId": 5}},
                     {"expectedTarget": {"commandId": "x"}}):
            with self.assertRaises(app.HTTPException) as error:
                post(body)
            self.assertEqual(400, error.exception.status_code)
        self.assertEqual([], self.enqueued)

    def test_reused_request_id_for_another_project_is_rejected(self):
        post({"clientRequestId": "req-1"})
        self.target.update({"taskId": "box-1-06", "attemptId": "attempt-2"})
        with self.assertRaises(app.HTTPException) as error:
            post({"clientRequestId": "req-1"})
        self.assertEqual(409, error.exception.status_code)
        self.assertEqual(1, len(self.enqueued))

    def test_reused_request_id_for_same_project_reaches_idempotent_enqueue(self):
        post({"clientRequestId": "req-1"})
        post({"clientRequestId": "req-1"})
        self.assertEqual(2, len(self.enqueued))  # enqueue_control_command itself dedupes

    def test_target_check_and_enqueue_are_serialised(self):
        inside = threading.Event()
        release = threading.Event()
        order = []

        def slow_enqueue(target, client_request_id=""):
            order.append(("start", client_request_id))
            inside.set()
            release.wait(2)
            order.append(("end", client_request_id))
            return {"commandId": client_request_id}

        with patch("app.enqueue_control_command", side_effect=slow_enqueue):
            first = threading.Thread(target=post, args=({"clientRequestId": "a"},))
            first.start()
            self.assertTrue(inside.wait(2))
            second = threading.Thread(target=post, args=({"clientRequestId": "b"},))
            second.start()
            time.sleep(0.2)
            self.assertEqual([("start", "a")], order)
            release.set()
            first.join(3)
            second.join(3)
        self.assertEqual([("start", "a"), ("end", "a"), ("start", "b"), ("end", "b")], order)


if __name__ == "__main__":
    unittest.main()
