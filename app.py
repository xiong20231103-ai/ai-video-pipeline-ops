from __future__ import annotations

import csv
import ctypes
import hashlib
import ipaddress
import json
import os
import re
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "ops.db"
CONFIG_PATH = BASE_DIR / "config.json"
CONTINUE_COMMAND_NAME = "continue_current_project.json"
CONTROL_COMMAND_DIR = DATA_DIR / "control-commands"
CONTROL_COMMAND_TTL_SECONDS = 300
CONTROL_COMMAND_CLAIM_TIMEOUT_SECONDS = 90
TASK_BOX_RECEIPT_DIR = DATA_DIR / "task-box-completion-receipts"
TASK_BOX_RECONCILIATION_DIR = DATA_DIR / "task-box-reconciliation"
LEGACY_INVALID_JSON_BACKSLASH = re.compile(r'(?<!\\)\\(?!["\\/bfnrtu])')
CONTROL_ACTIONS_PATH = DATA_DIR / "control_actions.json"
TEST_RESET_STATE_PATH = DATA_DIR / "test_reset_state.json"
CAPCUT_DRAFT_CLEANUP_STATUS_PATH = DATA_DIR / "capcut_draft_cleanup_status.json"
CAPCUT_DRAFT_CLEANUP_BACKUP_DIR = DATA_DIR / "capcut-draft-cleanup-backups"
CAPCUT_DRAFT_CLEANUP_CONFIRM = "RECYCLE_SELECTED_CAPCUT_DRAFTS"
CAPCUT_DRAFT_LOCK = threading.RLock()
AUDIO_CLEANUP_STATUS_PATH = DATA_DIR / "audio_cleanup_status.json"
AUDIO_CLEANUP_BACKUP_DIR = DATA_DIR / "audio-cleanup-records"
AUDIO_CLEANUP_CONFIRM = "RECYCLE_SELECTED_AUDIO_FILES"
AUDIO_CLEANUP_LOCK = threading.RLock()
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
PRODUCTION_FILE_CLEANUP_STATUS_PATH = DATA_DIR / "production_file_cleanup_status.json"
PRODUCTION_FILE_CLEANUP_BACKUP_DIR = DATA_DIR / "production-file-cleanup-records"
PRODUCTION_FILE_CLEANUP_INDEX_PATH = DATA_DIR / "production_file_cleanup_index.json"
PRODUCTION_FILE_CLEANUP_CONFIRM = "RECYCLE_SELECTED_PRODUCTION_FILES"
PRODUCTION_FILE_CLEANUP_LOCK = threading.RLock()
PRODUCTION_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
LOCAL_PATH_PATTERN = re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/][^\"\r\n]*")
SENSITIVE_KEY_PARTS = ("accesstoken", "access_token", "password", "secret", "authorization")

CAPCUT_STATE_TEXT = {
    "Waiting": "等待剪辑",
    "Launching": "启动剪映",
    "CreatingProject": "创建项目",
    "Importing": "导入视频",
    "PlacingOnTimeline": "加入时间线",
    "MutingOriginal": "静音原轨",
    "ImportingAudio": "导入音频",
    "PlacingAudioOnTimeline": "加入音频轨",
    "ImportingSample": "导入结尾样品",
    "PlacingSample": "样品接到末尾",
    "AdjustingSampleSpeed": "调整样品速度",
    "RecognizingCaptions": "识别字幕",
    "ApplyingSubtitleStyle": "应用字幕样式",
    "TrimmingFirstCaption": "检查首帧字幕",
    "ReplacingMainVideo": "替换主视频",
    "Exporting": "2K导出",
    "PostProcessing": "FFmpeg替换第0帧",
    "CleaningDraft": "清理草稿",
    "RecyclingSource": "等待云端核验与清理",
    "Completed": "剪辑完成",
    "Failed": "剪辑失败",
}

WAITING_STATES = {"Waiting", "waiting_capcut", "waiting_client", "stopped"}
RECOVERABLE_DRAFT_REOPEN_ERRORS = {
    "draft_card_location_failed",
    "draft_editor_binding_failed",
    "draft_cover_location_failed",
    "draft_checkpoint_current_lease_directory_missing",
    "draft_checkpoint_current_lease_files_missing",
}


def _is_recoverable_draft_waiting(item: dict[str, Any] | None) -> bool:
    """Whether a CapCut task deliberately stopped at the safe reopen boundary."""
    value = item or {}
    state = str(value.get("state") or value.get("currentPhase") or value.get("phase") or "").lower()
    fingerprint = str(
        value.get("failureFingerprint") or value.get("failure_fingerprint") or value.get("errorCode") or ""
    ).strip()
    error = str(value.get("error") or value.get("message") or value.get("pipelineStateText") or "")
    if state in {"waiting", "waiting_capcut", "waiting_client", "stopped"}:
        return fingerprint in RECOVERABLE_DRAFT_REOPEN_ERRORS or "等待重开草稿，可安全继续" in error
    # Compatibility for the currently retained pre-fix checkpoint.  Older
    # clients wrote this exact safe-stop as Failed without a fingerprint.
    return state == "failed" and "主页未能动态识别并安全定位" in error and "未执行点击" in error
COMPLETED_STATES = {"Completed", "completed"}
FAILED_STATES = {"Failed", "failed", "validation_failed", "manual_review"}
LEGACY_DRAFT_CLEANUP_MARKERS = (
    "草稿待清理",
    "草稿索引更新失败",
    "返回首页并删除本条唯一新增草稿失败",
)


def split_completed_cleanup_warning(
    state: str, error: str, cleanup_status: str = "", cleanup_warning: str = ""
) -> tuple[str, str, str]:
    """Keep post-success housekeeping out of the production error domain.

    Clients released before the dedicated cleanup fields stored a best-effort
    draft cleanup warning in ``error`` even though the media task was already
    Completed.  Normalize those records on read so historical JSON cannot
    become a current CapCut failure or a Feishu incident.
    """
    normalized_error = str(error or "")
    normalized_status = str(cleanup_status or "")
    normalized_warning = str(cleanup_warning or "")
    if state in COMPLETED_STATES and any(
        marker in normalized_error for marker in LEGACY_DRAFT_CLEANUP_MARKERS
    ):
        normalized_status = normalized_status or "pending"
        normalized_warning = normalized_warning or normalized_error
        normalized_error = ""
    return normalized_error, normalized_status, normalized_warning


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_time(value: Any, fallback: float = 0.0) -> float:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return fallback


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def sanitize_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_public_value(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS)
        }
    if isinstance(value, list):
        return [sanitize_public_value(item) for item in value]
    if isinstance(value, str):
        return LOCAL_PATH_PATTERN.sub("[本机路径已隐藏]", value)
    return value


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


def load_config() -> dict[str, Any]:
    defaults = {
        "machine_name": socket.gethostname(),
        "listen_host": "127.0.0.1",
        "listen_port": 8765,
        "workbench_dir": "../TikHub_AI_视频工作台",
        "workbench_ops_status": "../TikHub_AI_视频工作台/ops_pipeline_status.json",
        "download_state_file": "../TikHub_AI_视频工作台/handoff/download/download_batch_state.json",
        "download_project_status_file": "../TikHub_AI_视频工作台/handoff/download/project_status.json",
        "receiver_status_url": "http://127.0.0.1:8766/api/pipeline/snapshot",
        "control_plane_url": "http://127.0.0.1:18790",
        "download_root": "",
        "voice_handoff_file": "../TikHub_AI_视频工作台/tools/BatchVoiceClient-Portable/data/last_batch_handoff.json",
        "audio_roots": [],
        "generation_output_root": "E:/生成视频",
        "capcut_handoff_dir": "../TikHub_AI_视频工作台/handoff/capcut",
        "fourth_step_handoff_dir": "../TikHub_AI_视频工作台/交接记录",
        "final_output_root": "E:/",
        "capcut_draft_root": "",
        "upload_status_file": "../TikHub_AI_视频工作台/handoff/upload/upload_status.json",
        "prepared_sample_roots": [
            str((BASE_DIR.parent / "capcut-auto-caption-client" / "bin" / "data" / "prepared-samples").resolve())
        ],
        "capcut_test_roots": [
            str((BASE_DIR.parent / "capcut-auto-caption-client" / "bin" / "data" / "local-sample-e2e").resolve()),
            str((BASE_DIR.parent / "capcut-auto-caption-client" / "bin" / "data" / "first-caption-e2e-output").resolve()),
        ],
        "isolated_runtime_markers": [
            "AI视频工作台-内测版-20260724",
            "isolated-subtitle-style-lab.profile",
        ],
        "baidu_sync_roots": [],
        "scan_interval_seconds": 2,
        "pipeline_live_after_seconds": 15,
        "heartbeat_interval_seconds": 60,
        "offline_after_seconds": 180,
        "simulation_enabled": True,
        # Explicitly archived test batches remain visible in task history, but
        # must never affect a formal production project's counts or handoff gate.
        "test_history_batch_ids": [],
        "test_history_remote_task_ids": [],
    }
    if CONFIG_PATH.exists():
        try:
            defaults.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return defaults


def receiver_base_url() -> str:
    """Return the local receiver origin without exposing its sender token."""
    status_url = str(CONFIG.get("receiver_status_url") or "http://127.0.0.1:8766/api/pipeline/snapshot")
    parts = urllib.parse.urlsplit(status_url)
    if not parts.scheme or not parts.netloc:
        raise ValueError("任务接收器地址无效")
    return f"{parts.scheme}://{parts.netloc}"


def ensure_receiver_workbench_running() -> dict[str, Any]:
    """Ask the receiver to own workbench startup and single-instance checks."""
    # The receiver waits up to 20 seconds for the workbench readiness heartbeat.
    return receiver_json("/api/workbench/ensure-running", method="POST", timeout=28)


def _continue_launch_result(result: dict[str, Any]) -> dict[str, Any]:
    started = bool(result.get("started"))
    already_running = bool(result.get("alreadyRunning"))
    message = str(result.get("message") or "").strip()
    if already_running:
        status_message = "命令已发送，现有工作台正在接收"
    elif started:
        status_message = "命令已发送，正在启动工作台"
    else:
        status_message = message or "命令已发送，接收器正在确认工作台状态"
    return {
        "workbenchStarted": started,
        "workbenchAlreadyRunning": already_running,
        "workbenchReady": bool(result.get("ready")),
        "workbenchStartPending": bool(result.get("startPending")),
        "workbenchPid": int(result.get("pid") or 0),
        "workbenchLaunchCode": "",
        "workbenchLaunchLog": "",
        "workbenchLaunchError": "",
        "message": status_message,
    }


def _ensure_workbench_for_continue() -> dict[str, Any]:
    """Keep the durable command even when receiver-side startup fails."""
    try:
        return _continue_launch_result(ensure_receiver_workbench_running())
    except HTTPException as exc:
        detail = exc.detail
        structured = detail if isinstance(detail, dict) else {}
        error_message = str(structured.get("message") or detail)
        return {
            "workbenchStarted": False,
            "workbenchAlreadyRunning": False,
            "workbenchReady": False,
            "workbenchStartPending": False,
            "workbenchPid": 0,
            "workbenchLaunchCode": str(structured.get("code") or f"http_{exc.status_code}"),
            "workbenchLaunchLog": str(structured.get("logFile") or ""),
            "workbenchLaunchError": error_message,
            "message": f"继续命令已保存，但工作台启动失败：{error_message}",
        }


def _persist_continue_launch_state(command_file: Path, command_id: str, launch: dict[str, Any]) -> None:
    """Persist startup feedback while leaving workbench-owned running states untouched."""
    try:
        current = json.loads(command_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(current, dict) or str(current.get("commandId") or "") != command_id:
        return
    if str(current.get("state") or "") != "requested":
        return
    for key in (
        "workbenchStarted", "workbenchAlreadyRunning", "workbenchPid",
        "workbenchReady", "workbenchStartPending", "workbenchLaunchCode",
        "workbenchLaunchLog", "workbenchLaunchError", "message",
    ):
        current[key] = launch.get(key)
    current["workbenchLaunchUpdatedAt"] = now_iso()
    temp = command_file.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, command_file)


def _continue_target_signature(payload: dict[str, Any] | None) -> tuple[str, str, str, str, str]:
    """The identity a safe-continue command is allowed to own.

    ``batchId/taskId/date`` was enough before retries had their own CapCut
    manifest.  Keeping manifest + attempt in the signature stops a stale
    recovery from silently owning the next attempt of the same project.
    """
    value = payload or {}
    return tuple(str(value.get(key) or "") for key in (
        "batchId", "taskId", "productionDate", "manifestId", "attemptId",
    ))


def _continue_target_changed(command: dict[str, Any] | None, target: dict[str, Any] | None) -> bool:
    """Whether a mailbox command belongs to a different current project.

    ``manifestId`` and ``attemptId`` were introduced after old commands had
    already been written, so they are compared only when both sides provide a
    value.  The durable project triple is always required.  This prevents a
    1/2-step ``completed`` record from making a stale command look current
    after the workbench has moved on to a later pipeline phase/project.
    """
    command_signature = _continue_target_signature(command)
    target_signature = _continue_target_signature(target)
    if not any(command_signature[:3]) or not any(target_signature[:3]):
        return False
    if command_signature[:3] != target_signature[:3]:
        return True
    return any(
        command_value and target_value and command_value != target_value
        for command_value, target_value in zip(command_signature[3:], target_signature[3:])
    )


def _archive_continue_command(command_file: Path, command: dict[str, Any], reason: str) -> None:
    """Keep an immutable audit copy before a stale mailbox command is retired.

    The active mailbox is still retained as ``expired`` for backward
    compatibility with older workbenches.  The history copy stops future
    reconciliations from treating the old target as the current project.
    """
    command_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(command.get("commandId") or "legacy"))
    archive_dir = command_file.parent / "history"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived = {
        **command,
        "archivedAt": now_iso(),
        "archiveReason": reason,
    }
    archive_path = archive_dir / f"{command_id}-{int(time.time() * 1000)}.json"
    _write_json_atomic(archive_path, archived)


def _expire_continue_command(command_file: Path, command: dict[str, Any], reason: str) -> dict[str, Any]:
    """Mark one non-current command terminal and preserve its audit record."""
    retired = dict(command)
    _archive_continue_command(command_file, retired, reason)
    retired.update({
        "state": "expired",
        "stale": True,
        "expiredReason": reason,
        "finishedAt": now_iso(),
    })
    _write_json_atomic(command_file, retired)
    return retired


def _capcut_recovery_command_is_stale(command: dict[str, Any], runtime_item: dict[str, Any]) -> bool:
    """Return true only for a dead CapCut recovery, never a live client.

    A workbench can safely stop CapCut after a failed task.  Its old command
    used to remain ``recovering`` forever, so subsequent Dashboard clicks
    returned the same id and did nothing.  A fresh heartbeat or an actual
    running client always wins over this timeout check.
    """
    if str(command.get("state") or "") not in {"running", "recovering"}:
        return False
    pipeline = str(runtime_item.get("pipelineStatus") or "").lower()
    if pipeline not in {"blocked_capcut", "capcut_pending", "capcut_failed"}:
        return False
    capcut = runtime_item.get("capcut") if isinstance(runtime_item.get("capcut"), dict) else {}
    if int(capcut.get("running") or 0) > 0:
        return False
    current_phase = str(runtime_item.get("currentPhase") or "").lower()
    if current_phase == "capcut_running":
        return False
    if _is_recoverable_draft_waiting(runtime_item):
        return True
    heartbeat = parse_time(str(command.get("lastHeartbeat") or command.get("startedAt") or ""))
    return bool(heartbeat and time.time() - heartbeat > 120)


def request_workbench_continue(target: dict[str, Any]) -> dict[str, Any]:
    """Queue one safe-resume request for the local workbench."""
    workbench_dir = resolve_path(str(CONFIG.get("workbench_dir") or ""))
    # The deployed Dashboard config points at the suite root while the desktop
    # workbench itself owns the nested workbench/ handoff mailbox.
    if (workbench_dir / "workbench").is_dir():
        workbench_dir = workbench_dir / "workbench"
    if not workbench_dir.is_dir():
        raise HTTPException(status_code=503, detail="工作台目录不可用，无法发送继续指令")
    command_file = workbench_dir / "handoff" / "control" / CONTINUE_COMMAND_NAME
    command_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(command_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        existing = {}
    # A command can remain behind when an older workbench wrote finishedAt
    # while retaining state=running, or after its project has completed.
    in_flight_states = {"requested", "accepted", "running", "recovering"}
    if isinstance(existing, dict) and existing.get("state") in in_flight_states:
        existing_target = _continue_target_signature(existing)
        requested_target = _continue_target_signature(target)
        old_runtime = read_json_object(workbench_dir / "handoff" / "download" / "project_status.json")
        old_items = old_runtime.get("items") if isinstance(old_runtime.get("items"), dict) else {}
        old_item = old_items.get(existing_target[1]) if isinstance(old_items, dict) else {}
        old_pipeline = str(old_item.get("pipelineStatus") or "").lower() if isinstance(old_item, dict) else ""
        heartbeat = parse_time(str(existing.get("lastHeartbeat") or existing.get("startedAt") or existing.get("requestedAt") or ""))
        expired_reason = ""
        if existing.get("finishedAt"):
            expired_reason = "运行命令已含完成时间"
        elif old_pipeline in {"completed", "cancelled", "withdrawn"}:
            expired_reason = "命令所属项目已结束"
        elif isinstance(old_item, dict) and _capcut_recovery_command_is_stale(existing, old_item):
            expired_reason = "CapCut 恢复命令心跳已失效，且客户端未运行；允许重新安全继续"
        elif (
            existing.get("state") in {"requested", "accepted"}
            and existing_target == requested_target
            and old_pipeline in {
                "step1_completed", "step12_completed", "voice_pending", "voice_completed",
                "stitch_pending", "blocked_voice", "blocked_stitch", "blocked_reconcile",
            }
            and heartbeat
            and time.time() - heartbeat > 120
            and not existing.get("lastHeartbeat")
        ):
            # Workbench owns the transition to running and writes a heartbeat
            # only after it has actually started a task-scoped recovery.
            # A Dashboard/receiver startup acknowledgement alone is not a
            # running production command and must not block another click.
            expired_reason = "继续命令未确认启动，已允许安全重试"
        elif existing_target != requested_target:
            # ``continue_current_project`` has exactly one owner.  Once the
            # current identity differs, an old command must not keep the new
            # task's button locked, even if it was recently written.
            expired_reason = "安全继续目标已变化，旧命令已归档"
        if expired_reason:
            existing = _expire_continue_command(command_file, existing, expired_reason)
    # A prior command can remain marked running after the task-scoped Fish
    # handoff has already entered a terminal voice failure.  Only that same
    # task is allowed to supersede the stale command.
    runtime_status = read_json_object(workbench_dir / "handoff" / "download" / "project_status.json")
    runtime_items = runtime_status.get("items") if isinstance(runtime_status.get("items"), dict) else {}
    runtime_item = runtime_items.get(str(target.get("taskId") or "")) if isinstance(runtime_items, dict) else {}
    pipeline_status = str(runtime_item.get("pipelineStatus") or "").lower() if isinstance(runtime_item, dict) else ""
    task_id = str(target.get("taskId") or "")
    voice_handoff = read_json_object(resolve_path(str(CONFIG.get("voice_handoff_file") or "")))
    voice_status = str(voice_handoff.get("status") or "").lower()
    handoff_task_ids = {
        str(item.get("canonicalTaskId") or "")
        for item in (voice_handoff.get("failedItems") or [])
        if isinstance(item, dict)
    }
    handoff_task_ids.update(str(value or "") for value in (voice_handoff.get("canonicalTaskIds") or []))
    terminal_voice_for_task = (
        task_id in handoff_task_ids
        and voice_status in {"failed", "completed_with_errors", "cancelled", "canceled"}
    )
    handoff_terminal_at = parse_time(str(
        voice_handoff.get("finishedAt")
        or voice_handoff.get("completedAt")
        or voice_handoff.get("updatedAt")
        or ""
    ))
    command_requested_at = parse_time(str(
        existing.get("requestedAt")
        or existing.get("startedAt")
        or ""
    )) if isinstance(existing, dict) else None
    voice_failure_for_task = terminal_voice_for_task and (
        not command_requested_at
        or not handoff_terminal_at
        or handoff_terminal_at >= command_requested_at
    )
    retryable_terminal_voice = (
        pipeline_status in {"blocked_voice", "voice_failed", "voice_login_required"}
        or voice_failure_for_task
    )
    if (
        isinstance(existing, dict)
        and existing.get("state") in in_flight_states
        and voice_failure_for_task
        and _continue_target_signature(existing)[1] == task_id
    ):
        existing["state"] = "expired"
        existing["stale"] = True
        existing["expiredReason"] = "Fish 配音批次已进入终态失败，已解除旧安全继续命令"
        existing["phase"] = "voice_failed"
        existing["finishedAt"] = now_iso()
        existing["message"] = "配音批次失败，可安全继续重试缺失语音"
        _write_json_atomic(command_file, existing)
        existing = {}
    if (
        isinstance(existing, dict)
        and existing.get("state") in in_flight_states
        and not retryable_terminal_voice
    ):
        existing_target = _continue_target_signature(existing)
        requested_target = _continue_target_signature(target)
        if existing_target != requested_target:
            raise HTTPException(status_code=409, detail="已有另一项目的安全继续命令正在处理")
        response = {
            "accepted": True,
            "commandId": str(existing.get("commandId") or ""),
            "state": existing.get("state"),
        }
        launch = _ensure_workbench_for_continue()
        _persist_continue_launch_state(command_file, response["commandId"], launch)
        response.update(launch)
        return response
    payload = {
        "command": "continue_current_project",
        "commandId": str(target.get("commandId") or f"continue-{uuid.uuid4().hex[:12]}"),
        "clientRequestId": str(target.get("clientRequestId") or ""),
        "state": "requested",
        "requestedAt": now_iso(),
        "requestedBy": "dashboard",
        "batchId": str(target.get("batchId") or ""),
        "taskId": str(target.get("taskId") or ""),
        "productionDate": str(target.get("productionDate") or ""),
        "manifestId": str(target.get("manifestId") or ""),
        "attemptId": str(target.get("attemptId") or ""),
        "snapshotUpdatedAt": str(target.get("snapshotUpdatedAt") or ""),
    }
    temp = command_file.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, command_file)
    response = {
        "accepted": True,
        "commandId": payload["commandId"],
        "state": "requested",
    }
    launch = _ensure_workbench_for_continue()
    _persist_continue_launch_state(command_file, response["commandId"], launch)
    response.update(launch)
    return response


def enqueue_control_command(target: dict[str, Any], client_request_id: str = "") -> dict[str, Any]:
    now = now_iso()
    for existing in list_control_commands():
        if client_request_id and str(existing.get("clientRequestId") or "") == client_request_id:
            return existing
        if (
            str(existing.get("state") or "") in {
                "requested", "persisted", "receiver_acknowledged",
                "workbench_acknowledged", "executing",
            }
            and _continue_target_signature(existing) == _continue_target_signature(target)
            and parse_time(str(existing.get("expiresAt") or "")) > time.time()
        ):
            return existing
    mailbox = read_json_object(continue_command_file())
    if (
        str(mailbox.get("state") or "") in {"requested", "accepted", "running", "recovering"}
        and _continue_target_signature(mailbox) == _continue_target_signature(target)
        and not mailbox.get("finishedAt")
        and parse_time(str(mailbox.get("requestedAt") or mailbox.get("startedAt") or "")) >= time.time() - CONTROL_COMMAND_TTL_SECONDS
    ):
        command_id = str(mailbox.get("commandId") or f"continue-{uuid.uuid4().hex[:12]}")
        imported = {
            **mailbox,
            "schemaVersion": 1,
            "commandId": command_id,
            "clientRequestId": str(mailbox.get("clientRequestId") or client_request_id or f"dashboard-{uuid.uuid4().hex}"),
            "state": "receiver_acknowledged" if str(mailbox.get("state")) == "requested" else (
                "workbench_acknowledged" if str(mailbox.get("state")) == "accepted" else "executing"
            ),
            "persistedAt": str(mailbox.get("requestedAt") or now),
            "expiresAt": datetime.fromtimestamp(time.time() + CONTROL_COMMAND_TTL_SECONDS, timezone.utc).isoformat(),
            "message": str(mailbox.get("message") or "已有同一任务的安全继续命令，正在核对"),
        }
        write_control_command(imported)
        return imported
    command_id = f"continue-{uuid.uuid4().hex[:12]}"
    command = {
        "schemaVersion": 1,
        "command": "continue_current_project",
        "commandId": command_id,
        "clientRequestId": client_request_id or f"dashboard-{uuid.uuid4().hex}",
        "state": "persisted",
        "requestedAt": now,
        "persistedAt": now,
        "expiresAt": datetime.fromtimestamp(time.time() + CONTROL_COMMAND_TTL_SECONDS, timezone.utc).isoformat(),
        "requestedBy": "dashboard",
        **{key: str(target.get(key) or "") for key in (
            "batchId", "taskId", "productionDate", "manifestId", "attemptId", "snapshotUpdatedAt",
        )},
        "message": "命令已保存，等待家里接收器确认",
    }
    write_control_command(command)
    try:
        legacy = request_workbench_continue({**target, "commandId": command_id, "clientRequestId": command["clientRequestId"]})
    except HTTPException as exc:
        command["message"] = f"命令已保存；接收器暂未确认：{exc.detail}"
        write_control_command(command)
        return command
    command.update({
        "state": "receiver_acknowledged" if not legacy.get("workbenchLaunchError") else "persisted",
        "receiverAcknowledgedAt": now_iso() if not legacy.get("workbenchLaunchError") else "",
        "workbenchPid": int(legacy.get("workbenchPid") or 0),
        "message": (
            "家里接收器已收到，等待工作台领取"
            if not legacy.get("workbenchLaunchError")
            else str(legacy.get("message") or "命令已保存，等待接收器恢复")
        ),
    })
    write_control_command(command)
    return command


def continue_command_file() -> Path:
    runtime = workbench_runtime_dir()
    return runtime / "handoff" / "control" / CONTINUE_COMMAND_NAME


def fish_bridge_status() -> dict[str, Any]:
    """Read the local-only Fish bridge ownership record for remote diagnosis."""
    handoff_path = resolve_path(str(CONFIG.get("voice_handoff_file") or ""))
    runtime = read_json_object(handoff_path.with_name("fish_bridge_runtime.json"))
    if not runtime:
        return {"state": "idle", "message": "Fish 桥接尚未启动"}
    return {
        "state": str(runtime.get("state") or "idle"),
        "message": str(runtime.get("message") or runtime.get("cleanupReason") or ""),
        "pid": int(runtime.get("pid") or 0),
        "port": int(runtime.get("port") or 5178),
        "batchId": str(runtime.get("batchId") or ""),
        "updatedAt": str(runtime.get("updatedAt") or runtime.get("startedAt") or ""),
        "terminalStatus": str(runtime.get("terminalStatus") or ""),
    }


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def capcut_draft_root() -> Path:
    configured = str(CONFIG.get("capcut_draft_root") or "").strip()
    if configured:
        return resolve_path(configured)
    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local_app_data) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _stable_file_id(value: str) -> str:
    readable = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "")).strip("-.")[:48]
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]
    return f"{readable or 'item'}-{digest}"


def task_box_receipt_path(batch_id: str) -> Path:
    return TASK_BOX_RECEIPT_DIR / f"{_stable_file_id(batch_id)}.json"


def load_task_box_receipt(batch_id: str) -> dict[str, Any]:
    receipt = read_json_object(task_box_receipt_path(batch_id))
    if str(receipt.get("batchId") or "") != str(batch_id or ""):
        return {}
    expected_hash = str(receipt.get("receiptHash") or "")
    body = {key: value for key, value in receipt.items() if key != "receiptHash"}
    actual_hash = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return receipt if expected_hash and expected_hash == actual_hash else {}


