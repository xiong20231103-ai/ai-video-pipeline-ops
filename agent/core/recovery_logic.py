"""Pinned R4 recovery bodies. No import/start of the old Dashboard.

All configuration, authority state, IO and deferred projections are explicit ports.
"""
from __future__ import annotations
from typing import Any
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


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_time(value: Any, fallback: float = 0.0) -> float:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return fallback


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


def _continue_target_signature(payload: dict[str, Any] | None) -> tuple[str, str, str, str, str, str, str, str]:
    """The identity a safe-continue command is allowed to own.

    ``batchId/taskId/date`` was enough before retries had their own CapCut
    manifest.  Keeping manifest + attempt in the signature stops a stale
    recovery from silently owning the next attempt of the same project.
    """
    value = payload or {}
    selected = value.get("selectedProjects")
    if isinstance(selected, (list, tuple, set)):
        selected_scope = ",".join(sorted({
            str(item or "").strip() for item in selected if str(item or "").strip()
        }))
    else:
        selected_scope = str(selected or "").strip()
    return (
        str(value.get("batchId") or ""),
        str(value.get("taskId") or ""),
        str(value.get("productionDate") or ""),
        str(value.get("manifestId") or ""),
        str(value.get("attemptId") or ""),
        str(value.get("runGroupId") or ""),
        str(value.get("batchKind") or ""),
        selected_scope,
    )


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
    if command_signature[5:] != target_signature[5:]:
        # A scoped submission is a separate safety domain. Retire an older
        # unscoped mailbox instead of allowing it to claim this run group.
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
    """Submit an independent request; only the workbench delivers the mailbox."""
    import importlib.util
    workbench_dir = resolve_path(str(CONFIG.get("workbench_dir") or ""))
    if (workbench_dir / "workbench").is_dir():
        workbench_dir = workbench_dir / "workbench"
    module_path = workbench_dir / "recovery_control.py"
    if not module_path.is_file():
        raise HTTPException(status_code=503, detail="共享恢复控制模块不可用")
    spec = importlib.util.spec_from_file_location("dashboard_recovery_control", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    control_dir = workbench_dir / "handoff" / "control"
    controller = module.RecoveryControl(
        control_dir / "automatic_recovery.json",
        control_dir / "automatic_recovery.lock",
        control_dir / CONTINUE_COMMAND_NAME,
    )
    payload = {
        **target, "command": "continue_current_project",
        "commandId": str(target.get("commandId") or f"continue-{uuid.uuid4().hex}"),
        "requestedAt": now_iso(), "requestedBy": "dashboard",
    }
    try:
        queued = controller.enqueue_request(payload)
    except (module.RecoveryControlError, OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=f"继续请求未提交：{exc}") from exc
    return {
        "accepted": True, "commandId": queued["commandId"], "state": queued["state"],
        **_ensure_workbench_for_continue(),
    }


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
            "runGroupId", "batchKind",
        )},
        "selectedProjects": list(target.get("selectedProjects") or []),
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
    except (OSError, ValueError, UnicodeError) as exc:
        if _CLEANUP_SOURCE_STRICT.get():
            raise HTTPException(503, "清理引用来源无法读取，请修复后重新盘点") from exc
        return {}
    if _CLEANUP_SOURCE_STRICT.get() and not isinstance(payload, dict):
        raise HTTPException(503, "清理引用来源格式无效，禁止清理")
    return payload if isinstance(payload, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _stable_file_id(value: str) -> str:
    readable = re.sub(r"[^0-9A-Za-z._-]+", "-", str(value or "")).strip("-.")[:48]
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]
    return f"{readable or 'item'}-{digest}"


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
    elif state == "executing" and expires_at and now_ts > expires_at:
        stale_reason = _stale_step12_recovery_reason(payload, now_ts)
        if stale_reason:
            payload.update({
                "state": "expired",
                "stale": True,
                "finishedAt": now_iso(),
                "terminalObservedAt": now_iso(),
                "expiredReason": stale_reason,
                "message": "第 1/2 步恢复会话已中断；25条已完成结果保留，可安全继续剩余条目",
            })
            # The mailbox is the workbench-facing source.  Retire the same
            # command there as well; otherwise its old ``recovering`` value
            # would map the durable queue record back to ``executing`` on the
            # next Dashboard poll.
            if mailbox_matches:
                retired_mailbox = dict(mailbox)
                retired_mailbox.update({
                    "state": "expired",
                    "stale": True,
                    "finishedAt": payload["finishedAt"],
                    "terminalObservedAt": payload["terminalObservedAt"],
                    "expiredReason": stale_reason,
                    "message": payload["message"],
                })
                try:
                    _write_json_atomic(continue_command_file(), retired_mailbox)
                except OSError:
                    # Read-only diagnostics and unit tests may intentionally
                    # mount the workbench mailbox without write access.  The
                    # durable Dashboard command still becomes terminal; the
                    # next writable reconciliation retires the mailbox too.
                    pass
    if payload != queued:
        write_control_command(payload)
    return payload


