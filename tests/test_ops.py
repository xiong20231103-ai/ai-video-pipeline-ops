import json
import tempfile
import unittest
from pathlib import Path

import app


class OpsTests(unittest.TestCase):
    def test_upload_backlog_finds_completed_local_outputs_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = root / "records" / "7.22"
            records.mkdir(parents=True)
            final_ready = root / "ready.mp4"
            final_ready.write_bytes(b"video")
            final_uploaded = root / "uploaded.mp4"
            final_uploaded.write_bytes(b"video")
            manifest = {
                "tasks": [
                    {"taskId": "ready", "status": "completed", "finalOutputPath": str(final_ready)},
                    {"taskId": "uploaded", "status": "completed", "finalOutputPath": str(final_uploaded)},
                    {"taskId": "waiting", "status": "waiting_client", "finalOutputPath": str(root / "waiting.mp4")},
                    {"taskId": "missing", "status": "completed", "finalOutputPath": str(root / "missing.mp4")},
                ]
            }
            (records / "第四步到第五步.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            state = root / "upload_status.json"
            state.write_text(json.dumps({"tasks": {"uploaded": {"status": "uploaded"}}}), encoding="utf-8")

            audit = app.inspect_upload_backlog(root / "records", state)

            self.assertEqual([item["taskId"] for item in audit["candidates"]], ["ready"])
            self.assertEqual([item["taskId"] for item in audit["missing"]], ["missing"])
            self.assertEqual(audit["scanned"], 3)

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

    def test_project_download_statuses_keep_per_project_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            status = root / "project_status.json"
            status.write_text(json.dumps({
                "items": {
                    "cloud-1": {
                        "taskId": "cloud-1", "date": "7.20", "project": "云手机", "material": "碳岩板",
                        "expectedCount": 25, "completed": 20, "failed": 2, "missingCount": 5,
                        "status": "blocked_missing_links", "stateText": "待补链：还差 5 条",
                        "updatedAt": "2026-07-20T12:00:00+08:00",
                    }
                }
            }, ensure_ascii=False), encoding="utf-8")
            store = app.Store(root / "ops.db")
            config = dict(app.CONFIG)
            config["download_project_status_file"] = str(status)
            # This fixture verifies file fallback, not the live home receiver.
            config["receiver_status_url"] = ""
            collector = app.Collector(config, store)

            collector.scan_project_download_statuses()

            self.assertEqual(len(collector.project_download_statuses), 1)
            self.assertEqual(collector.project_download_statuses[0]["missingCount"], 5)
            self.assertEqual(collector.project_download_statuses[0]["project"], "云手机")

    def test_state_categories(self):
        self.assertEqual(app.task_category("Waiting"), "waiting")
        self.assertEqual(app.task_category("Exporting"), "running")
        self.assertEqual(app.task_category("PostProcessing"), "running")
        self.assertEqual(app.CAPCUT_STATE_TEXT["PostProcessing"], "FFmpeg替换第0帧")
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

    def test_upload_pipeline_exposes_cloud_cleanup_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "upload_status.json"
            status.write_text(json.dumps({
                "configured": True,
                "authorized": True,
                "updatedAt": "2026-07-21T12:00:00+08:00",
                "tasks": {
                    "cleaned": {
                        "date": "7.21", "status": "uploaded", "progress": 100,
                        "cleanup": {"state": "local_media_deleted"},
                    },
                    "pending": {
                        "date": "7.21", "status": "uploaded", "progress": 100,
                        "cleanup": {"state": "cloud_verified"},
                    },
                    "blocked": {
                        "date": "7.21", "status": "uploaded", "progress": 100,
                        "cleanup": {"state": "blocked_cloud_size_mismatch"},
                    },
                },
            }, ensure_ascii=False), encoding="utf-8")
            config = dict(app.CONFIG)
            config["upload_status_file"] = str(status)
            collector = app.Collector(config, app.Store(root / "ops.db"))

            collector.scan_upload_pipeline()

            stage = collector.pipeline_history["upload"]["7.21"]
            self.assertEqual(1, stage["localCleaned"])
            self.assertEqual(1, stage["cleanupPending"])
            self.assertEqual(1, stage["cleanupBlocked"])

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

    def test_capcut_remote_contract_is_preserved_and_test_history_is_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            store = app.Store(Path(folder) / "test.db")
            collector = app.Collector(app.CONFIG, store)
            collector.metadata = {
                "production": {
                    "date": "7.21", "project": "云手机", "material": "碳岩板",
                    "remotePipelineTaskId": "remote-cloud", "expectedTaskCount": 24,
                },
                "legacy-test": {"date": "7.21", "project": "实体机", "material": "净白板"},
            }
            production = collector.normalize_task({"taskId": "production", "state": "Waiting"}, Path("p.json"), 1.0)
            legacy = collector.normalize_task({"taskId": "legacy-test", "state": "Failed"}, Path("t.json"), 1.0)
            store.upsert_task(production)
            store.upsert_task(legacy)
            rows = store.tasks("7.21")
            formal = [row for row in rows if row["remote_pipeline_task_id"]]
            history = [row for row in rows if not row["remote_pipeline_task_id"]]
            self.assertEqual(1, len(formal))
            self.assertEqual(24, formal[0]["expected_task_count"])
            self.assertEqual(1, len(history))

    def test_archived_remote_batch_is_excluded_from_formal_production(self):
        previous = list(app.CONFIG.get("test_history_batch_ids", []))
        try:
            app.CONFIG["test_history_batch_ids"] = ["legacy-test-batch"]
            self.assertTrue(app.is_test_history_task({"batch_id": "legacy-test-batch"}))
            self.assertFalse(app.is_test_history_task({"batch_id": "production-batch"}))
        finally:
            app.CONFIG["test_history_batch_ids"] = previous

    def test_production_task_filter_uses_only_authoritative_handoff_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = root / "records"
            handoff.mkdir()
            previous_store = app.STORE
            previous_metadata = app.COLLECTOR.metadata
            previous_root = app.CONFIG.get("fourth_step_handoff_dir")
            try:
                app.STORE = app.Store(root / "test.db")
                app.CONFIG["fourth_step_handoff_dir"] = str(handoff)
                app.COLLECTOR.metadata = {
                    "formal": {
                        "_source": str(handoff / "7.21.json"),
                        "remotePipelineTaskId": "parent-1",
                    },
                    "old-test": {
                        "_source": str(root / "old-launch.json"),
                        "remotePipelineTaskId": "legacy-1",
                    },
                }
                for task_id, remote_id in (("formal", "parent-1"), ("old-test", "legacy-1")):
                    app.STORE.upsert_task({
                        "task_id": task_id, "batch_id": "batch", "date_label": "7.21",
                        "project": "云手机", "material": "碳岩板", "language": "英语",
                        "number": "001", "sequence": 1, "video_path": "", "audio_path": "",
                        "output_path": "", "state": "Waiting", "state_text": "等待",
                        "error": "", "source_file": "source.json", "source_timestamp": 1.0,
                        "remote_pipeline_task_id": remote_id, "expected_task_count": 24,
                    })

                rows = app.production_capcut_tasks("7.21")

                self.assertEqual(["formal"], [row["task_id"] for row in rows])
            finally:
                app.STORE = previous_store
                app.COLLECTOR.metadata = previous_metadata
                app.CONFIG["fourth_step_handoff_dir"] = previous_root

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
