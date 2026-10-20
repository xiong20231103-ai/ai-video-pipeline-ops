"""R3 ordinary command bodies extracted from fixed f78db5a app.py.

No app import, worker startup or globals loaded at import time. All native I/O,
paths, clock and Store are explicit ports. Bind through ordinary.py only.
"""
from __future__ import annotations
from typing import Any
def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


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


def receiver_base_url() -> str:
    """Return the local receiver origin without exposing its sender token."""
    status_url = str(CONFIG.get("receiver_status_url") or "http://127.0.0.1:8766/api/pipeline/snapshot")
    parts = urllib.parse.urlsplit(status_url)
    if not parts.scheme or not parts.netloc:
        raise ValueError("任务接收器地址无效")
    return f"{parts.scheme}://{parts.netloc}"


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


def load_control_actions() -> dict[str, Any]:
    return read_json_object(CONTROL_ACTIONS_PATH)


def save_control_action(name: str, payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    actions = load_control_actions()
    actions[name] = {**payload, "updatedAt": now_iso()}
    temp = CONTROL_ACTIONS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, CONTROL_ACTIONS_PATH)


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


async def control_create_task(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="任务不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="任务不是有效 JSON")
    return receiver_json("/api/tasks/create", method="POST", payload=payload)


async def control_replenish_task(task_id: str, request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="补链不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="补链不是有效 JSON")
    return receiver_json(f"/api/tasks/replenish/{task_id}", method="POST", payload=payload)


def control_start_task(task_id: str, request: Request):
    require_control_permission(request)
    return receiver_json(f"/api/tasks/{task_id}/start", method="POST")


def control_cancel_task(task_id: str, request: Request):
    require_control_permission(request)
    return receiver_json(f"/api/tasks/{task_id}/cancel", method="POST")


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


async def unhandled_error(_, exc: Exception):
    STORE.event("ApiError", "ERROR", "Dashboard接口异常", {"error": str(exc)})
    return JSONResponse(status_code=500, content={"error": "Dashboard暂时无法读取数据"})

REQUIRED_PORTS=('BASE_DIR', 'CONFIG', 'CONTROL_ACTIONS_PATH', 'DATA_DIR', 'HTTPException', 'JSONResponse', 'LOCAL_PATH_PATTERN', 'Path', 'SENSITIVE_KEY_PARTS', 'STORE', '_CLEANUP_SOURCE_STRICT', 'datetime', 'ipaddress', 'json', 'os', 'psutil', 'subprocess', 'time', 'urllib', 'uuid')