def _stale_step12_recovery_reason(command: dict[str, Any], now_ts: float | None = None) -> str:
    """Explain a dead 1/2-step recovery without mistaking service liveness for work.

    A live workbench process is not proof that its download/OCR child session
    survived.  The recovery state is relevant only when it belongs to this
    command and was updated after the command started.  Fresh state keeps the
    command locked; an explicit bridge failure or an interrupted state with no
    heartbeat for 90 seconds safely releases it.
    """
    now_value = float(now_ts if now_ts is not None else time.time())
    heartbeat = parse_time(str(
        command.get("lastHeartbeat")
        or command.get("executingAt")
        or command.get("startedAt")
        or command.get("requestedAt")
        or ""
    ))
    if not heartbeat or now_value - heartbeat <= CONTROL_COMMAND_CLAIM_TIMEOUT_SECONDS:
        return ""

    state_path = workbench_runtime_dir() / "handoff" / "download" / "download_batch_state.json"
    download_state = read_json_object(state_path)
    request = ((download_state.get("context") or {}).get("request") or {}) if isinstance(download_state, dict) else {}
    active_task = download_state.get("activeExternalTask") if isinstance(download_state, dict) else {}
    task_id = str(command.get("taskId") or "")
    state_task_id = str(request.get("taskId") or (active_task or {}).get("taskId") or "")
    if not task_id or state_task_id != task_id or not bool(request.get("resumeInterrupted")):
        return ""

    command_started = parse_time(str(command.get("startedAt") or command.get("requestedAt") or ""))
    state_updated = parse_time(str(download_state.get("updatedAt") or ""))
    runtime_failure = download_state.get("downloadRuntimeFailure") if isinstance(download_state, dict) else {}
    failure_observed = parse_time(str((runtime_failure or {}).get("observedAt") or ""))
    relevant_update = max(state_updated, failure_observed)
    # A stale download state from an earlier phase of the same task must not
    # expire a later Fish/CapCut/upload recovery command.
    if command_started and relevant_update < command_started:
        return ""

    if runtime_failure and failure_observed and (not command_started or failure_observed >= command_started):
        error_code = str(runtime_failure.get("errorCode") or "DOWNLOAD_BRIDGE_RUNTIME_FAILED")
        return f"第 1/2 步恢复会话已终止（{error_code}），命令已过期并解除锁定"

    stats = download_state.get("stats") if isinstance(download_state, dict) else {}
    status_text = str((stats or {}).get("status") or "")
    state_is_stale = not state_updated or now_value - state_updated > CONTROL_COMMAND_CLAIM_TIMEOUT_SECONDS
    if state_is_stale and any(marker in status_text for marker in ("运行中断", "已中断", "可安全继续")):
        return "第 1/2 步恢复状态已超过90秒未更新且明确中断，命令已过期并解除锁定"
    return ""


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


def workbench_runtime_dir() -> Path:
    path = resolve_path(str(CONFIG.get("workbench_dir") or ""))
    if (path / "workbench").is_dir():
        path = path / "workbench"
    return path


