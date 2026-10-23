"""Exact normalize_task from CI-tested/deployed PR49; isolated profile only."""
from __future__ import annotations

def normalize_task(
        self,
        item: dict[str, Any],
        source: Path,
        source_timestamp: float,
        batch_id: str = "",
        date_label: str = "",
    ) -> dict[str, Any]:
        task_id = str(item.get("taskId") or "")
        meta = self.metadata.get(task_id, {})
        state = str(item.get("state") or item.get("status") or meta.get("status") or "Waiting")
        state_text = str(
            item.get("stateText")
            or CAPCUT_STATE_TEXT.get(state)
            or {
                "waiting_capcut": "等待第五步",
                "waiting_client": "等待CapCut",
                "stopped": "已停止",
                "validation_failed": "校验失败",
                "manual_review": "等待人工确认",
                "completed": "剪辑完成",
                "failed": "剪辑失败",
            }.get(state, state)
        )
        # Reconcile only a terminal maintenance failure, never an active attempt.
        # The live ledger's QC + exact final bytes outrank a stale failed status.
        from verified_final import released_final_verified
        verified_maintenance = (
            state in FAILED_STATES
            and str(meta.get("status") or "") in FAILED_STATES
            and released_final_verified(meta)
        )
        historical_error = str(item.get("error") or meta.get("maintenanceError") or meta.get("error") or "")
        if verified_maintenance:
            state = "completed"
            state_text = "成片已验证完成（保留历史维护异常）"
        normalized_error, cleanup_status, cleanup_warning = split_completed_cleanup_warning(
            state,
            str(item.get("error") or ""),
            str(item.get("draftCleanupStatus") or meta.get("draftCleanupStatus") or ""),
            str(item.get("draftCleanupWarning") or meta.get("draftCleanupWarning") or ""),
        )
        if verified_maintenance:
            normalized_error = ""
            cleanup_status = "warning"
            cleanup_warning = "历史维护异常：" + (historical_error or "旧尝试失败；成片已核验")
        return {
            "task_id": task_id,
            "batch_id": batch_id or str(meta.get("_batch_id") or ""),
            "date_label": date_label or str(meta.get("date") or meta.get("_date_label") or ""),
            "project": str(item.get("project") or meta.get("project") or "未分类"),
            "material": str(item.get("material") or meta.get("material") or ""),
            "language": str(item.get("language") or meta.get("language") or ""),
            "number": str(item.get("number") or meta.get("number") or ""),
            "sequence": int(item.get("sequence") or meta.get("sequence") or 0),
            "video_path": str(item.get("videoPath") or meta.get("videoPath") or ""),
            "audio_path": str(item.get("audioPath") or meta.get("audioPath") or ""),
            "output_path": str(meta["finalOutputPath"]) if verified_maintenance else str(
                item.get("outputPath") or item.get("finalOutputPath")
                or meta.get("finalOutputPath") or ""
            ),
            "state": state,
            "state_text": state_text,
            "phase": "completed" if verified_maintenance else str(item.get("currentPhase") or item.get("phase") or item.get("state") or meta.get("currentPhase") or ""),
            "phase_text": state_text if verified_maintenance else str(item.get("phaseText") or item.get("stateText") or meta.get("phaseText") or ""),
            "manifest_id": str(item.get("manifestId") or meta.get("activeManifestId") or ""),
            "attempt_id": str(item.get("attemptId") or meta.get("activeAttemptId") or ""),
            "heartbeat_at": str(item.get("heartbeatAt") or ""),
            "error": normalized_error,
            "draft_cleanup_status": cleanup_status,
            "draft_cleanup_warning": cleanup_warning,
            "draft_cleanup_updated_at": str(
                item.get("draftCleanupUpdatedAt") or meta.get("draftCleanupUpdatedAt") or ""
            ),
            "failure_fingerprint": str(
                item.get("failureFingerprint") or meta.get("failureFingerprint") or ""
            ),
            "remote_pipeline_task_id": str(
                item.get("remotePipelineTaskId") or meta.get("remotePipelineTaskId") or ""
            ).strip(),
            "expected_task_count": int(
                item.get("expectedTaskCount") or meta.get("expectedTaskCount") or 0
            ),
            "source_file": str(source),
            "source_timestamp": source_timestamp,
        }
