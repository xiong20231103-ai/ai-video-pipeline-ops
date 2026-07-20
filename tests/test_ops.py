import json
import tempfile
import unittest
from pathlib import Path

import app


class OpsTests(unittest.TestCase):
    def test_download_directory_fallback_finds_today_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "实体机"
            project.mkdir()
            (project / "video_ai_sttn.mp4").write_bytes(b"video")
            store = app.Store(root / "test.db")
            config = dict(app.CONFIG)
            config["download_root"] = str(root)
            collector = app.Collector(config, store)
            collector.scan_download_pipeline(False)
            stage = collector.pipeline["download"]
            self.assertEqual(stage["completed"], 1)
            self.assertEqual(stage["todayCompleted"], 1)
            self.assertIn("实体机 1条", stage["todaySummary"])

    def test_download_scan_recognizes_external_task_batch_structure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = root / "任务批次" / "7.20" / "云手机" / "碳岩板" / "video_ai_sttn.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"video")
            store = app.Store(root / "test.db")
            config = dict(app.CONFIG)
            config["download_root"] = str(root)
            collector = app.Collector(config, store)

            collector.scan_download_pipeline(False)

            stage = collector.pipeline_history["download"]["7.20"]
            self.assertEqual(stage["completed"], 1)
            self.assertIn("云手机 / 碳岩板 1条", stage["current"])

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

    def test_saved_download_batch_preserves_failures_and_exact_links(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "download_batch_state.json"
            state.write_text(json.dumps({
                "updatedAt": "2026-07-20T12:00:00+08:00",
                "context": {"date": "7.20", "project": "云手机", "material": "碳岩板"},
                "stats": {"total": "3", "success": "2", "failed": "1", "progress": "100%"},
                "lastBatchResult": {"total": 3, "succeeded": 2, "failed": 1},
                "tasks": [
                    {"url": "https://example.test/ok", "values": ["https://example.test/ok", "已完成", "已完成", "等待拼接配置", "100%", "", ""]},
                    {"url": "https://example.test/failed", "values": ["https://example.test/failed", "失败", "未开始", "处理失败", "失败", "", ""]},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            store = app.Store(root / "ops.db")
            config = dict(app.CONFIG)
            config["download_state_file"] = str(state)
            config["download_root"] = str(root / "missing-output")
            collector = app.Collector(config, store)

            collector.scan_download_pipeline(False)

            stage = collector.pipeline_history["download"]["7.20"]
            self.assertEqual(stage["failed"], 1)
            self.assertEqual(stage["state"], "failed")
            self.assertEqual(stage["failureItems"][0]["url"], "https://example.test/failed")

    def test_state_categories(self):
        self.assertEqual(app.task_category("Waiting"), "waiting")
        self.assertEqual(app.task_category("Exporting"), "running")
        self.assertEqual(app.task_category("Completed"), "completed")
        self.assertEqual(app.task_category("Failed"), "failed")

    def test_upload_pipeline_reads_real_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "upload_status.json"
            status.write_text(
                json.dumps(
                    {
                        "configured": True,
                        "authorized": True,
                        "updatedAt": "2026-07-20T12:00:00+08:00",
                        "account": "测试账号",
                        "chunkSizeMB": 32,
                        "tasks": {
                            "one": {
                                "date": "7.20",
                                "project": "云手机",
                                "material": "碳岩板",
                                "language": "英语",
                                "status": "uploaded",
                                "progress": 100,
                            },
                            "two": {
                                "date": "7.20",
                                "project": "实体机",
                                "material": "净白板",
                                "language": "俄语",
                                "status": "uploading",
                                "progress": 50,
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            config = dict(app.CONFIG)
            config["upload_status_file"] = str(status)
            store = app.Store(root / "ops.db")
            collector = app.Collector(config, store)
            collector.scan_upload_pipeline()
            stage = collector.pipeline_history["upload"]["7.20"]
            self.assertEqual("running", stage["state"])
            self.assertEqual(2, stage["total"])
            self.assertEqual(1, stage["completed"])
            self.assertEqual(75, stage["progress"])

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