def persist_task_box_receipt(box: dict[str, Any]) -> dict[str, Any]:
    """Create an immutable production-completion fact for one task box.

    An existing valid receipt is never replaced.  Upload/cloud fields are an
    append-only concern handled by reconciliation records; they cannot revoke
    the production completion asserted here.
    """
    batch_id = str(box.get("batchId") or "")
    if not batch_id:
        return {}
    existing = load_task_box_receipt(batch_id)
    if existing:
        return existing
    items = [item for item in box.get("items") or [] if isinstance(item, dict)]
    project_count = safe_int(box.get("projectCount"))
    total_videos = safe_int(box.get("totalVideos"))
    if (
        not project_count
        or safe_int(box.get("completedProjects")) != project_count
        or safe_int(box.get("completedVideos")) != total_videos
        or any(str(item.get("status") or "") != "completed" for item in items)
    ):
        return {}
    upload_tasks = upload_task_index()
    upload_evidence: list[dict[str, Any]] = []
    uploaded_total = 0
    cloud_verified_total = 0
    for item in items:
        remote_id = str(item.get("taskId") or "")
        rows = production_capcut_tasks(remote_task_id=remote_id)
        uploaded = 0
        cloud_verified = 0
        for row in rows:
            upload = upload_tasks.get(str(row.get("task_id") or ""), {})
            if str(upload.get("status") or "") != "uploaded":
                continue
            uploaded += 1
            cleanup = upload.get("cleanup") if isinstance(upload.get("cleanup"), dict) else {}
            if safe_int(upload.get("cloudSize") or cleanup.get("cloudVerifiedSize")) > 0:
                cloud_verified += 1
        uploaded_total += uploaded
        cloud_verified_total += cloud_verified
        upload_evidence.append({
            "canonicalTaskId": str(item.get("canonicalTaskId") or remote_id),
            "planned": safe_int(item.get("expected")),
            "uploaded": uploaded,
            "cloudVerified": cloud_verified,
        })
    upload_status = (
        "cloud_verified" if cloud_verified_total == total_videos
        else "uploaded_pending_verification" if uploaded_total == total_videos
        else "upload_pending"
    )
    body: dict[str, Any] = {
        "schemaVersion": 1,
        "batchId": batch_id,
        "productionDate": str(box.get("productionDate") or ""),
        "projectCount": project_count,
        "plannedVideoCount": total_videos,
        "completedVideoCount": total_videos,
        "projects": [
            {
                "canonicalTaskId": str(item.get("canonicalTaskId") or item.get("taskId") or ""),
                "taskId": str(item.get("taskId") or ""),
                "project": str(item.get("project") or ""),
                "material": str(item.get("material") or ""),
                "planned": safe_int(item.get("expected")),
                "completed": safe_int(item.get("finalCompleted")),
                "capcutTerminal": "completed",
            }
            for item in items
        ],
        "productionStatus": "completed_verified",
        "uploadStatus": upload_status,
        "uploadEvidence": upload_evidence,
        "completedAt": str(box.get("updatedAt") or now_iso()),
        "source": "receiver_manifest+capcut_formal_manifest",
        "createdAt": now_iso(),
    }
    body["receiptHash"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path = task_box_receipt_path(batch_id)
    if not path.exists():
        _write_json_atomic(path, body)
    return load_task_box_receipt(batch_id)


def control_command_path(command_id: str) -> Path:
    return CONTROL_COMMAND_DIR / f"{_stable_file_id(command_id)}.json"


def read_control_command(command_id: str) -> dict[str, Any]:
    value = read_json_object(control_command_path(command_id))
    return value if str(value.get("commandId") or "") == command_id else {}


def write_control_command(payload: dict[str, Any]) -> None:
    command_id = str(payload.get("commandId") or "")
    if not command_id:
        raise ValueError("control command requires commandId")
    _write_json_atomic(control_command_path(command_id), payload)


def list_control_commands() -> list[dict[str, Any]]:
    CONTROL_COMMAND_DIR.mkdir(parents=True, exist_ok=True)
    items = [read_json_object(path) for path in CONTROL_COMMAND_DIR.glob("*.json")]
    return sorted(
        [item for item in items if item.get("commandId")],
        key=lambda item: parse_time(str(item.get("requestedAt") or "")),
        reverse=True,
    )


def _capcut_draft_processes() -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(process.info.get("name") or "")
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        normalized = f"{name} {command}".lower()
        if (
            name.lower() in {"capcut.exe", "capcutbatchclient.exe"}
            or "capcutbatchclient" in normalized
        ):
            active.append({"pid": int(process.info.get("pid") or 0), "name": name or "CapCut"})
    return active


def _draft_timestamp(value: Any, fallback: float) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return fallback
    if number > 10_000_000_000:
        number /= 1_000_000
    return number if number > 0 else fallback


def _draft_directory_size(folder: Path) -> int:
    total = 0
    try:
        for current, _directories, files in os.walk(folder):
            for name in files:
                try:
                    total += (Path(current) / name).stat().st_size
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _draft_content_summary(folder: Path) -> tuple[str, str]:
    content_path = folder / "draft_content.json"
    try:
        raw = content_path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        raw = ""
    lowered = raw.lower()
    if "remote-inbox-" in lowered:
        category = "formal"
    elif "lab-" in lowered or "lab_" in lowered or "isolatedtest" in lowered:
        category = "lab"
    else:
        category = "manual_or_unknown"
    candidates = re.findall(
        r"[^\"\\/]{1,180}\.(?:mp4|mov|mkv|avi|webm)",
        raw,
        flags=re.IGNORECASE,
    )
    source_label = candidates[0].strip() if candidates else ""
    return category, source_label


def _capcut_draft_snapshot(root: Path, index_path: Path) -> str:
    digest = hashlib.sha256()
    try:
        digest.update(index_path.read_bytes())
    except OSError:
        digest.update(b"missing-index")
    try:
        folders = sorted(
            (item for item in root.iterdir() if item.is_dir() and not item.name.startswith(".")),
            key=lambda item: item.name.casefold(),
        )
    except OSError:
        folders = []
    for folder in folders:
        try:
            stat = folder.stat()
            digest.update(f"{folder.name}\0{stat.st_mtime_ns}\0".encode("utf-8", errors="replace"))
        except OSError:
            digest.update(f"{folder.name}\0missing\0".encode("utf-8", errors="replace"))
    return digest.hexdigest()


def _capcut_draft_inventory(root: Path | None = None) -> dict[str, Any]:
    root = (root or capcut_draft_root()).resolve()
    index_path = root / "root_meta_info.json"
    if not root.is_dir():
        return {
            "available": False, "message": "CapCut 草稿目录不存在", "snapshotToken": "",
            "items": [], "counts": {}, "runningProcesses": [],
        }
    try:
        index_payload = json.loads(index_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        index_payload = {}
    index_records = index_payload.get("all_draft_store") if isinstance(index_payload, dict) else []
    index_records = index_records if isinstance(index_records, list) else []
    index_by_id: dict[str, list[dict[str, Any]]] = {}
    for record in index_records:
        if not isinstance(record, dict):
            continue
        draft_id = str(record.get("draft_id") or "").strip()
        if draft_id:
            index_by_id.setdefault(draft_id, []).append(record)

    try:
        folders = [
            item for item in root.iterdir()
            if item.is_dir() and not item.name.startswith(".")
        ]
    except OSError:
        folders = []
    running = _capcut_draft_processes()
    now_epoch = time.time()
    items: list[dict[str, Any]] = []
    folder_ids: set[str] = set()
    for folder in folders:
        meta = read_json_object(folder / "draft_meta_info.json")
        draft_id = str(meta.get("draft_id") or "").strip()
        if draft_id:
            folder_ids.add(draft_id)
        records = index_by_id.get(draft_id, []) if draft_id else []
        record = records[0] if len(records) == 1 else {}
        try:
            folder_stat = folder.stat()
            modified_epoch = _draft_timestamp(
                meta.get("tm_draft_modified") or record.get("tm_draft_modified"),
                folder_stat.st_mtime,
            )
            created_epoch = _draft_timestamp(
                meta.get("tm_draft_create") or record.get("tm_draft_create"),
                folder_stat.st_ctime,
            )
        except OSError:
            modified_epoch = created_epoch = 0.0
        category, source_label = _draft_content_summary(folder)
        protected_reason = ""
        if running:
            protected_reason = "CapCut 或批处理客户端正在运行"
        elif not draft_id:
            protected_reason = "草稿缺少唯一 draft_id"
        elif len(records) > 1:
            protected_reason = "草稿索引存在重复 draft_id"
        elif modified_epoch and now_epoch - modified_epoch < 900:
            protected_reason = "草稿在最近15分钟内更新"
        name = str(meta.get("draft_name") or record.get("draft_name") or folder.name)
        items.append({
            "draftId": draft_id or f"unidentified:{hashlib.sha256(folder.name.encode('utf-8')).hexdigest()[:16]}",
            "name": name,
            "folderName": folder.name,
            "createdAt": datetime.fromtimestamp(created_epoch).astimezone().isoformat(timespec="seconds") if created_epoch else "",
            "updatedAt": datetime.fromtimestamp(modified_epoch).astimezone().isoformat(timespec="seconds") if modified_epoch else "",
            "sizeBytes": _draft_directory_size(folder),
            "category": category,
            "sourceLabel": source_label,
            "inIndex": len(records) == 1,
            "protected": bool(protected_reason),
            "protectedReason": protected_reason,
            "_path": str(folder),
        })
    stale_index_records = sum(
        len(records)
        for draft_id, records in index_by_id.items()
        if draft_id not in folder_ids
    )
    items.sort(key=lambda item: (parse_time(item.get("updatedAt")), item.get("name") or ""), reverse=True)
    counts = {
        "total": len(items),
        "formal": sum(item["category"] == "formal" for item in items),
        "lab": sum(item["category"] == "lab" for item in items),
        "manualOrUnknown": sum(item["category"] == "manual_or_unknown" for item in items),
        "protected": sum(bool(item["protected"]) for item in items),
        "staleIndexRecords": stale_index_records,
    }
    return {
        "available": True,
        "message": "草稿清单已读取",
        "snapshotToken": _capcut_draft_snapshot(root, index_path),
        "items": items,
        "counts": counts,
        "runningProcesses": running,
        "_root": str(root),
        "_index": str(index_path),
        "_indexPayload": index_payload,
    }


def capcut_draft_inventory_public(root: Path | None = None) -> dict[str, Any]:
    inventory = _capcut_draft_inventory(root)
    return {
        key: value for key, value in inventory.items()
        if not key.startswith("_") and key != "items"
    } | {
        "items": [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in inventory.get("items", [])
        ],
        "updatedAt": now_iso(),
    }


def _selected_capcut_drafts(
    draft_ids: list[str],
    *,
    root: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = list(dict.fromkeys(str(value or "").strip() for value in draft_ids if str(value or "").strip()))
    if not normalized:
        raise HTTPException(status_code=400, detail="请至少选择一个草稿")
    if len(normalized) > 500 or any(len(value) > 160 for value in normalized):
        raise HTTPException(status_code=400, detail="选择的草稿数量或标识无效")
    inventory = _capcut_draft_inventory(root)
    if not inventory.get("available"):
        raise HTTPException(status_code=503, detail=str(inventory.get("message") or "草稿目录不可用"))
    by_id = {str(item.get("draftId") or ""): item for item in inventory.get("items", [])}
    missing = [value for value in normalized if value not in by_id]
    if missing:
        raise HTTPException(status_code=409, detail=f"有 {len(missing)} 个草稿已变化，请刷新清单后重试")
    return inventory, [by_id[value] for value in normalized]


def preview_capcut_draft_cleanup(draft_ids: list[str], *, root: Path | None = None) -> dict[str, Any]:
    inventory, selected = _selected_capcut_drafts(draft_ids, root=root)
    deletable = [item for item in selected if not item.get("protected")]
    blocked = [item for item in selected if item.get("protected")]
    return {
        "state": "preview",
        "snapshotToken": str(inventory.get("snapshotToken") or ""),
        "selectedCount": len(selected),
        "deletableCount": len(deletable),
        "blockedCount": len(blocked),
        "sizeBytes": sum(safe_int(item.get("sizeBytes")) for item in deletable),
        "containsManualOrUnknown": any(item.get("category") == "manual_or_unknown" for item in deletable),
        "deletable": [
            {"draftId": item["draftId"], "name": item["name"], "category": item["category"]}
            for item in deletable
        ],
        "blocked": [
            {
                "draftId": item["draftId"], "name": item["name"],
                "reason": item.get("protectedReason") or "草稿受保护",
            }
            for item in blocked
        ],
        "message": f"可移入回收站 {len(deletable)} 个，受保护 {len(blocked)} 个",
    }


def _recycle_directory(path: Path) -> None:
    if os.name != "nt":
        raise OSError("草稿回收站操作仅支持 Windows")

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_bool),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    operation = SHFILEOPSTRUCTW()
    operation.wFunc = 3  # FO_DELETE
    operation.pFrom = str(path) + "\0\0"
    operation.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400  # undo, no confirm, silent, no UI errors
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0 or operation.fAnyOperationsAborted:
        raise OSError(f"Windows 回收站操作失败（代码 {result}）")


def execute_capcut_draft_cleanup(
    draft_ids: list[str],
    snapshot_token: str,
    *,
    include_unknown: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    with CAPCUT_DRAFT_LOCK:
        inventory, selected = _selected_capcut_drafts(draft_ids, root=root)
        if str(inventory.get("snapshotToken") or "") != str(snapshot_token or ""):
            raise HTTPException(status_code=409, detail="草稿清单已变化，请重新预览")
        running = inventory.get("runningProcesses") or []
        if running:
            raise HTTPException(status_code=409, detail="CapCut 或批处理客户端正在运行，请全部关闭后再删除草稿")
        blocked = [item for item in selected if item.get("protected")]
        if blocked:
            raise HTTPException(status_code=409, detail=f"所选草稿中有 {len(blocked)} 个正在使用或身份不完整")
        if any(item.get("category") == "manual_or_unknown" for item in selected) and not include_unknown:
            raise HTTPException(status_code=400, detail="包含人工或来源不明草稿，需要额外确认")

        root_path = Path(str(inventory["_root"])).resolve()
        index_path = Path(str(inventory["_index"])).resolve()
        index_payload = inventory.get("_indexPayload")
        if not isinstance(index_payload, dict):
            raise HTTPException(status_code=409, detail="CapCut 草稿索引无效，已停止删除")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = CAPCUT_DRAFT_CLEANUP_BACKUP_DIR / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)
        try:
            (backup_dir / "root_meta_info.json").write_bytes(index_path.read_bytes())
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"草稿索引备份失败：{exc}") from exc
        manifest = {
            "cleanupId": f"draft-cleanup-{uuid.uuid4().hex[:12]}",
            "createdAt": now_iso(),
            "snapshotToken": snapshot_token,
            "drafts": [
                {
                    "draftId": item["draftId"], "name": item["name"],
                    "category": item["category"], "folderName": item["folderName"],
                }
                for item in selected
            ],
        }
        _write_json_atomic(backup_dir / "cleanup-manifest.json", manifest)

        original_records = index_payload.get("all_draft_store")
        original_records = original_records if isinstance(original_records, list) else []
        selected_ids = {str(item["draftId"]) for item in selected}
        provisional = dict(index_payload)
        provisional["all_draft_store"] = [
            record for record in original_records
            if not (isinstance(record, dict) and str(record.get("draft_id") or "") in selected_ids)
        ]
        try:
            _write_json_atomic(index_path, provisional)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"草稿索引更新失败：{exc}") from exc

        removed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for item in selected:
            if _capcut_draft_processes():
                failed.append({"draftId": item["draftId"], "name": item["name"], "reason": "删除过程中 CapCut 被启动"})
                continue
            folder = Path(str(item.get("_path") or "")).resolve()
            try:
                if folder.parent != root_path or not folder.is_dir():
                    raise OSError("草稿目录身份已经变化")
                _recycle_directory(folder)
                removed.append({"draftId": item["draftId"], "name": item["name"]})
            except OSError as exc:
                failed.append({"draftId": item["draftId"], "name": item["name"], "reason": str(exc)})

        if failed:
            successful_ids = {str(item["draftId"]) for item in removed}
            final_index = dict(index_payload)
            final_index["all_draft_store"] = [
                record for record in original_records
                if not (isinstance(record, dict) and str(record.get("draft_id") or "") in successful_ids)
            ]
            _write_json_atomic(index_path, final_index)

        result = {
            "cleanupId": manifest["cleanupId"],
            "state": "completed" if not failed else ("partial" if removed else "failed"),
            "message": f"已移入回收站 {len(removed)} 个草稿；失败 {len(failed)} 个",
            "removedCount": len(removed),
            "failedCount": len(failed),
            "removed": removed,
            "failed": failed,
            "updatedAt": now_iso(),
        }
        _write_json_atomic(CAPCUT_DRAFT_CLEANUP_STATUS_PATH, result)
        save_control_action("capcutDraftCleanup", result)
        return result


def _path_key(value: str | Path) -> str:
    try:
        return str(Path(value).resolve()).replace("/", "\\").casefold()
    except (OSError, ValueError):
        return str(value).replace("/", "\\").casefold()


def _audio_producer_processes() -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(process.info.get("name") or "")
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        normalized = f"{name} {command}".casefold()
        if "runbatch.js" in normalized or "batchvoiceclient" in normalized:
            active.append({"pid": int(process.info.get("pid") or 0), "name": name or "Fish配音"})
    return active


def _audio_reference_inventory() -> dict[str, list[dict[str, Any]]]:
    references: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str]] = set()

    def add(item: dict[str, Any], *, source: str, active: bool = False, state: str = "") -> None:
        audio_path = str(item.get("audioPath") or item.get("audio_path") or "").strip()
        if not audio_path:
            return
        key = _path_key(audio_path)
        task_id = str(
            item.get("taskId") or item.get("task_id")
            or item.get("canonicalTaskId") or item.get("canonical_task_id") or ""
        ).strip()
        record_key = (key, task_id, source)
        if record_key in seen:
            return
        seen.add(record_key)
        references.setdefault(key, []).append({
            "taskId": task_id,
            "canonicalTaskId": str(
                item.get("canonicalTaskId") or item.get("canonical_task_id")
                or item.get("remotePipelineTaskId") or item.get("remote_pipeline_task_id") or ""
            ).strip(),
            "date": str(item.get("productionDate") or item.get("date") or item.get("date_label") or "").strip(),
            "project": str(item.get("project") or "").strip(),
            "material": str(item.get("material") or "").strip(),
            "language": str(item.get("language") or "").strip(),
            "audioBatch": str(item.get("audioBatch") or item.get("audio_batch") or "").strip(),
            "state": state or str(item.get("state") or item.get("status") or "").strip(),
            "phase": str(item.get("phaseText") or item.get("phase_text") or item.get("currentPhase") or "").strip(),
            "active": bool(active),
            "source": source,
            "_path": audio_path,
        })

    # The task table is the authoritative source for active/waiting recovery
    # references. Every non-completed row remains protected.
    try:
        for item in STORE.tasks():
            task_state = str(item.get("state") or "")
            add(
                item,
                source="当前第五步任务",
                active=task_state not in COMPLETED_STATES,
                state=task_state,
            )
    except (OSError, sqlite3.Error):
        pass

    # The immutable Step 4/5 metadata supplies project identity even after a
    # task has left the current table.
    try:
        for item in COLLECTOR.metadata.values():
            add(item, source="正式任务清单", active=False)
    except (AttributeError, RuntimeError):
        pass

    handoff = read_json_object(resolve_path(str(CONFIG.get("voice_handoff_file") or "")))
    handoff_state = str(handoff.get("status") or "").casefold()
    handoff_active = handoff_state not in {"", "completed", "completed_with_errors", "failed", "cancelled"}
    for field in ("completedItems", "failedItems", "items", "tasks"):
        values = handoff.get(field)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    add(item, source="Fish配音交接", active=handoff_active, state=handoff_state)

    upload = read_json_object(resolve_path(str(CONFIG.get("upload_status_file") or "")))
    upload_tasks = upload.get("tasks") if isinstance(upload.get("tasks"), dict) else {}
    for item in upload_tasks.values():
        if isinstance(item, dict):
            add(item, source="上传登记", active=False)
    return references


def _registered_audio_roots(references: dict[str, list[dict[str, Any]]]) -> list[Path]:
    roots: list[Path] = []
    configured = CONFIG.get("audio_roots")
    if isinstance(configured, list):
        for value in configured:
            if str(value or "").strip():
                roots.append(resolve_path(str(value)))

    if not roots:
        for records in references.values():
            for record in records:
                path = Path(str(record.get("_path") or ""))
                if not path.is_absolute():
                    continue
                chosen: Path | None = None
                for parent in path.parents:
                    if parent.name == "音频":
                        chosen = parent
                        break
                if chosen is None and path.parent.name.endswith("音频"):
                    chosen = path.parent.parent
                roots.append(chosen or path.parent)

    unique: dict[str, Path] = {}
    for root in roots:
        try:
            resolved = root.resolve()
        except (OSError, ValueError):
            continue
        if resolved.is_dir():
            unique.setdefault(_path_key(resolved), resolved)
    return list(unique.values())


def _audio_snapshot(items: list[dict[str, Any]], roots: list[Path]) -> str:
    digest = hashlib.sha256()
    for root in sorted(roots, key=lambda value: _path_key(value)):
        digest.update(f"root\0{_path_key(root)}\0".encode("utf-8", errors="replace"))
    for item in sorted(items, key=lambda value: str(value.get("audioId") or "")):
        digest.update(
            (
                f"{item.get('audioId')}\0{item.get('sizeBytes')}\0{item.get('_mtimeNs')}\0"
                f"{item.get('protected')}\0{item.get('protectedReason')}\0"
            ).encode("utf-8", errors="replace")
        )
    return digest.hexdigest()


