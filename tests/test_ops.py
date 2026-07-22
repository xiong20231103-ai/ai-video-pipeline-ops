import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class OpsTests(unittest.TestCase):
    def test_receiver_v2_reconciliation_clears_ghost_and_archives_history(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "schemaVersion": 2,
                    "updatedAt": "2026-07-22T10:00:00+08:00",
                    "reconciledAt": "2026-07-22T10:00:00+08:00",
                    "reconciliationState": "healthy",
                    "projects": {},
                    "archivedProjects": {
                        "ghost": {
                            "taskId": "ghost", "batchId": "box-1", "date": "7.21",
                            "project": "实体机", "material": "净白板",
                            "status": "cancelled", "archiveReason": "operator_cancelled",
                        }
                    },
                }, ensure_ascii=False).encode("utf-8")

        with tempfile.TemporaryDirectory() as folder:
            collector = app.Collector(dict(app.CONFIG, receiver_status_url="http://receiver/snapshot"), app.Store(Path(folder) / "ops.db"))
            collector.project_download_statuses = [{"taskId": "ghost", "batchId": "box-1"}]
            with patch("app.urllib.request.urlopen", return_value=Response()):
                collector.scan_project_download_statuses()
            self.assertTrue(collector.receiver_control_ready)
            self.assertEqual([], collector.project_download_statuses)
            self.assertEqual("ghost", collector.archived_project_statuses[0]["taskId"])

    def test_receiver_v1_snapshot_is_not_trusted_for_controls(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "schemaVersion": 1,
                    "projects": {"ghost": {"taskId": "ghost", "batchId": "box-1"}},
                }).encode("utf-8")

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fallback = root / "project_status.json"
            fallback.write_text(json.dumps({"items": {}}), encoding="utf-8")
            collector = app.Collector(
                dict(app.CONFIG, receiver_status_url="http://receiver/snapshot", download_project_status_file=str(fallback)),
                app.Store(root / "ops.db"),
            )
            with patch("app.urllib.request.urlopen", return_value=Response()):
                collector.scan_project_download_statuses()
            self.assertFalse(collector.receiver_control_ready)
            self.assertEqual([], collector.project_download_statuses)
            self.assertEqual("接收器状态未对账", collector.receiver_error)

    def test_continue_command_persists_exact_target_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "workbench").mkdir()
            previous = app.CONFIG.get("workbench_dir")
            app.CONFIG["workbench_dir"] = str(root)
            target = {
                "batchId": "box-1", "taskId": "task-1", "productionDate": "7.21",
                "snapshotUpdatedAt": "2026-07-22T10:00:00+08:00",
            }
            try:
                first = app.request_workbench_continue(target)
                second = app.request_workbench_continue(target)
                saved = json.loads((root / "workbench" / "handoff" / "control" / app.CONTINUE_COMMAND_NAME).read_text(encoding="utf-8"))
                self.assertEqual(first["commandId"], second["commandId"])
                for key, value in target.items():
                    self.assertEqual(value, saved[key])
            finally:
                app.CONFIG["workbench_dir"] = previous

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

    def test_completed_download_gap_is_canonicalized_to_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            status = root / "project_status.json"
            status.write_text(json.dumps({
                "items": {
                    "cloud": {
                        "taskId": "cloud", "date": "7.21", "project": "云手机",
                        "material": "碳岩板", "expectedCount": 24, "completed": 24,
                        "failed": 1, "missingCount": 23, "status": "blocked_missing_links",
                        "stateText": "待补链：还差23条",
                    }
                }
            }, ensure_ascii=False), encoding="utf-8")
            config = dict(app.CONFIG)
            config["receiver_status_url"] = ""
            config["download_project_status_file"] = str(status)
            collector = app.Collector(config, app.Store(root / "ops.db"))

            collector.scan_project_download_statuses()

            item = collector.project_download_statuses[0]
            self.assertEqual("completed", item["status"])
            self.assertEqual(0, item["missingCount"])
            self.assertEqual(0, item["failed"])
            self.assertEqual(1, item["historicalFailed"])
            self.assertFalse(item["gapActive"])

    def test_task_box_is_dynamic_and_advances_after_full_capcut_validation(self):
        previous = app.COLLECTOR.project_download_statuses
        try:
            app.COLLECTOR.project_download_statuses = [
                {
                    "taskId": f"task-{sequence}", "batchId": "box-9",
                    "batchSequence": sequence, "batchSize": 9, "date": "7.21",
                    "project": "云手机" if sequence == 1 else f"项目{sequence}",
                    "material": "碳岩板", "expectedCount": 24 if sequence == 1 else 1,
                    "completed": 24 if sequence == 1 else 0, "failed": 0,
                    "gapActive": False, "notStarted": sequence > 1, "status": "completed" if sequence == 1 else "planned",
                }
                for sequence in range(1, 10)
            ]
            capcut = {
                "task-1": {
                    "expected": 24, "total": 24, "completed": 24, "valid": 24,
                    "failed": 0, "waiting": 0, "running": 0, "complete": True,
                    "updatedAt": "2026-07-21T23:59:00+08:00",
                }
            }
            with patch("app.remote_capcut_summaries", return_value=capcut):
                box = app.task_box_payloads()[0]

            self.assertEqual(9, box["projectCount"])
            self.assertEqual(1, box["completedProjects"])
            self.assertEqual("completed", box["items"][0]["status"])
            self.assertEqual(2, box["currentSequence"])
            self.assertEqual("task-2", box["current"]["taskId"])
        finally:
            app.COLLECTOR.project_download_statuses = previous

    def test_task_box_does_not_complete_at_23_of_24(self):
        previous = app.COLLECTOR.project_download_statuses
        try:
            app.COLLECTOR.project_download_statuses = [{
                "taskId": "cloud", "batchId": "box", "batchSequence": 1,
                "batchSize": 1, "date": "7.21", "project": "云手机",
                "material": "碳岩板", "expectedCount": 24, "completed": 24,
                "gapActive": False, "status": "completed",
            }]
            capcut = {
                "cloud": {
                    "expected": 24, "total": 23, "completed": 23, "valid": 23,
                    "failed": 0, "waiting": 0, "running": 0, "complete": False,
                    "updatedAt": "2026-07-21T23:59:00+08:00",
                }
            }
            with patch("app.remote_capcut_summaries", return_value=capcut):
                box = app.task_box_payloads()[0]

            self.assertEqual(0, box["completedProjects"])
            self.assertEqual("running", box["items"][0]["status"])
            self.assertEqual(23, box["items"][0]["finalCompleted"])
        finally:
            app.COLLECTOR.project_download_statuses = previous

    def test_dashboard_keeps_other_regions_when_receiver_api_fails(self):
        previous = app.COLLECTOR.project_download_statuses
        try:
            app.COLLECTOR.project_download_statuses = []
            with patch("app.receiver_json", side_effect=app.HTTPException(status_code=503, detail="receiver offline")):
                payload = app.dashboard_payload("7.21")

            self.assertEqual("receiver offline", payload["receiverQueue"]["error"])
            self.assertEqual("receiver offline", payload["templates"]["error"])
            self.assertIn("overview", payload)
            self.assertIn("pipeline", payload)
            self.assertIn("services", payload)
        finally:
            app.COLLECTOR.project_download_statuses = previous

    def test_state_categories(self):
        self.assertEqual(app.task_category("Waiting"), "waiting")
        self.assertEqual(app.task_category("Exporting"), "running")
        self.assertEqual(app.task_category("PostProcessing"), "running")
        self.assertEqual(app.CAPCUT_STATE_TEXT["PostProcessing"], "FFmpeg替换第0帧")
        self.assertEqual(app.task_category("Completed"), "completed")
        self.assertEqual(app.task_category("Failed"), "failed")

    def test_public_task_payload_removes_local_paths(self):
        item = app.public_task_item({
            "task_id": "task", "state": "Completed", "video_path": "E:/secret/source.mp4",
            "audio_path": "C:/private/audio.wav", "output_path": "E:/final/result.mp4",
            "source_file": "E:/handoff/task.json", "batch_id": "production",
        })
        serialized = json.dumps(item, ensure_ascii=False)
        self.assertNotIn("E:/", serialized)
        self.assertNotIn("C:/", serialized)
        self.assertEqual("source.mp4", item["video_name"])
        self.assertEqual("result.mp4", item["output_name"])

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
                        "cleanup": {"state": "local_final_deleted"},
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
