import json
import tempfile
import unittest
from pathlib import Path

import app


class OpsTests(unittest.TestCase):
    def test_pipeline_stage_normalization(self):
        stage = app.Collector.normalize_stage(
            {
                "status": "completed_with_errors",
                "total": 9,
                "completed": 8,
                "failed": 1,
                "current": {"stage": "正在去字幕", "name": "视频001"},
            },
            "test",
        )
        self.assertEqual(stage["state"], "failed")
        self.assertEqual(stage["progress"], 100)
        self.assertIn("正在去字幕", stage["current"])
        self.assertEqual(stage["source"], "test")

    def test_state_categories(self):
        self.assertEqual(app.task_category("Waiting"), "waiting")
        self.assertEqual(app.task_category("Exporting"), "running")
        self.assertEqual(app.task_category("Completed"), "completed")
        self.assertEqual(app.task_category("Failed"), "failed")

    def test_normalize_uses_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            store = app.Store(Path(folder) / "test.db")
            collector = app.Collector(app.CONFIG, store)
            collector.metadata = {
                "task-1": {
                    "date": "7.17",
                    "project": "云手机",
                    "material": "碳岩板",
                    "language": "西班牙语",
                    "number": "003",
                    "sequence": 2,
                }
            }
            task = collector.normalize_task(
                {"taskId": "task-1", "state": "Exporting"},
                Path("status.json"),
                100.0,
                "batch-1",
            )
            self.assertEqual(task["project"], "云手机")
            self.assertEqual(task["state_text"], "2K导出")
            self.assertEqual(task["date_label"], "7.17")

    def test_broken_json_keeps_previous_task(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            store = app.Store(root / "test.db")
            config = dict(app.CONFIG)
            config["capcut_handoff_dir"] = str(root)
            config["fourth_step_handoff_dir"] = str(root / "records")
            config["simulation_enabled"] = False
            collector = app.Collector(config, store)
            status = root / "sample.status.json"
            status.write_text(json.dumps({
                "batchId": "b1",
                "date": "7.17",
                "updatedAt": "2026-07-19T10:00:00+08:00",
                "tasks": [{"taskId": "t1", "state": "Completed", "project": "云手机"}],
            }, ensure_ascii=False), encoding="utf-8")
            collector.scan_metadata()
            collector.scan_statuses()
            self.assertEqual(len(store.tasks()), 1)
            status.write_text('{"tasks": [', encoding="utf-8")
            collector.scan_statuses()
            self.assertEqual(len(store.tasks()), 1)
            self.assertEqual(store.tasks()[0]["state"], "Completed")
            self.assertEqual(len(store.source_errors()), 1)


if __name__ == "__main__":
    unittest.main()
