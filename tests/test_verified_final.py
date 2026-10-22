import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from verified_final import released_final_verified, _digest


class VerifiedFinalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "final.mp4"
        self.output.write_bytes(b"verified-final-fixture")
        self.report = self.root / "qc.json"
        self.qc = {"status": "passed", "taskId": "child", "canonicalTaskId": "parent",
                   "fileName": "final.mp4", "fileSize": self.output.stat().st_size,
                   "sha256": hashlib.sha256(self.output.read_bytes()).hexdigest()}
        self.meta = {"taskId": "child", "remotePipelineTaskId": "parent", "status": "failed",
                     "productionStatus": "completed", "draftReleaseStatus": "released",
                     "qualityStatus": "passed", "qualityReportPath": str(self.report),
                     "finalOutputPath": str(self.output), "maintenanceError": "old draft failure"}
        self.save()

    def save(self):
        self.report.write_text(json.dumps(self.qc), encoding="utf-8")

    def normalize(self, state="failed"):
        with patch.dict(app.COLLECTOR.metadata, {"child": self.meta}, clear=True):
            return app.COLLECTOR.normalize_task({"taskId": "child", "status": state,
                "error": "old draft failure", "currentPhase": "Failed"}, self.root / "status.json", 1)

    def test_exact_verified_final_reconciles_stale_failure_without_writing_ledger(self):
        original = dict(self.meta)
        task = self.normalize()
        self.assertEqual("completed", task["state"])
        self.assertEqual("completed", task["phase"])
        self.assertEqual("", task["error"])
        self.assertIn("old draft failure", task["draft_cleanup_warning"])
        self.assertEqual(original, self.meta)
        row = {**task, "expected_task_count": 1}
        with patch("app.production_capcut_tasks", return_value=[row]), patch("app.upload_task_index", return_value={}):
            summary = app.remote_capcut_summaries()["parent"]
        self.assertTrue(summary["complete"])
        self.assertEqual((1, 1, 0), (summary["completed"], summary["valid"], summary["failed"]))

    def test_wrong_identity_failed_qc_wrong_name_size_and_hash_remain_failed(self):
        for key, value in [("taskId", "other"), ("canonicalTaskId", "other"),
                           ("status", "failed"), ("fileName", "temp.mp4"),
                           ("fileSize", 1), ("sha256", "0" * 64)]:
            with self.subTest(key=key):
                old = self.qc[key]; self.qc[key] = value; self.save()
                self.assertEqual("failed", self.normalize()["state"])
                self.qc[key] = old; self.save()

    def test_pending_release_missing_file_malformed_report_and_flag_alone_rejected(self):
        self.meta["draftReleaseStatus"] = "pending"
        self.assertFalse(released_final_verified(self.meta))
        self.meta["draftReleaseStatus"] = "released"
        self.report.write_text("{", encoding="utf-8")
        self.assertFalse(released_final_verified(self.meta))
        self.save(); self.output.unlink()
        self.assertEqual("failed", self.normalize()["state"])

    def test_active_attempt_is_never_overridden(self):
        self.assertEqual("Running", self.normalize("Running")["state"])

    def test_changed_bytes_invalidate_cached_digest(self):
        self.assertTrue(released_final_verified(self.meta))
        self.output.write_bytes(b"x" * self.qc["fileSize"])
        self.assertFalse(released_final_verified(self.meta))

    def test_unchanged_mutable_file_is_rehashed(self):
        with patch('verified_final._digest', wraps=_digest) as digest:
            self.assertTrue(released_final_verified(self.meta))
            self.assertTrue(released_final_verified(self.meta))
            self.assertEqual(2, digest.call_count)

    def test_same_size_content_change_with_identical_stat_is_rejected(self):
        original_stat = Path.stat
        stable = self.output.stat()
        def stat(path, *args, **kwargs):
            return stable if path == self.output else original_stat(path, *args, **kwargs)
        with patch.object(Path, 'stat', stat):
            self.assertTrue(released_final_verified(self.meta))
            self.output.write_bytes(b'x' * self.qc['fileSize'])
            self.assertFalse(released_final_verified(self.meta))

    def test_four_finals_with_one_stale_failure_count_four_not_three(self):
        verified = self.normalize()
        rows = [{**verified, "task_id": "child-" + str(i), "expected_task_count": 4}
                for i in range(3)] + [{**verified, "expected_task_count": 4}]
        with patch("app.production_capcut_tasks", return_value=rows), patch("app.upload_task_index", return_value={}):
            summary = app.remote_capcut_summaries()["parent"]
        self.assertEqual((4, 4, 4, 0), tuple(summary[k] for k in ("total", "completed", "valid", "failed")))
        self.assertTrue(summary["complete"])

    def test_temporary_output_is_not_published_as_final(self):
        with patch.dict(app.COLLECTOR.metadata, {"child": self.meta}, clear=True):
            task = app.COLLECTOR.normalize_task({"taskId": "child", "status": "failed",
                "outputPath": str(self.root / "capcut-temp.mp4")}, self.root / "status.json", 1)
        self.assertEqual(str(self.output), task["output_path"])
