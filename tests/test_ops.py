import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class OpsTests(unittest.TestCase):
    def test_completion_receipt_is_immutable_and_survives_missing_local_rows(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.TASK_BOX_RECEIPT_DIR", Path(folder)):
            box = {
                "batchId": "batch-complete",
                "productionDate": "8.17",
                "projectCount": 1,
                "completedProjects": 1,
                "totalVideos": 5,
                "completedVideos": 5,
                "updatedAt": "2026-08-17T12:00:00+00:00",
                "items": [{
                    "taskId": "task-1", "canonicalTaskId": "task-1", "project": "实体机",
                    "material": "碳岩板", "expected": 5, "finalCompleted": 5, "status": "completed",
                }],
            }
            first = app.persist_task_box_receipt(box)
            self.assertEqual("completed_verified", first["productionStatus"])
            box["completedVideos"] = 0
            second = app.persist_task_box_receipt(box)
            self.assertEqual(first["receiptHash"], second["receiptHash"])
            self.assertEqual(5, second["completedVideoCount"])

    def test_summary_etag_ignores_scan_clock_but_tracks_state(self):
        first = {"updatedAt": "2026-08-19T10:00:00+08:00", "pipeline": {"state": "running", "completed": 3}}
        later = {"updatedAt": "2026-08-19T10:00:05+08:00", "pipeline": {"state": "running", "completed": 3}}
        changed = {"updatedAt": "2026-08-19T10:00:05+08:00", "pipeline": {"state": "running", "completed": 4}}
        self.assertEqual(app.dashboard_summary_etag(first), app.dashboard_summary_etag(later))
        self.assertNotEqual(app.dashboard_summary_etag(first), app.dashboard_summary_etag(changed))

    def test_authoritative_task_box_does_not_fall_back_to_history(self):
        historical = {"batchId": "old", "state": "completed", "items": [], "current": None}
        with patch.object(app.COLLECTOR, "active_workbench_task_id", return_value=""):
            self.assertIsNone(app.authoritative_active_task_box([historical]))

    def test_control_command_expires_when_workbench_does_not_claim(self):
        with tempfile.TemporaryDirectory() as folder, \
            patch("app.CONTROL_COMMAND_DIR", Path(folder) / "commands"), \
            patch("app.continue_command_file", return_value=Path(folder) / "mailbox.json"):
            command = {
                "commandId": "continue-test", "state": "persisted",
                "requestedAt": "2020-01-01T00:00:00+00:00",
                "persistedAt": "2020-01-01T00:00:00+00:00",
                "expiresAt": "2020-01-01T00:05:00+00:00",
            }
            app.write_control_command(command)
            result = app._sync_queued_command_from_mailbox()
            self.assertEqual("expired", result["state"])
            self.assertIn("未领取", result["message"])

    def test_executing_step12_command_expires_after_bridge_failure(self):
        with tempfile.TemporaryDirectory() as folder, \
            patch("app.CONTROL_COMMAND_DIR", Path(folder) / "commands"), \
            patch("app.continue_command_file", return_value=Path(folder) / "workbench" / "handoff" / "control" / "mailbox.json"), \
            patch("app.workbench_runtime_dir", return_value=Path(folder) / "workbench"):
            root = Path(folder) / "workbench" / "handoff"
            (root / "control").mkdir(parents=True)
            (root / "download").mkdir(parents=True)
            command = {
                "commandId": "continue-step12-stale",
                "state": "persisted",
                "requestedAt": "2026-08-20T23:15:16+08:00",
                "persistedAt": "2026-08-20T23:15:16+08:00",
                "expiresAt": "2026-08-20T23:20:16+08:00",
                "taskId": "task-step12",
            }
            mailbox = {
                **command,
                "state": "recovering",
                "startedAt": "2026-08-20T23:15:16+08:00",
                "lastHeartbeat": "2026-08-20T23:15:16+08:00",
            }
            app.write_control_command(command)
            app._write_json_atomic(app.continue_command_file(), mailbox)
            app._write_json_atomic(root / "download" / "download_batch_state.json", {
                "updatedAt": "2026-08-20T23:17:42+08:00",
                "context": {"request": {"taskId": "task-step12", "resumeInterrupted": True}},
                "downloadRuntimeFailure": {
                    "errorCode": "DOWNLOAD_BRIDGE_RUNTIME_FAILED",
                    "observedAt": "2026-08-20T23:15:22+08:00",
                },
                "stats": {"status": "后台任务运行中断 · 可安全继续"},
            })
            now_value = app.parse_time("2026-08-20T23:43:58+08:00")
            with patch("app.time.time", return_value=now_value):
                result = app._sync_queued_command_from_mailbox()
            self.assertEqual("expired", result["state"])
            self.assertTrue(result["stale"])
            self.assertIn("DOWNLOAD_BRIDGE_RUNTIME_FAILED", result["expiredReason"])
            saved_mailbox = json.loads(app.continue_command_file().read_text(encoding="utf-8"))
            self.assertEqual("expired", saved_mailbox["state"])

    def test_fresh_step12_session_keeps_executing_command_locked(self):
        with tempfile.TemporaryDirectory() as folder, \
            patch("app.CONTROL_COMMAND_DIR", Path(folder) / "commands"), \
            patch("app.continue_command_file", return_value=Path(folder) / "workbench" / "handoff" / "control" / "mailbox.json"), \
            patch("app.workbench_runtime_dir", return_value=Path(folder) / "workbench"):
            root = Path(folder) / "workbench" / "handoff"
            (root / "control").mkdir(parents=True)
            (root / "download").mkdir(parents=True)
            command = {
                "commandId": "continue-step12-live",
                "state": "persisted",
                "requestedAt": "2026-08-20T23:15:16+08:00",
                "persistedAt": "2026-08-20T23:15:16+08:00",
                "expiresAt": "2026-08-20T23:20:16+08:00",
                "taskId": "task-step12",
            }
            app.write_control_command(command)
            app._write_json_atomic(app.continue_command_file(), {
                **command,
                "state": "recovering",
                "startedAt": "2026-08-20T23:15:16+08:00",
                "lastHeartbeat": "2026-08-20T23:43:30+08:00",
            })
            app._write_json_atomic(root / "download" / "download_batch_state.json", {
                "updatedAt": "2026-08-20T23:43:45+08:00",
                "context": {"request": {"taskId": "task-step12", "resumeInterrupted": True}},
                "stats": {"status": "后台任务运行中"},
            })
            now_value = app.parse_time("2026-08-20T23:43:58+08:00")
            with patch("app.time.time", return_value=now_value):
                result = app._sync_queued_command_from_mailbox()
            self.assertEqual("executing", result["state"])

    def test_control_plane_rejects_non_loopback_target(self):
        with patch.dict(app.CONFIG, {"control_plane_url": "http://example.com:18790"}):
            with self.assertRaises(app.HTTPException) as error:
                app.control_plane_json("/api/quality/current")
        self.assertEqual(500, error.exception.status_code)
        self.assertIn("回环", str(error.exception.detail))

    def _make_capcut_draft(self, root: Path, draft_id: str, name: str, marker: str = "") -> Path:
        folder = root / name
        folder.mkdir(parents=True)
        timestamp = int((time.time() - 3600) * 1_000_000)
        (folder / "draft_meta_info.json").write_text(
            json.dumps({
                "draft_id": draft_id,
                "draft_name": name,
                "tm_draft_create": timestamp,
                "tm_draft_modified": timestamp,
            }),
            encoding="utf-8",
        )
        (folder / "draft_content.json").write_text(
            json.dumps({"materials": {"videos": [{"path": f"{marker or 'manual'}-source.mp4"}]}}),
            encoding="utf-8",
        )
        return folder

    def _write_capcut_index(self, root: Path, items: list[tuple[str, str]]) -> None:
        (root / "root_meta_info.json").write_text(
            json.dumps({
                "all_draft_store": [
                    {"draft_id": draft_id, "draft_name": name, "draft_fold_path": str(root / name)}
                    for draft_id, name in items
                ],
                "draft_ids": len(items),
                "root_path": str(root),
            }),
            encoding="utf-8",
        )

    def test_capcut_draft_inventory_classifies_and_hides_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._make_capcut_draft(root, "formal-id", "formal", "remote-inbox-20260726")
            self._make_capcut_draft(root, "lab-id", "lab", "lab-20260726")
            self._make_capcut_draft(root, "manual-id", "manual")
            self._write_capcut_index(root, [
                ("formal-id", "formal"), ("lab-id", "lab"), ("manual-id", "manual"),
            ])
            with patch("app._capcut_draft_processes", return_value=[]):
                payload = app.capcut_draft_inventory_public(root)
            self.assertEqual(3, payload["counts"]["total"])
            self.assertEqual({"formal", "lab", "manual_or_unknown"}, {item["category"] for item in payload["items"]})
            self.assertFalse(any("_path" in item for item in payload["items"]))
            self.assertNotIn(str(root), json.dumps(payload, ensure_ascii=False))

    def test_capcut_draft_preview_blocks_while_capcut_is_running(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._make_capcut_draft(root, "formal-id", "formal", "remote-inbox-20260726")
            self._write_capcut_index(root, [("formal-id", "formal")])
            with patch("app._capcut_draft_processes", return_value=[{"pid": 123, "name": "CapCut.exe"}]):
                preview = app.preview_capcut_draft_cleanup(["formal-id"], root=root)
            self.assertEqual(0, preview["deletableCount"])
            self.assertEqual(1, preview["blockedCount"])
            self.assertIn("正在运行", preview["blocked"][0]["reason"])

    def test_capcut_draft_cleanup_removes_exact_index_entry_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = self._make_capcut_draft(root, "first-id", "first", "remote-inbox-20260726")
            second = self._make_capcut_draft(root, "second-id", "second", "remote-inbox-20260726")
            self._write_capcut_index(root, [("first-id", "first"), ("second-id", "second")])
            preview = app.preview_capcut_draft_cleanup(["first-id"], root=root)
            recycle_target = root / ".recycled-first"

            def fake_recycle(path: Path) -> None:
                path.rename(recycle_target)

            with (
                patch("app._capcut_draft_processes", return_value=[]),
                patch("app._recycle_directory", side_effect=fake_recycle),
                patch("app.CAPCUT_DRAFT_CLEANUP_BACKUP_DIR", root / ".backups"),
                patch("app.CAPCUT_DRAFT_CLEANUP_STATUS_PATH", root / ".status.json"),
                patch("app.save_control_action"),
            ):
                result = app.execute_capcut_draft_cleanup(
                    ["first-id"], preview["snapshotToken"], root=root
                )
            index = json.loads((root / "root_meta_info.json").read_text(encoding="utf-8"))
            self.assertEqual(1, result["removedCount"])
            self.assertFalse(first.exists())
            self.assertTrue(second.exists())
            self.assertEqual(["second-id"], [item["draft_id"] for item in index["all_draft_store"]])
            with self.assertRaises(app.HTTPException):
                app.preview_capcut_draft_cleanup(["first-id"], root=root)

    def test_capcut_draft_cleanup_rejects_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self._make_capcut_draft(root, "formal-id", "formal", "remote-inbox-20260726")
            self._write_capcut_index(root, [("formal-id", "formal")])
            preview = app.preview_capcut_draft_cleanup(["formal-id"], root=root)
            self._write_capcut_index(root, [("formal-id", "formal"), ("other-id", "other")])
            with patch("app._capcut_draft_processes", return_value=[]):
                with self.assertRaises(app.HTTPException) as context:
                    app.execute_capcut_draft_cleanup(
                        ["formal-id"], preview["snapshotToken"], root=root
                    )
            self.assertEqual(409, context.exception.status_code)

    def test_audio_inventory_protects_active_task_and_hides_absolute_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "voice.mp3"
            audio.write_bytes(b"audio")
            references = {
                app._path_key(audio): [{
                    "taskId": "task-1", "project": "云手机", "material": "碳岩板",
                    "language": "英语", "state": "Waiting", "phase": "等待 CapCut",
                    "active": True, "_path": str(audio),
                }]
            }
            with patch("app._audio_producer_processes", return_value=[]):
                inventory = app._audio_inventory(roots=[root], references=references)
            self.assertEqual(1, inventory["counts"]["protected"])
            self.assertEqual("云手机", inventory["items"][0]["project"])
            self.assertIn("任务正在使用", inventory["items"][0]["protectedReason"])
            public = {
                key: value for key, value in inventory["items"][0].items()
                if not key.startswith("_")
            }
            self.assertNotIn(str(root), json.dumps(public, ensure_ascii=False))

    def test_audio_cleanup_direct_call_cannot_bypass_active_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "voice.wav"
            audio.write_bytes(b"audio")
            references = {
                app._path_key(audio): [{
                    "taskId": "task-1", "project": "SPC墙板", "material": "晶岩墙板",
                    "language": "德语", "state": "waiting_client", "phase": "等待恢复",
                    "active": True, "_path": str(audio),
                }]
            }
            with (
                patch("app._audio_reference_inventory", return_value=references),
                patch("app._audio_producer_processes", return_value=[]),
                patch("app.AUDIO_CLEANUP_STATUS_PATH", root / "status.json"),
                patch("app.AUDIO_CLEANUP_BACKUP_DIR", root / "records"),
                patch("app.save_control_action"),
            ):
                inventory = app._audio_inventory(roots=[root], references=references)
                with patch("app._registered_audio_roots", return_value=[root]):
                    with self.assertRaises(app.HTTPException) as context:
                        app.execute_audio_cleanup(
                            [inventory["items"][0]["audioId"]],
                            inventory["snapshotToken"],
                        )
            self.assertEqual(409, context.exception.status_code)
            self.assertTrue(audio.exists())
            self.assertIn("禁止删除", str(context.exception.detail))

    def test_audio_cleanup_rechecks_snapshot_and_recycles_exact_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "completed.mp3"
            audio.write_bytes(b"completed-audio")
            references = {
                app._path_key(audio): [{
                    "taskId": "task-2", "project": "实体机", "material": "净白板",
                    "language": "英语", "state": "Completed", "phase": "已完成",
                    "active": False, "_path": str(audio),
                }]
            }
            recycled = root / "recycled.completed.mp3"

            def fake_recycle(path: Path) -> None:
                path.rename(recycled)

            with (
                patch("app._audio_reference_inventory", return_value=references),
                patch("app._registered_audio_roots", return_value=[root]),
                patch("app._audio_producer_processes", return_value=[]),
                patch("app._recycle_directory", side_effect=fake_recycle),
                patch("app.AUDIO_CLEANUP_STATUS_PATH", root / "status.json"),
                patch("app.AUDIO_CLEANUP_BACKUP_DIR", root / "records"),
                patch("app.save_control_action"),
            ):
                preview = app.preview_audio_cleanup([
                    app._audio_inventory(roots=[root], references=references)["items"][0]["audioId"]
                ])
                result = app.execute_audio_cleanup(
                    [preview["deletable"][0]["audioId"]],
                    preview["snapshotToken"],
                )
            self.assertEqual(1, result["removedCount"])
            self.assertFalse(audio.exists())

    def _production_fixture(self, root: Path) -> tuple[dict, dict[str, Path]]:
        paths = {
            "download": root / "downloads" / "removed.mp4",
            "stitch": root / "stitch" / "stitched.mp4",
            "temporary": root / "capcut-temp" / "temporary.mp4",
            "final": root / "final" / "final.mp4",
            "prepared": root / "prepared-samples" / "prepared.mp4",
            "test": root / "capcut-tests" / "test.mp4",
        }
        for index, path in enumerate(paths.values(), start=1):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bytes([index]) * (100 + index))
        workbench = root / "workbench"
        checkpoint_root = workbench / "handoff" / "download" / "checkpoints"
        checkpoint_root.mkdir(parents=True)
        (checkpoint_root / "parent-task.json").write_text(json.dumps({
            "taskId": "parent-task",
            "items": {
                "video-1": {
                    "status": "completed",
                    "outputPath": str(paths["download"]),
                }
            },
        }), encoding="utf-8")
        upload = {
            "taskId": "capcut-task-1",
            "canonicalTaskId": "parent-task",
            "productionDate": "7.26",
            "project": "SPC地板",
            "material": "塑木地板",
            "language": "英语",
            "status": "uploaded",
            "sourceVideoPath": str(paths["stitch"]),
            "temporaryOutputPath": str(paths["temporary"]),
            "localPath": str(paths["final"]),
            "preparedSamplePath": str(paths["prepared"]),
            "fsId": "cloud-file-1",
            "cloudSize": 987,
            "cleanup": {
                "cloudVerifiedAt": "2026-07-26T12:00:00+08:00",
                "cloudVerifiedSize": 987,
            },
        }
        return upload, paths

    def test_production_file_inventory_uses_exact_registered_paths_and_safe_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            upload, paths = self._production_fixture(root)
            project = {
                "pipelineStatus": "completed",
                "productionDate": "7.26",
                "project": "SPC地板",
                "material": "塑木地板",
            }
            config = {
                "download_root": str(paths["download"].parent),
                "generation_output_root": str(paths["stitch"].parent),
                "prepared_sample_roots": [str(paths["prepared"].parent)],
                "capcut_test_roots": [str(paths["test"].parent)],
                "baidu_sync_roots": [],
            }
            with (
                patch.dict(app.CONFIG, config),
                patch("app._workbench_root", return_value=root / "workbench"),
                patch("app._canonical_task_aliases", return_value={}),
                patch("app._project_status_records", return_value={"parent-task": project}),
                patch("app._upload_task_records", return_value=[upload]),
                patch("app._production_active_projects", return_value=(set(), {})),
                patch("app._isolated_runtime_processes", return_value=[]),
            ):
                inventory = app._production_file_inventory()
                public = app.production_file_inventory_public()

            self.assertEqual(6, inventory["counts"]["total"])
            self.assertEqual(6, inventory["counts"]["deletable"])
            self.assertEqual(5, inventory["counts"]["defaultSelected"])
            self.assertEqual(
                {
                    "subtitle_output", "stitch_output", "capcut_temporary",
                    "local_final", "prepared_sample", "capcut_test",
                },
                {item["category"] for item in inventory["items"]},
            )
            test_item = next(item for item in inventory["items"] if item["category"] == "capcut_test")
            self.assertFalse(test_item["defaultSelected"])
            self.assertNotIn(str(root), json.dumps(public, ensure_ascii=False))

    def test_production_file_inventory_protects_active_or_unverified_tasks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            upload, paths = self._production_fixture(root)
            upload["cleanup"] = {}
            project = {
                "pipelineStatus": "capcut_running",
                "productionDate": "7.26",
                "project": "SPC地板",
                "material": "塑木地板",
            }
            config = {
                "download_root": str(paths["download"].parent),
                "generation_output_root": str(paths["stitch"].parent),
                "prepared_sample_roots": [str(paths["prepared"].parent)],
                "capcut_test_roots": [str(paths["test"].parent)],
                "baidu_sync_roots": [],
            }
            with (
                patch.dict(app.CONFIG, config),
                patch("app._workbench_root", return_value=root / "workbench"),
                patch("app._canonical_task_aliases", return_value={}),
                patch("app._project_status_records", return_value={"parent-task": project}),
                patch("app._upload_task_records", return_value=[upload]),
                patch(
                    "app._production_active_projects",
                    return_value=({"parent-task"}, {"parent-task": "CapCut 正在处理"}),
                ),
                patch("app._isolated_runtime_processes", return_value=[]),
            ):
                inventory = app._production_file_inventory()

            production_items = [item for item in inventory["items"] if item["category"] != "capcut_test"]
            self.assertTrue(all(item["protected"] for item in production_items))
            self.assertTrue(all(not item["defaultSelected"] for item in production_items))
            self.assertTrue(any("活动" in item["protectedReason"] or "运行" in item["protectedReason"] for item in production_items))

    def test_production_file_cleanup_recycles_exact_file_and_rejects_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "registered" / "safe.mp4"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"safe-production-file")
            item = app._production_file_identity(
                path=target,
                category="capcut_test",
                root=target.parent,
            )
            inventory = {
                "available": True,
                "snapshotToken": app._production_snapshot([item]),
                "items": [item],
            }
            recycled = root / "recycled.mp4"

            def fake_recycle(path: Path) -> None:
                path.rename(recycled)

            with (
                patch("app._production_file_inventory", return_value=inventory),
                patch("app._recycle_directory", side_effect=fake_recycle),
                patch("app.PRODUCTION_FILE_CLEANUP_STATUS_PATH", root / "status.json"),
                patch("app.PRODUCTION_FILE_CLEANUP_BACKUP_DIR", root / "records"),
                patch("app.PRODUCTION_FILE_CLEANUP_INDEX_PATH", root / "index.json"),
                patch("app.save_control_action"),
            ):
                with self.assertRaises(app.HTTPException) as context:
                    app.execute_production_file_cleanup([item["fileId"]], "stale-token")
                self.assertEqual(409, context.exception.status_code)
                self.assertTrue(target.exists())
                result = app.execute_production_file_cleanup(
                    [item["fileId"]], inventory["snapshotToken"]
                )

            self.assertEqual(1, result["removedCount"])
            self.assertFalse(target.exists())
            self.assertTrue(recycled.exists())
            self.assertTrue(recycled.exists())
            self.assertEqual("recycled", result["removed"][0]["state"])

    def test_metadata_scan_ignores_handoff_backup_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = root / "交接记录" / "7.22"
            handoff.mkdir(parents=True)
            live = handoff / "第四步到第五步.json"
            backup = handoff / "第四步到第五步.before-repair.json"
            live.write_text(json.dumps({"date": "7.22", "tasks": [{"taskId": "live"}]}), encoding="utf-8")
            backup.write_text(json.dumps({"date": "7.22", "tasks": [{"taskId": "backup"}]}), encoding="utf-8")
            collector = app.Collector(
                dict(app.CONFIG, capcut_handoff_dir=str(root / "capcut"), fourth_step_handoff_dir=str(root / "交接记录")),
                app.Store(root / "ops.db"),
            )
            collector.scan_metadata()
            self.assertEqual({"live"}, set(collector.metadata))

    def test_current_ledger_requeue_overrides_old_active_capcut_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            capcut = root / "capcut"
            ledger = root / "ledger"
            capcut.mkdir()
            ledger.mkdir()
            (capcut / "old-attempt.json").write_text(
                json.dumps({"tasks": [{"taskId": "wall-ru", "activeManifestId": "old", "status": "running"}]}),
                encoding="utf-8",
            )
            (ledger / "current.json").write_text(
                json.dumps({"tasks": [{"taskId": "wall-ru", "status": "waiting_capcut"}]}),
                encoding="utf-8",
            )
            collector = app.Collector(
                dict(app.CONFIG, capcut_handoff_dir=str(capcut), fourth_step_handoff_dir=str(ledger)),
                app.Store(root / "ops.db"),
            )
            collector.scan_metadata()
            self.assertEqual("waiting_capcut", collector.metadata["wall-ru"]["status"])
            self.assertEqual((ledger / "current.json"), Path(collector.metadata["wall-ru"]["_source"]))

    def test_explicit_contract_reset_overrides_newer_abandoned_status(self):
        with tempfile.TemporaryDirectory() as folder:
            store = app.Store(Path(folder) / "ops.db")
            base = {
                "task_id": "wall-ru", "batch_id": "batch", "date_label": "7.22",
                "project": "SPC墙板", "material": "晶岩墙板", "language": "俄语",
                "number": "001", "sequence": 1, "video_path": "", "audio_path": "",
                "output_path": "", "state_text": "", "error": "",
                "source_file": "old.status.json", "remote_pipeline_task_id": "parent",
                "expected_task_count": 4,
            }
            store.upsert_task({**base, "state": "Completed", "state_text": "剪辑完成", "source_timestamp": 200.0})
            store.upsert_task({
                **base,
                "state": "waiting_capcut",
                "state_text": "等待第五步",
                "source_file": "current-ledger.json",
                "source_timestamp": 100.0,
                "_force_contract_reset": True,
            })
            self.assertEqual("waiting_capcut", store.tasks()[0]["state"])

    def test_store_clear_all_removes_only_dashboard_records(self):
        with tempfile.TemporaryDirectory() as folder:
            store = app.Store(Path(folder) / "ops.db")
            store.event("Test", "INFO", "old event")
            store.save_heartbeat("test", {"ok": True})
            store.source_result(Path(folder) / "source.json", False, "missing", "missing")

            store.clear_all()

            self.assertEqual([], store.events(10))
            self.assertIsNone(store.last_heartbeat())
            self.assertEqual([], store.source_errors())

    def test_reset_generation_ignores_old_media_but_accepts_new_media(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old_video = root / "old" / "old.mp4"
            old_video.parent.mkdir()
            old_video.write_bytes(b"old")
            old_epoch = time.time() - 60
            os.utime(old_video, (old_epoch, old_epoch))
            store = app.Store(root / "ops.db")
            collector = app.Collector(dict(app.CONFIG, download_root=str(root)), store)

            reset_at = app.datetime.fromtimestamp(time.time()).astimezone().isoformat(timespec="seconds")
            collector.reset_runtime(reset_at)
            collector.scan_download_pipeline(False)
            self.assertEqual({}, collector.pipeline_history["download"])

            new_video = root / "new" / "new.mp4"
            new_video.parent.mkdir()
            new_video.write_bytes(b"new")
            collector.last_download_scan_epoch = 0
            collector.scan_download_pipeline(False)
            self.assertTrue(collector.pipeline_history["download"])

    def test_receiver_v2_reconciliation_clears_ghost_and_archives_history(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "schemaVersion": 3,
                    "updatedAt": "2026-07-22T10:00:00+08:00",
                    "reconciledAt": "2026-07-22T10:00:00+08:00",
                    "reconciliationState": "healthy",
                    "projects": [],
                    "archivedProjects": [
                        {
                            "taskId": "ghost", "batchId": "box-1", "date": "7.21",
                            "project": "实体机", "material": "净白板",
                            "status": "cancelled", "archiveReason": "operator_cancelled",
                        }
                    ],
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
                with patch(
                    "app.ensure_receiver_workbench_running",
                    side_effect=[
                        {"started": True, "alreadyRunning": False, "pid": 4321},
                        {"started": False, "alreadyRunning": True, "pid": 9876},
                    ],
                ) as ensure_running:
                    first = app.request_workbench_continue(target)
                    second = app.request_workbench_continue(target)
                saved = json.loads((root / "workbench" / "handoff" / "control" / app.CONTINUE_COMMAND_NAME).read_text(encoding="utf-8"))
                self.assertEqual(first["commandId"], second["commandId"])
                self.assertTrue(first["workbenchStarted"])
                self.assertTrue(second["workbenchAlreadyRunning"])
                self.assertEqual(2, ensure_running.call_count)
                self.assertTrue(saved["workbenchAlreadyRunning"])
                self.assertEqual(9876, saved["workbenchPid"])
                for key, value in target.items():
                    self.assertEqual(value, saved[key])
            finally:
                app.CONFIG["workbench_dir"] = previous

    def test_stale_accepted_continue_command_is_replaced_for_same_task(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workbench = root / "workbench"
            control = workbench / "handoff" / "control"
            runtime = workbench / "handoff" / "download"
            control.mkdir(parents=True)
            runtime.mkdir(parents=True)
            target = {
                "batchId": "box-accepted", "taskId": "task-accepted", "productionDate": "7.28",
                "snapshotUpdatedAt": "2026-07-28T21:00:00+08:00",
            }
            old = {
                **target,
                "commandId": "continue-old",
                "state": "accepted",
                "requestedAt": "2026-07-28T20:00:00+08:00",
                "startedAt": "2026-07-28T20:00:01+08:00",
            }
            (control / app.CONTINUE_COMMAND_NAME).write_text(json.dumps(old), encoding="utf-8")
            (runtime / "project_status.json").write_text(json.dumps({
                "items": {"task-accepted": {"pipelineStatus": "voice_completed"}},
            }), encoding="utf-8")
            previous = app.CONFIG.get("workbench_dir")
            app.CONFIG["workbench_dir"] = str(root)
            try:
                with patch("app.time.time", return_value=1785247200), patch(
                    "app.ensure_receiver_workbench_running",
                    return_value={"started": False, "alreadyRunning": True, "pid": 2468},
                ):
                    result = app.request_workbench_continue(target)
                saved = json.loads((control / app.CONTINUE_COMMAND_NAME).read_text(encoding="utf-8"))
                self.assertNotEqual("continue-old", result["commandId"])
                self.assertEqual("requested", saved["state"])
                self.assertEqual("task-accepted", saved["taskId"])
            finally:
                app.CONFIG["workbench_dir"] = previous

    def test_stale_capcut_recovering_command_is_replaced_when_client_is_gone(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workbench = root / "workbench"
            control = workbench / "handoff" / "control"
            runtime = workbench / "handoff" / "download"
            control.mkdir(parents=True)
            runtime.mkdir(parents=True)
            target = {
                "batchId": "box-capcut", "taskId": "task-capcut", "productionDate": "7.28",
                "manifestId": "manifest-new", "attemptId": "attempt-new",
                "snapshotUpdatedAt": "2026-07-29T10:10:00+08:00",
            }
            old = {
                **target,
                "commandId": "continue-stale-capcut",
                "state": "recovering",
                "requestedAt": "2026-07-29T09:50:00+08:00",
                "startedAt": "2026-07-29T09:50:01+08:00",
                "lastHeartbeat": "2026-07-29T10:06:00+08:00",
            }
            (control / app.CONTINUE_COMMAND_NAME).write_text(json.dumps(old), encoding="utf-8")
            (runtime / "project_status.json").write_text(json.dumps({
                "items": {"task-capcut": {
                    "pipelineStatus": "blocked_capcut",
                    "currentPhase": "waiting_client",
                    "capcut": {"running": 0},
                }},
            }), encoding="utf-8")
            previous = app.CONFIG.get("workbench_dir")
            app.CONFIG["workbench_dir"] = str(root)
            try:
                current_time = app.parse_time("2026-07-29T10:10:00+08:00")
                with patch("app.time.time", return_value=current_time), patch(
                    "app.ensure_receiver_workbench_running",
                    return_value={"started": False, "alreadyRunning": True, "pid": 2468},
                ):
                    result = app.request_workbench_continue(target)
                saved = json.loads((control / app.CONTINUE_COMMAND_NAME).read_text(encoding="utf-8"))
                self.assertNotEqual("continue-stale-capcut", result["commandId"])
                self.assertEqual("requested", saved["state"])
                self.assertEqual("manifest-new", saved["manifestId"])
                self.assertEqual("attempt-new", saved["attemptId"])
            finally:
                app.CONFIG["workbench_dir"] = previous

    def test_continue_retires_a_recent_command_for_a_different_project(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            workbench = root / "workbench"
            control = workbench / "handoff" / "control"
            runtime = workbench / "handoff" / "download"
            control.mkdir(parents=True)
            runtime.mkdir(parents=True)
            old = {
                "commandId": "continue-old-project",
                "state": "recovering",
                "requestedAt": "2026-08-03T18:00:00+08:00",
                "lastHeartbeat": "2026-08-03T18:00:05+08:00",
                "batchId": "batch-old", "taskId": "task-old", "productionDate": "8.2",
            }
            target = {
                "batchId": "batch-new", "taskId": "task-new", "productionDate": "8.3",
                "snapshotUpdatedAt": "2026-08-03T18:00:06+08:00",
            }
            (control / app.CONTINUE_COMMAND_NAME).write_text(json.dumps(old), encoding="utf-8")
            (runtime / "project_status.json").write_text(json.dumps({"items": {}}), encoding="utf-8")
            previous = app.CONFIG.get("workbench_dir")
            app.CONFIG["workbench_dir"] = str(root)
            try:
                with patch("app.ensure_receiver_workbench_running", return_value={"started": False, "alreadyRunning": True, "pid": 2468}):
                    result = app.request_workbench_continue(target)
                saved = json.loads((control / app.CONTINUE_COMMAND_NAME).read_text(encoding="utf-8"))
                archived = list((control / "history").glob("continue-old-project-*.json"))
                self.assertNotEqual("continue-old-project", result["commandId"])
                self.assertEqual("requested", saved["state"])
                self.assertEqual("task-new", saved["taskId"])
                self.assertEqual(1, len(archived))
                self.assertEqual("安全继续目标已变化，旧命令已归档", json.loads(archived[0].read_text(encoding="utf-8"))["archiveReason"])
            finally:
                app.CONFIG["workbench_dir"] = previous

    def test_live_capcut_recovery_command_is_not_expired(self):
        command = {
            "state": "recovering",
            "lastHeartbeat": "2026-07-29T10:06:00+08:00",
        }
        runtime_item = {
            "pipelineStatus": "blocked_capcut",
            "currentPhase": "capcut_running",
            "capcut": {"running": 1},
        }
        self.assertFalse(app._capcut_recovery_command_is_stale(command, runtime_item))

    def test_recoverable_draft_waiting_expires_command_immediately(self):
        command = {
            "state": "recovering",
            "lastHeartbeat": "2026-07-29T10:09:59+08:00",
        }
        runtime_item = {
            "pipelineStatus": "blocked_capcut",
            "currentPhase": "waiting_client",
            "failureFingerprint": "draft_card_location_failed",
            "capcut": {"running": 0},
        }
        self.assertTrue(app._capcut_recovery_command_is_stale(command, runtime_item))

    def test_recoverable_draft_waiting_requires_structured_reason(self):
        self.assertTrue(app._is_recoverable_draft_waiting({
            "state": "Waiting",
            "failure_fingerprint": "draft_editor_binding_failed",
        }))
        self.assertFalse(app._is_recoverable_draft_waiting({
            "state": "Waiting",
            "error": "ordinary queued task",
        }))
        self.assertTrue(app._is_recoverable_draft_waiting({
            "state": "Failed",
            "error": "CapCut 主页未能动态识别并安全定位 root_meta_info 首张目标草稿；未执行点击",
        }))

    def test_continue_keeps_command_when_receiver_cannot_launch_workbench(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "workbench").mkdir()
            previous = app.CONFIG.get("workbench_dir")
            app.CONFIG["workbench_dir"] = str(root)
            target = {
                "batchId": "box-2", "taskId": "task-2", "productionDate": "7.22",
                "snapshotUpdatedAt": "2026-07-22T11:00:00+08:00",
            }
            try:
                with patch(
                    "app.ensure_receiver_workbench_running",
                    side_effect=app.HTTPException(status_code=503, detail="receiver offline"),
                ):
                    result = app.request_workbench_continue(target)
                command_file = root / "workbench" / "handoff" / "control" / app.CONTINUE_COMMAND_NAME
                self.assertTrue(command_file.is_file())
                self.assertTrue(result["accepted"])
                self.assertFalse(result["workbenchStarted"])
                self.assertEqual("receiver offline", result["workbenchLaunchError"])
                saved = json.loads(command_file.read_text(encoding="utf-8"))
                self.assertEqual("receiver offline", saved["workbenchLaunchError"])
            finally:
                app.CONFIG["workbench_dir"] = previous

    def test_continue_keeps_structured_receiver_startup_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "workbench").mkdir()
            previous = app.CONFIG.get("workbench_dir")
            app.CONFIG["workbench_dir"] = str(root)
            target = {
                "batchId": "box-startup", "taskId": "task-startup", "productionDate": "7.22",
                "snapshotUpdatedAt": "2026-07-23T10:00:00+08:00",
            }
            detail = {"code": "ready_timeout", "message": "工作台在 20 秒内未写入就绪心跳。", "logFile": "C:/temp/log"}
            try:
                with patch("app.ensure_receiver_workbench_running", side_effect=app.HTTPException(status_code=503, detail=detail)):
                    result = app.request_workbench_continue(target)
                self.assertEqual("ready_timeout", result["workbenchLaunchCode"])
                self.assertEqual(detail["message"], result["workbenchLaunchError"])
                self.assertEqual("C:/temp/log", result["workbenchLaunchLog"])
                command = app.read_json_object(root / "workbench" / "handoff" / "control" / app.CONTINUE_COMMAND_NAME)
                self.assertEqual("requested", command["state"])
                self.assertEqual("ready_timeout", command["workbenchLaunchCode"])
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

    def test_historical_cloud_verification_request_targets_only_unverified_legacy_uploads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            upload_root = root / "handoff" / "upload"
            upload_root.mkdir(parents=True)
            upload_state = upload_root / "upload_status.json"
            upload_state.write_text(
                json.dumps(
                    {
                        "tasks": {
                            "legacy-pending": {
                                "status": "uploaded",
                                "cleanupPolicyVersion": 0,
                                "cleanup": {"state": "legacy_retained"},
                            },
                            "legacy-verified": {
                                "status": "uploaded",
                                "cleanupPolicyVersion": 0,
                                "cleanup": {"cloudVerifiedAt": "now"},
                            },
                            "current-policy": {
                                "status": "uploaded",
                                "cleanupPolicyVersion": 2,
                                "cleanup": {},
                            },
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with (
                patch("app.workbench_runtime_dir", return_value=root),
                patch.dict(app.CONFIG, {"upload_status_file": str(upload_state)}),
                patch(
                    "app._ensure_upload_service_running",
                    return_value={"running": True, "started": False, "pid": 123},
                ),
                patch("app.save_control_action"),
            ):
                result = app.request_historical_cloud_verification()

            request = json.loads(
                (upload_root / "historical_cloud_verify_request.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("requested", result["state"])
            self.assertEqual(1, result["eligible"])
            self.assertEqual(["legacy-pending"], request["taskIds"])

    def test_historical_cloud_verification_status_hides_local_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            status_path = (
                root
                / "handoff"
                / "upload"
                / "historical_cloud_verify_status.json"
            )
            status_path.parent.mkdir(parents=True)
            status_path.write_text(
                json.dumps(
                    {
                        "commandId": "verify-one",
                        "state": "partial",
                        "message": r"失败文件 E:\secret\final.mp4",
                        "total": 2,
                        "processed": 2,
                        "verified": 1,
                        "failed": 1,
                        "failures": [{"taskId": "task-one", "message": r"E:\secret"}],
                    }
                ),
                encoding="utf-8",
            )
            with patch("app.workbench_runtime_dir", return_value=root):
                result = app.historical_cloud_verification_status()

            serialized = json.dumps(result, ensure_ascii=False)
            self.assertEqual("partial", result["state"])
            self.assertNotIn(r"E:\secret", serialized)
            self.assertNotIn("failures", result)

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

    def test_task_boxes_are_ordered_by_production_date_with_open_boxes_first(self):
        # Reported 2026-10-08: the dropdown read 8.3, 8.2, 8.25 … 7.28, 10.7,
        # 7.22, 10.6 because it followed the latest update time.
        def box(batch_id, date, state="completed", updated="2026-10-07T21:22:00+08:00"):
            return {"batchId": batch_id, "productionDate": date, "state": state, "updatedAt": updated}

        boxes = [
            box("formal-batch-1785728400000-aaaaaaaaaa", "8.3"),               # 2026-08-03
            box("dispatch-20260802-101000-abcdef", "8.2"),
            box("formal-batch-1787641200000-bbbbbbbbbb", "8.25", updated="2026-08-25T10:00:00+08:00"),
            box("formal-batch-1791361570062-cccccccccc", "10.7", updated="2026-10-08T10:15:00+08:00"),
            box("formal-batch-1791250637841-dddddddddd", "10.6", state="blocked",
                updated="2026-10-07T13:00:00+08:00"),
            box("formal-batch-1798646400000-eeeeeeeeee", "1.2"),               # created 2026-12-31
            box("formal-batch-1791370000000-ffffffffff", "10.7", updated="2026-10-07T12:00:00+08:00"),
        ]
        ordered = [item["batchId"][-10:] for item in sorted(boxes, key=app.task_box_sort_key, reverse=True)]
        self.assertEqual(
            ["dddddddddd", "eeeeeeeeee", "ffffffffff", "cccccccccc", "bbbbbbbbbb", "aaaaaaaaaa", "000-abcdef"],
            ordered,
        )

    def test_task_box_payloads_use_the_production_order(self):
        previous = app.COLLECTOR.project_download_statuses
        try:
            app.COLLECTOR.project_download_statuses = [
                {"taskId": f"{batch}-01", "batchId": batch, "batchSequence": 1, "batchSize": 1,
                 "date": date, "project": "云手机", "material": "碳岩板", "expectedCount": 1,
                 "completed": 0, "status": "planned", "notStarted": True, "updatedAt": updated}
                for batch, date, updated in (
                    ("formal-batch-1785728400000-aaaaaaaaaa", "8.3", "2026-10-07T21:22:00+08:00"),
                    ("formal-batch-1791361570062-cccccccccc", "10.7", "2026-10-07T16:00:00+08:00"),
                )
            ]
            with patch("app.remote_capcut_summaries", return_value={}), \
                    patch("app.load_task_box_receipt", return_value={}):
                dates = [item["productionDate"] for item in app.task_box_payloads()]
            self.assertEqual(["10.7", "8.3"], dates)
        finally:
            app.COLLECTOR.project_download_statuses = previous

    def test_workbench_completed_project_stays_completed_without_capcut_rows(self):
        # 2026-10-09: after upload cleanup the 10.7 CapCut rows were gone and
        # five finished projects read "第1/2步完成，等待后续步骤" (box 0/8).
        previous = app.COLLECTOR.project_download_statuses
        try:
            app.COLLECTOR.project_download_statuses = [
                {"taskId": "done", "batchId": "box-done", "batchSequence": 1, "batchSize": 2, "date": "10.7",
                 "project": "实体机", "material": "PU石", "expectedCount": 3, "completed": 3,
                 "status": "completed", "pipelineStatus": "completed",
                 "pipelineStateText": "第 5 步 CapCut 成片完成，已交给自动上传"},
                {"taskId": "parked", "batchId": "box-done", "batchSequence": 2, "batchSize": 2, "date": "10.7",
                 "project": "SPC地板", "material": "塑木地板", "expectedCount": 4, "completed": 3,
                 "status": "blocked_missing_links", "gapActive": True, "pipelineStatus": "blocked_missing_links",
                 "stateText": "待补链：已完成 3 / 4，还差 1 条"},
            ]
            with patch("app.remote_capcut_summaries", return_value={}), \
                    patch("app.load_task_box_receipt", return_value={}):
                box = app.task_box_payloads()[0]
            done, parked = box["items"]
            self.assertEqual(("completed", 3), (done["status"], done["finalCompleted"]))
            self.assertEqual("blocked", parked["status"])
            self.assertEqual((1, 3), (box["completedProjects"], box["completedVideos"]))
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

    def test_task_box_prefers_blocked_capcut_over_download_completed(self):
        previous = app.COLLECTOR.project_download_statuses
        try:
            app.COLLECTOR.project_download_statuses = [{
                "taskId": "capcut-blocked", "batchId": "box", "batchSequence": 1,
                "batchSize": 1, "date": "7.31", "project": "cloud", "material": "wood",
                "expectedCount": 24, "completed": 24, "gapActive": False,
                # This is intentionally only the Step 1/2 status.  The
                # current full pipeline is blocked in CapCut.
                "status": "completed", "pipelineStatus": "blocked_capcut",
                "pipelineStateText": "CapCut waiting for recovery",
            }]
            with patch("app.remote_capcut_summaries", return_value={}):
                box = app.task_box_payloads()[0]

            self.assertEqual("blocked", box["state"])
            self.assertEqual("blocked", box["current"]["status"])
            self.assertIn("CapCut", box["current"]["currentStep"])
        finally:
            app.COLLECTOR.project_download_statuses = previous

    def test_safe_continue_prefers_workbench_owned_older_unfinished_batch(self):
        boxes = [
            {
                "batchId": "new-box", "productionDate": "8.3", "state": "blocked",
                "current": {"taskId": "new-voice", "status": "blocked", "sequence": 6},
                "items": [{"taskId": "new-voice", "status": "blocked", "sequence": 6}],
                "updatedAt": "2026-08-03T19:00:00+08:00",
            },
            {
                "batchId": "old-box", "productionDate": "7.31", "state": "blocked",
                "current": {"taskId": "old-capcut", "status": "blocked", "sequence": 9},
                "items": [{"taskId": "old-capcut", "status": "blocked", "sequence": 9}],
                "updatedAt": "2026-08-03T17:00:00+08:00",
            },
        ]
        with patch.object(app.COLLECTOR, "active_workbench_task_id", return_value="old-capcut"):
            selected = app.authoritative_active_task_box(boxes)

        self.assertEqual("old-box", selected["batchId"])
        self.assertEqual("old-capcut", selected["current"]["taskId"])

    def test_safe_continue_ignores_terminal_workbench_context(self):
        boxes = [
            {
                "batchId": "new-box", "productionDate": "8.3", "state": "blocked",
                "current": {"taskId": "new-voice", "status": "blocked", "sequence": 2},
                "items": [{"taskId": "new-voice", "status": "blocked", "sequence": 2}],
            },
            {
                "batchId": "old-box", "productionDate": "7.31", "state": "completed",
                "current": None,
                "items": [{"taskId": "old-capcut", "status": "completed", "sequence": 9}],
            },
        ]
        with patch.object(app.COLLECTOR, "active_workbench_task_id", return_value="old-capcut"):
            selected = app.authoritative_active_task_box(boxes)

        self.assertEqual("new-box", selected["batchId"])

    def test_task_box_shows_current_task_voice_pending_not_stale_global_voice(self):
        previous = app.COLLECTOR.project_download_statuses
        try:
            app.COLLECTOR.project_download_statuses = [{
                "taskId": "huang-5", "batchId": "box-9", "batchSequence": 5,
                "batchSize": 9, "date": "7.22", "project": "黄颢", "material": "碳岩板",
                "expectedCount": 4, "completed": 4, "failed": 0, "gapActive": False,
                "notStarted": False, "status": "completed", "pipelineStatus": "voice_pending",
                "pipelineStateText": "第 1/2 步已完整，正在启动当前项目的配音",
            }]
            with patch("app.remote_capcut_summaries", return_value={}):
                box = app.task_box_payloads()[0]

            self.assertEqual("running", box["current"]["status"])
            self.assertEqual("第 3 步准备配音", box["current"]["currentStep"])
            self.assertEqual("huang-5", box["current"]["taskId"])
        finally:
            app.COLLECTOR.project_download_statuses = previous

    def test_task_box_uses_dynamic_material_rows_but_fixed_total_53(self):
        previous = app.COLLECTOR.project_download_statuses
        try:
            # The per-material split is intentionally different from the 7.22
            # split.  Dashboard must trust each submitted row and only require
            # the formal task-box sum to remain 53.
            counts = [3, 4, 6, 24, 4, 4, 4, 2, 2]
            app.COLLECTOR.project_download_statuses = [
                {
                    "taskId": f"dynamic-{sequence}", "batchId": "dynamic-53",
                    "batchSequence": sequence, "batchSize": len(counts), "date": "7.23",
                    "project": "实体机" if sequence <= 3 else "项目",
                    "material": f"材料{sequence}", "expectedCount": count,
                    "completed": 0, "failed": 0, "gapActive": False,
                    "notStarted": True, "status": "planned",
                }
                for sequence, count in enumerate(counts, 1)
            ]
            with patch("app.remote_capcut_summaries", return_value={}):
                box = app.task_box_payloads()[0]

            self.assertEqual(53, box["totalVideos"])
            self.assertEqual(counts, [item["expected"] for item in box["items"]])
            self.assertEqual(9, box["projectCount"])
            self.assertEqual("planned", box["items"][0]["status"])
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
                                "observedSize": 1000,
                                "startedAt": "2026-07-20T11:59:50+08:00",
                                "completedAt": "2026-07-20T12:00:00+08:00",
                            },
                            "two": {
                                "date": "7.20",
                                "project": "实体机",
                                "material": "净白板",
                                "language": "俄语",
                                "status": "uploading",
                                "progress": 50,
                                "observedSize": 1000,
                                "resume": {
                                    "size": 1000,
                                    "chunkSize": 500,
                                    "uploadedParts": [0],
                                },
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
            self.assertEqual(2000, stage["bytesTotal"])
            self.assertEqual(1500, stage["bytesUploaded"])
            self.assertEqual(500, stage["bytesRemaining"])
            self.assertEqual(100, stage["speedBytesPerSecond"])
            self.assertEqual(5, stage["etaSeconds"])
            self.assertEqual("", stage["currentFileName"])
            self.assertEqual(500, stage["currentFileBytes"])

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
                        "cleanup": {
                            "state": "cleanup_completed",
                            "cloudVerifiedAt": "2026-07-21T12:00:00+08:00",
                            "taskFilesCleanedAt": "2026-07-21T12:00:01+08:00",
                            "audioPathState": "permanent_keep",
                        },
                    },
                    "pending": {
                        "date": "7.21", "status": "uploaded", "progress": 100,
                        "cleanup": {
                            "state": "waiting_shared_release",
                            "cloudVerifiedAt": "2026-07-21T12:00:00+08:00",
                            "taskFilesCleanedAt": "2026-07-21T12:00:01+08:00",
                        },
                    },
                    "blocked": {
                        "date": "7.21", "status": "uploaded", "progress": 100,
                        "cleanup": {
                            "state": "blocked_cloud_size_mismatch",
                            "cloudVerifiedAt": "2026-07-21T12:00:00+08:00",
                        },
                    },
                },
            }, ensure_ascii=False), encoding="utf-8")
            config = dict(app.CONFIG)
            config["upload_status_file"] = str(status)
            collector = app.Collector(config, app.Store(root / "ops.db"))

            collector.scan_upload_pipeline()

            stage = collector.pipeline_history["upload"]["7.21"]
            self.assertEqual(1, stage["localCleaned"])
            self.assertEqual(2, stage["taskFilesCleaned"])
            self.assertEqual(1, stage["waitingSharedRelease"])
            self.assertEqual(3, stage["cloudVerified"])
            self.assertEqual(1, stage["cleanupPending"])
            self.assertEqual(1, stage["cleanupBlocked"])
            self.assertEqual(1, stage["permanentKeep"])

    def test_pipeline_for_date_does_not_reuse_upload_from_another_day(self):
        pipeline = {
            key: app.Collector.empty_stage("idle")
            for key in ("download", "voice", "stitch", "capcut", "upload")
        }
        pipeline["upload"].update({
            "state": "completed",
            "stateText": "旧任务上传完成 53/53",
            "completed": 53,
            "total": 53,
            "historyDate": "7.22",
        })
        history = {
            key: {}
            for key in ("download", "voice", "stitch", "capcut", "upload")
        }
        with (
            patch.object(app.COLLECTOR, "pipeline", pipeline),
            patch.object(app.COLLECTOR, "pipeline_history", history),
            patch.object(app, "current_date_label", return_value="7.28"),
            patch.object(app, "production_capcut_tasks", return_value=[]),
        ):
            stage = app.pipeline_for_date("7.28")["upload"]
        self.assertEqual(0, stage["completed"])
        self.assertEqual(0, stage["total"])
        self.assertNotIn("53/53", stage["stateText"])

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

    def test_completed_draft_cleanup_warning_is_not_a_production_error(self):
        with tempfile.TemporaryDirectory() as folder:
            store = app.Store(Path(folder) / "test.db")
            collector = app.Collector(app.CONFIG, store)
            task = collector.normalize_task(
                {
                    "taskId": "completed-cleanup-pending",
                    "state": "Completed",
                    "error": "最终成片已验证并等待上传；草稿待清理: 草稿索引更新失败",
                },
                Path("status.json"),
                100.0,
                "batch-1",
            )

            self.assertEqual("", task["error"])
            self.assertEqual("pending", task["draft_cleanup_status"])
            self.assertIn("草稿待清理", task["draft_cleanup_warning"])
            store.upsert_task(task)
            stored = store.tasks()[0]
            self.assertEqual("Completed", stored["state"])
            self.assertEqual("", stored["error"])
            self.assertEqual("pending", stored["draft_cleanup_status"])

    def test_completed_task_keeps_real_non_cleanup_error_visible(self):
        error, status, warning = app.split_completed_cleanup_warning(
            "Completed", "媒体身份校验失败"
        )
        self.assertEqual("媒体身份校验失败", error)
        self.assertEqual("", status)
        self.assertEqual("", warning)

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
                for task_id, remote_id in (("formal", "parent-1"), ("formal-second", "parent-2"), ("old-test", "legacy-1")):
                    source = handoff / f"{task_id}.json" if task_id != "old-test" else root / "old-launch.json"
                    app.COLLECTOR.metadata[task_id] = {
                        "_source": str(source),
                        "remotePipelineTaskId": remote_id,
                    }
                    app.STORE.upsert_task({
                        "task_id": task_id, "batch_id": "batch", "date_label": "7.21",
                        "project": "云手机", "material": "碳岩板", "language": "英语",
                        "number": "001", "sequence": 1, "video_path": "", "audio_path": "",
                        "output_path": "", "state": "Waiting", "state_text": "等待",
                        "error": "", "source_file": "source.json", "source_timestamp": 1.0,
                        "remote_pipeline_task_id": remote_id, "expected_task_count": 24,
                    })

                rows = app.production_capcut_tasks("7.21")
                scoped = app.production_capcut_tasks("7.21", remote_task_id="parent-2")

                self.assertEqual({"formal", "formal-second"}, {row["task_id"] for row in rows})
                self.assertEqual(["formal-second"], [row["task_id"] for row in scoped])
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

    def test_current_project_voice_uses_task_scoped_capcut_handoff_when_language_plan_missing(self):
        current = {
            "canonicalTaskId": "task-current",
            "batchId": "batch-current",
            "productionDate": "7.31",
            "expected": 4,
            "downloadCompleted": 4,
            "project": "project",
            "material": "material",
            "pipelineStatus": "",
        }
        rows = [
            {"task_id": f"capcut-{index}", "state": "Waiting"}
            for index in range(4)
        ]
        with (
            patch("app.production_capcut_tasks", return_value=rows),
            patch(
                "app.capcut_stage_for_tasks",
                return_value={
                    "state": "idle",
                    "completed": 2,
                    "failed": 0,
                    "total": 4,
                    "stateText": "2 waiting",
                },
            ),
            patch("app.upload_task_index", return_value={}),
        ):
            payload = app.current_project_status_payload(current, {})

        voice = next(stage for stage in payload["stages"] if stage["step"] == "voice")
        self.assertEqual("completed", voice["status"])
        self.assertEqual(4, voice["completed"])
        self.assertEqual(4, voice["total"])

    def test_current_project_exposes_full_pipeline_state_not_download_status(self):
        current = {
            "canonicalTaskId": "task-capcut", "batchId": "batch", "productionDate": "7.31",
            "expected": 24, "downloadCompleted": 24, "project": "cloud", "material": "wood",
            "status": "completed", "pipelineStatus": "blocked_capcut",
            "pipelineStateText": "CapCut task failed; safe continue is required",
        }
        with (
            patch("app.production_capcut_tasks", return_value=[]),
            patch("app.capcut_stage_for_tasks", return_value={"state": "unknown", "completed": 0, "failed": 0, "total": 0}),
            patch("app.upload_task_index", return_value={}),
        ):
            payload = app.current_project_status_payload(current, {})

        capcut = next(stage for stage in payload["stages"] if stage["step"] == "capcut")
        self.assertEqual("completed", payload["downloadStatus"])
        self.assertEqual("blocked", payload["state"])
        self.assertEqual("blocked_capcut", payload["pipelineStatus"])
        self.assertEqual("blocked", capcut["status"])

    def test_current_project_preserves_structured_recovery_error_code(self):
        current = {
            "canonicalTaskId": "task-voice", "batchId": "batch", "productionDate": "8.20",
            "expected": 5, "downloadCompleted": 5, "status": "completed",
            "pipelineStatus": "blocked_voice", "currentPhase": "voice_generation",
            "pipelineStateText": "Fish page heartbeat timed out",
            "errorCode": "VOICE_PAGE_HEARTBEAT_TIMEOUT",
        }
        with (
            patch("app.production_capcut_tasks", return_value=[]),
            patch("app.capcut_stage_for_tasks", return_value={"state": "unknown", "completed": 0, "failed": 0, "total": 0}),
            patch("app.upload_task_index", return_value={}),
        ):
            payload = app.current_project_status_payload(current, {})
        self.assertEqual("voice", payload["errors"][0]["component"])
        self.assertEqual("voice_generation", payload["errors"][0]["phase"])
        self.assertEqual("VOICE_PAGE_HEARTBEAT_TIMEOUT", payload["errors"][0]["errorCode"])

    def test_current_project_classifies_legacy_capcut_import_dialog_timeout_once(self):
        current = {
            "canonicalTaskId": "task-capcut", "batchId": "batch", "productionDate": "8.20",
            "expected": 5, "downloadCompleted": 5, "status": "completed",
            "pipelineStatus": "blocked_capcut", "currentPhase": "capcut",
            "pipelineStateText": "第 5 步 CapCut 需要处理",
        }
        rows = [{
            "task_id": "video-1", "state": "Failed", "phase": "importing",
            "error": "导入第一条主视频失败: 未出现系统文件选择窗口。当前剪映版本可能需要调整 Import 定位规则。",
            "attempt_id": "attempt-1",
        }]
        with (
            patch("app.production_capcut_tasks", return_value=rows),
            patch("app.capcut_stage_for_tasks", return_value={"state": "failed", "completed": 0, "failed": 1, "total": 1}),
            patch("app.upload_task_index", return_value={}),
        ):
            payload = app.current_project_status_payload(current, {})

        self.assertEqual(1, len(payload["errors"]))
        self.assertEqual("capcut", payload["errors"][0]["component"])
        self.assertEqual("CAPCUT_IMPORT_DIALOG_TIMEOUT", payload["errors"][0]["errorCode"])

    def test_current_project_migrates_legacy_capcut_window_transition_error(self):
        current = {
            "canonicalTaskId": "denor-current", "batchId": "denor-batch", "productionDate": "9.2",
            "expected": 21, "downloadCompleted": 21, "status": "completed",
            "pipelineStatus": "blocked_capcut", "currentPhase": "capcut",
            "pipelineStateText": "第 5 步 CapCut 需要处理",
        }
        rows = [{
            "task_id": "output-02", "state": "Failed", "phase": "draft_creation",
            "error": "创建本条独立草稿失败: 剪映主窗口不可用",
            "attemptId": "attempt-denor",
        }]
        with (
            patch("app.production_capcut_tasks", return_value=rows),
            patch("app.capcut_stage_for_tasks", return_value={"state": "failed", "completed": 1, "failed": 1, "total": 21}),
            patch("app.upload_task_index", return_value={}),
        ):
            payload = app.current_project_status_payload(current, {})

        self.assertEqual(1, len(payload["errors"]))
        self.assertEqual("CAPCUT_MAIN_WINDOW_TRANSITION_TIMEOUT", payload["errors"][0]["errorCode"])
        self.assertEqual("attempt-denor", payload["errors"][0]["attemptId"])

    def test_current_project_exposes_structured_upload_failure(self):
        current = {
            "canonicalTaskId": "task-upload", "batchId": "batch", "productionDate": "8.20",
            "expected": 1, "downloadCompleted": 1, "status": "completed", "pipelineStatus": "capcut_running",
        }
        rows = [{"task_id": "video-1", "state": "Completed"}]
        upload = {"video-1": {
            "status": "failed", "phase": "uploading", "errorCode": "UPLOAD_NETWORK_ERROR",
            "error": "connection reset",
        }}
        with (
            patch("app.production_capcut_tasks", return_value=rows),
            patch("app.capcut_stage_for_tasks", return_value={"state": "completed", "completed": 1, "failed": 0, "total": 1}),
            patch("app.upload_task_index", return_value=upload),
        ):
            payload = app.current_project_status_payload(current, {})
        error = next(item for item in payload["errors"] if item["component"] == "upload")
        self.assertEqual("UPLOAD_NETWORK_ERROR", error["errorCode"])

    def test_current_project_voice_uses_verified_fish_handoff_when_plan_is_omitted(self):
        current = {
            "canonicalTaskId": "task-korean",
            "batchId": "batch-korean",
            "productionDate": "8.2",
            "expected": 26,
            "downloadCompleted": 26,
            "project": "true-huanghao",
            "material": "wood",
            "pipelineStatus": "voice_completed",
            "languagePlan": [],
        }
        handoff = {
            "status": "completed",
            "completedItems": [
                {"taskId": f"voice-{index}", "canonicalTaskId": "task-korean", "voiceVerified": True, "audioPath": f"audio-{index}.mp3"}
                for index in range(8)
            ],
        }
        with (
            patch("app.production_capcut_tasks", return_value=[]),
            patch("app.capcut_stage_for_tasks", return_value={"state": "idle", "completed": 0, "failed": 0, "total": 0}),
            patch("app.upload_task_index", return_value={}),
            patch("app.read_json_object", return_value=handoff),
        ):
            payload = app.current_project_status_payload(current, {})

        voice = next(stage for stage in payload["stages"] if stage["step"] == "voice")
        self.assertEqual("completed", voice["status"])
        self.assertEqual(8, voice["completed"])
        self.assertEqual(8, voice["total"])

    def test_upload_rescan_also_requests_live_cloud_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with (
                patch("app.workbench_runtime_dir", return_value=root),
                patch(
                    "app.inspect_upload_backlog",
                    return_value={
                        "candidates": [{"taskId": "waiting"}],
                        "missing": [],
                    },
                ),
                patch(
                    "app._ensure_upload_service_running",
                    return_value={"running": True, "started": False, "pid": 123},
                ),
                patch(
                    "app.request_historical_cloud_verification",
                    return_value={"state": "requested", "eligible": 16},
                ) as verification,
                patch("app.save_control_action"),
            ):
                result = app.request_upload_rescan()

            verification.assert_called_once_with()
            self.assertEqual("requested", result["verificationState"])
            self.assertEqual(16, result["verificationEligible"])

    def test_subtitle_verification_inventory_keeps_historical_batch_audit_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            checkpoint_dir = root / "handoff" / "download" / "checkpoints"
            checkpoint_dir.mkdir(parents=True)
            checkpoint = checkpoint_dir / "task-85.json"
            checkpoint.write_text(json.dumps({
                "taskId": "task-85",
                "productionDate": "8.5",
                "items": {
                    "https://example.test/a": {
                        "status": "completed",
                        "outputPath": str(root / "a.mp4"),
                        "subtitleOutcome": "processed",
                        "verification": {},
                    },
                    "https://example.test/b": {
                        "status": "failed",
                        "outputPath": str(root / "b.mp4"),
                        "verification": {"verificationStatus": "residual_detected"},
                    },
                },
            }, ensure_ascii=False), encoding="utf-8")
            with patch("app._workbench_root", return_value=root):
                payload = app.subtitle_verification_inventory("task-85", "8.5")

        self.assertEqual(2, payload["total"])
        self.assertEqual(1, payload["counts"]["audit_pending"])
        self.assertEqual(1, payload["counts"]["residual_detected"])
        self.assertTrue(all(item["historicalAuditOnly"] for item in payload["items"]))


if __name__ == "__main__":
    unittest.main()