def _audio_inventory(
    *,
    roots: list[Path] | None = None,
    references: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    references = references if references is not None else _audio_reference_inventory()
    roots = roots if roots is not None else _registered_audio_roots(references)
    if not roots:
        return {
            "available": False,
            "message": "尚未从正式任务登记中找到音频目录",
            "snapshotToken": "",
            "items": [],
            "counts": {"total": 0, "protected": 0, "deletable": 0},
            "producerProcesses": _audio_producer_processes(),
        }

    producer_processes = _audio_producer_processes()
    now_epoch = time.time()
    items: list[dict[str, Any]] = []
    visited: set[str] = set()
    for root in roots:
        try:
            candidates = root.rglob("*")
            for path in candidates:
                if not path.is_file() or path.suffix.casefold() not in AUDIO_EXTENSIONS:
                    continue
                path_key = _path_key(path)
                if path_key in visited:
                    continue
                visited.add(path_key)
                try:
                    stat = path.stat()
                    relative = path.relative_to(root)
                except (OSError, ValueError):
                    continue
                file_references = references.get(path_key, [])
                active_references = [item for item in file_references if item.get("active")]
                protected_reason = ""
                if active_references:
                    current = active_references[0]
                    identity = " / ".join(
                        value for value in (
                            str(current.get("project") or ""),
                            str(current.get("material") or ""),
                            str(current.get("language") or ""),
                        ) if value
                    ) or str(current.get("taskId") or "当前任务")
                    phase = str(current.get("phase") or current.get("state") or "等待恢复")
                    protected_reason = f"任务正在使用，禁止删除：{identity} · {phase}"
                elif producer_processes and now_epoch - stat.st_mtime < 900:
                    protected_reason = "Fish配音正在运行，且该音频在最近15分钟内更新"

                primary = file_references[0] if file_references else {}
                date_label = str(primary.get("date") or "")
                if not date_label:
                    date_label = next(
                        (part for part in relative.parts if re.fullmatch(r"\d{1,2}\.\d{1,2}", part)),
                        "",
                    )
                audio_id = hashlib.sha256(path_key.encode("utf-8", errors="replace")).hexdigest()[:24]
                items.append({
                    "audioId": audio_id,
                    "name": path.name,
                    "relativePath": str(Path(root.name) / relative).replace("\\", "/"),
                    "rootLabel": root.name,
                    "sizeBytes": stat.st_size,
                    "createdAt": datetime.fromtimestamp(stat.st_ctime).astimezone().isoformat(timespec="seconds"),
                    "updatedAt": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
                    "date": date_label,
                    "project": str(primary.get("project") or ""),
                    "material": str(primary.get("material") or ""),
                    "language": str(primary.get("language") or ""),
                    "audioBatch": str(primary.get("audioBatch") or date_label),
                    "taskState": str(primary.get("state") or ("历史/未引用" if not file_references else "已登记")),
                    "referenceCount": len(file_references),
                    "protected": bool(protected_reason),
                    "protectedReason": protected_reason,
                    "_path": str(path),
                    "_root": str(root),
                    "_mtimeNs": stat.st_mtime_ns,
                })
        except OSError:
            continue

    items.sort(key=lambda item: (parse_time(item.get("updatedAt")), item.get("name") or ""), reverse=True)
    counts = {
        "total": len(items),
        "protected": sum(bool(item.get("protected")) for item in items),
        "deletable": sum(not item.get("protected") for item in items),
        "sizeBytes": sum(safe_int(item.get("sizeBytes")) for item in items),
    }
    return {
        "available": True,
        "message": "音频清单已读取",
        "snapshotToken": _audio_snapshot(items, roots),
        "items": items,
        "counts": counts,
        "producerProcesses": producer_processes,
        "_roots": [str(root) for root in roots],
    }


def audio_inventory_public() -> dict[str, Any]:
    inventory = _audio_inventory()
    return {
        key: value for key, value in inventory.items()
        if not key.startswith("_") and key != "items"
    } | {
        "items": [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in inventory.get("items", [])
        ],
        "updatedAt": now_iso(),
    }


def _selected_audio_files(audio_ids: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = list(dict.fromkeys(str(value or "").strip() for value in audio_ids if str(value or "").strip()))
    if not normalized:
        raise HTTPException(status_code=400, detail="请至少选择一个音频文件")
    if len(normalized) > 2000 or any(len(value) > 80 for value in normalized):
        raise HTTPException(status_code=400, detail="选择的音频数量或标识无效")
    inventory = _audio_inventory()
    if not inventory.get("available"):
        raise HTTPException(status_code=503, detail=str(inventory.get("message") or "音频目录不可用"))
    by_id = {str(item.get("audioId") or ""): item for item in inventory.get("items", [])}
    missing = [value for value in normalized if value not in by_id]
    if missing:
        raise HTTPException(status_code=409, detail=f"有 {len(missing)} 个音频文件状态已变化，请刷新后重新对账")
    return inventory, [by_id[value] for value in normalized]


def preview_audio_cleanup(audio_ids: list[str]) -> dict[str, Any]:
    inventory, selected = _selected_audio_files(audio_ids)
    deletable = [item for item in selected if not item.get("protected")]
    blocked = [item for item in selected if item.get("protected")]
    return {
        "state": "preview",
        "snapshotToken": str(inventory.get("snapshotToken") or ""),
        "selectedCount": len(selected),
        "deletableCount": len(deletable),
        "blockedCount": len(blocked),
        "sizeBytes": sum(safe_int(item.get("sizeBytes")) for item in deletable),
        "deletable": [
            {"audioId": item["audioId"], "name": item["name"], "relativePath": item["relativePath"]}
            for item in deletable
        ],
        "blocked": [
            {
                "audioId": item["audioId"],
                "name": item["name"],
                "reason": item.get("protectedReason") or "音频受活动任务保护",
            }
            for item in blocked
        ],
        "message": f"可移入回收站 {len(deletable)} 个音频；受活动任务保护 {len(blocked)} 个",
    }


def execute_audio_cleanup(audio_ids: list[str], snapshot_token: str) -> dict[str, Any]:
    with AUDIO_CLEANUP_LOCK:
        inventory, selected = _selected_audio_files(audio_ids)
        blocked = [item for item in selected if item.get("protected")]
        if blocked:
            reason = str(blocked[0].get("protectedReason") or "任务正在使用，禁止删除")
            result = {
                "state": "blocked",
                "message": reason,
                "removedCount": 0,
                "blockedCount": len(blocked),
                "blocked": [
                    {"name": item["name"], "reason": item.get("protectedReason") or reason}
                    for item in blocked
                ],
                "updatedAt": now_iso(),
            }
            _write_json_atomic(AUDIO_CLEANUP_STATUS_PATH, result)
            save_control_action("audioCleanup", result)
            raise HTTPException(status_code=409, detail=reason)

        if str(inventory.get("snapshotToken") or "") != str(snapshot_token or ""):
            result = {
                "state": "blocked",
                "message": "音频状态已变化，请刷新清单并重新对账",
                "removedCount": 0,
                "blockedCount": len(selected),
                "updatedAt": now_iso(),
            }
            _write_json_atomic(AUDIO_CLEANUP_STATUS_PATH, result)
            save_control_action("audioCleanup", result)
            raise HTTPException(status_code=409, detail=result["message"])

        allowed_roots = [Path(value).resolve() for value in inventory.get("_roots", [])]
        cleanup_id = f"audio-cleanup-{uuid.uuid4().hex[:12]}"
        manifest = {
            "cleanupId": cleanup_id,
            "createdAt": now_iso(),
            "snapshotToken": snapshot_token,
            "files": [
                {
                    "audioId": item["audioId"],
                    "name": item["name"],
                    "relativePath": item["relativePath"],
                    "path": item["_path"],
                    "sizeBytes": item["sizeBytes"],
                }
                for item in selected
            ],
        }
        AUDIO_CLEANUP_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(AUDIO_CLEANUP_BACKUP_DIR / f"{cleanup_id}.json", manifest)

        removed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for item in selected:
            path = Path(str(item.get("_path") or "")).resolve()
            try:
                root = next((value for value in allowed_roots if path.is_relative_to(value)), None)
                if root is None or path.suffix.casefold() not in AUDIO_EXTENSIONS:
                    raise OSError("音频路径不在登记目录或文件类型不受支持")
                if not path.exists():
                    removed.append({
                        "audioId": item["audioId"],
                        "name": item["name"],
                        "state": "already_missing",
                    })
                    continue
                if not path.is_file():
                    raise OSError("目标不是音频文件")
                _recycle_directory(path)
                removed.append({
                    "audioId": item["audioId"],
                    "name": item["name"],
                    "state": "recycled",
                })
            except OSError as exc:
                failed.append({
                    "audioId": item["audioId"],
                    "name": item["name"],
                    "reason": str(exc),
                })

        result = {
            "cleanupId": cleanup_id,
            "state": "completed" if not failed else ("partial" if removed else "failed"),
            "message": f"已移入回收站 {sum(item['state'] == 'recycled' for item in removed)} 个音频；失败 {len(failed)} 个",
            "removedCount": len(removed),
            "failedCount": len(failed),
            "removed": removed,
            "failed": failed,
            "updatedAt": now_iso(),
        }
        _write_json_atomic(AUDIO_CLEANUP_STATUS_PATH, result)
        save_control_action("audioCleanup", result)
        return result


PRODUCTION_FILE_CATEGORY_LABELS = {
    "subtitle_output": "第1+2步去字幕视频",
    "stitch_output": "第4步拼接视频",
    "capcut_temporary": "第5步 CapCut 临时成片",
    "local_final": "本地正式成片",
    "prepared_sample": "任务专属预处理样品",
    "capcut_test": "CapCut 测试及首帧文件",
}


def _configured_directory_list(name: str) -> list[Path]:
    values = CONFIG.get(name)
    if not isinstance(values, list):
        return []
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        if not str(value or "").strip():
            continue
        try:
            path = resolve_path(str(value)).resolve()
        except (OSError, ValueError):
            continue
        key = _path_key(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _workbench_root() -> Path:
    project_status = str(CONFIG.get("download_project_status_file") or "").strip()
    if project_status:
        try:
            status_path = resolve_path(project_status).resolve()
            if status_path.parent.name == "download" and status_path.parent.parent.name == "handoff":
                return status_path.parent.parent.parent
        except (OSError, ValueError):
            pass
    root = resolve_path(str(CONFIG.get("workbench_dir") or "")).resolve()
    if (root / "handoff").is_dir():
        return root
    nested = root / "workbench"
    return nested if (nested / "handoff").is_dir() else root


def _canonical_task_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    root = _workbench_root() / "handoff" / "task_inbox" / "imported"
    if not root.is_dir():
        return aliases
    for path in root.glob("*.json"):
        payload = read_json_object(path)
        task_id = str(payload.get("taskId") or path.stem).strip()
        canonical_id = str(
            payload.get("canonicalTaskId")
            or payload.get("replenishForTaskId")
            or payload.get("mergedIntoParentTaskId")
            or task_id
        ).strip()
        if task_id and canonical_id:
            aliases[task_id] = canonical_id
    return aliases


def _canonical_task_id(item: dict[str, Any], aliases: dict[str, str] | None = None) -> str:
    aliases = aliases or {}
    direct = str(
        item.get("canonicalTaskId")
        or item.get("canonical_task_id")
        or item.get("remotePipelineTaskId")
        or item.get("remote_pipeline_task_id")
        or ""
    ).strip()
    if direct:
        return aliases.get(direct, direct)
    for field in ("sourceVideoPath", "videoPath", "localPath", "generationIdentity"):
        value = str(item.get(field) or "")
        match = re.search(r"(?:remote-)?(inbox-\d{14}-[0-9a-fA-F]{8})", value)
        if match:
            found = match.group(1)
            return aliases.get(found, found)
    task_id = str(item.get("taskId") or item.get("task_id") or "").strip()
    return aliases.get(task_id, task_id if task_id.startswith("inbox-") else "")


def _project_status_records() -> dict[str, dict[str, Any]]:
    payload = read_json_object(resolve_path(str(CONFIG.get("download_project_status_file") or "")))
    items = payload.get("items") if isinstance(payload.get("items"), dict) else {}
    return {
        str(task_id): dict(item)
        for task_id, item in items.items()
        if isinstance(item, dict)
    }


def _upload_task_records() -> list[dict[str, Any]]:
    payload = read_json_object(resolve_path(str(CONFIG.get("upload_status_file") or "")))
    tasks = payload.get("tasks")
    if isinstance(tasks, dict):
        return [dict(item) for item in tasks.values() if isinstance(item, dict)]
    if isinstance(tasks, list):
        return [dict(item) for item in tasks if isinstance(item, dict)]
    return []


def _cloud_verification(item: dict[str, Any]) -> tuple[bool, str]:
    if str(item.get("status") or "").casefold() != "uploaded":
        return False, "对应成片尚未上传完成"
    cleanup = item.get("cleanup") if isinstance(item.get("cleanup"), dict) else {}
    verified_at = str(cleanup.get("cloudVerifiedAt") or "").strip()
    verified_size = safe_int(cleanup.get("cloudVerifiedSize"))
    cloud_size = safe_int(item.get("cloudSize"))
    if not verified_at:
        return False, "尚无云端实时核验记录"
    if not str(item.get("fsId") or "").strip():
        return False, "云端文件身份未登记"
    if verified_size <= 0 or cloud_size <= 0 or verified_size != cloud_size:
        return False, "云端文件大小核验不一致"
    return True, ""


def _production_active_projects() -> tuple[set[str], dict[str, str]]:
    active: set[str] = set()
    reasons: dict[str, str] = {}
    aliases = _canonical_task_aliases()
    for canonical_id, record in _project_status_records().items():
        status = str(record.get("pipelineStatus") or record.get("status") or "").casefold()
        if status != "completed":
            active.add(canonical_id)
            reasons[canonical_id] = str(record.get("pipelineStateText") or record.get("stateText") or "项目尚未完成")
    try:
        for item in STORE.tasks():
            state = str(item.get("state") or "").strip()
            if state in COMPLETED_STATES:
                continue
            canonical_id = _canonical_task_id(item, aliases)
            if canonical_id:
                active.add(canonical_id)
                reasons[canonical_id] = str(item.get("phaseText") or item.get("error") or state or "任务正在等待或恢复")
    except (OSError, sqlite3.Error):
        pass
    return active, reasons


def _isolated_runtime_processes() -> list[dict[str, Any]]:
    markers = [
        str(value).casefold()
        for value in (CONFIG.get("isolated_runtime_markers") or [])
        if str(value or "").strip()
    ]
    active: list[dict[str, Any]] = []
    if not markers:
        return active
    for process in psutil.process_iter(["pid", "name", "cmdline", "exe"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            haystack = f"{process.info.get('name') or ''} {process.info.get('exe') or ''} {command}".casefold()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if any(marker in haystack for marker in markers):
            active.append({
                "pid": int(process.info.get("pid") or 0),
                "name": str(process.info.get("name") or "隔离测试程序"),
            })
    return active


def _is_baidu_sync_path(path: Path) -> bool:
    key = _path_key(path)
    for root in _configured_directory_list("baidu_sync_roots"):
        try:
            if path.is_relative_to(root):
                return True
        except (OSError, ValueError):
            continue
    return "baidunetdisk" in key or "百度网盘同步空间" in key


def _production_file_identity(
    *,
    path: Path,
    category: str,
    root: Path,
    task: dict[str, Any] | None = None,
    canonical_task_id: str = "",
    protected_reason: str = "",
    default_selected: bool = False,
    reference_count: int = 0,
) -> dict[str, Any] | None:
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        if not resolved.is_file() or not resolved.is_relative_to(root_resolved):
            return None
        stat = resolved.stat()
        relative = resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    task = task or {}
    if resolved.suffix.casefold() not in PRODUCTION_VIDEO_EXTENSIONS:
        return None
    if _is_baidu_sync_path(resolved):
        protected_reason = "文件位于百度网盘同步目录，永久禁止清理"
    task_state = str(task.get("status") or task.get("state") or "")
    file_id = hashlib.sha256(
        f"{category}\0{_path_key(resolved)}".encode("utf-8", errors="replace")
    ).hexdigest()[:24]
    return {
        "fileId": file_id,
        "name": resolved.name,
        "relativePath": str(Path(root_resolved.name) / relative).replace("\\", "/"),
        "rootLabel": root_resolved.name,
        "category": category,
        "categoryLabel": PRODUCTION_FILE_CATEGORY_LABELS[category],
        "sizeBytes": stat.st_size,
        "createdAt": datetime.fromtimestamp(stat.st_ctime).astimezone().isoformat(timespec="seconds"),
        "updatedAt": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
        "date": str(task.get("productionDate") or task.get("date") or ""),
        "project": str(task.get("project") or ""),
        "material": str(task.get("material") or ""),
        "language": str(task.get("language") or ""),
        "taskId": str(task.get("taskId") or ""),
        "canonicalTaskId": canonical_task_id,
        "taskState": task_state or ("测试文件" if category == "capcut_test" else "已登记"),
        "cloudVerified": not bool(protected_reason) and category != "capcut_test",
        "referenceCount": reference_count,
        "protected": bool(protected_reason),
        "protectedReason": protected_reason,
        "defaultSelected": bool(default_selected and not protected_reason and category != "capcut_test"),
        "_path": str(resolved),
        "_root": str(root_resolved),
        "_mtimeNs": stat.st_mtime_ns,
    }


def _production_snapshot(items: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in sorted(items, key=lambda value: str(value.get("fileId") or "")):
        digest.update(
            (
                f"{item.get('fileId')}\0{item.get('sizeBytes')}\0{item.get('_mtimeNs')}\0"
                f"{item.get('protected')}\0{item.get('protectedReason')}\0"
                f"{item.get('referenceCount')}\0"
            ).encode("utf-8", errors="replace")
        )
    return digest.hexdigest()


def _production_file_inventory() -> dict[str, Any]:
    aliases = _canonical_task_aliases()
    projects = _project_status_records()
    active_projects, active_reasons = _production_active_projects()
    upload_tasks = _upload_task_records()
    upload_by_canonical: dict[str, list[dict[str, Any]]] = {}
    upload_by_path: dict[str, dict[str, Any]] = {}
    for task in upload_tasks:
        canonical_id = _canonical_task_id(task, aliases)
        if canonical_id:
            upload_by_canonical.setdefault(canonical_id, []).append(task)
        for field in (
            "sourceVideoPath", "temporaryOutputPath", "localPath",
            "postProcessWorkingPath", "preparedSamplePath",
        ):
            value = str(task.get(field) or "").strip()
            if value:
                upload_by_path[_path_key(value)] = task

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any] | None) -> None:
        if not item:
            return
        path_key = _path_key(str(item.get("_path") or ""))
        if path_key in seen:
            return
        seen.add(path_key)
        items.append(item)

    # Step 1+2 is registered by exact outputPath in the per-task download
    # checkpoints. Replenishment checkpoints are folded into their parent ID.
    checkpoint_root = _workbench_root() / "handoff" / "download" / "checkpoints"
    if checkpoint_root.is_dir():
        for checkpoint_path in checkpoint_root.glob("*.json"):
            checkpoint = read_json_object(checkpoint_path)
            source_task_id = str(checkpoint.get("taskId") or checkpoint_path.stem)
            canonical_id = aliases.get(source_task_id, source_task_id)
            project = projects.get(canonical_id, {})
            related_uploads = upload_by_canonical.get(canonical_id, [])
            cloud_results = [_cloud_verification(task) for task in related_uploads]
            project_complete = str(project.get("pipelineStatus") or project.get("status") or "").casefold() == "completed"
            shared_reason = ""
            if not project:
                shared_reason = "旧任务缺少完整项目身份，无法安全关联"
            elif canonical_id in active_projects:
                shared_reason = f"项目仍在活动或恢复：{active_reasons.get(canonical_id, '尚未结束')}"
            elif not project_complete:
                shared_reason = "项目尚未完成，共享去字幕视频仍可能被引用"
            elif not related_uploads:
                shared_reason = "没有找到该项目的正式上传清单"
            elif any(not ok for ok, _ in cloud_results):
                shared_reason = next(reason for ok, reason in cloud_results if not ok)
            values = checkpoint.get("items") if isinstance(checkpoint.get("items"), dict) else {}
            for record in values.values():
                if not isinstance(record, dict) or str(record.get("status") or "").casefold() != "completed":
                    continue
                value = str(record.get("outputPath") or "").strip()
                if not value:
                    continue
                path = Path(value)
                root = resolve_path(str(CONFIG.get("download_root") or path.parent))
                add(_production_file_identity(
                    path=path,
                    category="subtitle_output",
                    root=root,
                    task=project,
                    canonical_task_id=canonical_id,
                    protected_reason=shared_reason,
                    default_selected=not shared_reason,
                    reference_count=len(related_uploads),
                ))

    def registered_task_reason(task: dict[str, Any], canonical_id: str) -> str:
        if not canonical_id:
            return "旧任务缺少完整身份，无法安全关联"
        if canonical_id in active_projects:
            return f"任务正在运行、等待或恢复：{active_reasons.get(canonical_id, '尚未结束')}"
        verified, reason = _cloud_verification(task)
        return "" if verified else reason

    # These paths are immutable fields in the upload task registry. We never
    # discover them through filename similarity.
    field_categories = (
        ("sourceVideoPath", "stitch_output"),
        ("temporaryOutputPath", "capcut_temporary"),
        ("localPath", "local_final"),
    )
    for task in upload_tasks:
        canonical_id = _canonical_task_id(task, aliases)
        reason = registered_task_reason(task, canonical_id)
        for field, category in field_categories:
            value = str(task.get(field) or "").strip()
            if not value:
                continue
            path = Path(value)
            if category == "stitch_output":
                root = resolve_path(str(CONFIG.get("generation_output_root") or path.parent))
            else:
                # final_output_root can be a broad drive. The exact registered
                # path remains the real authorization boundary.
                root = path.parent
            add(_production_file_identity(
                path=path,
                category=category,
                root=root,
                task=task,
                canonical_task_id=canonical_id,
                protected_reason=reason,
                default_selected=not reason,
                reference_count=1,
            ))

    # Prepared samples are task-specific FFmpeg copies. Registered files inherit
    # their upload verification; unregistered legacy copies stay visible but
    # cannot be selected.
    for root in _configured_directory_list("prepared_sample_roots"):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in PRODUCTION_VIDEO_EXTENSIONS:
                continue
            task = upload_by_path.get(_path_key(path))
            canonical_id = _canonical_task_id(task, aliases) if task else ""
            reason = (
                registered_task_reason(task, canonical_id)
                if task else "专属样品缺少正式任务登记，无法安全关联"
            )
            add(_production_file_identity(
                path=path,
                category="prepared_sample",
                root=root,
                task=task,
                canonical_task_id=canonical_id,
                protected_reason=reason,
                default_selected=bool(task) and not reason,
                reference_count=1 if task else 0,
            ))

    # The two explicit test roots are intentionally never default-selected.
    # They can be recycled only while the isolated workbench/client is stopped.
    isolated_processes = _isolated_runtime_processes()
    test_reason = ""
    if isolated_processes:
        pids = "、".join(str(item.get("pid")) for item in isolated_processes[:5])
        test_reason = f"隔离工作台或隔离 CapCut 正在运行（PID {pids}）"
    for root in _configured_directory_list("capcut_test_roots"):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.casefold() not in PRODUCTION_VIDEO_EXTENSIONS:
                continue
            add(_production_file_identity(
                path=path,
                category="capcut_test",
                root=root,
                protected_reason=test_reason,
                default_selected=False,
                reference_count=0,
            ))

    items.sort(
        key=lambda item: (
            list(PRODUCTION_FILE_CATEGORY_LABELS).index(str(item.get("category"))),
            -parse_time(item.get("updatedAt")),
            str(item.get("name") or ""),
        )
    )
    counts: dict[str, Any] = {
        "total": len(items),
        "protected": sum(bool(item.get("protected")) for item in items),
        "deletable": sum(not item.get("protected") for item in items),
        "defaultSelected": sum(bool(item.get("defaultSelected")) for item in items),
        "sizeBytes": sum(safe_int(item.get("sizeBytes")) for item in items),
        "categories": {},
    }
    for category, label in PRODUCTION_FILE_CATEGORY_LABELS.items():
        category_items = [item for item in items if item.get("category") == category]
        counts["categories"][category] = {
            "label": label,
            "total": len(category_items),
            "sizeBytes": sum(safe_int(item.get("sizeBytes")) for item in category_items),
            "protected": sum(bool(item.get("protected")) for item in category_items),
            "deletable": sum(not item.get("protected") for item in category_items),
        }
    return {
        "available": bool(items),
        "message": "生产文件清单已读取" if items else "尚未发现已登记的生产文件",
        "snapshotToken": _production_snapshot(items),
        "items": items,
        "counts": counts,
        "isolatedProcesses": isolated_processes,
    }


def production_file_inventory_public() -> dict[str, Any]:
    inventory = _production_file_inventory()
    return {
        key: value for key, value in inventory.items()
        if not key.startswith("_") and key != "items"
    } | {
        "items": [
            {key: value for key, value in item.items() if not key.startswith("_")}
            for item in inventory.get("items", [])
        ],
        "updatedAt": now_iso(),
    }


def _selected_production_files(file_ids: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized = list(dict.fromkeys(str(value or "").strip() for value in file_ids if str(value or "").strip()))
    if not normalized:
        raise HTTPException(status_code=400, detail="请至少选择一个生产文件")
    if len(normalized) > 5000 or any(len(value) > 80 for value in normalized):
        raise HTTPException(status_code=400, detail="选择的生产文件数量或标识无效")
    inventory = _production_file_inventory()
    if not inventory.get("available"):
        raise HTTPException(status_code=503, detail=str(inventory.get("message") or "生产文件清单不可用"))
    by_id = {str(item.get("fileId") or ""): item for item in inventory.get("items", [])}
    missing = [value for value in normalized if value not in by_id]
    if missing:
        raise HTTPException(status_code=409, detail=f"有 {len(missing)} 个文件状态已变化，请刷新后重新对账")
    return inventory, [by_id[value] for value in normalized]


def preview_production_file_cleanup(file_ids: list[str]) -> dict[str, Any]:
    inventory, selected = _selected_production_files(file_ids)
    deletable = [item for item in selected if not item.get("protected")]
    blocked = [item for item in selected if item.get("protected")]
    categories: dict[str, dict[str, Any]] = {}
    for item in deletable:
        category = str(item.get("category") or "")
        record = categories.setdefault(category, {
            "label": PRODUCTION_FILE_CATEGORY_LABELS.get(category, category),
            "count": 0,
            "sizeBytes": 0,
        })
        record["count"] += 1
        record["sizeBytes"] += safe_int(item.get("sizeBytes"))
    return {
        "state": "preview",
        "snapshotToken": str(inventory.get("snapshotToken") or ""),
        "selectedCount": len(selected),
        "deletableCount": len(deletable),
        "blockedCount": len(blocked),
        "sizeBytes": sum(safe_int(item.get("sizeBytes")) for item in deletable),
        "categories": list(categories.values()),
        "containsTestFiles": any(item.get("category") == "capcut_test" for item in deletable),
        "deletable": [
            {
                "fileId": item["fileId"],
                "name": item["name"],
                "category": item["category"],
                "categoryLabel": item["categoryLabel"],
            }
            for item in deletable
        ],
        "blocked": [
            {
                "fileId": item["fileId"],
                "name": item["name"],
                "reason": item.get("protectedReason") or "文件受生产任务保护",
            }
            for item in blocked
        ],
        "message": f"可移入回收站 {len(deletable)} 个文件；受保护 {len(blocked)} 个",
    }


def execute_production_file_cleanup(file_ids: list[str], snapshot_token: str) -> dict[str, Any]:
    with PRODUCTION_FILE_CLEANUP_LOCK:
        inventory, selected = _selected_production_files(file_ids)
        if str(inventory.get("snapshotToken") or "") != str(snapshot_token or ""):
            result = {
                "state": "blocked",
                "message": "生产文件状态已变化，请刷新清单并重新预览",
                "removedCount": 0,
                "blockedCount": len(selected),
                "updatedAt": now_iso(),
            }
            _write_json_atomic(PRODUCTION_FILE_CLEANUP_STATUS_PATH, result)
            save_control_action("productionFileCleanup", result)
            raise HTTPException(status_code=409, detail=result["message"])

        cleanup_id = f"production-cleanup-{uuid.uuid4().hex[:12]}"
        PRODUCTION_FILE_CLEANUP_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        manifest = {
            "cleanupId": cleanup_id,
            "createdAt": now_iso(),
            "snapshotToken": snapshot_token,
            "files": [
                {
                    "fileId": item["fileId"],
                    "name": item["name"],
                    "relativePath": item["relativePath"],
                    "category": item["category"],
                    "path": item["_path"],
                    "sizeBytes": item["sizeBytes"],
                    "taskId": item.get("taskId") or "",
                    "canonicalTaskId": item.get("canonicalTaskId") or "",
                }
                for item in selected
            ],
        }
        _write_json_atomic(PRODUCTION_FILE_CLEANUP_BACKUP_DIR / f"{cleanup_id}.json", manifest)

        removed: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for item in selected:
            if item.get("protected"):
                blocked.append({
                    "fileId": item["fileId"],
                    "name": item["name"],
                    "reason": item.get("protectedReason") or "文件受生产任务保护",
                })
                continue
            try:
                path = Path(str(item.get("_path") or "")).resolve()
                root = Path(str(item.get("_root") or "")).resolve()
                if (
                    not path.is_relative_to(root)
                    or path.suffix.casefold() not in PRODUCTION_VIDEO_EXTENSIONS
                    or _is_baidu_sync_path(path)
                ):
                    raise OSError("文件路径不在登记目录、类型不受支持或位于保护目录")
                if not path.exists():
                    removed.append({
                        "fileId": item["fileId"],
                        "name": item["name"],
                        "state": "already_missing",
                    })
                    continue
                if not path.is_file():
                    raise OSError("目标不是生产视频文件")
                _recycle_directory(path)
                removed.append({
                    "fileId": item["fileId"],
                    "name": item["name"],
                    "state": "recycled",
                })
            except OSError as exc:
                failed.append({
                    "fileId": item["fileId"],
                    "name": item["name"],
                    "reason": str(exc),
                })

        index = read_json_object(PRODUCTION_FILE_CLEANUP_INDEX_PATH)
        records = index.get("items") if isinstance(index.get("items"), dict) else {}
        for item in removed:
            records[str(item["fileId"])] = {
                "state": item["state"],
                "cleanupId": cleanup_id,
                "updatedAt": now_iso(),
            }
        index["schemaVersion"] = 1
        index["updatedAt"] = now_iso()
        index["items"] = records
        _write_json_atomic(PRODUCTION_FILE_CLEANUP_INDEX_PATH, index)

        result = {
            "cleanupId": cleanup_id,
            "state": (
                "completed" if not blocked and not failed
                else ("partial" if removed else "blocked" if blocked and not failed else "failed")
            ),
            "message": (
                f"已移入回收站 {sum(item['state'] == 'recycled' for item in removed)} 个文件；"
                f"此前已清理 {sum(item['state'] == 'already_missing' for item in removed)} 个；"
                f"受保护 {len(blocked)} 个；失败 {len(failed)} 个"
            ),
            "removedCount": len(removed),
            "blockedCount": len(blocked),
            "failedCount": len(failed),
            "removed": removed,
            "blocked": blocked,
            "failed": failed,
            "updatedAt": now_iso(),
        }
        _write_json_atomic(PRODUCTION_FILE_CLEANUP_STATUS_PATH, result)
        save_control_action("productionFileCleanup", result)
        return result


def _sync_queued_command_from_mailbox() -> dict[str, Any]:
    mailbox = read_json_object(continue_command_file())
    commands = list_control_commands()
    queued = next(
        (item for item in commands if str(item.get("commandId") or "") == str(mailbox.get("commandId") or "")),
        commands[0] if commands else {},
    )
    if not queued:
        return mailbox
    payload = dict(queued)
    now_ts = time.time()
    mailbox_matches = bool(mailbox and str(mailbox.get("commandId") or "") == str(payload.get("commandId") or ""))
    mailbox_state = str(mailbox.get("state") or "") if mailbox_matches else ""
    state_map = {
        "requested": "receiver_acknowledged",
        "accepted": "workbench_acknowledged",
        "running": "executing",
        "recovering": "executing",
        "completed": "completed",
        "blocked": "blocked",
        "failed": "blocked",
        "expired": "expired",
        "cancelled": "expired",
    }
    if mailbox_state:
        mapped = state_map.get(mailbox_state, str(payload.get("state") or "persisted"))
        payload.update(mailbox)
        payload["state"] = mapped
        if mapped == "workbench_acknowledged" and not payload.get("workbenchAcknowledgedAt"):
            payload["workbenchAcknowledgedAt"] = str(mailbox.get("startedAt") or now_iso())
            payload["message"] = "家里工作台已领取，正在核对恢复条件"
        elif mapped == "executing" and not payload.get("executingAt"):
            payload["executingAt"] = str(mailbox.get("startedAt") or now_iso())
            payload["message"] = str(mailbox.get("message") or "正在安全继续")
        elif mapped in {"completed", "blocked", "expired"}:
            payload["finishedAt"] = str(mailbox.get("finishedAt") or now_iso())
    state = str(payload.get("state") or "persisted")
    claim_started = parse_time(str(payload.get("persistedAt") or payload.get("requestedAt") or ""))
    expires_at = parse_time(str(payload.get("expiresAt") or ""))
    if state in {"persisted", "receiver_acknowledged"} and claim_started and now_ts - claim_started > CONTROL_COMMAND_CLAIM_TIMEOUT_SECONDS:
        payload.update({
            "state": "expired",
            "finishedAt": now_iso(),
            "expiredReason": "家里工作台在90秒内未领取命令",
            "message": "家里工作台未领取，命令已过期；按钮已解锁",
        })
    elif state in {"persisted", "receiver_acknowledged", "workbench_acknowledged"} and expires_at and now_ts > expires_at:
        payload.update({
            "state": "expired",
            "finishedAt": now_iso(),
            "expiredReason": "安全继续命令已超过5分钟有效期",
            "message": "命令已过期，不会延迟执行",
        })
    if payload != queued:
        write_control_command(payload)
    return payload


def continue_command_status() -> dict[str, Any]:
    payload = _sync_queued_command_from_mailbox()
    if not payload:
        return {"state": "idle", "message": "尚未执行安全继续对账", "stale": False}
    state = str(payload.get("state") or "idle")
    if state in {"requested", "running"} and payload.get("finishedAt"):
        state = "expired"
    # ``accepted`` is only the short hand-off between the Dashboard and the
    # workbench.  If no workbench heartbeat follows it, keeping the button
    # locked forever cannot be correct.  Report it as historical so the next
    # click can create a fresh idempotent command.
    accepted_at = parse_time(str(payload.get("startedAt") or payload.get("requestedAt") or ""))
    if (
        state == "accepted"
        and not payload.get("lastHeartbeat")
        and accepted_at
        and time.time() - accepted_at > 120
    ):
        state = "expired"
    runtime = read_json_object(workbench_runtime_dir() / "handoff" / "download" / "project_status.json")
    runtime_items = runtime.get("items") if isinstance(runtime.get("items"), dict) else {}
    runtime_item = runtime_items.get(str(payload.get("taskId") or "")) if isinstance(runtime_items, dict) else {}
    # A failed Fish handoff can already have been consumed by the workbench
    # observer.  Reconcile it here as well, so a Dashboard refresh unlocks the
    # button even when no new click has reached the control endpoint yet.
    voice_handoff = read_json_object(resolve_path(str(CONFIG.get("voice_handoff_file") or "")))
    voice_status = str(voice_handoff.get("status") or "").lower()
    handoff_task_ids = {
        str(item.get("canonicalTaskId") or "")
        for item in (voice_handoff.get("failedItems") or [])
        if isinstance(item, dict)
    }
    handoff_task_ids.update(str(value or "") for value in (voice_handoff.get("canonicalTaskIds") or []))
    command_task_id = str(payload.get("taskId") or "")
    terminal_voice_for_command = (
        command_task_id in handoff_task_ids
        and voice_status in {"failed", "completed_with_errors", "cancelled", "canceled"}
    )
    handoff_terminal_at = parse_time(str(
        voice_handoff.get("finishedAt")
        or voice_handoff.get("completedAt")
        or voice_handoff.get("updatedAt")
        or ""
    ))
    command_started_at = parse_time(str(
        payload.get("startedAt")
        or payload.get("requestedAt")
        or ""
    ))
    if (
        state in {"requested", "accepted", "running", "recovering", "persisted", "receiver_acknowledged", "workbench_acknowledged", "executing"}
        and terminal_voice_for_command
        and (not command_started_at or not handoff_terminal_at or handoff_terminal_at >= command_started_at)
    ):
        state = "expired"
        payload["stale"] = True
        payload["expiredReason"] = "Fish 配音批次已进入终态失败，旧安全继续命令已解除锁定"
        payload["message"] = "配音批次失败，可安全继续重试缺失语音"
    if isinstance(runtime_item, dict) and _capcut_recovery_command_is_stale(payload, runtime_item):
        state = "expired"
        payload["stale"] = True
        payload["expiredReason"] = "CapCut 恢复命令心跳已失效，且客户端未运行；可重新点击安全继续"
    # A completed/blocked command is historical once the task has moved to a
    # retryable downstream phase.  Leaving the old terminal label on screen
    # made operators believe that the next safe-continue click was still
    # blocked even though it correctly creates a fresh command.
    if state in {"blocked", "failed", "cancelled"} and payload.get("finishedAt"):
        current = runtime_items.get(str(payload.get("taskId") or "")) if isinstance(runtime_items, dict) else {}
        pipeline = str((current or {}).get("pipelineStatus") or "").lower()
        phase = str((current or {}).get("currentPhase") or "").lower()
        if pipeline in {"capcut_pending", "capcut_running", "voice_pending", "stitch_pending"} or phase in {
            "waiting_capcut", "waiting_client", "stopped"
        }:
            state = "expired"
    result = {
        "commandId": str(payload.get("commandId") or ""),
        "state": state,
        "message": str(payload.get("message") or ""),
        "requestedAt": str(payload.get("requestedAt") or ""),
        "persistedAt": str(payload.get("persistedAt") or ""),
        "receiverAcknowledgedAt": str(payload.get("receiverAcknowledgedAt") or ""),
        "workbenchAcknowledgedAt": str(payload.get("workbenchAcknowledgedAt") or ""),
        "executingAt": str(payload.get("executingAt") or ""),
        "expiresAt": str(payload.get("expiresAt") or ""),
        "clientRequestId": str(payload.get("clientRequestId") or ""),
        "startedAt": str(payload.get("startedAt") or ""),
        "finishedAt": str(payload.get("finishedAt") or ""),
        "lastHeartbeat": str(payload.get("lastHeartbeat") or ""),
        "expiredReason": str(payload.get("expiredReason") or ""),
        "requestedBy": str(payload.get("requestedBy") or ""),
        "batchId": str(payload.get("batchId") or ""),
        "taskId": str(payload.get("taskId") or ""),
        "productionDate": str(payload.get("productionDate") or ""),
        "manifestId": str(payload.get("manifestId") or ""),
        "attemptId": str(payload.get("attemptId") or ""),
        "boundManifestId": str(payload.get("boundManifestId") or ""),
        "boundAttemptId": str(payload.get("boundAttemptId") or ""),
        "boundStatusFile": str(payload.get("boundStatusFile") or ""),
        "clientPid": int(payload.get("clientPid") or 0),
        "operationGeneration": str(payload.get("operationGeneration") or ""),
        "boundOperationState": str(payload.get("boundOperationState") or ""),
        "terminalObservedAt": str(payload.get("terminalObservedAt") or ""),
        "snapshotUpdatedAt": str(payload.get("snapshotUpdatedAt") or ""),
        "workbenchStarted": bool(payload.get("workbenchStarted")),
        "workbenchAlreadyRunning": bool(payload.get("workbenchAlreadyRunning")),
        "workbenchReady": bool(payload.get("workbenchReady")),
        "workbenchStartPending": bool(payload.get("workbenchStartPending")),
        "workbenchPid": int(payload.get("workbenchPid") or 0),
        "workbenchLaunchCode": str(payload.get("workbenchLaunchCode") or ""),
        "workbenchLaunchLog": str(payload.get("workbenchLaunchLog") or ""),
        "workbenchLaunchError": str(payload.get("workbenchLaunchError") or ""),
        "workbenchLaunchUpdatedAt": str(payload.get("workbenchLaunchUpdatedAt") or ""),
        "bridgeState": str(payload.get("bridgeState") or ""),
        "bridgeMessage": str(payload.get("bridgeMessage") or ""),
        "bridgePid": int(payload.get("bridgePid") or 0),
        "bridgePort": int(payload.get("bridgePort") or 5178),
        "bridgeUpdatedAt": str(payload.get("bridgeUpdatedAt") or ""),
        "stale": bool(payload.get("stale", False) or state == "expired"),
    }
    if state == "expired" and not result["expiredReason"]:
        result["expiredReason"] = "旧恢复结果已归档；当前项目已进入可恢复步骤"
        result["message"] = result["expiredReason"]
    bridge = fish_bridge_status()
    if not result["bridgeState"]:
        result["bridgeState"] = str(bridge.get("state") or "idle")
    if not result["bridgeMessage"]:
        result["bridgeMessage"] = str(bridge.get("message") or "")
    if not result["bridgePid"]:
        result["bridgePid"] = int(bridge.get("pid") or 0)
    if not result["bridgeUpdatedAt"]:
        result["bridgeUpdatedAt"] = str(bridge.get("updatedAt") or "")
    result["bridgeTerminalStatus"] = str(bridge.get("terminalStatus") or "")
    latest_project_update = max(
        (parse_time(item.get("updatedAt")) for item in COLLECTOR.project_download_statuses),
        default=0.0,
    )
    finished = parse_time(result["finishedAt"])
    if finished and latest_project_update > finished:
        result["stale"] = True
    return result


def load_control_actions() -> dict[str, Any]:
    return read_json_object(CONTROL_ACTIONS_PATH)


def save_control_action(name: str, payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    actions = load_control_actions()
    actions[name] = {**payload, "updatedAt": now_iso()}
    temp = CONTROL_ACTIONS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, CONTROL_ACTIONS_PATH)


def load_test_reset_state() -> dict[str, Any]:
    return read_json_object(TEST_RESET_STATE_PATH)


def save_test_reset_state(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = TEST_RESET_STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, TEST_RESET_STATE_PATH)


def workbench_runtime_dir() -> Path:
    path = resolve_path(str(CONFIG.get("workbench_dir") or ""))
    if (path / "workbench").is_dir():
        path = path / "workbench"
    return path


def inspect_upload_backlog(records_root: Path, upload_state_file: Path) -> dict[str, Any]:
    """Find verified CapCut outputs that are not yet in a terminal upload state."""
    try:
        upload_state = json.loads(upload_state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        upload_state = {}
    known = upload_state.get("tasks") if isinstance(upload_state, dict) else {}
    known = known if isinstance(known, dict) else {}
    candidates: dict[str, str] = {}
    missing: dict[str, str] = {}
    scanned = 0
    if not records_root.is_dir():
        return {"scanned": 0, "candidates": [], "missing": [], "reason": "第四步到第五步清单目录不存在"}
    for manifest_path in records_root.glob("*/第四步到第五步.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict):
            continue
        for item in manifest.get("tasks") or []:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("taskId") or "").strip()
            if not task_id:
                continue
            completed = str(item.get("status") or "").lower() == "completed"
            status_file = Path(str(item.get("statusFile") or ""))
            if not completed and status_file.is_file():
                try:
                    status_payload = json.loads(status_file.read_text(encoding="utf-8"))
                    status_item = next(
                        (row for row in status_payload.get("tasks") or []
                         if isinstance(row, dict) and str(row.get("taskId") or "") == task_id),
                        None,
                    )
                    completed = bool(status_item and str(status_item.get("state") or "") == "Completed")
                except (OSError, json.JSONDecodeError):
                    pass
            if not completed:
                continue
            scanned += 1
            current = known.get(task_id) if isinstance(known.get(task_id), dict) else {}
            if str(current.get("status") or "") in {"uploaded", "uploading"}:
                continue
            final_path = Path(str(item.get("finalOutputPath") or item.get("outputPath") or ""))
            try:
                valid = final_path.is_file() and final_path.stat().st_size > 0
            except OSError:
                valid = False
            if valid:
                candidates[task_id] = str(final_path)
            else:
                missing[task_id] = str(final_path)
    return {
        "scanned": scanned,
        "candidates": [{"taskId": key, "path": value} for key, value in candidates.items()],
        "missing": [{"taskId": key, "path": value} for key, value in missing.items()],
    }


def _ensure_upload_service_running() -> dict[str, Any]:
    runtime = workbench_runtime_dir()
    upload_script = runtime / "upload_service.py"
    pythonw = runtime / ".venv" / "Scripts" / "pythonw.exe"
    if not upload_script.is_file() or not pythonw.is_file():
        raise HTTPException(status_code=503, detail="百度网盘上传服务运行文件不完整")
    pid_file = runtime / "handoff" / "upload" / "upload_service.pid"
    pid = 0
    try:
        pid = int(pid_file.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        pass
    running = False
    if pid > 0 and psutil.pid_exists(pid):
        try:
            command_line = " ".join(psutil.Process(pid).cmdline()).casefold()
            running = "upload_service.py" in command_line
        except (psutil.Error, OSError):
            running = False
    if not running:
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(pythonw), str(upload_script)],
            cwd=str(runtime),
            creationflags=flags,
            close_fds=True,
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            time.sleep(0.1)
            try:
                pid = int(pid_file.read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                pid = 0
            if pid > 0 and psutil.pid_exists(pid):
                running = True
                break
            if process.poll() is not None:
                break
    return {
        "running": running,
        "started": running and "process" in locals(),
        "pid": pid if running else 0,
    }


def historical_cloud_verification_status() -> dict[str, Any]:
    runtime = workbench_runtime_dir()
    status_path = runtime / "handoff" / "upload" / "historical_cloud_verify_status.json"
    status = read_json_object(status_path)
    if not status:
        return {
            "state": "idle",
            "message": "尚未核验历史百度云文件",
            "eligible": 0,
            "processed": 0,
            "verified": 0,
            "failed": 0,
        }
    public = {
        key: status.get(key)
        for key in (
            "commandId",
            "state",
            "message",
            "requestedAt",
            "startedAt",
            "finishedAt",
            "updatedAt",
            "total",
            "processed",
            "verified",
            "failed",
        )
        if status.get(key) is not None
    }
    return sanitize_public_value(public)


def request_historical_cloud_verification() -> dict[str, Any]:
    runtime = workbench_runtime_dir()
    upload_root = runtime / "handoff" / "upload"
    upload_state_file = resolve_path(
        str(CONFIG.get("upload_status_file") or upload_root / "upload_status.json")
    )
    upload_state = read_json_object(upload_state_file)
    tasks = upload_state.get("tasks") if isinstance(upload_state.get("tasks"), dict) else {}
    eligible_ids = []
    for task_id, item in tasks.items():
        if not isinstance(item, dict):
            continue
        cleanup = item.get("cleanup") if isinstance(item.get("cleanup"), dict) else {}
        if (
            str(item.get("status") or "") == "uploaded"
            and int(item.get("cleanupPolicyVersion") or 0) < 2
            and not cleanup.get("cloudVerifiedAt")
        ):
            eligible_ids.append(str(task_id))

    current = historical_cloud_verification_status()
    if str(current.get("state") or "") in {"requested", "running"}:
        return {
            **current,
            "accepted": True,
            "message": current.get("message") or "历史百度云核验正在进行，请勿重复点击",
        }
    if not eligible_ids:
        result = {
            "accepted": True,
            "state": "completed",
            "eligible": 0,
            "processed": 0,
            "verified": 0,
            "failed": 0,
            "message": "没有需要补做云端核验的历史上传记录",
        }
        save_control_action("historicalCloudVerification", result)
        return result

    command_id = f"verify-history-{uuid.uuid4().hex[:12]}"
    requested_at = now_iso()
    request_payload = {
        "schemaVersion": 1,
        "commandId": command_id,
        "requestedAt": requested_at,
        "taskIds": eligible_ids,
    }
    _write_json_atomic(
        upload_root / "historical_cloud_verify_request.json",
        request_payload,
    )
    worker = _ensure_upload_service_running()
    result = {
        "accepted": True,
        "state": "requested",
        "commandId": command_id,
        "requestedAt": requested_at,
        "eligible": len(eligible_ids),
        "total": len(eligible_ids),
        "processed": 0,
        "verified": 0,
        "failed": 0,
        "message": (
            f"已提交 {len(eligible_ids)} 条历史百度云核验；"
            "只查询云端文件和大小，不补传、不删除、不改变任务状态"
        ),
        "uploadWorkerStarted": bool(worker.get("started")),
    }
    save_control_action("historicalCloudVerification", result)
    return result


def request_upload_rescan() -> dict[str, Any]:
    """Audit completed outputs and ensure the existing upload worker is alive."""
    runtime = workbench_runtime_dir()
    records_root = resolve_path(str(CONFIG.get("fourth_step_handoff_dir") or runtime / "交接记录"))
    upload_state_file = resolve_path(str(CONFIG.get("upload_status_file") or runtime / "handoff" / "upload" / "upload_status.json"))
    audit = inspect_upload_backlog(records_root, upload_state_file)
    worker = _ensure_upload_service_running()
    verification = request_historical_cloud_verification()
    running = bool(worker.get("running"))
    candidate_count = len(audit.get("candidates") or [])
    missing_count = len(audit.get("missing") or [])
    action = "上传服务正在运行" if running else "已重新启动上传服务"
    result = {
        "accepted": True,
        "running": True,
        "candidates": candidate_count,
        "missing": missing_count,
        "verificationState": str(verification.get("state") or ""),
        "verificationEligible": safe_int(
            verification.get("eligible") or verification.get("total")
        ),
        "message": (
            f"对账完成：发现 {candidate_count} 条可补传，{missing_count} 条成片不存在；"
            f"{action}。上传服务会自动去重，并继续核验尚未完成的安全清理。"
        ),
    }
    save_control_action("uploadRescan", {**result, "state": "completed"})
    return result


def is_test_history_task(item: dict[str, Any]) -> bool:
    """Return whether a persisted CapCut row belongs to an archived test run.

    Legacy test batches can carry an old remote task id, so the id alone is not
    a reliable production classifier.  The archive list is deliberately local
    configuration: it preserves history without changing production manifests.
    """
    archived_batches = {str(value) for value in CONFIG.get("test_history_batch_ids", [])}
    archived_remote_tasks = {
        str(value) for value in CONFIG.get("test_history_remote_task_ids", [])
    }
    return (
        str(item.get("batch_id") or "") in archived_batches
        or str(
            item.get("remote_pipeline_task_id")
            or item.get("remotePipelineTaskId")
            or ""
        ) in archived_remote_tasks
    )


def _is_tailnet_or_local(request: Request) -> bool:
    host = str(request.client.host if request.client else "")
    if host in {"127.0.0.1", "::1"}:
        return True
    try:
        address = ipaddress.ip_address(host)
        return (
            address in ipaddress.ip_network("100.64.0.0/10")
            or address in ipaddress.ip_network("fd7a:115c:a1e0::/48")
        )
    except ValueError:
        return False


def require_control_permission(request: Request) -> None:
    if not _is_tailnet_or_local(request):
        raise HTTPException(status_code=403, detail="控制操作仅允许通过 Tailscale 或家里电脑本机执行")


def receiver_json(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 3,
) -> dict[str, Any]:
    request = urllib.request.Request(
        receiver_base_url().rstrip("/") + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            response_error = json.loads(raw)
        except json.JSONDecodeError:
            response_error = raw
        detail = response_error.get("detail", response_error) if isinstance(response_error, dict) else response_error
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise HTTPException(status_code=503, detail=f"任务接收器不可用：{exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="任务接收器返回无效数据")
    return payload


def control_plane_json(path: str, timeout: float = 8) -> dict[str, Any]:
    base_url = str(CONFIG.get("control_plane_url") or "http://127.0.0.1:18790").rstrip("/")
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HTTPException(status_code=500, detail="生产安全控制面地址无效")
    if (parts.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=500, detail="生产安全控制面只允许本机回环地址")
    request = urllib.request.Request(
        base_url + path,
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=f"生产安全控制面返回错误：{exc.code}") from exc
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=503, detail=f"生产安全控制面不可用：{exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="生产安全控制面返回无效数据")
    return sanitize_public_value(payload)


class Store:
    def __init__(self, path: Path):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self._init_db()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def connection(self):
        db = self.connect()
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def _init_db(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    batch_id TEXT, date_label TEXT, project TEXT, material TEXT,
                    language TEXT, number TEXT, sequence INTEGER,
                    video_path TEXT, audio_path TEXT, output_path TEXT,
                    state TEXT, state_text TEXT, error TEXT,
                    source_file TEXT, source_timestamp REAL,
                    phase TEXT DEFAULT '', phase_text TEXT DEFAULT '',
                    manifest_id TEXT DEFAULT '', attempt_id TEXT DEFAULT '',
                    heartbeat_at TEXT DEFAULT '',
                    draft_cleanup_status TEXT DEFAULT '',
                    draft_cleanup_warning TEXT DEFAULT '',
                    draft_cleanup_updated_at TEXT DEFAULT '',
                    updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS task_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT, state TEXT, state_text TEXT, error TEXT,
                    recorded_at TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT, severity TEXT, message TEXT,
                    details TEXT, dedupe_key TEXT, created_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_created ON events(id DESC);
                CREATE TABLE IF NOT EXISTS heartbeats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    machine_name TEXT, payload TEXT, created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS source_health (
                    path TEXT PRIMARY KEY, status TEXT, signature TEXT,
                    error TEXT, updated_at TEXT
                );
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
            if "remote_pipeline_task_id" not in columns:
                db.execute("ALTER TABLE tasks ADD COLUMN remote_pipeline_task_id TEXT DEFAULT ''")
            if "expected_task_count" not in columns:
                db.execute("ALTER TABLE tasks ADD COLUMN expected_task_count INTEGER DEFAULT 0")
            for name in ("phase", "phase_text", "manifest_id", "attempt_id", "heartbeat_at"):
                if name not in columns:
                    db.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT DEFAULT ''")
            for name in ("draft_cleanup_status", "draft_cleanup_warning", "draft_cleanup_updated_at"):
                if name not in columns:
                    db.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT DEFAULT ''")
            # One-time compatibility migration for completed tasks written by
            # clients that overloaded Error with a cleanup-only warning.
            legacy_predicate = " OR ".join("error LIKE ?" for _ in LEGACY_DRAFT_CLEANUP_MARKERS)
            db.execute(
                f"""UPDATE tasks
                    SET draft_cleanup_status=CASE WHEN draft_cleanup_status='' THEN 'pending' ELSE draft_cleanup_status END,
                        draft_cleanup_warning=CASE WHEN draft_cleanup_warning='' THEN error ELSE draft_cleanup_warning END,
                        error=''
                    WHERE state IN ('Completed','completed') AND ({legacy_predicate})""",
                tuple(f"%{marker}%" for marker in LEGACY_DRAFT_CLEANUP_MARKERS),
            )

    def event(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
        dedupe_key: str = "",
    ) -> None:
        with self.lock, self.connection() as db:
            if dedupe_key:
                previous = db.execute(
                    "SELECT dedupe_key FROM events WHERE dedupe_key=? ORDER BY id DESC LIMIT 1",
                    (dedupe_key,),
                ).fetchone()
                if previous:
                    return
            db.execute(
                """INSERT INTO events
                   (event_type,severity,message,details,dedupe_key,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (
                    event_type,
                    severity,
                    message,
                    json.dumps(details or {}, ensure_ascii=False),
                    dedupe_key,
                    now_iso(),
                ),
            )

    def source_result(self, path: Path, ok: bool, signature: str, error: str = "") -> None:
        key = str(path)
        new_status = "ok" if ok else "error"
        with self.lock, self.connection() as db:
            old = db.execute("SELECT * FROM source_health WHERE path=?", (key,)).fetchone()
            changed = not old or old["status"] != new_status or old["signature"] != signature
            db.execute(
                """INSERT INTO source_health(path,status,signature,error,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(path) DO UPDATE SET status=excluded.status,
                   signature=excluded.signature,error=excluded.error,updated_at=excluded.updated_at""",
                (key, new_status, signature, error, now_iso()),
            )
        if changed and not ok:
            self.event(
                "SourceReadFailed",
                "ERROR",
                f"状态文件读取失败：{path.name}",
                {"path": key, "error": error},
                f"source-error:{key}:{signature}",
            )
        elif changed and ok and old and old["status"] == "error":
            self.event(
                "SourceRecovered",
                "SUCCESS",
                f"状态文件已恢复：{path.name}",
                {"path": key},
                f"source-recovered:{key}:{signature}",
            )

    def upsert_task(self, task: dict[str, Any]) -> None:
        with self.lock, self.connection() as db:
            old = db.execute("SELECT * FROM tasks WHERE task_id=?", (task["task_id"],)).fetchone()
            # A deliberate Step 4 -> Step 5 requeue is an explicit current
            # contract.  Its ledger mtime can legitimately be older than an
            # abandoned CapCut status file, so timestamp order alone must not
            # resurrect the abandoned attempt in the Dashboard.
            if (
                old
                and float(old["source_timestamp"] or 0) > float(task["source_timestamp"])
                and not bool(task.get("_force_contract_reset"))
            ):
                return
            state_changed = (
                not old
                or old["state"] != task["state"]
                or old["error"] != task["error"]
                or old["state_text"] != task["state_text"]
            )
            db.execute(
                """INSERT INTO tasks(
                    task_id,batch_id,date_label,project,material,language,number,sequence,
                    video_path,audio_path,output_path,state,state_text,error,
                    source_file,source_timestamp,remote_pipeline_task_id,expected_task_count,
                    phase,phase_text,manifest_id,attempt_id,heartbeat_at,
                    draft_cleanup_status,draft_cleanup_warning,draft_cleanup_updated_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET
                    batch_id=excluded.batch_id,date_label=excluded.date_label,
                    project=excluded.project,material=excluded.material,
                    language=excluded.language,number=excluded.number,sequence=excluded.sequence,
                    video_path=excluded.video_path,audio_path=excluded.audio_path,
                    output_path=excluded.output_path,state=excluded.state,
                    state_text=excluded.state_text,error=excluded.error,
                    source_file=excluded.source_file,source_timestamp=excluded.source_timestamp,
                    remote_pipeline_task_id=excluded.remote_pipeline_task_id,
                    expected_task_count=excluded.expected_task_count,
                    phase=excluded.phase,phase_text=excluded.phase_text,
                    manifest_id=excluded.manifest_id,attempt_id=excluded.attempt_id,
                    heartbeat_at=excluded.heartbeat_at,
                    draft_cleanup_status=excluded.draft_cleanup_status,
                    draft_cleanup_warning=excluded.draft_cleanup_warning,
                    draft_cleanup_updated_at=excluded.draft_cleanup_updated_at,
                    updated_at=excluded.updated_at""",
                (
                    task["task_id"], task["batch_id"], task["date_label"], task["project"],
                    task["material"], task["language"], task["number"], task["sequence"],
                    task["video_path"], task["audio_path"], task["output_path"], task["state"],
                    task["state_text"], task["error"], task["source_file"],
                    task["source_timestamp"], task["remote_pipeline_task_id"],
                    task["expected_task_count"], task.get("phase", ""),
                    task.get("phase_text", ""), task.get("manifest_id", ""),
                    task.get("attempt_id", ""), task.get("heartbeat_at", ""),
                    task.get("draft_cleanup_status", ""), task.get("draft_cleanup_warning", ""),
                    task.get("draft_cleanup_updated_at", ""), now_iso(),
                ),
            )
            if state_changed:
                db.execute(
                    """INSERT INTO task_history(task_id,state,state_text,error,recorded_at)
                       VALUES(?,?,?,?,?)""",
                    (
                        task["task_id"], task["state"], task["state_text"],
                        task["error"], now_iso(),
                    ),
                )
                severity = (
                    "ERROR" if task["state"] in FAILED_STATES
                    else "SUCCESS" if task["state"] in COMPLETED_STATES
                    else "INFO"
                )
                db.execute(
                    """INSERT INTO events(event_type,severity,message,details,dedupe_key,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (
                        "TaskStateChanged", severity,
                        f'{task["project"]} · {task["language"]}：{task["state_text"]}',
                        json.dumps({"taskId": task["task_id"], "error": task["error"]}, ensure_ascii=False),
                        "",
                        now_iso(),
                    ),
                )

    def save_heartbeat(self, machine_name: str, payload: dict[str, Any]) -> None:
        with self.lock, self.connection() as db:
            db.execute(
                "INSERT INTO heartbeats(machine_name,payload,created_at) VALUES(?,?,?)",
                (machine_name, json.dumps(payload, ensure_ascii=False), now_iso()),
            )
            db.execute(
                """DELETE FROM heartbeats WHERE id NOT IN
                   (SELECT id FROM heartbeats ORDER BY id DESC LIMIT 1440)"""
            )

    def tasks(self, date_label: str = "", state: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM tasks WHERE 1=1"
        args: list[Any] = []
        if date_label:
            sql += " AND date_label=?"
            args.append(date_label)
        if state:
            sql += " AND state=?"
            args.append(state)
        sql += " ORDER BY source_timestamp DESC, project, language, sequence"
        with self.connection() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def events(self, limit: int) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["details"] = json.loads(item["details"] or "{}")
            except json.JSONDecodeError:
                item["details"] = {}
            result.append(item)
        return result

    def source_errors(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM source_health WHERE status='error' ORDER BY updated_at DESC"
                ).fetchall()
            ]

    def last_heartbeat(self) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM heartbeats ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["payload"] = json.loads(result["payload"])
        except json.JSONDecodeError:
            result["payload"] = {}
        return result

    def clear_all(self) -> None:
        """Clear Dashboard-derived records only; never touch production files."""
        with self.lock, self.connection() as db:
            for table in ("tasks", "task_history", "events", "heartbeats", "source_health"):
                db.execute(f"DELETE FROM {table}")


class Collector:
    def __init__(self, config: dict[str, Any], store: Store):
        self.config = config
        self.store = store
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.last_scan_at = ""
        self.last_scan_epoch = 0.0
        self.last_metrics: dict[str, Any] = {}
        self.last_heartbeat_epoch = 0.0
        self.metadata: dict[str, dict[str, Any]] = {}
        self.pipeline: dict[str, dict[str, Any]] = {
            "capcut": self.empty_stage("Waiting for CapCut task"),
            "download": self.empty_stage("等待工作台启动"),
            "voice": self.empty_stage("等待语音任务"),
            "stitch": self.empty_stage("等待拼接任务"),
            "upload": self.empty_stage("等待百度网盘上传"),
        }
        self.pipeline_history: dict[str, dict[str, dict[str, Any]]] = {
            "capcut": {},
            "download": {},
            "voice": {},
            "stitch": {},
            "upload": {},
        }
        self.last_generation_scan_epoch = 0.0
        self.last_download_scan_epoch = 0.0
        self.last_metadata_scan_epoch = 0.0
        self.project_download_statuses: list[dict[str, Any]] = []
        self.archived_project_statuses: list[dict[str, Any]] = []
        self.receiver_snapshot: dict[str, Any] = {}
        self.receiver_snapshot_at = ""
        self.receiver_data_updated_at = ""
        self.receiver_error = ""
        self.receiver_schema_version = 0
        self.receiver_reconciled_at = ""
        self.receiver_reconciliation_state = "unknown"
        self.receiver_reconciliation_message = "等待接收器对账"
        self.receiver_control_ready = False
        self.reset_epoch = parse_time(load_test_reset_state().get("resetAt"))

    def reset_runtime(self, reset_at: str) -> None:
        """Forget derived state and ignore files older than the reset generation."""
        self.reset_epoch = parse_time(reset_at, time.time())
        self.metadata = {}
        self.pipeline = {
            "capcut": self.empty_stage("Waiting for CapCut task"),
            "download": self.empty_stage("等待工作台启动"),
            "voice": self.empty_stage("等待语音任务"),
            "stitch": self.empty_stage("等待拼接任务"),
            "upload": self.empty_stage("等待百度网盘上传"),
        }
        self.pipeline_history = {"download": {}, "voice": {}, "stitch": {}, "capcut": {}, "upload": {}}
        self.project_download_statuses = []
        self.archived_project_statuses = []
        self.receiver_snapshot = {}
        self.receiver_snapshot_at = ""
        self.receiver_data_updated_at = ""
        self.receiver_error = ""
        self.receiver_schema_version = 0
        self.receiver_reconciled_at = ""
        self.receiver_reconciliation_state = "unknown"
        self.receiver_reconciliation_message = "等待接收器对账"
        self.receiver_control_ready = False
        self.last_generation_scan_epoch = 0.0
        self.last_download_scan_epoch = 0.0
        self.last_metadata_scan_epoch = 0.0
        self.last_scan_at = reset_at
        self.last_scan_epoch = self.reset_epoch

    @staticmethod
    def empty_stage(state_text: str = "等待任务") -> dict[str, Any]:
        return {
            "state": "idle",
            "stateText": state_text,
            "total": 0,
            "completed": 0,
            "failed": 0,
            "progress": 0,
            "current": "",
            "updatedAt": "",
            "source": "",
            "isLive": False,
            "historyDate": "",
            "todayCompleted": 0,
            "todaySummary": "",
            "failureItems": [],
        }

    @staticmethod
    def normalize_stage(data: dict[str, Any], source: str = "") -> dict[str, Any]:
        stage = Collector.empty_stage()
        raw_state = str(data.get("state") or data.get("status") or "idle").lower()
        state_map = {
            "waiting": "idle",
            "pending": "idle",
            "running": "running",
            "processing": "running",
            "completed": "completed",
            "complete": "completed",
            "success": "completed",
            "completed_with_errors": "failed",
            "failed": "failed",
            "error": "failed",
        }
        stage["state"] = state_map.get(raw_state, raw_state if raw_state else "idle")
        stage["stateText"] = str(
            data.get("stateText") or data.get("message") or {
                "idle": "等待任务",
                "running": "处理中",
                "completed": "已完成",
                "failed": "处理失败",
            }.get(stage["state"], stage["state"])
        )
        for key in ("total", "completed", "failed"):
            try:
                stage[key] = max(0, int(data.get(key) or 0))
            except (TypeError, ValueError):
                stage[key] = 0
        try:
            stage["progress"] = max(0, min(100, round(float(data.get("progress") or 0))))
        except (TypeError, ValueError):
            stage["progress"] = 0
        if not data.get("progress") and stage["total"]:
            stage["progress"] = round((stage["completed"] + stage["failed"]) * 100 / stage["total"])
        current = data.get("current") or data.get("currentTask") or data.get("project") or ""
        if isinstance(current, dict):
            current = " / ".join(
                str(current.get(key) or "") for key in ("stage", "name", "progressText")
                if current.get(key)
            )
        stage["current"] = str(current)
        stage["updatedAt"] = str(
            data.get("updatedAt") or data.get("lastHeartbeat")
            or data.get("completedAt") or data.get("startedAt") or ""
        )
        stage["source"] = source
        stage["isLive"] = bool(data.get("isLive", False))
        stage["historyDate"] = str(data.get("historyDate") or "")
        try:
            stage["todayCompleted"] = max(0, int(data.get("todayCompleted") or 0))
        except (TypeError, ValueError):
            stage["todayCompleted"] = 0
        stage["todaySummary"] = str(data.get("todaySummary") or "")
        raw_failures = data.get("failureItems") or data.get("failures") or []
        if isinstance(raw_failures, list):
            stage["failureItems"] = [item for item in raw_failures if isinstance(item, dict)][:50]
        return stage

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, name="ops-collector", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def run(self) -> None:
        self.store.event("OpsStarted", "INFO", "OPS Dashboard 已启动")
        while not self.stop_event.is_set():
            try:
                self.scan()
            except Exception as exc:  # keep monitoring alive
                self.store.event(
                    "CollectorError",
                    "ERROR",
                    "状态采集发生异常",
                    {"error": str(exc)},
                    f"collector:{type(exc).__name__}:{exc}",
                )
            self.stop_event.wait(max(1, float(self.config["scan_interval_seconds"])))

    def _json(self, path: Path) -> dict[str, Any] | None:
        try:
            raw = path.read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Legacy workbench handoffs occasionally contain a single
                # Windows path separator. Read it compatibly so an old path
                # cannot erase otherwise valid current status from the UI.
                data = json.loads(LEGACY_INVALID_JSON_BACKSLASH.sub(r"\\\\", raw))
            signature = f"{path.stat().st_mtime_ns}:{path.stat().st_size}"
            self.store.source_result(path, True, signature)
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError) as exc:
            try:
                signature = f"{path.stat().st_mtime_ns}:{path.stat().st_size}"
            except OSError:
                signature = "missing"
            self.store.source_result(path, False, signature, str(exc))
            return None

    def scan_metadata(self) -> None:
        # Metadata contains immutable manifests plus archived diagnostics.  The
        # active status files are still read every collector pass below, but a
        # full recursive manifest walk does not need to run every two seconds.
        # Keeping the last good map also prevents a transient file lock from
        # making the Dashboard forget the formal task contract.
        now = time.time()
        if self.metadata and now - self.last_metadata_scan_epoch < 5:
            return
        roots = [
            resolve_path(str(self.config["capcut_handoff_dir"])),
            resolve_path(str(self.config["fourth_step_handoff_dir"])),
        ]
        # The durable Step 4 -> Step 5 ledger is the current task contract.
        # A prior CapCut attempt can retain activeManifestId after a safe
        # requeue, but it must never mask the ledger's new waiting state.
        fourth_step_root = roots[1].resolve()
        metadata: dict[str, dict[str, Any]] = {}
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*.json"):
                if path.name.endswith(".status.json"):
                    continue
                relative_parts = {part.casefold() for part in path.relative_to(root).parts}
                # Backups and reset snapshots are intentionally retained next
                # to the handoff data, but they are audit material—not a live
                # Step 4 -> Step 5 manifest.  Scanning them inflated current
                # production counts after a safe repair.
                if (
                    ".before-" in path.name
                    or path.name.endswith(".bak.json")
                    or "test_reset_backups" in relative_parts
                    or "archive" in relative_parts
                ):
                    continue
                data = self._json(path)
                if not data:
                    continue
                batch_id = str(data.get("batchId") or "")
                date_label = str(data.get("date") or "")
                for item in data.get("tasks") or []:
                    if not isinstance(item, dict) or not item.get("taskId"):
                        continue
                    candidate = dict(item)
                    candidate["_batch_id"] = batch_id
                    candidate["_date_label"] = date_label
                    candidate["_source"] = str(path)
                    # ``contractResetAt`` is written only by the workbench
                    # when a prior fifth-step attempt was explicitly archived
                    # and returned to waiting.  It is stronger than a stale
                    # client status, but does not affect normal active tasks.
                    candidate["_authoritative_reset"] = bool(
                        candidate.get("contractResetAt")
                        or candidate.get("wallDraftMismatchResetAt")
                    )
                    task_id = str(item["taskId"])
                    previous = metadata.get(task_id, {})
                    # The live ledger binds a task to exactly one manifest.
                    # Do not let an older JSON discovered later in rglob()
                    # overwrite a newer retry attempt.
                    # The exception is the authoritative fourth-step ledger:
                    # its explicit requeue/reset state must supersede a stale
                    # CapCut attempt that was scanned first.
                    is_current_ledger = root.resolve() == fourth_step_root
                    if (
                        previous.get("activeManifestId")
                        and not candidate.get("activeManifestId")
                        and not is_current_ledger
                    ):
                        continue
                    metadata[task_id] = {**previous, **candidate}
        self.metadata = metadata
        self.last_metadata_scan_epoch = now

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
        normalized_error, cleanup_status, cleanup_warning = split_completed_cleanup_warning(
            state,
            str(item.get("error") or ""),
            str(item.get("draftCleanupStatus") or meta.get("draftCleanupStatus") or ""),
            str(item.get("draftCleanupWarning") or meta.get("draftCleanupWarning") or ""),
        )
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
            "output_path": str(
                item.get("outputPath") or item.get("finalOutputPath")
                or meta.get("finalOutputPath") or ""
            ),
            "state": state,
            "state_text": state_text,
            "phase": str(item.get("currentPhase") or item.get("phase") or item.get("state") or meta.get("currentPhase") or ""),
            "phase_text": str(item.get("phaseText") or item.get("stateText") or meta.get("phaseText") or ""),
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

    def scan_statuses(self) -> None:
        status_paths: list[Path] = []
        capcut_dir = resolve_path(str(self.config["capcut_handoff_dir"]))
        if capcut_dir.exists():
            status_paths.extend(capcut_dir.glob("*.status.json"))
        simulation = DATA_DIR / "simulation.status.json"
        if self.config.get("simulation_enabled") and simulation.exists():
            status_paths.append(simulation)

        records: list[tuple[float, Path, dict[str, Any]]] = []
        for path in status_paths:
            data = self._json(path)
            if not data:
                continue
            timestamp = parse_time(data.get("updatedAt"), path.stat().st_mtime)
            records.append((timestamp, path, data))

        for timestamp, path, data in sorted(records, key=lambda row: row[0]):
            batch_id = str(data.get("batchId") or "")
            date_label = str(data.get("date") or "")
            for item in data.get("tasks") or []:
                if isinstance(item, dict) and item.get("taskId"):
                    meta = self.metadata.get(str(item.get("taskId") or ""), {})
                    # Do not allow an old status file to re-activate a task
                    # that the durable Step 4 ledger explicitly reset.
                    if meta.get("_authoritative_reset"):
                        continue
                    expected_manifest = str(meta.get("handoffManifest") or "").strip()
                    active_manifest = str(meta.get("activeManifestId") or "").strip()
                    status_manifest = str(data.get("manifestId") or item.get("manifestId") or "").strip()
                    manifest_path = Path(str(path).removesuffix(".status.json") + ".json")
                    if expected_manifest and Path(expected_manifest).resolve() != manifest_path.resolve():
                        continue
                    if active_manifest and status_manifest and active_manifest != status_manifest:
                        continue
                    self.store.upsert_task(
                        self.normalize_task(item, path, timestamp, batch_id, date_label)
                    )

        # The fourth-step manifest is authoritative when it was explicitly
        # re-saved (for example after a safe requeue).  Use its real mtime:
        # a newer manifest can clear an obsolete client failure, while a later
        # real CapCut status still wins normally.
        for task_id, item in self.metadata.items():
            source = Path(item.get("_source") or "")
            try:
                fallback_timestamp = source.stat().st_mtime
            except OSError:
                fallback_timestamp = 0.0
            normalized = self.normalize_task(
                item,
                source,
                fallback_timestamp,
                str(item.get("_batch_id") or ""),
                str(item.get("date") or item.get("_date_label") or ""),
            )
            normalized["_force_contract_reset"] = bool(item.get("_authoritative_reset"))
            self.store.upsert_task(normalized)

    def scan_workbench_pipeline(self) -> bool:
        path = resolve_path(str(self.config.get("workbench_ops_status") or ""))
        if not path.exists():
            return False
        data = self._json(path)
        if not data:
            return False
        updated_epoch = parse_time(data.get("updatedAt"), path.stat().st_mtime)
        fresh = time.time() - updated_epoch <= float(
            self.config.get("pipeline_live_after_seconds") or 15
        )
        stages = data.get("stages") or {}
        for name in ("download", "voice", "stitch", "capcut", "upload"):
            if isinstance(stages.get(name), dict):
                item = dict(stages[name])
                item.setdefault("updatedAt", data.get("updatedAt"))
                item["isLive"] = fresh
                self.pipeline[name] = self.normalize_stage(item, "工作台实时状态")
                if not fresh and self.pipeline[name]["state"] == "running":
                    self.pipeline[name]["state"] = "offline"
                    self.pipeline[name]["stateText"] = "状态已中断"
        return fresh

    def download_root(self) -> Path | None:
        configured = str(self.config.get("download_root") or "").strip()
        if configured:
            root = resolve_path(configured)
            return root if root.exists() else None
        settings_path = resolve_path(str(self.config.get("workbench_dir") or "")) / "workbench_settings.json"
        if not settings_path.exists():
            return None
        settings = self._json(settings_path)
        if not settings:
            return None
        selected = Path(str(settings.get("tikhub_downloads") or "").strip())
        if not selected.exists():
            return None
        # The workbench normally stores a selected project folder such as
        # downloads/实体机. Scan the parent so all project categories are included.
        return selected.parent if selected.parent.exists() else selected

    def download_state_file(self) -> Path:
        configured = str(self.config.get("download_state_file") or "").strip()
        if configured:
            return resolve_path(configured)
        return resolve_path(str(self.config.get("workbench_dir") or "")) / "handoff" / "download" / "download_batch_state.json"

    def project_download_status_file(self) -> Path:
        configured = str(self.config.get("download_project_status_file") or "").strip()
        if configured:
            return resolve_path(configured)
        return resolve_path(str(self.config.get("workbench_dir") or "")) / "handoff" / "download" / "project_status.json"

    def replenishment_contracts(self) -> dict[str, dict[str, Any]]:
        """Read durable parent links for one-link gap replenishments."""
        suite_root = resolve_path(str(self.config.get("workbench_dir") or ""))
        workbench_root = suite_root / "workbench" if (suite_root / "workbench").is_dir() else suite_root
        inbox = workbench_root / "handoff" / "task_inbox" / "imported"
        contracts: dict[str, dict[str, Any]] = {}
        if not inbox.is_dir():
            return contracts
        for path in inbox.glob("*.json"):
            data = self._json(path)
            if not isinstance(data, dict) or not data.get("isReplenishment"):
                continue
            child = str(data.get("taskId") or "").strip()
            parent = str(data.get("replenishForTaskId") or "").strip()
            if child and parent:
                contracts[child] = data
        return contracts

    def active_workbench_task_id(self) -> str:
        """Return the canonical task currently owned by Workbench, if any."""
        suite_root = resolve_path(str(self.config.get("workbench_dir") or ""))
        workbench_root = suite_root / "workbench" if (suite_root / "workbench").is_dir() else suite_root
        payload = self._json(workbench_root / "handoff" / "current_pipeline_context.json")
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("canonicalTaskId") or payload.get("taskId") or "").strip()

    def scan_project_download_statuses(self) -> None:
        """Expose one durable status card per submitted project to remote clients."""
        payload = None
        receiver_attempted = False
        receiver_url = str(self.config.get("receiver_status_url") or "").strip()
        if receiver_url:
            receiver_attempted = True
            try:
                summary_url = receiver_url.rsplit("/", 1)[0] + "/summary"
                with urllib.request.urlopen(summary_url, timeout=1.5) as response:
                    candidate = json.loads(response.read().decode("utf-8"))
                    if isinstance(candidate, dict):
                        self.receiver_snapshot = candidate
                        self.receiver_snapshot_at = now_iso()
                        self.receiver_data_updated_at = str(candidate.get("updatedAt") or "")
                        self.receiver_schema_version = safe_int(candidate.get("schemaVersion"))
                        self.receiver_reconciled_at = str(candidate.get("reconciledAt") or "")
                        self.receiver_reconciliation_state = str(candidate.get("reconciliationState") or "unknown")
                        self.receiver_reconciliation_message = str(candidate.get("reconciliationMessage") or "")
                        self.receiver_control_ready = bool(
                            self.receiver_schema_version >= 3
                            and self.receiver_reconciliation_state == "healthy"
                        )
                        archived = candidate.get("archivedProjects")
                        archived_rows = (
                            [dict(item, taskId=str(item.get("taskId") or task_id))
                             for task_id, item in archived.items() if isinstance(item, dict)]
                            if isinstance(archived, dict)
                            else [dict(item) for item in archived if isinstance(item, dict)]
                            if isinstance(archived, list)
                            else []
                        )
                        self.archived_project_statuses = archived_rows
                        if self.receiver_control_ready:
                            self.receiver_error = ""
                            projects = candidate.get("projects") or []
                            payload = {"items": {
                                str(item.get("taskId") or ""): item
                                for item in projects if isinstance(item, dict) and item.get("taskId")
                            }}
                        else:
                            self.receiver_error = "接收器状态未对账"
            except (OSError, ValueError, urllib.error.URLError) as exc:
                self.receiver_error = str(exc)
                self.receiver_control_ready = False
                payload = None
        if receiver_attempted and payload is None and self.project_download_statuses:
            # Keep the last trusted active view when only the receiver source
            # is unavailable/unreconciled; never replace it with a ghost v1 snapshot.
            return
        if payload is None:
            path = self.project_download_status_file()
            if not path.exists():
                self.project_download_statuses = []
                return
            payload = self._json(path)
        if not payload:
            return
        raw_items = payload.get("items") if isinstance(payload.get("items"), dict) else {}
        # The receiver owns the durable task-box snapshot, while the
        # workbench owns live step-3/4 state.  Merge only task-scoped pipeline
        # fields so Dashboard can surface a Fish failure without altering
        # receiver counts or task-box membership.
        local_status = self._json(self.project_download_status_file())
        local_items = local_status.get("items") if isinstance(local_status.get("items"), dict) else {}
        records: list[dict[str, Any]] = []
        for task_id, raw in raw_items.items():
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item["taskId"] = str(item.get("taskId") or task_id)
            local_item = local_items.get(item["taskId"]) if isinstance(local_items, dict) else None
            if isinstance(local_item, dict):
                for field in ("pipelineStatus", "pipelineStateText", "pipelineUpdatedAt", "currentPhase", "attemptId", "manifestId"):
                    if field in local_item:
                        item[field] = local_item[field]
            try:
                expected = max(0, int(item.get("expectedCount") or 0))
                completed = max(0, int(item.get("completed") or 0))
                failed = max(0, int(item.get("failed") or 0))
                stored_missing = item.get("remaining", item.get("missingCount"))
                missing = max(0, int(stored_missing)) if stored_missing not in (None, "") else max(0, expected - completed)
            except (TypeError, ValueError):
                expected, completed, failed, missing = 0, 0, 0, 0
            status = str(item.get("status") or "").lower()
            historical_failed = failed
            if expected and completed >= expected:
                completed = expected
                missing = 0
                status = "completed"
                item["stateText"] = f"已完成 {completed} / {expected}"
            # A submitted project has a target, but it is not a production
            # gap until the receiver/workbench has actually started it.
            # Pending confirmation must remain an informational plan card.
            not_started = bool(item.get("notStarted")) or status in {
                "pending_confirmation", "received", "queued", "planned", "waiting_download"
            }
            terminal = bool(item.get("terminal")) or status in {"completed", "blocked_missing_links"}
            item["stateText"] = str(item.get("stateText") or "")
            item["currentTask"] = str(item.get("currentTask") or "")
            item["error"] = str(item.get("error") or "")
            item.update({
                "expectedCount": expected,
                "completed": completed,
                "failed": 0 if status == "completed" else failed,
                "historicalFailed": historical_failed if status == "completed" else 0,
                "missingCount": missing,
                "notStarted": not_started,
                "terminal": terminal,
                "status": status,
                "gapActive": bool(
                    not not_started
                    and terminal
                    and status != "completed"
                    and (bool(item.get("gapActive")) or status == "blocked_missing_links")
                ),
            })
            records.append(item)
        # A completed supplement closes the original project's missing slot;
        # it is not a second project and must not make 23/24 look unresolved.
        by_task_id = {str(item.get("taskId") or ""): item for item in records}
        for child_id, contract in self.replenishment_contracts().items():
            child = by_task_id.get(child_id)
            parent_id = str(contract.get("replenishForTaskId") or "")
            parent = by_task_id.get(parent_id)
            if not child or not parent:
                continue
            try:
                expected = max(1, int(contract.get("replenishmentBaseExpected") or parent.get("expectedCount") or 1))
                completed_before = max(0, int(contract.get("replenishmentCompletedBefore") or 0))
                child_completed = max(0, int(child.get("completed") or 0))
            except (TypeError, ValueError):
                continue
            completed = min(expected, completed_before + child_completed)
            remaining = max(0, expected - completed)
            parent.update({
                "expectedCount": expected,
                "completed": completed,
                "failed": 0 if remaining == 0 else int(child.get("failed") or parent.get("failed") or 0),
                "remaining": remaining,
                "missingCount": remaining,
                "replenishedByTaskId": child_id,
                "updatedAt": child.get("updatedAt") or parent.get("updatedAt"),
            })
            if remaining == 0:
                parent.update({"status": "completed", "stateText": f"补链已完成：{completed} / {expected}"})
            # The child is a detail of the parent, never its own gap card.
            by_task_id.pop(child_id, None)
        records = list(by_task_id.values())
        self.project_download_statuses = sorted(
            records,
            key=lambda item: (parse_time(item.get("updatedAt")), str(item.get("taskId") or "")),
            reverse=True,
        )

    @staticmethod
    def download_failure_items(tasks: list[Any]) -> list[dict[str, str]]:
        """Extract exact failed links from the workbench's persisted task table."""
        items: list[dict[str, str]] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            url = str(task.get("url") or "").strip()
            values = task.get("values")
            if not isinstance(values, list):
                continue
            download = str(values[1] if len(values) > 1 else "")
            subtitle = str(values[2] if len(values) > 2 else "")
            stage = str(values[3] if len(values) > 3 else "")
            if not (download == "失败" or subtitle == "失败" or stage == "处理失败"):
                continue
            reason = " / ".join(part for part in (stage, download, subtitle) if part and part not in {"失败", "处理失败"})
            items.append({
                "url": url or "未记录链接",
                "reason": reason or "下载或 AI 去字幕失败",
            })
        return items

    def scan_saved_download_state(self) -> dict[str, Any] | None:
        """Use the saved workbench batch state when the GUI is closed or restarted."""
        path = self.download_state_file()
        if not path.exists():
            return None
        data = self._json(path)
        if not data:
            return None
        stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
        tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
        failures = self.download_failure_items(tasks)
        context = data.get("context") if isinstance(data.get("context"), dict) else {}
        updated_at = str(data.get("updatedAt") or "")
        total = len(tasks)
        try:
            total = max(total, int(stats.get("total") or 0))
        except (TypeError, ValueError):
            pass
        try:
            completed = int(stats.get("success") or 0)
        except (TypeError, ValueError):
            completed = 0
        try:
            failed = max(len(failures), int(stats.get("failed") or 0))
        except (TypeError, ValueError):
            failed = len(failures)
        try:
            progress = int(str(stats.get("progress") or "0").rstrip("%"))
        except (TypeError, ValueError):
            progress = 0
        last_result = data.get("lastBatchResult") if isinstance(data.get("lastBatchResult"), dict) else {}
        running = bool(total and not last_result and progress < 100 and (completed + failed) < total)
        state = "running" if running else ("failed" if failed else ("completed" if total else "idle"))
        state_text = (
            "正在下载与 AI 去字幕" if running else
            (f"{failed} 条失败，等待补链重试" if failed else (f"{completed} 条已完成" if total else "等待下载任务"))
        )
        # A dispatched task owns an immutable production date.  A scan that
        # crosses midnight must continue to appear under its submission date.
        date_label = str(context.get("productionDate") or context.get("date") or "").strip()
        if not date_label:
            timestamp = parse_time(updated_at, path.stat().st_mtime)
            stamp = datetime.fromtimestamp(timestamp).astimezone()
            date_label = f"{stamp.month}.{stamp.day}"
        current = ""
        if failures:
            current = failures[0]["url"]
        elif context:
            current = " / ".join(str(context.get(key) or "") for key in ("project", "material") if context.get(key))
        stage = self.normalize_stage({
            "state": state,
            "stateText": state_text,
            "total": total,
            "completed": completed,
            "failed": failed,
            "progress": progress,
            "current": current,
            "updatedAt": updated_at,
            "historyDate": date_label,
            "failureItems": failures,
        }, "工作台保存的下载批次")
        self.pipeline_history["download"][date_label] = stage
        return stage

    def scan_download_pipeline(self, workbench_live: bool) -> None:
        if time.time() - self.last_download_scan_epoch < 2:
            return
        self.last_download_scan_epoch = time.time()
        saved_stage = self.scan_saved_download_state()
        if saved_stage:
            self.pipeline["download"] = dict(saved_stage)
        root = self.download_root()
        if not root:
            return
        today = datetime.now().astimezone().date()
        today_label = f"{today.month}.{today.day}"
        grouped_files: dict[str, list[tuple[Path, str]]] = {}
        for path in root.rglob("*.mp4"):
            try:
                if path.stat().st_mtime <= self.reset_epoch:
                    continue
                relative = path.relative_to(root)
                parts = relative.parts
                # New external tasks are deliberately stored as
                # 任务批次/日期/项目/材料/video.mp4.  The original shallow
                # glob missed them entirely and displayed the material as the
                # project.  Keep old folders compatible by falling back to
                # their modification date and parent folder.
                if len(parts) >= 5 and parts[0] == "任务批次":
                    label = str(parts[1])
                    category = " / ".join(str(part) for part in parts[2:4])
                else:
                    modified_date = datetime.fromtimestamp(path.stat().st_mtime).astimezone().date()
                    label = f"{modified_date.month}.{modified_date.day}"
                    category = path.parent.name
                grouped_files.setdefault(label, []).append((path, category))
            except OSError:
                continue
        history: dict[str, dict[str, Any]] = {}
        for date_label, entries in grouped_files.items():
            files = [item[0] for item in entries]
            latest = max(files, key=lambda item: item.stat().st_mtime)
            projects: dict[str, int] = {}
            for _path, category in entries:
                projects[category] = projects.get(category, 0) + 1
            summary = "、".join(
                f"{name} {count}条" for name, count in sorted(projects.items())
            )
            history[date_label] = self.normalize_stage(
                {
                    "state": "completed",
                    "stateText": f"该日已处理 {len(files)} 条",
                    "total": len(files),
                    "completed": len(files),
                    "failed": 0,
                    "progress": 100,
                    "current": f"{summary} · 最新 {latest.name}",
                    "updatedAt": datetime.fromtimestamp(
                        latest.stat().st_mtime
                    ).astimezone().isoformat(timespec="seconds"),
                    "historyDate": date_label,
                    "todayCompleted": len(files) if date_label == today_label else 0,
                    "todaySummary": summary if date_label == today_label else "",
                },
                "下载目录扫描",
            )
        # Keep saved batches (and their failures) even if their outputs were
        # cleaned up or have not been written to the directory yet.
        previous_history = dict(self.pipeline_history["download"])
        for date_label, stage in previous_history.items():
            if date_label not in history:
                history[date_label] = dict(stage)
                continue
            if date_label in history and stage.get("failed"):
                history[date_label]["failed"] = stage["failed"]
                history[date_label]["failureItems"] = stage.get("failureItems", [])
                history[date_label]["total"] = max(history[date_label]["total"], stage.get("total", 0))
                history[date_label]["progress"] = 100 if stage.get("completed", 0) + stage.get("failed", 0) >= history[date_label]["total"] else stage.get("progress", 0)
                history[date_label]["state"] = "failed"
                history[date_label]["stateText"] = f"{stage['failed']} 条失败，等待补链重试"
        self.pipeline_history["download"] = history
        today_stage = history.get(today_label)
        if not today_stage:
            return
        if workbench_live:
            stage = self.pipeline["download"]
            stage["todayCompleted"] = today_stage["completed"]
            stage["todaySummary"] = today_stage["current"].split(" · 最新", 1)[0]
            stage["historyDate"] = today_label
            if stage["state"] == "idle":
                stage["stateText"] = f"等待任务 · 今日已处理 {today_stage['completed']} 条"
                stage["total"] = today_stage["total"]
                stage["completed"] = today_stage["completed"]
                stage["progress"] = 100
                stage["current"] = stage["todaySummary"]
            return
        self.pipeline["download"] = dict(today_stage)
        self.pipeline["download"]["stateText"] = f"今日已处理 {today_stage['completed']} 条"

    def scan_voice_pipeline(self) -> None:
        path = resolve_path(str(self.config.get("voice_handoff_file") or ""))
        if not path.exists():
            return
        data = self._json(path)
        if not data:
            return
        item = dict(data)
        item["updatedAt"] = (
            data.get("completedAt") or data.get("lastHeartbeat") or data.get("startedAt")
        )
        item["stateText"] = {
            "running": "正在生成语音",
            "completed": "语音生成完成",
            "completed_with_errors": "语音生成有失败",
            "failed": "语音生成失败",
        }.get(str(data.get("status") or ""), str(data.get("status") or "等待语音任务"))
        direct = self.normalize_stage(item, "语音客户端批次记录")
        selected = data.get("selectedProjects") or []
        if selected:
            direct["current"] = "、".join(str(item) for item in selected)
        # Prefer the immutable dispatch date.  Legacy voice handoffs did not
        # carry it, so recover it from the registered audio directory only as
        # a compatibility fallback.
        history_date = str(
            data.get("productionDate") or data.get("date") or data.get("audioBatch") or ""
        ).strip()
        if not history_date:
            for completed_item in (data.get("completedItems") or []) + (data.get("failedItems") or []):
                if isinstance(completed_item, dict) and completed_item.get("audioPath"):
                    history_date = Path(str(completed_item["audioPath"])).parent.name
                    break
        if not history_date:
            timestamp = parse_time(data.get("completedAt") or data.get("startedAt"))
            if timestamp:
                value = datetime.fromtimestamp(timestamp).astimezone()
                history_date = f"{value.month}.{value.day}"
        if history_date:
            direct["historyDate"] = history_date
            self.pipeline_history["voice"][history_date] = dict(direct)
        direct_timestamp = max(
            parse_time(direct.get("updatedAt")),
            parse_time(data.get("completedAt")),
            parse_time(data.get("startedAt")),
        )
        current_timestamp = parse_time(self.pipeline["voice"].get("updatedAt"))
        active_task_id = self.active_workbench_task_id()
        candidates = [
            str(data.get("canonicalTaskId") or "").strip(),
            str(data.get("taskId") or "").strip(),
            *[str(value or "").strip() for value in (data.get("canonicalTaskIds") or [])],
            *[str(value or "").strip() for value in (data.get("taskIds") or [])],
        ]
        belongs_to_active_task = not active_task_id or any(
            value == active_task_id or active_task_id in value for value in candidates if value
        )
        if belongs_to_active_task and direct_timestamp >= current_timestamp:
            self.pipeline["voice"] = direct

    def apply_active_workbench_voice_pending(self) -> None:
        """Keep the primary voice card scoped to the active Workbench task.

        The durable handoff file is intentionally retained after a batch.  A
        completed handoff from a prior project must therefore never make the
        current project's dashboard card look like ``1/1`` before its own
        voice job has started.
        """
        suite_root = resolve_path(str(self.config.get("workbench_dir") or ""))
        workbench_root = suite_root / "workbench" if (suite_root / "workbench").is_dir() else suite_root
        context = self._json(workbench_root / "handoff" / "current_pipeline_context.json")
        if not isinstance(context, dict):
            return
        task_id = str(context.get("canonicalTaskId") or context.get("taskId") or "").strip()
        status = str(context.get("status") or "").lower()
        if not task_id or status not in {"step1_completed", "step12_completed", "voice_pending"}:
            return
        handoff = self._json(resolve_path(str(self.config.get("voice_handoff_file") or "")))
        handoff_ids = {
            str(handoff.get("canonicalTaskId") or "").strip(),
            str(handoff.get("taskId") or "").strip(),
            *[str(value or "").strip() for value in (handoff.get("canonicalTaskIds") or [])],
            *[str(value or "").strip() for value in (handoff.get("taskIds") or [])],
        } if isinstance(handoff, dict) else set()
        if task_id in handoff_ids:
            return
        language_plan = context.get("languagePlan") if isinstance(context.get("languagePlan"), list) else []
        expected = sum(max(0, safe_int(item.get("audioCount"))) for item in language_plan if isinstance(item, dict))
        expected = expected or max(0, safe_int(context.get("expectedCount")))
        stage = self.empty_stage("当前项目等待配音")
        stage.update({
            "state": "waiting",
            "stateText": "第1/2步已完成，等待当前项目配音",
            "total": expected,
            "completed": 0,
            "failed": 0,
            "progress": 0,
            "current": " / ".join(
                str(context.get(key) or "") for key in ("project", "material") if context.get(key)
            ),
            "updatedAt": str(context.get("createdAt") or ""),
            "source": "工作台当前项目状态",
            "isLive": True,
        })
        self.pipeline["voice"] = stage

    def scan_generation_pipeline(self, workbench_available: bool) -> None:
        if time.time() - self.last_generation_scan_epoch < 10:
            return
        self.last_generation_scan_epoch = time.time()
        root = resolve_path(str(self.config.get("generation_output_root") or ""))
        if not root.exists():
            return
        paths = list(root.glob("*/*/generation_records_*.json"))
        paths = [path for path in paths if path.stat().st_mtime > self.reset_epoch]
        if not paths:
            return
        grouped: dict[str, dict[str, Any]] = {}
        for path in paths:
            try:
                records = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(records, list):
                    continue
                signature = f"{path.stat().st_mtime_ns}:{path.stat().st_size}"
                self.store.source_result(path, True, signature)
            except (OSError, json.JSONDecodeError) as exc:
                try:
                    signature = f"{path.stat().st_mtime_ns}:{path.stat().st_size}"
                except OSError:
                    signature = "missing"
                self.store.source_result(path, False, signature, str(exc))
                continue
            date_label = path.parent.parent.name
            bucket = grouped.setdefault(
                date_label,
                {"records": {}, "projects": set(), "latest": 0.0},
            )
            bucket["projects"].add(path.parent.name)
            bucket["latest"] = max(bucket["latest"], path.stat().st_mtime)
            for index, item in enumerate(records):
                if not isinstance(item, dict):
                    continue
                key = str(item.get("output") or f"{path}:{index}")
                bucket["records"][key] = item

        history: dict[str, dict[str, Any]] = {}
        for date_label, bucket in grouped.items():
            records = list(bucket["records"].values())
            completed = sum(1 for item in records if item.get("status") == "success")
            failed = sum(1 for item in records if item.get("status") == "failed")
            total = len(records)
            projects = "、".join(sorted(bucket["projects"]))
            history[date_label] = self.normalize_stage(
                {
                    "state": "failed" if failed else ("completed" if total else "idle"),
                    "stateText": f"该日完成 {completed}，失败 {failed}" if total else "该日无拼接记录",
                    "total": total,
                    "completed": completed,
                    "failed": failed,
                    "progress": round((completed + failed) * 100 / total) if total else 0,
                    "current": f"{date_label} / {projects}",
                    "updatedAt": datetime.fromtimestamp(bucket["latest"]).astimezone().isoformat(
                        timespec="seconds"
                    ),
                    "historyDate": date_label,
                },
                "第四步生成记录",
            )
        self.pipeline_history["stitch"] = history
        if workbench_available and self.pipeline["stitch"].get("state") == "running":
            return
        if history:
            newest = max(history.values(), key=lambda item: parse_time(item.get("updatedAt")))
            if parse_time(newest["updatedAt"]) >= parse_time(
                self.pipeline["stitch"].get("updatedAt")
            ):
                self.pipeline["stitch"] = dict(newest)

    def scan_upload_pipeline(self) -> None:
        path = resolve_path(str(self.config.get("upload_status_file") or ""))
        data = self._json(path) if path.is_file() else {}
        if not data:
            stage = self.empty_stage("百度网盘上传未配置")
            stage["state"] = "unconfigured"
            stage["source"] = "百度网盘上传状态"
            self.pipeline["upload"] = stage
            self.pipeline_history["upload"] = {}
            return
        configured = bool(data.get("configured"))
        authorized = bool(data.get("authorized"))
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in (data.get("tasks") or {}).values():
            if not isinstance(item, dict):
                continue
            grouped.setdefault(str(item.get("productionDate") or item.get("date") or ""), []).append(item)
        history: dict[str, dict[str, Any]] = {}
        for date_label, items in grouped.items():
            total = len(items)
            completed = sum(1 for item in items if item.get("status") == "uploaded")
            failed = sum(1 for item in items if item.get("status") == "failed")
            uploading = sum(1 for item in items if item.get("status") == "uploading")
            waiting = max(0, total - completed - failed - uploading)
            cloud_verified = sum(
                1 for item in items
                if bool((item.get("cleanup") or {}).get("cloudVerifiedAt"))
            )
            task_files_cleaned = sum(
                1 for item in items
                if bool((item.get("cleanup") or {}).get("taskFilesCleanedAt"))
            )
            waiting_shared_release = sum(
                1 for item in items
                if (item.get("cleanup") or {}).get("state") == "waiting_shared_release"
            )
            local_cleaned = sum(
                1 for item in items
                if (item.get("cleanup") or {}).get("state") == "cleanup_completed"
            )
            cleanup_blocked = sum(
                1 for item in items
                if str((item.get("cleanup") or {}).get("state") or "").startswith("blocked_")
            )
            legacy_retained = sum(
                1 for item in items
                if (item.get("cleanup") or {}).get("state") == "legacy_retained"
            )
            cleanup_pending = max(
                0, completed - local_cleaned - cleanup_blocked - legacy_retained
            )

            def registered_size(item: dict[str, Any]) -> int:
                cleanup = item.get("cleanup") if isinstance(item.get("cleanup"), dict) else {}
                resume = item.get("resume") if isinstance(item.get("resume"), dict) else {}
                return max(
                    0,
                    safe_int(item.get("cloudSize")),
                    safe_int(cleanup.get("cloudVerifiedSize")),
                    safe_int(resume.get("size")),
                    safe_int(item.get("observedSize")),
                )

            def transferred_size(item: dict[str, Any]) -> int:
                size = registered_size(item)
                if str(item.get("status") or "") == "uploaded":
                    return size
                resume = item.get("resume") if isinstance(item.get("resume"), dict) else {}
                chunk_size = max(0, safe_int(resume.get("chunkSize")))
                uploaded_parts = resume.get("uploadedParts") if isinstance(resume.get("uploadedParts"), list) else []
                if not size or not chunk_size or not uploaded_parts:
                    return 0
                transferred = 0
                for raw_part in uploaded_parts:
                    part = safe_int(raw_part, -1)
                    if part < 0:
                        continue
                    offset = part * chunk_size
                    if offset >= size:
                        continue
                    transferred += min(chunk_size, size - offset)
                return min(size, transferred)

            bytes_total = sum(registered_size(item) for item in items)
            bytes_uploaded = sum(transferred_size(item) for item in items)
            bytes_remaining = max(0, bytes_total - bytes_uploaded)
            legacy_progress = round(
                sum(int(item.get("progress") or 0) for item in items)
                / max(total, 1)
            )
            byte_progress = (
                min(100, round(bytes_uploaded * 100 / bytes_total))
                if bytes_total else legacy_progress
            )

            # The upload API reports progress after each Baidu multipart block.
            # Most production videos fit in one 32 MB block, so use recent real
            # completed-file throughput for a stable speed and ETA instead of
            # pretending to know progress inside an in-flight HTTP request.
            throughput_samples: list[tuple[float, int]] = []
            for item in items:
                if str(item.get("status") or "") != "uploaded":
                    continue
                started = parse_time(item.get("startedAt"))
                finished = parse_time(item.get("completedAt"))
                size = registered_size(item)
                duration = finished - started
                if size > 0 and 1 <= duration <= 3600:
                    throughput_samples.append((finished, round(size / duration)))
            throughput_samples.sort(key=lambda value: value[0], reverse=True)
            recent_rates = [rate for _, rate in throughput_samples[:8] if rate > 0]
            speed_bps = round(sum(recent_rates) / len(recent_rates)) if recent_rates else 0
            eta_seconds = round(bytes_remaining / speed_bps) if speed_bps > 0 else None

            active = [item for item in items if item.get("status") == "uploading"]
            if active:
                state, text, current = "running", "正在上传最终成片", active[0]
            elif failed:
                state, text = "failed", f"{failed} 条上传失败"
                current = next(item for item in items if item.get("status") == "failed")
            elif total and completed == total:
                state, text, current = "completed", f"{completed} 条上传完成", items[-1]
            else:
                state, text, current = "idle", f"{total - completed} 条等待上传", {}
            stage = self.normalize_stage(
                {
                    "state": state,
                    "stateText": text,
                    "total": total,
                    "completed": completed,
                    "failed": failed,
                    "progress": byte_progress,
                    "current": " / ".join(
                        str(current.get(key) or "")
                        for key in ("project", "material", "language")
                        if current.get(key)
                    ),
                    "updatedAt": data.get("updatedAt"),
                    "historyDate": date_label,
                    "account": data.get("account"),
                    "chunkSizeMB": data.get("chunkSizeMB"),
                },
                "百度网盘上传状态",
            )
            stage.update(
                {
                    "bytesTotal": bytes_total,
                    "bytesUploaded": bytes_uploaded,
                    "bytesRemaining": bytes_remaining,
                    "speedBytesPerSecond": speed_bps,
                    "etaSeconds": eta_seconds,
                    "currentFileName": Path(str(current.get("localPath") or "")).name,
                    "currentFileBytes": transferred_size(current),
                    "currentFileTotalBytes": registered_size(current),
                    "currentFileProgress": safe_int(current.get("progress")),
                    "currentFileStartedAt": str(current.get("startedAt") or ""),
                    "localCleaned": local_cleaned,
                    "taskFilesCleaned": task_files_cleaned,
                    "waitingSharedRelease": waiting_shared_release,
                    "cleanupPending": cleanup_pending,
                    "cleanupBlocked": cleanup_blocked,
                    "legacyRetained": legacy_retained,
                    "waiting": waiting,
                    "uploading": uploading,
                    "cloudVerified": cloud_verified,
                    "permanentKeep": sum(
                        1 for item in items
                        if (item.get("cleanup") or {}).get("audioPathState") == "permanent_keep"
                    ),
                }
            )
            history[date_label] = stage
        self.pipeline_history["upload"] = history
        today = current_date_label()
        if today in history:
            self.pipeline["upload"] = dict(history[today])
        elif history:
            newest = max(
                history.values(),
                key=lambda item: parse_time(item.get("updatedAt")),
            )
            self.pipeline["upload"] = dict(newest)
        else:
            stage = self.empty_stage(
                "等待第五步最终成片" if configured and authorized
                else ("等待百度网盘授权" if configured else "百度网盘上传未配置")
            )
            stage["state"] = "idle" if configured else "unconfigured"
            stage["updatedAt"] = str(data.get("updatedAt") or "")
            stage["source"] = "百度网盘上传状态"
            self.pipeline["upload"] = stage

    def scan_pipeline(self) -> None:
        workbench_available = self.scan_workbench_pipeline()
        self.scan_project_download_statuses()
        self.scan_download_pipeline(workbench_available)
        self.scan_voice_pipeline()
        self.scan_generation_pipeline(workbench_available)
        self.scan_upload_pipeline()
        self.apply_active_workbench_voice_pending()

    def scan(self) -> None:
        self.scan_metadata()
        self.scan_statuses()
        self.scan_pipeline()
        self.last_metrics = system_metrics(self.config)
        self.last_scan_at = now_iso()
        self.last_scan_epoch = time.time()
        heartbeat_interval = float(self.config["heartbeat_interval_seconds"])
        if time.time() - self.last_heartbeat_epoch >= heartbeat_interval:
            self.store.save_heartbeat(str(self.config["machine_name"]), self.last_metrics)
            self.last_heartbeat_epoch = time.time()


def process_status() -> dict[str, bool]:
    result = {"workbench": False, "voice": False, "stitch": False, "capcut": False, "upload": False}
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            name = (process.info.get("name") or "").lower()
            command = " ".join(process.info.get("cmdline") or []).lower()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        if "workbench.py" in command:
            result["workbench"] = True
        if "batchvoiceclient" in name or "runbatch.js" in command:
            result["voice"] = True
        if "board_video_stitcher" in command or "ai板材视频拼接工具" in command:
            result["stitch"] = True
        if "capcutbatchclient" in name or "capcutbatchclient" in command:
            result["capcut"] = True
        if "uploadworker" in name or "upload_service.py" in command:
            result["upload"] = True
    return result


def gpu_metrics() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if completed.returncode != 0 or not completed.stdout.strip():
            raise RuntimeError(completed.stderr.strip() or "nvidia-smi unavailable")
        row = next(csv.reader([completed.stdout.strip().splitlines()[0]]))
        return {
            "available": True,
            "name": row[0].strip(),
            "usage": float(row[1]),
            "memory_used_mb": float(row[2]),
            "memory_total_mb": float(row[3]),
            "temperature": float(row[4]),
        }
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError, IndexError):
        return {
            "available": False, "name": "未检测到NVIDIA GPU", "usage": None,
            "memory_used_mb": None, "memory_total_mb": None, "temperature": None,
        }


def system_metrics(config: dict[str, Any]) -> dict[str, Any]:
    root = resolve_path(str(config.get("final_output_root") or ""))
    disk_path = root if root.exists() else Path.home().anchor
    try:
        disk = psutil.disk_usage(str(disk_path))
        disk_data = {
            "path": str(disk_path), "percent": round(disk.percent, 1),
            "free_gb": round(disk.free / (1024 ** 3), 1),
            "total_gb": round(disk.total / (1024 ** 3), 1),
        }
    except OSError:
        disk_data = {"path": str(disk_path), "percent": None, "free_gb": None, "total_gb": None}
    active_interfaces = [
        name for name, stats in psutil.net_if_stats().items()
        if stats.isup and not name.lower().startswith(("loopback", "npcap"))
    ]
    memory = psutil.virtual_memory()
    return {
        "time": now_iso(),
        "cpu": round(psutil.cpu_percent(interval=None), 1),
        "memory": round(memory.percent, 1),
        "memory_used_gb": round(memory.used / (1024 ** 3), 1),
        "memory_total_gb": round(memory.total / (1024 ** 3), 1),
        "disk": disk_data,
        "gpu": gpu_metrics(),
        "network": {"online": bool(active_interfaces), "interfaces": active_interfaces},
        "processes": process_status(),
    }


CONFIG = load_config()
STORE = Store(DB_PATH)
COLLECTOR = Collector(CONFIG, STORE)


def task_category(state: str) -> str:
    if state in COMPLETED_STATES:
        return "completed"
    if state in FAILED_STATES:
        return "failed"
    if state in WAITING_STATES:
        return "waiting"
    return "running"


STAGE_META = {
    "download": ("1", "下载与AI去字幕", "工作台", "workbench"),
    "voice": ("2", "批量语音生成", "语音客户端", "voice"),
    "stitch": ("3", "AI素材拼接", "工作台", "workbench"),
    "capcut": ("4", "CapCut自动剪辑", "CapCut客户端", "capcut"),
    "upload": ("5", "最终成片上传", "上传服务", "upload"),
}


def decorate_pipeline_stages(stages: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    processes = (COLLECTOR.last_metrics.get("processes") or {})
    result: dict[str, dict[str, Any]] = {}
    for key, original in stages.items():
        stage = dict(original)
        step, name, program, process_key = STAGE_META[key]
        program_online = bool(processes.get(process_key))
        stage["key"] = key
        stage["step"] = step
        stage["name"] = name
        stage["program"] = program
        stage["programOnline"] = program_online
        updated_epoch = parse_time(stage.get("updatedAt"))
        stage["ageSeconds"] = max(0, round(time.time() - updated_epoch)) if updated_epoch else None
        if stage["state"] == "running":
            stage["isLive"] = bool(
                program_online
                and updated_epoch
                and time.time() - updated_epoch
                <= float(CONFIG.get("pipeline_live_after_seconds") or 15)
            )
        elif stage["state"] == "unconfigured":
            stage["isLive"] = False
        else:
            stage["isLive"] = bool(stage.get("isLive"))
        result[key] = stage
    return result


def capcut_stage_for_tasks(tasks: list[dict[str, Any]], date_label: str = "") -> dict[str, Any]:
    counts = {"waiting": 0, "running": 0, "completed": 0, "failed": 0}
    for item in tasks:
        counts[task_category(item["state"])] += 1
    priority = {"running": 4, "failed": 3, "waiting": 2, "completed": 1}
    latest = max(
        tasks,
        key=lambda item: (
            priority[task_category(item["state"])],
            item["source_timestamp"],
            item["updated_at"],
        ),
        default=None,
    )
    if counts["running"]:
        state, text = "running", latest["state_text"] if latest else "剪辑中"
    elif counts["failed"]:
        state, text = "failed", f"{counts['failed']} 条失败"
    elif counts["waiting"]:
        state, text = "idle", f"{counts['waiting']} 条等待处理"
    elif counts["completed"]:
        state, text = "completed", f"{counts['completed']} 条已完成"
    else:
        state, text = "idle", "该日无CapCut任务" if date_label else "等待第五步任务"
    total = len(tasks)
    return Collector.normalize_stage(
        {
            "state": state,
            "stateText": text,
            "total": total,
            "completed": counts["completed"],
            "failed": counts["failed"],
            "progress": round((counts["completed"] + counts["failed"]) * 100 / total)
            if total else 0,
            "current": (
                " / ".join(
                    part for part in (
                        latest["project"], latest["material"], latest["language"],
                        latest.get("phase_text") or latest.get("phase") or "",
                    ) if part
                )
                if latest else ""
            ),
            "updatedAt": latest["updated_at"] if latest else "",
            "currentPhase": latest.get("phase") if latest else "",
            "phaseText": latest.get("phase_text") if latest else "",
            "heartbeatAt": latest.get("heartbeat_at") if latest else "",
            "historyDate": date_label,
            "testHistoryCount": 0,
        },
        "CapCut任务状态",
    )


def current_date_label() -> str:
    value = datetime.now().astimezone()
    return f"{value.month}.{value.day}"


def pipeline_dates() -> list[str]:
    values = {current_date_label()}
    for history in COLLECTOR.pipeline_history.values():
        values.update(history.keys())
    values.update(item["date_label"] for item in STORE.tasks() if item["date_label"])

    def key(label: str) -> tuple[int, int]:
        try:
            month, day = label.split(".", 1)
            return int(month), int(day)
        except (ValueError, AttributeError):
            return 0, 0

    return sorted(values, key=key, reverse=True)


def authoritative_capcut_task_ids() -> set[str]:
    """Return task ids owned by the durable Step 4 -> Step 5 manifest.

    Status files and the SQLite store intentionally retain old attempts for
    audit.  They must never inflate the current production queue.
    """
    fourth_step_root = resolve_path(str(CONFIG.get("fourth_step_handoff_dir") or ""))
    return {
        task_id
        for task_id, metadata in COLLECTOR.metadata.items()
        if str(metadata.get("_source") or "").startswith(str(fourth_step_root))
        and metadata.get("remotePipelineTaskId")
        and not is_test_history_task(metadata)
    }


def production_capcut_tasks(
    date_label: str = "", state: str = "", remote_task_id: str = ""
) -> list[dict[str, Any]]:
    active_ids = authoritative_capcut_task_ids()
    owner = str(remote_task_id or "").strip()
    return [
        item for item in STORE.tasks(date_label, state)
        if item.get("task_id") in active_ids
        and item.get("remote_pipeline_task_id")
        and (not owner or str(item.get("remote_pipeline_task_id") or "") == owner)
        and not is_test_history_task(item)
    ]


def upload_task_index() -> dict[str, dict[str, Any]]:
    path = resolve_path(str(CONFIG.get("upload_status_file") or ""))
    payload = read_json_object(path)
    tasks = payload.get("tasks") if isinstance(payload.get("tasks"), dict) else {}
    return {
        str(task_id): item
        for task_id, item in tasks.items()
        if isinstance(item, dict)
    }


def _local_or_cloud_final_is_valid(
    task: dict[str, Any], upload_tasks: dict[str, dict[str, Any]]
) -> bool:
    output = Path(str(task.get("output_path") or ""))
    try:
        if output.is_file() and output.stat().st_size > 0:
            return True
    except OSError:
        pass
    upload = upload_tasks.get(str(task.get("task_id") or ""), {})
    if str(upload.get("status") or "") != "uploaded":
        return False
    cleanup = upload.get("cleanup") if isinstance(upload.get("cleanup"), dict) else {}
    try:
        cloud_size = int(
            upload.get("cloudSize")
            or cleanup.get("cloudVerifiedSize")
            or 0
        )
    except (TypeError, ValueError):
        cloud_size = 0
    return cloud_size > 0


def remote_capcut_summaries() -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in production_capcut_tasks():
        remote_id = str(item.get("remote_pipeline_task_id") or "")
        if remote_id:
            grouped.setdefault(remote_id, []).append(item)
    upload_tasks = upload_task_index()
    summaries: dict[str, dict[str, Any]] = {}
    for remote_id, rows in grouped.items():
        unique = {str(row.get("task_id") or ""): row for row in rows}
        items = list(unique.values())
        expected = max((safe_int(row.get("expected_task_count")) for row in items), default=0)
        completed = sum(1 for row in items if row.get("state") in COMPLETED_STATES)
        failed = sum(1 for row in items if row.get("state") in FAILED_STATES)
        valid = sum(
            1 for row in items
            if row.get("state") in COMPLETED_STATES
            and _local_or_cloud_final_is_valid(row, upload_tasks)
        )
        total = len(items)
        summaries[remote_id] = {
            "expected": expected,
            "total": total,
            "completed": completed,
            "valid": valid,
            "failed": failed,
            "waiting": sum(1 for row in items if task_category(str(row.get("state") or "")) == "waiting"),
            "running": sum(1 for row in items if task_category(str(row.get("state") or "")) == "running"),
            "complete": bool(
                expected > 0
                and total == expected
                and completed == expected
                and valid == expected
                and failed == 0
            ),
            "updatedAt": max((str(row.get("updated_at") or "") for row in items), default=""),
        }
    return summaries


def task_box_payloads(date_label: str = "") -> list[dict[str, Any]]:
    capcut = remote_capcut_summaries()
    projects = [
        dict(item) for item in COLLECTOR.project_download_statuses
        if not date_label or str(item.get("date") or "") == date_label
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in projects:
        batch_id = str(item.get("batchId") or item.get("taskId") or "")
        if batch_id:
            grouped.setdefault(batch_id, []).append(item)
    boxes: list[dict[str, Any]] = []
    for batch_id, rows in grouped.items():
        normalized: list[dict[str, Any]] = []
        for raw in rows:
            task_id = str(raw.get("taskId") or "")
            expected = max(0, safe_int(raw.get("expectedCount")))
            download_completed = min(expected, max(0, safe_int(raw.get("completed"))))
            capcut_state = dict(capcut.get(task_id) or {})
            if not capcut_state:
                capcut_state = {
                    "expected": expected, "total": 0, "completed": 0,
                    "valid": 0, "failed": 0, "waiting": 0,
                    "running": 0, "complete": False, "updatedAt": "",
                }
            source_status = str(raw.get("status") or "").lower()
            pipeline_status = str(raw.get("pipelineStatus") or "").lower()
            pipeline_state_text = str(raw.get("pipelineStateText") or "").strip()
            # ``status=completed`` is only the Step 1/2 terminal marker.
            # Pipeline state must be considered before date-level CapCut
            # summaries: those summaries can briefly be empty while a task is
            # blocked in its current CapCut attempt.
            if pipeline_status in {"blocked_capcut", "capcut_failed"}:
                status = "blocked"
                current_step = "第 5 步 CapCut 成片需要安全继续"
                state_text = pipeline_state_text or "CapCut 有失败、停止或等待恢复的任务"
            elif pipeline_status in {"capcut_pending", "capcut_running"}:
                status = "running"
                current_step = "第 5 步 CapCut 成片"
                state_text = pipeline_state_text or "正在准备或运行 CapCut"
            elif capcut_state.get("complete"):
                status = "completed"
                current_step = "第5步完成，最终成片已验证"
                state_text = f"完整流程完成 {expected} / {expected}"
            elif safe_int(capcut_state.get("failed")) > 0 or safe_int(capcut_state.get("total")) > expected:
                status = "blocked"
                current_step = "第5步被阻止"
                state_text = (
                    f"CapCut清单 {capcut_state.get('total', 0)} / {expected}，"
                    f"失败 {capcut_state.get('failed', 0)}"
                )
            elif safe_int(capcut_state.get("total")) > 0:
                status = "running"
                current_step = "第5步剪辑"
                state_text = (
                    f"有效成片 {capcut_state.get('valid', 0)} / {expected}，"
                    f"等待或处理中 {expected - safe_int(capcut_state.get('valid'))}"
                )
            elif bool(raw.get("gapActive")):
                status = "blocked"
                current_step = "第1/2步等待补链"
                state_text = str(raw.get("stateText") or "下载存在缺口")
            elif bool(raw.get("notStarted")):
                status = "planned"
                current_step = "等待启动"
                state_text = f"计划 {expected} 条，尚未开始"
            elif source_status in {"cancelled", "canceled"}:
                status = "cancelled"
                current_step = "已撤回"
                state_text = "任务尚未生产并已撤回"
            elif pipeline_status in {"blocked_voice", "voice_failed", "voice_login_required"}:
                # Step 1/2 may be complete while Fish is blocked.  Keep this
                # distinct from a download gap so Dashboard's safe-continue
                # command restarts only the task-scoped voice run.
                status = "blocked"
                current_step = "第 3 步配音需要安全继续"
                state_text = pipeline_state_text or "配音失败或登录失效；可安全继续重试，不会重新下载"
            elif pipeline_status == "voice_pending":
                status = "running"
                current_step = "第 3 步准备配音"
                state_text = pipeline_state_text or "第 1/2 步已完成，正在启动当前项目的配音"
            elif pipeline_status == "voice_running":
                status = "running"
                current_step = "第 3 步批量配音"
                state_text = pipeline_state_text or "正在生成语音"
            elif pipeline_status == "voice_completed":
                status = "running"
                current_step = "第 4 步AI素材拼接"
                state_text = pipeline_state_text or "配音完成，正在进入拼接"
            elif pipeline_status == "stitch_running":
                status = "running"
                current_step = "第 4 步AI素材拼接"
                state_text = pipeline_state_text or "正在拼接"
            elif pipeline_status in {"capcut_pending", "capcut_running"}:
                status = "running"
                current_step = "第 5 步CapCut剪辑"
                state_text = pipeline_state_text or "正在准备或运行CapCut"
            elif pipeline_status in {"step1_completed", "step12_completed"} and download_completed >= expected and expected:
                # A replenishment can close after the original step-1 runner
                # has exited.  Until the workbench consumes the task-scoped
                # handoff, report this as voice-pending rather than as an
                # ambiguous “waiting for later steps” state.
                status = "running"
                current_step = "第3步准备配音"
                state_text = pipeline_state_text or "第1/2步已完成，等待当前项目配音交接"
            elif download_completed >= expected and expected:
                status = "running"
                current_step = "第1/2步完成，等待后续步骤"
                state_text = f"下载与去字幕完成 {download_completed} / {expected}"
            else:
                status = "running"
                current_step = "第1/2步处理中"
                state_text = str(raw.get("stateText") or "正在处理")
            normalized.append({
                "taskId": task_id,
                "batchId": batch_id,
                # Keep the durable workbench identity on the public task-box
                # record.  Consumers must never recover these values from a
                # date-wide pipeline ledger: a task can keep its production
                # date while a later task is already running.
                "canonicalTaskId": str(raw.get("canonicalTaskId") or task_id),
                "manifestId": str(raw.get("manifestId") or ""),
                "attemptId": str(raw.get("attemptId") or ""),
                "pipelineStatus": pipeline_status,
                "pipelineStateText": pipeline_state_text,
                "currentPhase": str(raw.get("currentPhase") or ""),
                "languagePlan": list(raw.get("languagePlan") or []) if isinstance(raw.get("languagePlan"), list) else [],
                "gapActive": bool(raw.get("gapActive")),
                "sequence": max(1, safe_int(raw.get("batchSequence"), 1)),
                "batchSize": max(1, safe_int(raw.get("batchSize"), len(rows) or 1)),
                "productionDate": str(raw.get("productionDate") or raw.get("date") or ""),
                "project": str(raw.get("project") or "未分类"),
                "material": str(raw.get("material") or ""),
                "expected": expected,
                "downloadCompleted": download_completed,
                "finalCompleted": min(expected, safe_int(capcut_state.get("valid"))),
                "historicalFailed": safe_int(raw.get("historicalFailed")),
                "status": status,
                "stateText": state_text,
                "currentStep": current_step,
                "currentTask": str(raw.get("currentTask") or ""),
                "error": str(raw.get("error") or ""),
                "updatedAt": max(
                    (str(raw.get("updatedAt") or ""), str(capcut_state.get("updatedAt") or "")),
                    key=parse_time,
                ),
                "capcut": capcut_state,
            })
        normalized.sort(key=lambda item: (item["sequence"], item["taskId"]))
        current = next(
            (item for item in normalized if item["status"] not in {"completed", "cancelled"}),
            None,
        )
        next_item = next(
            (
                item for item in normalized
                if current and item["sequence"] > current["sequence"]
                and item["status"] not in {"completed", "cancelled"}
            ),
            None,
        )
        completed_projects = sum(1 for item in normalized if item["status"] == "completed")
        cancelled_projects = sum(1 for item in normalized if item["status"] == "cancelled")
        declared_sizes = {
            safe_int(item.get("batchSize"))
            for item in normalized
            if safe_int(item.get("batchSize")) > 0
        }
        # A receiver manifest has one declared project count.  Do not infer a
        # historical total with max(rows, batchSize): missing rows must remain
        # visibly incomplete instead of becoming a smaller synthetic box.
        project_count = declared_sizes.pop() if len(declared_sizes) == 1 else len(normalized)
        total_videos = sum(safe_int(item.get("expected")) for item in normalized)
        completed_videos = sum(safe_int(item.get("finalCompleted")) for item in normalized)
        box_state = (
            "completed" if project_count and completed_projects == project_count
            else "blocked" if current and current["status"] == "blocked"
            else "cancelled" if project_count and cancelled_projects == project_count
            else "running" if current else "idle"
        )
        box = {
            "batchId": batch_id,
            "productionDate": next((item["productionDate"] for item in normalized if item["productionDate"]), ""),
            "projectCount": project_count,
            "completedProjects": completed_projects,
            "cancelledProjects": cancelled_projects,
            "totalVideos": total_videos,
            "completedVideos": completed_videos,
            "state": box_state,
            "currentSequence": current["sequence"] if current else 0,
            "current": current,
            "next": next_item,
            "items": normalized,
            "updatedAt": max((item["updatedAt"] for item in normalized), default="", key=parse_time),
        }
        receipt = load_task_box_receipt(batch_id)
        if not receipt and box_state == "completed":
            receipt = persist_task_box_receipt(box)
        if receipt:
            # A valid receipt is an irreversible production fact.  Local media
            # cleanup, draft cleanup and archived detail rows cannot turn it
            # back into an active or incomplete task box.
            box.update({
                "productionDate": str(receipt.get("productionDate") or box["productionDate"]),
                "projectCount": safe_int(receipt.get("projectCount"), box["projectCount"]),
                "completedProjects": safe_int(receipt.get("projectCount"), box["completedProjects"]),
                "totalVideos": safe_int(receipt.get("plannedVideoCount"), box["totalVideos"]),
                "completedVideos": safe_int(receipt.get("completedVideoCount"), box["completedVideos"]),
                "state": "completed",
                "currentSequence": 0,
                "current": None,
                "next": None,
                "completionReceipt": {
                    "status": str(receipt.get("productionStatus") or "completed_verified"),
                    "completedAt": str(receipt.get("completedAt") or ""),
                    "receiptHash": str(receipt.get("receiptHash") or ""),
                    "uploadStatus": str(receipt.get("uploadStatus") or ""),
                },
            })
        elif project_count > len(normalized) and not current:
            box["state"] = "historical_incomplete_evidence"
            box["historyWarning"] = "历史记录不完整，等待对账"
        boxes.append(box)
    return sorted(boxes, key=lambda item: parse_time(item.get("updatedAt")), reverse=True)


def authoritative_active_task_box(boxes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the task box currently owned by Workbench.

    Task boxes are sorted by their latest update time for display.  That order
    is not a production scheduling contract: a later batch can receive a voice
    or download update while an earlier batch still has unfinished CapCut
    rows.  Safe Continue must therefore follow Workbench's durable current
    context whenever that task is still non-terminal.
    """
    active_task_id = COLLECTOR.active_workbench_task_id()
    if active_task_id:
        for box in boxes:
            items = box.get("items") if isinstance(box.get("items"), list) else []
            active_item = next(
                (
                    item for item in items
                    if str(item.get("taskId") or "") == active_task_id
                    and str(item.get("status") or "") not in {"completed", "cancelled"}
                ),
                None,
            )
            if not isinstance(active_item, dict):
                continue
            # Usually this is already box["current"].  Rebuild a shallow public
            # view when a previously buggy queue advanced past it, so every
            # consumer still receives the exact Workbench-owned identity.
            selected = dict(box)
            selected["current"] = active_item
            selected["currentSequence"] = safe_int(active_item.get("sequence"), 0)
            selected["state"] = "blocked" if active_item.get("status") == "blocked" else "running"
            selected["next"] = next(
                (
                    item for item in items
                    if safe_int(item.get("sequence")) > safe_int(active_item.get("sequence"))
                    and str(item.get("status") or "") not in {"completed", "cancelled"}
                ),
                None,
            )
            return selected
    return next((box for box in boxes if box.get("state") in {"running", "blocked"}), None)


def archived_task_payloads() -> list[dict[str, Any]]:
    """Return cancelled/merged audit rows without production totals."""
    items = []
    for raw in COLLECTOR.archived_project_statuses:
        if not isinstance(raw, dict):
            continue
        items.append({
            "taskId": str(raw.get("taskId") or ""),
            "batchId": str(raw.get("batchId") or ""),
            "productionDate": str(raw.get("productionDate") or raw.get("date") or ""),
            "project": str(raw.get("project") or "未分类"),
            "material": str(raw.get("material") or ""),
            "status": str(raw.get("status") or "cancelled"),
            "reason": str(raw.get("archiveReason") or raw.get("cancelReason") or "已撤回"),
            "archivedAt": str(raw.get("archivedAt") or raw.get("cancelledAt") or raw.get("updatedAt") or ""),
        })
    return sorted(items, key=lambda item: parse_time(item.get("archivedAt")), reverse=True)


def pipeline_for_date(date_label: str, remote_task_id: str = "") -> dict[str, dict[str, Any]]:
    selected = date_label or current_date_label()
    stages: dict[str, dict[str, Any]] = {}
    for key in ("download", "voice", "stitch", "capcut"):
        historical = COLLECTOR.pipeline_history[key].get(selected)
        live = COLLECTOR.pipeline[key]
        if selected == current_date_label() and live.get("state") == "running":
            stages[key] = dict(live)
        elif historical:
            stages[key] = dict(historical)
        elif selected == current_date_label() and live.get("historyDate") == selected:
            stages[key] = dict(live)
        else:
            stages[key] = Collector.empty_stage(f"{selected} 无记录")
            stages[key]["historyDate"] = selected
    formal_capcut_tasks = production_capcut_tasks(selected, remote_task_id=remote_task_id)
    if formal_capcut_tasks and not (
        selected == current_date_label() and COLLECTOR.pipeline["stitch"].get("state") == "running"
    ):
        stages["stitch"] = Collector.normalize_stage(
            {
                "state": "completed",
                "stateText": f"正式交接完成 {len(formal_capcut_tasks)} 条",
                "total": len(formal_capcut_tasks),
                "completed": len(formal_capcut_tasks),
                "failed": 0,
                "progress": 100,
                "current": "按第4步到第5步正式清单统计",
                "historyDate": selected,
                "updatedAt": max(
                    (str(item.get("updated_at") or "") for item in formal_capcut_tasks),
                    default="",
                ),
            },
            "第4步正式交接清单",
        )
    stages["capcut"] = capcut_stage_for_tasks(formal_capcut_tasks, selected)
    # Count archived history from its own authoritative handoff rows rather
    # than the retained SQLite audit rows, which may contain old status
    # snapshots for the same test task.
    fourth_step_root = resolve_path(str(CONFIG.get("fourth_step_handoff_dir") or ""))
    stages["capcut"]["testHistoryCount"] = sum(
        1
        for metadata in COLLECTOR.metadata.values()
        if (
            str(metadata.get("_source") or "").startswith(str(fourth_step_root))
            and is_test_history_task(metadata)
        )
    )
    upload_history = COLLECTOR.pipeline_history["upload"].get(selected)
    if upload_history:
        stages["upload"] = dict(upload_history)
    elif selected == current_date_label() and COLLECTOR.pipeline["upload"].get("historyDate") == selected:
        stages["upload"] = dict(COLLECTOR.pipeline["upload"])
    else:
        stages["upload"] = Collector.empty_stage(f"{selected} 无上传记录")
        stages["upload"]["historyDate"] = selected
        stages["upload"]["source"] = "百度网盘上传状态"
    return decorate_pipeline_stages(stages)


def overview_payload(date_label: str = "", remote_task_id: str = "") -> dict[str, Any]:
    tasks = production_capcut_tasks(date_label, remote_task_id=remote_task_id)
    counts = {"total": len(tasks), "waiting": 0, "running": 0, "completed": 0, "failed": 0}
    for item in tasks:
        counts[task_category(item["state"])] += 1
    dates = sorted({item["date_label"] for item in tasks if item["date_label"]}, reverse=True)
    # Prefer the task that still needs attention over an arbitrary completed row
    # when all tasks were written in the same status update.
    current_priority = {"running": 4, "failed": 3, "waiting": 2, "completed": 1}
    latest = max(
        tasks,
        key=lambda item: (
            current_priority[task_category(item["state"])],
            item["source_timestamp"],
            item["updated_at"],
        ),
        default=None,
    )
    heartbeat = STORE.last_heartbeat()
    offline_flag = DATA_DIR / "offline.flag"
    elapsed = time.time() - COLLECTOR.last_scan_epoch if COLLECTOR.last_scan_epoch else 999999
    online = (
        not offline_flag.exists()
        and elapsed <= float(CONFIG["offline_after_seconds"])
        and bool(COLLECTOR.thread and COLLECTOR.thread.is_alive())
    )
    if counts["running"]:
        capcut_state = "running"
        capcut_text = latest["state_text"] if latest else "剪辑中"
    elif counts["failed"]:
        capcut_state = "failed"
        capcut_text = f"{counts['failed']} 条失败"
    elif counts["waiting"]:
        capcut_state = "idle"
        capcut_text = f"{counts['waiting']} 条等待处理"
    elif counts["completed"]:
        capcut_state = "completed"
        capcut_text = f"{counts['completed']} 条已完成"
    else:
        capcut_state = "idle"
        capcut_text = "等待第五步任务"
    capcut_stage = Collector.normalize_stage(
        {
            "state": capcut_state,
            "stateText": capcut_text,
            "total": counts["total"],
            "completed": counts["completed"],
            "failed": counts["failed"],
            "progress": round((counts["completed"] + counts["failed"]) * 100 / counts["total"])
            if counts["total"] else 0,
            "current": (
                f"{latest['project']} / {latest['material']} / {latest['language']}"
                if latest else ""
            ),
            "updatedAt": latest["updated_at"] if latest else "",
        },
        "CapCut任务状态",
    )
    scoped_pipeline = pipeline_for_date(date_label, remote_task_id) if date_label else COLLECTOR.pipeline
    pipeline = {**scoped_pipeline, "capcut": capcut_stage}
    pipeline = decorate_pipeline_stages(pipeline)
    upload_stage = pipeline.get("upload") or Collector.empty_stage("等待第五步最终成片")
    payload = {
        "machine": {
            "name": CONFIG["machine_name"],
            "online": online,
            "status": "Alive" if online else "Machine Offline",
            "lastHeartbeat": heartbeat["created_at"] if heartbeat else None,
        },
        "metrics": public_metrics_payload(),
        "counts": counts,
        "testHistoryCount": sum(
            1 for metadata in COLLECTOR.metadata.values()
            if is_test_history_task(metadata)
        ),
        "dates": dates,
        "current": public_task_item(latest) if latest else None,
        "pipeline": pipeline,
        "upload": {
            "configured": upload_stage.get("state") != "unconfigured",
            "state": upload_stage.get("state"),
            "message": upload_stage.get("stateText"),
            "completed": upload_stage.get("completed", 0),
            "failed": upload_stage.get("failed", 0),
            "total": upload_stage.get("total", 0),
            "localCleaned": upload_stage.get("localCleaned", 0),
            "taskFilesCleaned": upload_stage.get("taskFilesCleaned", 0),
            "waitingSharedRelease": upload_stage.get("waitingSharedRelease", 0),
            "cleanupPending": upload_stage.get("cleanupPending", 0),
            "cleanupBlocked": upload_stage.get("cleanupBlocked", 0),
            "legacyRetained": upload_stage.get("legacyRetained", 0),
            "permanentKeep": upload_stage.get("permanentKeep", 0),
            "waiting": upload_stage.get("waiting", 0),
            "uploading": upload_stage.get("uploading", 0),
            "cloudVerified": upload_stage.get("cloudVerified", 0),
            "progress": upload_stage.get("progress", 0),
            "bytesTotal": upload_stage.get("bytesTotal", 0),
            "bytesUploaded": upload_stage.get("bytesUploaded", 0),
            "bytesRemaining": upload_stage.get("bytesRemaining", 0),
            "speedBytesPerSecond": upload_stage.get("speedBytesPerSecond", 0),
            "etaSeconds": upload_stage.get("etaSeconds"),
            "currentFileName": upload_stage.get("currentFileName", ""),
            "currentFileBytes": upload_stage.get("currentFileBytes", 0),
            "currentFileTotalBytes": upload_stage.get("currentFileTotalBytes", 0),
            "currentFileProgress": upload_stage.get("currentFileProgress", 0),
            "currentFileStartedAt": upload_stage.get("currentFileStartedAt", ""),
        },
        "sourceErrors": STORE.source_errors(),
        "updatedAt": COLLECTOR.last_scan_at,
    }
    return sanitize_public_value(payload)


def public_task_items(date_label: str = "", remote_task_id: str = "") -> list[dict[str, Any]]:
    items = production_capcut_tasks(date_label, remote_task_id=remote_task_id)
    return [public_task_item(item) for item in items]


def public_task_item(raw: dict[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    item["category"] = task_category(str(item.get("state") or ""))
    item["video_name"] = Path(str(item.get("video_path") or "")).name
    item["audio_name"] = Path(str(item.get("audio_path") or "")).name
    item["output_name"] = Path(str(item.get("output_path") or "")).name
    item["isTestHistory"] = is_test_history_task(item)
    item.pop("video_path", None)
    item.pop("audio_path", None)
    item.pop("output_path", None)
    item.pop("source_file", None)
    return item


def public_metrics_payload() -> dict[str, Any]:
    metrics = json.loads(json.dumps(COLLECTOR.last_metrics or {}))
    disk = metrics.get("disk") if isinstance(metrics.get("disk"), dict) else {}
    if disk:
        raw_path = str(disk.pop("path", "") or "")
        disk["label"] = Path(raw_path).drive or "成片磁盘"
    return metrics


def service_health_payload() -> list[dict[str, Any]]:
    metrics = COLLECTOR.last_metrics or {}
    processes = metrics.get("processes") if isinstance(metrics.get("processes"), dict) else {}
    overview = overview_payload()
    current = overview.get("current") if isinstance(overview.get("current"), dict) else {}
    receiver_updated = parse_time(COLLECTOR.receiver_snapshot_at)
    receiver_online = bool(
        COLLECTOR.receiver_snapshot
        and receiver_updated
        and time.time() - receiver_updated <= float(CONFIG.get("offline_after_seconds") or 180)
    )
    definitions = [
        ("dashboard", "Dashboard", True, COLLECTOR.last_scan_at),
        ("receiver", "任务接收器", receiver_online, COLLECTOR.receiver_snapshot_at),
        ("workbench", "工作台", bool(processes.get("workbench")), COLLECTOR.pipeline.get("download", {}).get("updatedAt")),
        ("voice", "语音客户端", bool(processes.get("voice")), COLLECTOR.pipeline.get("voice", {}).get("updatedAt")),
        ("capcut", "CapCut客户端", bool(processes.get("capcut")), current.get("updated_at") or ""),
        ("upload", "上传服务", bool(processes.get("upload")), COLLECTOR.pipeline.get("upload", {}).get("updatedAt")),
    ]
    return [
        {
            "key": key,
            "name": name,
            "online": online,
            "stateText": "运行中" if online else "未运行",
            "updatedAt": str(updated_at or ""),
        }
        for key, name, online, updated_at in definitions
    ]


def source_status_payload() -> dict[str, Any]:
    errors = [
        {
            "name": Path(str(item.get("path") or "")).name or "未知状态源",
            "error": str(item.get("error") or "读取失败"),
            "updatedAt": str(item.get("updated_at") or ""),
        }
        for item in STORE.source_errors()[:20]
    ]
    watchdog = read_json_object(DATA_DIR / "dashboard_watchdog_status.json")
    return {
        "errors": errors,
        "receiverError": COLLECTOR.receiver_error,
        "receiverReachedAt": COLLECTOR.receiver_snapshot_at,
        "receiverUpdatedAt": COLLECTOR.receiver_data_updated_at,
        "receiverSchemaVersion": COLLECTOR.receiver_schema_version,
        "receiverReconciledAt": COLLECTOR.receiver_reconciled_at,
        "receiverReconciliationState": COLLECTOR.receiver_reconciliation_state,
        "receiverReconciliationMessage": COLLECTOR.receiver_reconciliation_message,
        "receiverControlReady": COLLECTOR.receiver_control_ready,
        "dashboardUpdatedAt": COLLECTOR.last_scan_at,
        "watchdog": {
            "state": str(watchdog.get("state") or "unknown"),
            "message": str(watchdog.get("message") or "尚无守护状态"),
            "updatedAt": str(watchdog.get("updatedAt") or ""),
        },
        "stale": bool(
            not COLLECTOR.last_scan_epoch
            or time.time() - COLLECTOR.last_scan_epoch > float(CONFIG.get("offline_after_seconds") or 180)
        ),
    }


def reconciliation_payload(boxes: list[dict[str, Any]]) -> dict[str, Any]:
    command = continue_command_status()
    selected_box = authoritative_active_task_box(boxes)
    current = selected_box.get("current") if selected_box else None
    if not current and selected_box:
        items = selected_box.get("items") if isinstance(selected_box.get("items"), list) else []
        current = items[-1] if items else None
    date_label = str((selected_box or {}).get("productionDate") or current_date_label())
    expected = int((current or {}).get("expected") or 0)
    remote_id = str((current or {}).get("taskId") or "")
    current_target = {
        "batchId": str((selected_box or {}).get("batchId") or ""),
        "taskId": remote_id,
        "productionDate": date_label,
        "manifestId": str((current or {}).get("manifestId") or ""),
        "attemptId": str((current or {}).get("attemptId") or ""),
    }
    if current and remote_id and _continue_target_changed(command, current_target):
        # Never let a command for an earlier project masquerade as the active
        # task after we overwrite its public labels below.  The mailbox itself
        # is retired on the next continue click; this response-level guard
        # immediately unblocks the UI after a project switch/reload.
        command["archivedCommandTarget"] = {
            key: command.get(key, "")
            for key in ("batchId", "taskId", "productionDate", "manifestId", "attemptId")
        }
        command["state"] = "expired"
        command["stale"] = True
        command["expiredReason"] = "安全继续目标已变化，旧命令已归档"
        command["message"] = "旧项目的安全继续命令已归档；当前项目可按实际阶段继续。"
    stages = pipeline_for_date(date_label, remote_id)
    # `pipeline_for_date` normally selects a date history.  A task can carry
    # its immutable production date across midnight, however, so that history
    # may describe an earlier project's completed Fish/Stitch batch.  For the
    # active canonical task, use the live task-scoped voice stage instead of
    # showing an unrelated 1/1 or 19/19 result in the safe-continue panel.
    active_task_id = COLLECTOR.active_workbench_task_id()
    current_step = str((current or {}).get("currentStep") or "")
    if remote_id and remote_id == active_task_id and "配音" in current_step:
        live_voice = dict(COLLECTOR.pipeline.get("voice") or {})
        if live_voice:
            stages["voice"] = live_voice
        stages["stitch"] = Collector.empty_stage("当前项目尚未进入第4步拼接")
        stages["stitch"].update({"total": 0, "completed": 0, "failed": 0, "progress": 0})
    capcut_rows = [
        item for item in production_capcut_tasks(date_label, remote_task_id=remote_id)
        if str(item.get("remote_pipeline_task_id") or "") == remote_id
    ]
    capcut_recovery_rows = [
        item for item in STORE.tasks(date_label)
        if str(item.get("remote_pipeline_task_id") or "") == remote_id
    ]
    recoverable_draft_waiting = next(
        (item for item in capcut_recovery_rows if _is_recoverable_draft_waiting(item)),
        None,
    )
    upload = upload_task_index()
    uploaded = sum(
        1 for item in capcut_rows
        if str((upload.get(str(item.get("task_id") or "")) or {}).get("status") or "") == "uploaded"
    )
    command["batchId"] = current_target["batchId"]
    command["taskId"] = current_target["taskId"]
    command["productionDate"] = current_target["productionDate"]
    command["allowed"] = bool(COLLECTOR.receiver_control_ready and current and remote_id)
    command["receiverReconciliationState"] = COLLECTOR.receiver_reconciliation_state
    if (
        recoverable_draft_waiting
        and not process_status().get("capcut")
        and str(command.get("state") or "") in {"requested", "accepted", "running", "recovering", "blocked", "failed"}
    ):
        command["state"] = "expired"
        command["stale"] = True
        command["expiredReason"] = "CapCut 已安全停在草稿重开检查点"
        command["message"] = "等待重开草稿，可安全继续；不会重新导入、识别字幕或创建新草稿。"
    if not COLLECTOR.receiver_control_ready:
        command["message"] = "接收器状态未对账，安全继续已禁用"
    elif not current or not remote_id:
        command["message"] = "暂无活动项目，无需安全继续"
    elif str((current or {}).get("status") or "") == "blocked" and "配音" in str((current or {}).get("currentStep") or ""):
        if str(command.get("state") or "") in {"requested", "accepted", "running", "recovering", "persisted", "receiver_acknowledged", "workbench_acknowledged", "executing"}:
            command["message"] = "安全继续已发送，正在核对并恢复当前项目的缺失语音。"
        elif str(command.get("state") or "") == "expired" and command.get("stale"):
            # A terminal Fish failure is intentionally represented as an
            # expired historical command.  Do not overwrite it with the
            # generic blocked label, otherwise the Dashboard button remains
            # locked even though a fresh retry is allowed.
            command["message"] = "配音批次失败，可安全继续重试缺失语音。"
        else:
            # Do not leave a previous command as "completed" after a later
            # Fish failure.  A fresh in-flight command, however, must remain
            # visible as in-flight until the workbench writes its result.
            command["state"] = "blocked"
            command["stale"] = False
            command["message"] = (
                "第 3 步配音失败或已失效；点击安全继续只会重启当前项目的缺失语音，"
                "不会重新下载或覆盖已成功音频。"
            )
    elif (
        str((current or {}).get("status") or "") == "blocked"
        and str(command.get("state") or "") in {"requested", "accepted", "running", "recovering", "persisted", "receiver_acknowledged", "workbench_acknowledged", "executing"}
    ):
        # The project remains blocked until recovery succeeds, but that must
        # not overwrite a newly requested command.  The workbench owns the
        # command's terminal state; stale heartbeats are expired separately.
        command["stale"] = False
        current_step = str((current or {}).get("currentStep") or "")
        if "CapCut" in current_step:
            command["message"] = (
                "安全继续已发送，正在核对 CapCut 失败与等待任务；只恢复未完成成片。"
            )
        else:
            command["message"] = (
                f"安全继续已发送，正在核对“{current_step or '当前步骤'}”并恢复未完成任务。"
            )
    # A textual ``recovering`` label is not itself a lock.  The button stays
    # locked only while a matching CapCut client is actually alive, or while
    # the workbench is still in the short command-acceptance phase.
    in_flight_states = {
        "requested", "accepted", "running", "recovering", "persisted",
        "receiver_acknowledged", "workbench_acknowledged", "executing",
    }
    command_state = str(command.get("state") or "idle")
    capcut_process_alive = bool(process_status().get("capcut"))
    bound_operation_state = str(command.get("boundOperationState") or "").lower()
    retryable_bound_states = {
        "failed", "stopped", "completed_with_errors", "expired",
        "recoverable_failed",
    }
    has_live_bound_operation = bool(
        command_state in in_flight_states
        and capcut_process_alive
        and bound_operation_state not in retryable_bound_states
    )
    if command_state not in in_flight_states or bool(command.get("stale")):
        command["continueCanRetry"] = bool(command.get("allowed"))
        command["continueLockReason"] = ""
    elif has_live_bound_operation:
        command["continueCanRetry"] = False
        command["continueLockReason"] = "匹配的 CapCut 恢复操作仍在运行"
    elif bound_operation_state in retryable_bound_states or recoverable_draft_waiting:
        command["continueCanRetry"] = bool(command.get("allowed"))
        command["continueLockReason"] = ""
    else:
        command["continueCanRetry"] = False
        command["continueLockReason"] = "工作台正在接收或核对恢复命令"
    command["steps"] = [
        {"step": 1, "name": "下载 / 去字幕", "expected": expected, "actual": int((current or {}).get("downloadCompleted") or 0), "state": str((current or {}).get("status") or "idle")},
        {"step": 2, "name": "批量语音", "expected": int(stages["voice"].get("total") or 0), "actual": int(stages["voice"].get("completed") or 0), "state": str(stages["voice"].get("state") or "idle")},
        {"step": 3, "name": "AI素材拼接", "expected": int(stages["stitch"].get("total") or 0), "actual": int(stages["stitch"].get("completed") or 0), "state": str(stages["stitch"].get("state") or "idle")},
        {"step": 4, "name": "CapCut成片", "expected": expected, "actual": int((current or {}).get("finalCompleted") or 0), "state": "completed" if (current or {}).get("status") == "completed" else str((current or {}).get("status") or "idle")},
        {"step": 5, "name": "百度网盘上传", "expected": len(capcut_rows), "actual": uploaded, "state": "completed" if capcut_rows and uploaded == len(capcut_rows) else "running" if uploaded else "idle"},
    ]
    return command


def _current_stage(
    key: str,
    name: str,
    *,
    state: str = "unknown",
    completed: int = 0,
    total: int = 0,
    failed: int = 0,
    message: str = "",
    updated_at: str = "",
    scoped: bool = True,
) -> dict[str, Any]:
    """A task-scoped stage for remote consumers.

    Date-wide ledgers are intentionally retained elsewhere for the Dashboard
    history view.  This compact object is the only pipeline fact that the
    control plane may use for the currently active project.
    """
    return {
        "step": key,
        "name": name,
        "status": state or "unknown",
        "completed": max(0, int(completed or 0)),
        "total": max(0, int(total or 0)),
        "failed": max(0, int(failed or 0)),
        "message": str(message or ""),
        "updatedAt": str(updated_at or ""),
        "taskScoped": bool(scoped),
    }


def current_project_status_payload(current: dict[str, Any] | None, selected_box: dict[str, Any] | None) -> dict[str, Any]:
    """Return the authoritative facts for exactly one active project.

    Never use ``pipeline_for_date`` here.  Its rows are useful day totals but
    caused old voice/stitch/upload results to be announced under a new task.
    Unknown is safer than borrowing a number from another task.
    """
    item = dict(current or {})
    box = dict(selected_box or {})
    task_id = str(item.get("canonicalTaskId") or item.get("taskId") or "")
    production_date = str(item.get("productionDate") or box.get("productionDate") or "")
    expected = max(0, safe_int(item.get("expected")))
    pipeline_status = str(item.get("pipelineStatus") or "").lower()
    state_text = str(item.get("pipelineStateText") or item.get("stateText") or "")
    language_plan = item.get("languagePlan") if isinstance(item.get("languagePlan"), list) else []
    language_total = len([value for value in language_plan if str(value).strip()])
    identity = {
        "batchId": str(item.get("batchId") or box.get("batchId") or ""),
        "canonicalTaskId": task_id,
        "productionDate": production_date,
        "manifestId": str(item.get("manifestId") or ""),
        "attemptId": str(item.get("attemptId") or ""),
        "project": str(item.get("project") or ""),
        "material": str(item.get("material") or ""),
    }
    if not task_id:
        return {"identity": identity, "state": "idle", "stages": [], "errors": [], "updatedAt": ""}

    download_completed = safe_int(item.get("downloadCompleted"))
    download_gap_active = bool(item.get("gapActive"))
    download_state = "completed" if expected and download_completed >= expected else (
        "blocked" if download_gap_active else "running"
    )
    download_message = state_text
    if download_gap_active and expected:
        download_message = (
            f"下载与去字幕已完成 {download_completed}/{expected}，"
            f"还差 {max(0, expected - download_completed)} 条；请在 Dashboard 或任务投递器补链。"
        )
    elif download_state == "completed":
        download_message = f"下载与去字幕完成 {expected}/{expected}"
    stages = [
        _current_stage(
            "download", "下载 / 去字幕", state=download_state,
            completed=download_completed, total=expected,
            message=download_message,
            updated_at=str(item.get("updatedAt") or ""),
        )
    ]

    # A task-scoped CapCut handoff can only exist after this same task's voice
    # and stitch stages completed.  Use that handoff as a deterministic
    # fallback for older workbench snapshots that omitted languagePlan; never
    # borrow the date-wide voice total.
    capcut_rows = production_capcut_tasks(production_date, remote_task_id=task_id)
    handoff_total = len(capcut_rows)
    # Some receiver v3 snapshots intentionally omit ``languagePlan`` after a
    # completed Fish batch.  The task-scoped handoff remains the authoritative
    # record in that case; use only items carrying this exact canonical task
    # identity, never a date-wide voice total from another project.
    voice_handoff = read_json_object(resolve_path(str(CONFIG.get("voice_handoff_file") or "")))
    handoff_status = str(voice_handoff.get("status") or "").casefold()
    handoff_voice_items = [
        row for row in (voice_handoff.get("completedItems") or [])
        if isinstance(row, dict) and str(row.get("canonicalTaskId") or "") == task_id
    ]
    handoff_voice_total = len({str(row.get("taskId") or row.get("audioPath") or "") for row in handoff_voice_items if str(row.get("taskId") or row.get("audioPath") or "")})
    handoff_voice_verified = sum(
        1 for row in handoff_voice_items
        if bool(row.get("voiceVerified")) and str(row.get("audioPath") or "").strip()
    )
    voice_state = "unknown"
    voice_completed = 0
    voice_total = language_total
    if handoff_total:
        voice_state = "completed"
        voice_completed = max(language_total, handoff_total)
        voice_total = voice_completed
    elif pipeline_status == "voice_running":
        voice_state = "running"
    elif pipeline_status in {"blocked_voice", "voice_failed", "voice_login_required"}:
        voice_state = "blocked"
    elif pipeline_status in {"voice_completed", "stitch_running", "capcut_pending", "capcut_running", "completed"}:
        voice_state = "completed"
        if handoff_status == "completed" and handoff_voice_total:
            voice_total = max(language_total, handoff_voice_total)
            voice_completed = min(handoff_voice_verified, voice_total)
        else:
            voice_completed = language_total
    elif pipeline_status in {"voice_pending", "step1_completed", "step12_completed"}:
        voice_state = "waiting"
    stages.append(_current_stage(
        "voice", "批量语音", state=voice_state, completed=voice_completed,
        total=voice_total, message=state_text, updated_at=str(item.get("updatedAt") or ""),
    ))

    capcut_stage = capcut_stage_for_tasks(capcut_rows, production_date)
    # ``capcut_stage_for_tasks`` intentionally returns unknown when the
    # client has not yet written its public task rows.  The workbench's
    # task-scoped pipeline status is still authoritative in that interval.
    if pipeline_status in {"blocked_capcut", "capcut_failed"} and str(capcut_stage.get("state") or "unknown") in {"unknown", "idle", "waiting"}:
        capcut_stage = {
            **capcut_stage,
            "state": "blocked",
            "stateText": state_text or "CapCut 有失败、停止或等待恢复的任务",
            "total": expected or safe_int(capcut_stage.get("total")),
            "updatedAt": str(item.get("updatedAt") or capcut_stage.get("updatedAt") or ""),
        }
    elif pipeline_status in {"capcut_pending", "capcut_running"} and str(capcut_stage.get("state") or "unknown") in {"unknown", "idle"}:
        capcut_stage = {
            **capcut_stage,
            "state": "running",
            "stateText": state_text or "正在准备或运行 CapCut",
            "total": expected or safe_int(capcut_stage.get("total")),
            "updatedAt": str(item.get("updatedAt") or capcut_stage.get("updatedAt") or ""),
        }
    stitch_state = "unknown"
    stitch_completed = 0
    if handoff_total:
        stitch_state = "completed"
        stitch_completed = handoff_total
    elif pipeline_status == "stitch_running":
        stitch_state = "running"
    elif pipeline_status in {"blocked_stitch", "blocked_reconcile"}:
        stitch_state = "blocked"
    elif pipeline_status in {"voice_completed", "stitch_pending"}:
        stitch_state = "waiting"
    stages.append(_current_stage(
        "stitch", "AI素材拼接", state=stitch_state, completed=stitch_completed,
        total=expected if handoff_total else 0, message=state_text,
        updated_at=str(capcut_stage.get("updatedAt") or item.get("updatedAt") or ""),
    ))
    stages.append(_current_stage(
        "capcut", "CapCut成片", state=str(capcut_stage.get("state") or "unknown"),
        completed=safe_int(capcut_stage.get("completed")), total=expected if expected else safe_int(capcut_stage.get("total")),
        failed=safe_int(capcut_stage.get("failed")), message=str(capcut_stage.get("stateText") or ""),
        updated_at=str(capcut_stage.get("updatedAt") or ""),
    ))

    upload = upload_task_index()
    upload_rows = [upload.get(str(row.get("task_id") or ""), {}) for row in capcut_rows]
    uploaded = sum(1 for row in upload_rows if str(row.get("status") or "").lower() == "uploaded")
    uploading = sum(1 for row in upload_rows if str(row.get("status") or "").lower() == "uploading")
    upload_failed = sum(1 for row in upload_rows if str(row.get("status") or "").lower() in {"failed", "blocked"})
    upload_state = "unknown" if not capcut_rows else (
        "failed" if upload_failed else "completed" if uploaded == len(capcut_rows) else "running" if uploading else "waiting"
    )
    stages.append(_current_stage(
        "upload", "百度网盘上传", state=upload_state, completed=uploaded,
        total=len(capcut_rows), failed=upload_failed,
        message="" if capcut_rows else "当前项目尚未进入上传阶段",
        updated_at=max((str(row.get("updatedAt") or row.get("finishedAt") or "") for row in upload_rows), default=""),
    ))

    errors: list[dict[str, Any]] = []
    status = str(item.get("status") or "").lower()
    effective_state = status or "unknown"
    if pipeline_status in {"blocked_voice", "voice_failed", "voice_login_required", "blocked_stitch", "blocked_reconcile", "blocked_capcut", "capcut_failed"}:
        effective_state = "blocked"
    elif pipeline_status in {"voice_pending", "voice_running", "voice_completed", "stitch_pending", "stitch_running", "capcut_pending", "capcut_running"}:
        effective_state = "running"
    elif pipeline_status == "completed":
        effective_state = "completed"
    # A download gap has its own deterministic watchdog event and must not
    # simultaneously become a generic workbench failure notification.
    if (
        not download_gap_active
        and effective_state in {"failed", "blocked", "stalled", "login_required"}
        and str(item.get("error") or state_text).strip()
    ):
        errors.append({
            "component": "workbench", "phase": pipeline_status or "current",
            "errorCode": pipeline_status or status, "status": effective_state,
            "message": str(item.get("error") or state_text),
        })
    for row in capcut_rows:
        if task_category(str(row.get("state") or "")) != "failed":
            continue
        errors.append({
            "component": "capcut", "phase": str(row.get("phase") or "capcut"),
            "errorCode": str(row.get("error_code") or "capcut_failed"), "status": "failed",
            "message": str(row.get("error") or row.get("state_text") or "CapCut task failed"),
            "attemptId": str(row.get("attempt_id") or identity["attemptId"]),
        })
    return {
        "identity": identity,
        # Expose the full-pipeline state separately from the durable Step 1/2
        # status.  Consumers must not render download completion as project
        # completion when CapCut is currently blocked.
        "state": effective_state,
        "downloadStatus": status or "unknown",
        "pipelineStatus": pipeline_status or "unknown",
        "currentStep": str(item.get("currentStep") or ""),
        "stages": stages,
        "errors": errors,
        "updatedAt": str(item.get("updatedAt") or ""),
    }


def dashboard_payload(date_label: str = "", batch_id: str = "") -> dict[str, Any]:
    boxes = task_box_payloads()
    active_box = authoritative_active_task_box(boxes)
    selected_box = next((box for box in boxes if box.get("batchId") == batch_id), None)
    if not selected_box and date_label:
        selected_box = next((box for box in boxes if str(box.get("productionDate") or "") == date_label), None)
    if not selected_box:
        selected_box = active_box
    selected_date = str(date_label or (selected_box or {}).get("productionDate") or current_date_label())
    current = (active_box or {}).get("current") if isinstance((active_box or {}).get("current"), dict) else {}
    remote_id = str(((selected_box or {}).get("current") or {}).get("taskId") or "")
    stages = pipeline_for_date(selected_date, remote_id)
    current_project_status = current_project_status_payload(current, active_box)
    # The Step 5 panel is a daily production ledger, not only the currently
    # active project's queue.  When the queue advances to a project that has
    # not reached CapCut yet, filtering by that project made every completed
    # earlier project appear to disappear.
    tasks = public_task_items(selected_date)
    gaps = [
        item for item in COLLECTOR.project_download_statuses
        if not selected_date or str(item.get("date") or "") == selected_date
    ]
    queue_payload: dict[str, Any] = {"items": [], "error": ""}
    template_payload: dict[str, Any] = {"items": [], "error": ""}
    try:
        queue_payload = receiver_json("/api/tasks")
    except HTTPException as exc:
        queue_payload["error"] = str(exc.detail)
    try:
        template_payload = receiver_json("/api/templates")
    except HTTPException as exc:
        template_payload["error"] = str(exc.detail)
    payload = {
        "selectedDate": selected_date,
        "selectedBatchId": str((selected_box or {}).get("batchId") or ""),
        "availableDates": pipeline_dates(),
        "overview": overview_payload(selected_date),
        "pipeline": {"date": selected_date, "availableDates": pipeline_dates(), "items": list(stages.values())},
        "tasks": {"items": tasks, "count": len(tasks)},
        "events": {"items": STORE.events(30)},
        "projectGaps": {"items": gaps},
        "receiverQueue": queue_payload,
        "templates": template_payload,
        "taskBoxes": {"items": boxes, "selected": selected_box, "history": archived_task_payloads()},
        # ``pipeline`` remains the date ledger for the visual history.  These
        # two fields are the single fact domain for controls, Feishu and
        # current-project notifications.
        "currentProjectStatus": current_project_status,
        "currentProjectErrors": current_project_status.get("errors") or [],
        "controls": {
            "continue": reconciliation_payload(boxes),
            "uploadRescan": load_control_actions().get("uploadRescan") or {"state": "idle", "message": "尚未手动检查上传缺口"},
            "historicalCloudVerification": historical_cloud_verification_status(),
            "capcutDraftCleanup": load_control_actions().get("capcutDraftCleanup") or {"state": "idle", "message": "尚未手动清理 CapCut 草稿"},
            "audioCleanup": load_control_actions().get("audioCleanup") or {"state": "idle", "message": "尚未手动清理音频"},
            "productionFileCleanup": load_control_actions().get("productionFileCleanup") or {"state": "idle", "message": "尚未手动清理生产文件"},
            "resetRecords": load_control_actions().get("resetRecords") or {"state": "idle", "message": "尚未重置测试记录"},
        },
        "services": service_health_payload(),
        "sources": source_status_payload(),
        "updatedAt": COLLECTOR.last_scan_at,
    }
    return sanitize_public_value(payload)


def dashboard_summary_payload() -> dict[str, Any]:
    """Small, current-fact-only payload for remote polling.

    Historical rows, event logs, cleanup inventories and full CapCut task
    tables are deliberately excluded and remain available on demand through
    the existing detailed endpoints.
    """
    boxes = task_box_payloads()
    active_box = authoritative_active_task_box(boxes)
    current = active_box.get("current") if isinstance(active_box, dict) else {}
    if not isinstance(current, dict):
        current = {}
    production_date = str((active_box or {}).get("productionDate") or current.get("productionDate") or "")
    remote_id = str(current.get("taskId") or "")
    current_status = current_project_status_payload(current, active_box)
    stages = pipeline_for_date(production_date, remote_id) if active_box and production_date else {}
    active_public = None
    if isinstance(active_box, dict):
        active_public = {
            key: active_box.get(key)
            for key in (
                "batchId", "productionDate", "projectCount", "completedProjects",
                "totalVideos", "completedVideos", "state", "currentSequence",
                "current", "next", "updatedAt",
            )
        }
        active_public["items"] = [
            {
                key: item.get(key)
                for key in (
                    "taskId", "canonicalTaskId", "sequence", "project", "material",
                    "expected", "downloadCompleted", "finalCompleted", "status",
                    "currentStep", "stateText", "updatedAt",
                )
            }
            for item in active_box.get("items") or []
            if isinstance(item, dict)
        ]
    upload = stages.get("upload") if isinstance(stages.get("upload"), dict) else {}
    summary = {
        "schemaVersion": 1,
        "currentTaskBox": active_public,
        "currentProjectStatus": current_status,
        "currentProjectErrors": current_status.get("errors") or [],
        "pipeline": {
            "date": production_date,
            "items": list(stages.values()),
        },
        "services": service_health_payload(),
        "controls": {"continue": reconciliation_payload(boxes)},
        "upload": {
            "state": str(upload.get("state") or "not_started"),
            "stateText": str(upload.get("stateText") or "尚未进入上传阶段"),
            "total": safe_int(upload.get("total")),
            "completed": safe_int(upload.get("completed")),
            "failed": safe_int(upload.get("failed")),
            "progress": safe_int(upload.get("progress")),
        },
        "updatedAt": COLLECTOR.last_scan_at,
    }
    return sanitize_public_value(summary)


def dashboard_summary_etag(payload: Any) -> str:
    """Hash semantic state while ignoring heartbeat/scan clock churn."""
    volatile = {
        "updatedAt", "heartbeatAt", "lastHeartbeat", "observedAt",
        "scannedAt", "lastScanAt", "ageSeconds", "staleForSeconds",
    }

    def project(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: project(item)
                for key, item in sorted(value.items())
                if key not in volatile
            }
        if isinstance(value, list):
            return [project(item) for item in value]
        return value

    encoded = json.dumps(
        project(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f'"{hashlib.sha256(encoded).hexdigest()[:24]}"'


@asynccontextmanager
async def lifespan(_: FastAPI):
    COLLECTOR.start()
    yield
    COLLECTOR.stop()


app = FastAPI(
    title="AI视频生产线 OPS",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    if request.url.path == "/api/dashboard/summary":
        response.headers.setdefault("Cache-Control", "private, no-cache")
    elif request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "public, max-age=86400")
    else:
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    overview = overview_payload()
    return {
        "ok": True,
        "machine": overview["machine"],
        "collectorRunning": bool(COLLECTOR.thread and COLLECTOR.thread.is_alive()),
        "updatedAt": overview["updatedAt"],
    }


@app.get("/api/overview")
def overview(date: str = ""):
    return overview_payload(date)


@app.get("/api/dashboard")
def dashboard(request: Request, date: str = "", batchId: str = ""):
    require_control_permission(request)
    return dashboard_payload(date, batchId)


@app.get("/api/dashboard/summary")
def dashboard_summary(request: Request):
    require_control_permission(request)
    payload = dashboard_summary_payload()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    etag = dashboard_summary_etag(payload)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=encoded,
        media_type="application/json",
        headers={"ETag": etag, "X-Payload-Bytes": str(len(encoded))},
    )


@app.get("/api/task-boxes/current")
def task_boxes_current(request: Request):
    require_control_permission(request)
    current = authoritative_active_task_box(task_box_payloads())
    return {"current": current, "updatedAt": COLLECTOR.last_scan_at}


@app.get("/api/task-boxes/history")
def task_boxes_history(request: Request, date: str = ""):
    require_control_permission(request)
    boxes = task_box_payloads(date)
    return {
        "items": [box for box in boxes if box.get("state") not in {"running", "blocked"}],
        "updatedAt": COLLECTOR.last_scan_at,
    }


@app.get("/api/task-boxes/{batch_id}/completion-receipt")
def task_box_completion_receipt(batch_id: str, request: Request):
    require_control_permission(request)
    receipt = load_task_box_receipt(batch_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="该任务箱尚无有效完成凭证")
    return sanitize_public_value(receipt)


@app.post("/api/task-boxes/{batch_id}/reconcile")
def reconcile_task_box(batch_id: str, request: Request):
    require_control_permission(request)
    box = next((item for item in task_box_payloads() if str(item.get("batchId") or "") == batch_id), None)
    if not isinstance(box, dict):
        raise HTTPException(status_code=404, detail="未找到该任务箱的正式记录")
    receipt = load_task_box_receipt(batch_id) or persist_task_box_receipt(box)
    classification = (
        "completed_verified" if receipt
        else "active" if box.get("state") in {"running", "blocked"}
        else "cancelled" if box.get("state") == "cancelled"
        else "historical_incomplete_evidence"
    )
    result = {
        "batchId": batch_id,
        "classification": classification,
        "receiptCreated": bool(receipt),
        "receiptHash": str(receipt.get("receiptHash") or ""),
        "reconciledAt": now_iso(),
    }
    _write_json_atomic(TASK_BOX_RECONCILIATION_DIR / f"{_stable_file_id(batch_id)}.json", result)
    return result


@app.get("/api/safety")
def production_safety(request: Request):
    require_control_permission(request)
    endpoints = {
        "quality": "/api/quality/current",
        "versions": "/api/versions",
        "cloud": "/api/cloud/reconciliation",
        "disk": "/api/disk/forecast",
        "credentials": "/api/credentials/status",
        "integrity": "/api/task-integrity",
        "evidence": "/api/incidents/latest/evidence",
    }
    result: dict[str, Any] = {
        "updatedAt": now_iso(),
        "modelCalled": False,
        "sources": {},
    }
    for key, endpoint in endpoints.items():
        try:
            result[key] = control_plane_json(endpoint)
            result["sources"][key] = {"state": "ok"}
        except HTTPException as exc:
            result[key] = {
                "ok": False,
                "error": "source_unavailable",
                "message": str(exc.detail),
            }
            result["sources"][key] = {
                "state": "stale",
                "message": str(exc.detail),
            }
    try:
        boxes = task_box_payloads()
        selected = authoritative_active_task_box(boxes)
        current = selected.get("current") if isinstance(selected, dict) else {}
        result["subtitleVerification"] = subtitle_verification_inventory(
            task_id=str((current or {}).get("canonicalTaskId") or (current or {}).get("taskId") or ""),
            production_date=str((current or {}).get("productionDate") or (current or {}).get("date") or ""),
        )
        result["sources"]["subtitleVerification"] = {"state": "ok"}
    except Exception as exc:  # pragma: no cover - defensive status aggregation
        result["subtitleVerification"] = {
            "ok": False,
            "error": "source_unavailable",
            "message": f"去字幕质检状态不可用：{exc}",
        }
        result["sources"]["subtitleVerification"] = {"state": "stale", "message": str(exc)}
    try:
        result["autoRecovery"] = control_plane_json("/api/auto-recovery/status")
        result["sources"]["autoRecovery"] = {"state": "ok"}
    except HTTPException as exc:
        result["autoRecovery"] = {
            "ok": False,
            "error": "source_unavailable",
            "message": str(exc.detail),
        }
        result["sources"]["autoRecovery"] = {"state": "stale", "message": str(exc.detail)}
    return result


@app.get("/api/project-gaps")
def project_gaps(date: str = ""):
    items = list(COLLECTOR.project_download_statuses)
    if date:
        items = [item for item in items if str(item.get("date") or "") == date]
    return {"items": items, "updatedAt": COLLECTOR.last_scan_at}


@app.get("/api/controls/tasks")
def control_tasks(request: Request):
    """Expose the receiver queue to every trusted Dashboard device."""
    require_control_permission(request)
    return receiver_json("/api/tasks")


@app.get("/api/controls/templates")
def control_templates(request: Request):
    require_control_permission(request)
    return receiver_json("/api/templates")


@app.post("/api/controls/tasks/create")
async def control_create_task(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="任务不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="任务不是有效 JSON")
    return receiver_json("/api/tasks/create", method="POST", payload=payload)


@app.post("/api/controls/tasks/{task_id}/replenish")
async def control_replenish_task(task_id: str, request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="补链不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="补链不是有效 JSON")
    return receiver_json(f"/api/tasks/replenish/{task_id}", method="POST", payload=payload)


@app.post("/api/controls/tasks/{task_id}/start")
def control_start_task(task_id: str, request: Request):
    require_control_permission(request)
    return receiver_json(f"/api/tasks/{task_id}/start", method="POST")


@app.post("/api/controls/tasks/{task_id}/cancel")
def control_cancel_task(task_id: str, request: Request):
    require_control_permission(request)
    return receiver_json(f"/api/tasks/{task_id}/cancel", method="POST")


@app.post("/api/controls/continue-current")
def control_continue_current(request: Request):
    require_control_permission(request)
    if not COLLECTOR.receiver_control_ready:
        raise HTTPException(status_code=409, detail="接收器状态未对账，禁止安全继续")
    boxes = task_box_payloads()
    selected_box = authoritative_active_task_box(boxes)
    current = selected_box.get("current") if isinstance(selected_box, dict) else None
    if not isinstance(current, dict) or not str(current.get("taskId") or ""):
        raise HTTPException(status_code=409, detail="暂无活动项目，无需安全继续")
    current_task_id = str(current.get("taskId") or "")
    current_date = str(selected_box.get("productionDate") or current.get("productionDate") or "")
    current_capcut_rows = [
        item for item in STORE.tasks(current_date)
        if str(item.get("remote_pipeline_task_id") or "") == current_task_id
    ]
    if any(_is_recoverable_draft_waiting(item) for item in current_capcut_rows) and not process_status().get("capcut"):
        command_path = continue_command_file()
        previous_command = read_json_object(command_path)
        if (
            str(previous_command.get("taskId") or "") == current_task_id
            and str(previous_command.get("state") or "") in {"requested", "accepted", "running", "recovering"}
        ):
            previous_command["state"] = "expired"
            previous_command["stale"] = True
            previous_command["finishedAt"] = now_iso()
            previous_command["expiredReason"] = "CapCut 已安全停在草稿重开检查点"
            previous_command["message"] = "等待重开草稿，可安全继续"
            _write_json_atomic(command_path, previous_command)
    return request_workbench_continue({
        "batchId": str(selected_box.get("batchId") or ""),
        "taskId": current_task_id,
        "productionDate": current_date,
        "manifestId": str(current.get("manifestId") or ""),
        "attemptId": str(current.get("attemptId") or ""),
        "snapshotUpdatedAt": str(COLLECTOR.receiver_data_updated_at or ""),
    })


def _current_continue_target() -> dict[str, Any]:
    if not COLLECTOR.receiver_control_ready:
        raise HTTPException(status_code=409, detail="接收器状态未对账，禁止安全继续")
    selected_box = authoritative_active_task_box(task_box_payloads())
    current = selected_box.get("current") if isinstance(selected_box, dict) else None
    if not isinstance(current, dict) or not str(current.get("taskId") or ""):
        raise HTTPException(status_code=409, detail="暂无活动项目，无需安全继续")
    return {
        "batchId": str(selected_box.get("batchId") or ""),
        "taskId": str(current.get("taskId") or ""),
        "productionDate": str(selected_box.get("productionDate") or current.get("productionDate") or ""),
        "manifestId": str(current.get("manifestId") or ""),
        "attemptId": str(current.get("attemptId") or ""),
        "snapshotUpdatedAt": str(COLLECTOR.receiver_data_updated_at or ""),
    }


@app.post("/api/control-commands")
async def create_control_command(request: Request):
    require_control_permission(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="命令请求不是有效JSON")
    client_request_id = str(body.get("clientRequestId") or "").strip()
    target = _current_continue_target()
    command = enqueue_control_command(target, client_request_id)
    return sanitize_public_value(command)


@app.get("/api/control-commands/current")
def current_control_command(request: Request):
    require_control_permission(request)
    return continue_command_status()


@app.get("/api/control-commands/{command_id}")
def get_control_command(command_id: str, request: Request):
    require_control_permission(request)
    command = read_control_command(command_id)
    if not command:
        raise HTTPException(status_code=404, detail="未找到该安全继续命令")
    # Reconcile the active command with the workbench mailbox before reply.
    if command_id == str((_sync_queued_command_from_mailbox() or {}).get("commandId") or ""):
        command = read_control_command(command_id) or command
    return sanitize_public_value(command)


@app.post("/api/control-commands/{command_id}/cancel")
def cancel_control_command(command_id: str, request: Request):
    require_control_permission(request)
    command = read_control_command(command_id)
    if not command:
        raise HTTPException(status_code=404, detail="未找到该安全继续命令")
    if str(command.get("state") or "") == "executing":
        raise HTTPException(status_code=409, detail="工作台已开始执行，不能通过Dashboard撤回")
    if str(command.get("state") or "") not in {"completed", "blocked", "expired", "cancelled"}:
        command.update({"state": "cancelled", "finishedAt": now_iso(), "message": "命令已取消，不会延迟执行"})
        write_control_command(command)
        mailbox = read_json_object(continue_command_file())
        if str(mailbox.get("commandId") or "") == command_id and str(mailbox.get("state") or "") == "requested":
            mailbox.update({"state": "cancelled", "finishedAt": now_iso(), "message": command["message"]})
            _write_json_atomic(continue_command_file(), mailbox)
    return sanitize_public_value(command)


@app.get("/api/controls/continue-current/status")
def control_continue_current_status(request: Request):
    require_control_permission(request)
    return reconciliation_payload(task_box_payloads())


def subtitle_verification_inventory(task_id: str = "", production_date: str = "") -> dict[str, Any]:
    checkpoint_root = _workbench_root() / "handoff" / "download" / "checkpoints"
    rows: list[dict[str, Any]] = []
    if checkpoint_root.is_dir():
        for checkpoint_path in checkpoint_root.glob("*.json"):
            checkpoint = read_json_object(checkpoint_path)
            checkpoint_task_id = str(checkpoint.get("taskId") or checkpoint_path.stem)
            values = checkpoint.get("items") if isinstance(checkpoint.get("items"), dict) else {}
            for source_url, value in values.items():
                if not isinstance(value, dict):
                    continue
                output_path = Path(str(value.get("outputPath") or ""))
                inferred_date = str(checkpoint.get("productionDate") or checkpoint.get("date") or "")
                for part in output_path.parts:
                    if re.fullmatch(r"\d{1,2}\.\d{1,2}", part):
                        inferred_date = part
                        break
                if task_id and checkpoint_task_id != task_id:
                    continue
                if production_date and inferred_date != production_date:
                    continue
                verification = value.get("verification") if isinstance(value.get("verification"), dict) else {}
                status = str(verification.get("verificationStatus") or "")
                if not status:
                    status = "audit_pending" if value.get("subtitleOutcome") == "processed" else (
                        "verified_clean" if value.get("subtitleOutcome") == "verified_no_subtitle" else "not_applicable"
                    )
                rows.append({
                    "id": hashlib.sha256(f"{checkpoint_task_id}|{source_url}".encode("utf-8")).hexdigest()[:20],
                    "taskId": checkpoint_task_id,
                    "productionDate": inferred_date,
                    "sourceUrl": str(source_url),
                    "fileName": output_path.name,
                    "fileExists": output_path.is_file(),
                    "verificationStatus": status,
                    "detectedBand": verification.get("detectedBand") or [],
                    "sampleCount": int(verification.get("sampleCount") or 0),
                    "residualFrames": verification.get("residualFrames") or [],
                    "evidence": [Path(str(item)).name for item in verification.get("evidence") or []],
                    "verifiedAt": str(verification.get("verifiedAt") or ""),
                    "historicalAuditOnly": inferred_date == "8.5",
                })
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["verificationStatus"]] = counts.get(row["verificationStatus"], 0) + 1
    return {"generatedAt": now_iso(), "total": len(rows), "counts": counts, "items": rows}


@app.get("/api/subtitle-verification/current")
def subtitle_verification_current(request: Request):
    require_control_permission(request)
    boxes = task_box_payloads()
    selected = authoritative_active_task_box(boxes)
    current = selected.get("current") if isinstance(selected, dict) else {}
    return subtitle_verification_inventory(
        str((current or {}).get("taskId") or ""),
        str(selected.get("productionDate") or (current or {}).get("productionDate") or ""),
    )


@app.get("/api/subtitle-verification/audit")
def subtitle_verification_audit(request: Request, productionDate: str = ""):
    require_control_permission(request)
    return subtitle_verification_inventory(production_date=str(productionDate or ""))


@app.post("/api/subtitle-verification/retry/preview")
async def subtitle_verification_retry_preview(request: Request):
    require_control_permission(request)
    payload = await request.json()
    requested = {str(value) for value in (payload.get("ids") or [])} if isinstance(payload, dict) else set()
    inventory = subtitle_verification_inventory()
    selected = [item for item in inventory["items"] if item["id"] in requested]
    eligible = [item for item in selected if item["verificationStatus"] in {"residual_detected", "verification_failed"}]
    return {
        "previewOnly": True,
        "selected": len(selected),
        "eligible": len(eligible),
        "blocked": len(selected) - len(eligible),
        "items": eligible,
        "message": "仅生成重做预览；不会自动改变8.5或其他历史任务状态。",
    }


@app.post("/api/controls/upload/rescan")
def control_upload_rescan(request: Request):
    require_control_permission(request)
    try:
        return request_upload_rescan()
    except HTTPException as exc:
        save_control_action(
            "uploadRescan",
            {"state": "failed", "accepted": False, "message": str(exc.detail)},
        )
        raise


@app.post("/api/controls/upload/verify-history")
def control_upload_verify_history(request: Request):
    require_control_permission(request)
    try:
        return request_historical_cloud_verification()
    except HTTPException as exc:
        save_control_action(
            "historicalCloudVerification",
            {"state": "failed", "accepted": False, "message": str(exc.detail)},
        )
        raise


@app.get("/api/controls/upload/verify-history/status")
def control_upload_verify_history_status(request: Request):
    require_control_permission(request)
    return historical_cloud_verification_status()


@app.get("/api/controls/capcut-drafts")
def control_capcut_drafts(request: Request):
    require_control_permission(request)
    return capcut_draft_inventory_public()


@app.post("/api/controls/capcut-drafts/preview")
async def control_capcut_drafts_preview(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="草稿选择不是有效 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("draftIds"), list):
        raise HTTPException(status_code=400, detail="请提交要删除的草稿 ID")
    return preview_capcut_draft_cleanup(payload["draftIds"])


@app.post("/api/controls/capcut-drafts/cleanup")
async def control_capcut_drafts_cleanup(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="草稿删除请求不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="草稿删除请求无效")
    if payload.get("confirm") != CAPCUT_DRAFT_CLEANUP_CONFIRM:
        raise HTTPException(status_code=400, detail="必须明确确认移入 Windows 回收站")
    draft_ids = payload.get("draftIds")
    if not isinstance(draft_ids, list):
        raise HTTPException(status_code=400, detail="请提交要删除的草稿 ID")
    return execute_capcut_draft_cleanup(
        draft_ids,
        str(payload.get("snapshotToken") or ""),
        include_unknown=bool(payload.get("includeUnknown")),
    )


@app.get("/api/controls/capcut-drafts/cleanup/status")
def control_capcut_drafts_cleanup_status(request: Request):
    require_control_permission(request)
    status = read_json_object(CAPCUT_DRAFT_CLEANUP_STATUS_PATH)
    return status or {"state": "idle", "message": "尚未手动清理 CapCut 草稿"}


@app.get("/api/controls/audio-files")
def control_audio_files(request: Request):
    require_control_permission(request)
    return audio_inventory_public()


@app.post("/api/controls/audio-files/preview")
async def control_audio_files_preview(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="音频选择不是有效 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("audioIds"), list):
        raise HTTPException(status_code=400, detail="请提交要删除的音频 ID")
    return preview_audio_cleanup(payload["audioIds"])


@app.post("/api/controls/audio-files/recycle")
async def control_audio_files_recycle(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="音频删除请求不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="音频删除请求无效")
    if payload.get("confirm") != AUDIO_CLEANUP_CONFIRM:
        raise HTTPException(status_code=400, detail="必须明确确认将音频移入 Windows 回收站")
    audio_ids = payload.get("audioIds")
    if not isinstance(audio_ids, list):
        raise HTTPException(status_code=400, detail="请提交要删除的音频 ID")
    return execute_audio_cleanup(audio_ids, str(payload.get("snapshotToken") or ""))


@app.get("/api/controls/audio-files/recycle/status")
def control_audio_files_recycle_status(request: Request):
    require_control_permission(request)
    status = read_json_object(AUDIO_CLEANUP_STATUS_PATH)
    return status or {"state": "idle", "message": "尚未手动清理音频"}


@app.get("/api/controls/production-files")
def control_production_files(request: Request):
    require_control_permission(request)
    return production_file_inventory_public()


@app.post("/api/controls/production-files/preview")
async def control_production_files_preview(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="生产文件选择不是有效 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("fileIds"), list):
        raise HTTPException(status_code=400, detail="请提交要删除的生产文件 ID")
    return sanitize_public_value(preview_production_file_cleanup(payload["fileIds"]))


@app.post("/api/controls/production-files/recycle")
async def control_production_files_recycle(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="生产文件删除请求不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="生产文件删除请求无效")
    if payload.get("confirm") != PRODUCTION_FILE_CLEANUP_CONFIRM:
        raise HTTPException(status_code=400, detail="必须明确确认将生产文件移入 Windows 回收站")
    file_ids = payload.get("fileIds")
    if not isinstance(file_ids, list):
        raise HTTPException(status_code=400, detail="请提交要删除的生产文件 ID")
    return sanitize_public_value(execute_production_file_cleanup(
        file_ids,
        str(payload.get("snapshotToken") or ""),
    ))


@app.get("/api/controls/production-files/recycle/status")
def control_production_files_recycle_status(request: Request):
    require_control_permission(request)
    status = read_json_object(PRODUCTION_FILE_CLEANUP_STATUS_PATH)
    return sanitize_public_value(status or {"state": "idle", "message": "尚未手动清理生产文件"})


@app.post("/api/controls/testing/reset")
async def control_reset_testing_records(request: Request):
    """Archive runtime records in the receiver, then reset Dashboard state."""
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="重置确认无效") from exc
    if not isinstance(payload, dict) or payload.get("confirm") != "RESET_TEST_RECORDS":
        raise HTTPException(status_code=400, detail="必须明确确认重置全部测试记录")
    running = process_status()
    active_labels = [
        label for key, label in (
            ("workbench", "工作台"), ("voice", "语音客户端"),
            ("stitch", "拼接器"), ("capcut", "CapCut客户端"),
        )
        if running.get(key)
    ]
    if active_labels:
        raise HTTPException(
            status_code=409,
            detail=f"请先结束正在运行的生产客户端：{'、'.join(active_labels)}；记录尚未重置",
        )
    try:
        receiver_result = receiver_json("/api/testing/reset", method="POST", payload=payload, timeout=30)
    except HTTPException as exc:
        save_control_action(
            "resetRecords",
            {"state": "failed", "message": f"接收器未完成重置：{exc.detail}"},
        )
        raise

    reset_at = now_iso()
    reset_state = {
        "resetId": str(receiver_result.get("resetId") or f"reset-{uuid.uuid4().hex[:12]}"),
        "resetAt": reset_at,
        "archivedRecordCount": safe_int(receiver_result.get("archivedRecordCount")),
        "mediaDeleted": False,
    }
    save_test_reset_state(reset_state)
    STORE.clear_all()
    COLLECTOR.reset_runtime(reset_at)
    result = {
        **reset_state,
        "ok": True,
        "state": "completed",
        "message": (
            f"已备份并清空 {reset_state['archivedRecordCount']} 个测试记录；"
            "视频、音频、素材、配置与校准均保留"
        ),
    }
    save_control_action("resetRecords", result)
    return sanitize_public_value(result)


@app.get("/api/pipeline")
def pipeline(date: str = ""):
    selected = date or current_date_label()
    stages = pipeline_for_date(selected)
    return {
        "date": selected,
        "availableDates": pipeline_dates(),
        "items": list(stages.values()),
        "updatedAt": COLLECTOR.last_scan_at,
    }


@app.get("/api/tasks")
def tasks(date: str = "", state: str = "", include_history: bool = False):
    if include_history:
        items = STORE.tasks(date, state)
        for item in items:
            item["category"] = task_category(item["state"])
            item["video_name"] = Path(item["video_path"]).name if item["video_path"] else ""
            item["audio_name"] = Path(item["audio_path"]).name if item["audio_path"] else ""
            item["output_name"] = Path(item["output_path"]).name if item["output_path"] else ""
            item["isTestHistory"] = is_test_history_task(item)
            item.pop("video_path", None)
            item.pop("audio_path", None)
            item.pop("output_path", None)
            item.pop("source_file", None)
    else:
        items = public_task_items(date)
        if state:
            items = [item for item in items if item.get("state") == state]
    return {"items": items, "count": len(items), "updatedAt": COLLECTOR.last_scan_at}


@app.get("/api/events")
def events(limit: int = Query(30, ge=1, le=200)):
    return {"items": STORE.events(limit), "updatedAt": COLLECTOR.last_scan_at}


@app.exception_handler(Exception)
async def unhandled_error(_, exc: Exception):
    STORE.event("ApiError", "ERROR", "Dashboard接口异常", {"error": str(exc)})
    return JSONResponse(status_code=500, content={"error": "Dashboard暂时无法读取数据"})


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=str(CONFIG["listen_host"]),
        port=int(CONFIG["listen_port"]),
        reload=False,
        access_log=False,
    )
