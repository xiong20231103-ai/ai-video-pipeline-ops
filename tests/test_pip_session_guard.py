from __future__ import annotations

import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import session_guard as guard


class SessionGuardTests(unittest.TestCase):
    def test_console_and_foreign_sessions(self):
        self.assertTrue(guard.decide_session(1, 1).allowed)
        self.assertFalse(guard.decide_session(2, 1).allowed)
        self.assertFalse(guard.decide_session(0, 0).allowed)

    def test_transient_console_bounded_retry(self):
        values = iter([(1, 0xFFFFFFFF), (1, 1)])
        sleeps = []
        self.assertTrue(guard.startup_decision(query=lambda: next(values), sleep=sleeps.append).allowed)
        self.assertEqual(sleeps, [0.2])
        calls = []
        decision = guard.startup_decision(query=lambda: (1, -1), attempts=3, sleep=calls.append)
        self.assertFalse(decision.allowed)
        self.assertEqual(calls, [0.2, 0.2])

    def test_query_failure_never_leaks_exception(self):
        def broken():
            raise OSError("do-not-record-sensitive-command")
        decision = guard.startup_decision(query=broken)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "session_query_failed")

    def test_skip_log_contains_only_allowlisted_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            guard.record_skip(Path(temp), "dashboard", "not_console_session")
            payload = json.loads(next(Path(temp).glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(set(payload), {"schemaVersion", "at", "role", "event", "reason"})

    def test_logging_failure_still_refuses(self):
        with patch.object(guard, "startup_decision", return_value=guard.SessionDecision(False, False, "not_console_session")):
            with patch.object(Path, "mkdir", side_effect=PermissionError):
                self.assertFalse(guard.console_startup_allowed("dashboard", Path("unused")))

    def test_dashboard_refusal_records_supported_role(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(guard, "startup_decision", return_value=guard.SessionDecision(False, False, "not_console_session")):
                self.assertFalse(guard.console_startup_allowed("dashboard", Path(temp)))
            payload = json.loads(next(Path(temp).glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(payload["role"], "dashboard")

    def test_rejected_direct_scripts_exit_before_pipeline_imports(self):
        root = Path(__file__).resolve().parents[1]
        for script, role in (("app.py", "dashboard"),):
            with self.subTest(script=script):
                with patch.object(guard, "console_startup_allowed", return_value=False) as check:
                    with self.assertRaises(SystemExit) as exit_info:
                        runpy.run_path(str(root / script), run_name="__main__")
                    self.assertEqual(exit_info.exception.code, 0)
                    self.assertEqual(check.call_args.args[0], role)

    def test_invalid_attempt_count_rejected(self):
        for value in (0, 11):
            with self.assertRaises(ValueError):
                guard.startup_decision(attempts=value)

    def test_sessionname_environment_cannot_override_native_identity(self):
        with patch.dict(os.environ, {"SESSIONNAME": "Console"}):
            self.assertFalse(guard.startup_decision(query=lambda: (2, 1)).allowed)
        with patch.dict(os.environ, {"SESSIONNAME": "RDP-Tcp#99"}):
            self.assertTrue(guard.startup_decision(query=lambda: (1, 1)).allowed)

    @unittest.skipUnless(os.name == "nt", "Windows import guard")
    def test_rejected_asgi_and_library_imports_stop_before_pipeline_imports(self):
        root = Path(__file__).resolve().parents[1]
        for script in ("app.py",):
            with self.subTest(script=script):
                with patch.object(guard, "console_startup_allowed", return_value=False):
                    with self.assertRaisesRegex(RuntimeError, "import_refused_outside_console_session"):
                        runpy.run_path(str(root / script), run_name="guarded_import_test")


if __name__ == "__main__":
    unittest.main()