def workbench_health_payload(now: datetime | None = None) -> dict[str, Any]:
    """Open Safe Continue commands and the workbench log's recent errors.

    A step 1/2 command once sat in reconciliation_required for 8 days and
    another for a night before anyone read the log; both are shown here.
    Cached for 10 s because the summary is polled every 5 s.
    """
    if now is None and _HEALTH_CACHE["payload"] is not None and time.time() - _HEALTH_CACHE["at"] < 10:
        return _HEALTH_CACHE["payload"]
    current = now or datetime.now()
    root = workbench_runtime_dir()
    commands: list[dict[str, Any]] = []
    recovery = read_json_object(root / "handoff" / "control" / "automatic_recovery.json")
    for command in (recovery.get("commands") or {}).values():
        if not isinstance(command, dict) or str(command.get("state") or "") not in OPEN_RECOVERY_COMMAND_STATES:
            continue
        since = str(command.get("acceptedAt") or command.get("claimedAt") or command.get("updatedAt") or "")
        started = parse_time(since)
        commands.append({
            "commandId": str(command.get("commandId") or ""),
            "taskId": str(command.get("taskId") or command.get("canonicalTaskId") or ""),
            "step": str(command.get("step") or ""),
            "state": str(command.get("state") or ""),
            "since": since,
            "ageSeconds": max(0, int(current.timestamp() - started)) if started else None,
        })
    commands.sort(key=lambda item: -(item["ageSeconds"] or 0))
    errors: dict[str, dict[str, Any]] = {}
    log_found = False
    for days_back in (1, 0):
        day = current - timedelta(days=days_back)
        path = root / "handoff" / "logs" / f"workbench-{day:%Y%m%d}.log"
        try:
            with path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                handle.seek(max(0, handle.tell() - 512 * 1024))
                text = handle.read().decode("utf-8", errors="replace")
            log_found = True
        except OSError:
            continue
        for line in text.splitlines():
            match = HEALTH_LOG_LINE.match(line)
            if not match:
                continue
            stamp, message = match.groups()
            if not any(word in HEALTH_LOG_ZERO_FAILURES.sub("", message) for word in HEALTH_LOG_KEYWORDS) or any(
                    word in message for word in HEALTH_LOG_IGNORED):
                continue
            try:
                seen = datetime.fromisoformat(stamp)
            except ValueError:
                continue
            if (current - seen).total_seconds() > 24 * 3600:
                continue
            entry = errors.setdefault(message, {"message": message[:300], "count": 0, "lastAt": stamp})
            entry["count"] += 1
            entry["lastAt"] = max(entry["lastAt"], stamp)
    payload = {
        "openCommands": commands[:10],
        "openCommandCount": len(commands),
        "recentErrors": sorted(errors.values(), key=lambda item: item["lastAt"], reverse=True)[:8],
        "logAvailable": log_found,
        "updatedAt": now_iso(),
    }
    if now is None:
        _HEALTH_CACHE.update({"at": time.time(), "payload": payload})
    return payload


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
        "runGroupId": str((selected_box or {}).get("runGroupId") or (current or {}).get("runGroupId") or ""),
        "batchKind": str((selected_box or {}).get("batchKind") or (current or {}).get("batchKind") or "formal"),
        "selectedProjects": list((selected_box or {}).get("selectedProjects") or (current or {}).get("selectedProjects") or []),
    }
    if current and remote_id and _continue_target_changed(command, current_target):
        # Never let a command for an earlier project masquerade as the active
        # task after we overwrite its public labels below.  The mailbox itself
        # is retired on the next continue click; this response-level guard
        # immediately unblocks the UI after a project switch/reload.
        command["archivedCommandTarget"] = {
            key: command.get(key, "")
            for key in ("batchId", "taskId", "productionDate", "manifestId", "attemptId", "runGroupId", "batchKind", "selectedProjects")
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
        "runGroupId": str(selected_box.get("runGroupId") or current.get("runGroupId") or ""),
        "batchKind": str(selected_box.get("batchKind") or current.get("batchKind") or "formal"),
        "selectedProjects": list(selected_box.get("selectedProjects") or current.get("selectedProjects") or []),
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
        "runGroupId": str(selected_box.get("runGroupId") or current.get("runGroupId") or ""),
        "batchKind": str(selected_box.get("batchKind") or current.get("batchKind") or "formal"),
        "selectedProjects": list(selected_box.get("selectedProjects") or current.get("selectedProjects") or []),
        "snapshotUpdatedAt": str(COLLECTOR.receiver_data_updated_at or ""),
    }


async def create_control_command(request: Request):
    require_control_permission(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="命令请求不是有效JSON")
    client_request_id = str(body.get("clientRequestId") or "").strip()
    expected = _expected_continue_target(body)
    with CONTROL_COMMAND_LOCK:
        target = _current_continue_target()
        mismatched = [key for key, value in expected.items() if str(target.get(key) or "") != value]
        if mismatched:
            labels = "、".join(CONTINUE_EXPECTED_LABELS[key] for key in mismatched)
            raise HTTPException(
                status_code=409,
                detail=f"安全继续目标已变化（{labels}），请刷新页面确认当前项目后再试",
            )
        if client_request_id:
            previous = next(
                (item for item in list_control_commands()
                 if str(item.get("clientRequestId") or "") == client_request_id),
                None,
            )
            if previous and _continue_target_signature(previous) != _continue_target_signature(target):
                raise HTTPException(
                    status_code=409,
                    detail="该请求编号已用于另一个项目的安全继续，请刷新页面后重新点击",
                )
        command = enqueue_control_command(target, client_request_id)
    return sanitize_public_value(command)


def _expected_continue_target(body: dict[str, Any]) -> dict[str, str]:
    """Optional target the caller saw when it asked to continue.

    Older callers send only ``clientRequestId`` and keep working.  When a
    caller does name the project, every named field must still match the live
    target, otherwise a stale page could continue a different project.
    """
    raw = body.get("expectedTarget")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="expectedTarget 必须是对象")
    unknown = sorted(set(raw) - set(CONTINUE_EXPECTED_FIELDS))
    if unknown:
        raise HTTPException(status_code=400, detail=f"expectedTarget 含未知字段：{', '.join(unknown)}")
    expected: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"expectedTarget.{key} 必须是字符串")
        if value.strip():
            expected[key] = value.strip()
    return expected


def current_control_command(request: Request):
    require_control_permission(request)
    return continue_command_status()


def get_control_command(command_id: str, request: Request):
    require_control_permission(request)
    command = read_control_command(command_id)
    if not command:
        raise HTTPException(status_code=404, detail="未找到该安全继续命令")
    # Reconcile the active command with the workbench mailbox before reply.
    if command_id == str((_sync_queued_command_from_mailbox() or {}).get("commandId") or ""):
        command = read_control_command(command_id) or command
    return sanitize_public_value(command)


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


def control_continue_current_status(request: Request):
    require_control_permission(request)
    return reconciliation_payload(task_box_payloads())


async def unhandled_error(_, exc: Exception):
    STORE.event("ApiError", "ERROR", "Dashboard接口异常", {"error": str(exc)})
    return JSONResponse(status_code=500, content={"error": "Dashboard暂时无法读取数据"})

REQUIRED_PORTS=('BASE_DIR', 'COLLECTOR', 'CONFIG', 'CONTINUE_COMMAND_NAME', 'CONTINUE_EXPECTED_FIELDS', 'CONTINUE_EXPECTED_LABELS', 'CONTROL_COMMAND_CLAIM_TIMEOUT_SECONDS', 'CONTROL_COMMAND_DIR', 'CONTROL_COMMAND_LOCK', 'CONTROL_COMMAND_TTL_SECONDS', 'Collector', 'HEALTH_LOG_IGNORED', 'HEALTH_LOG_KEYWORDS', 'HEALTH_LOG_LINE', 'HEALTH_LOG_ZERO_FAILURES', 'HTTPException', 'JSONResponse', 'LOCAL_PATH_PATTERN', 'OPEN_RECOVERY_COMMAND_STATES', 'Path', 'RECOVERABLE_DRAFT_REOPEN_ERRORS', 'SENSITIVE_KEY_PARTS', 'STORE', '_CLEANUP_SOURCE_STRICT', '_HEALTH_CACHE', 'authoritative_active_task_box', 'current_date_label', 'datetime', 'hashlib', 'ipaddress', 'json', 'os', 'pipeline_for_date', 'process_status', 'production_capcut_tasks', 're', 'task_box_payloads', 'time', 'timedelta', 'timezone', 'upload_task_index', 'urllib', 'uuid')
