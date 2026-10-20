"""Pinned remaining read/HTTP helpers for the composed R6 host.

No installed app import, startup, mount, config discovery or __main__ execution.
"""
from __future__ import annotations
from typing import Any
from fastapi import Query
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


def load_test_reset_state() -> dict[str, Any]:
    return read_json_object(TEST_RESET_STATE_PATH)


def local_recovery_status() -> dict[str, Any]:
    """Read the Workbench's shared recovery facts when the optional control
    plane is unavailable.  Dashboard never invents a new budget or command;
    it only presents the same durable file owned by the Workbench.
    """
    workbench_dir = resolve_path(str(CONFIG.get("workbench_dir") or ""))
    if (workbench_dir / "workbench").is_dir():
        workbench_dir = workbench_dir / "workbench"
    state_path = workbench_dir / "handoff" / "control" / "automatic_recovery.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"enabled": False, "state": "paused", "stateText": "自动恢复尚未启用", "entries": []}
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        return {"enabled": False, "state": "paused", "stateText": "自动恢复状态不可确认", "errorCode": "RECOVERY_STATE_UNREADABLE", "message": str(exc)}
    if not isinstance(payload, dict) or payload.get("schemaVersion") not in {3, 4}:
        return {"enabled": False, "state": "paused", "stateText": "自动恢复状态需要迁移", "errorCode": "RECOVERY_STATE_SCHEMA_UNSUPPORTED"}
    entries = []
    for key, item in (payload.get("entries") or {}).items():
        if not isinstance(item, dict):
            continue
        entries.append({
            "stableRecoveryKey": key,
            "step": item.get("step"),
            "childTaskId": item.get("childTaskId"),
            "state": item.get("state"),
            "commandState": item.get("commandState"),
            "automaticAttemptCount": item.get("automaticAttemptCount", 0),
            "failureEventId": item.get("failureEventId"),
            "nextEligibleAt": item.get("nextEligibleAt"),
            "primaryError": item.get("primaryError"),
            "manualPause": bool(payload.get("manualPause", True)),
        })
    return {
        "enabled": not bool(payload.get("manualPause", True)) and not bool(payload.get("readError")),
        "state": "paused" if payload.get("manualPause", True) or payload.get("readError") else "ready",
        "stateText": "自动恢复已暂停" if payload.get("manualPause", True) else "自动恢复已启用",
        "entries": entries,
        "readError": payload.get("readError"),
        "migrationBlocked": bool(payload.get("migrationBlocked")),
    }


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


def health():
    overview = overview_payload()
    return {
        "ok": True,
        "machine": overview["machine"],
        "collectorRunning": bool(COLLECTOR.thread and COLLECTOR.thread.is_alive()),
        "updatedAt": overview["updatedAt"],
    }


def overview(date: str = ""):
    return overview_payload(date)


def dashboard(request: Request, date: str = "", batchId: str = ""):
    require_control_permission(request)
    return dashboard_payload(date, batchId)


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


def task_boxes_current(request: Request):
    require_control_permission(request)
    current = authoritative_active_task_box(task_box_payloads())
    return {"current": current, "updatedAt": COLLECTOR.last_scan_at}


def task_boxes_history(request: Request, date: str = ""):
    require_control_permission(request)
    boxes = task_box_payloads(date)
    return {
        "items": [box for box in boxes if box.get("state") not in {"running", "blocked"}],
        "updatedAt": COLLECTOR.last_scan_at,
    }


def task_box_completion_receipt(batch_id: str, request: Request):
    require_control_permission(request)
    receipt = load_task_box_receipt(batch_id)
    if not receipt:
        raise HTTPException(status_code=404, detail="该任务箱尚无有效完成凭证")
    return sanitize_public_value(receipt)


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


def compact_safety_payload(key: str, value: Any) -> Any:
    """Keep the remote safety card response small and free of task detail.

    The control-plane integrity endpoint can contain hundreds of thousands of
    bytes of record-level evidence.  The Dashboard safety cards only render
    aggregate counters, so forwarding the full payload made the remote page
    time out even though every local source was healthy.
    """
    if not isinstance(value, dict):
        return value
    common = {
        name: value.get(name)
        for name in ("ok", "checkedAt", "modelCalled", "text", "error", "message")
        if name in value
    }
    fields = {
        "quality": ("total", "passed", "warning", "blocked"),
        "versions": ("driftCount",),
        "cloud": ("total", "verified", "blocked"),
        "disk": ("remainingVideos", "estimatedPeakBytes", "requiredFreeBytes", "freeBytes", "ready", "reason"),
        "credentials": ("ready",),
        "integrity": ("totalRecords", "activeRecords", "hardFailureCount", "safe"),
        "evidence": (),
        "autoRecovery": (
            "schemaVersion", "enabled", "stableSeconds", "activeKey", "updatedAt",
            "state", "stateText", "attemptCount", "phase", "errorCode",
            "commandId", "commandState", "nextUserAction",
        ),
    }
    compact = {**common, **{name: value.get(name) for name in fields.get(key, ()) if name in value}}
    if key == "versions":
        # The UI only displays the component/service count.  Empty placeholders
        # retain the existing public contract without leaking their details.
        compact["items"] = [{} for _ in (value.get("items") or [])]
    if key == "credentials":
        compact["items"] = [
            {
                "service": str(item.get("service") or item.get("id") or "service"),
                "online": bool(item.get("online")),
                "required": bool(item.get("required", True)),
            }
            for item in (value.get("items") or [])
            if isinstance(item, dict)
        ]
    if key == "evidence":
        incident = value.get("incident")
        compact["incident"] = (
            {"incidentId": str(incident.get("incidentId") or "")}
            if isinstance(incident, dict)
            else None
        )
    return compact


def production_safety(request: Request):
    require_control_permission(request)
    now_mono = time.monotonic()
    cached = SAFETY_CACHE.get("payload")
    if isinstance(cached, dict) and now_mono < float(SAFETY_CACHE.get("expiresAt") or 0):
        return cached

    # The control plane obtains its authoritative task snapshot from this
    # Dashboard.  Letting every browser poll synchronously fan out to seven
    # control-plane endpoints created Dashboard -> control-plane -> Dashboard
    # request amplification and could exhaust Starlette's worker threads.  A
    # single caller refreshes the aggregate; concurrent callers get the last
    # trustworthy snapshot instead of opening another recursive request tree.
    if not SAFETY_CACHE_LOCK.acquire(blocking=False):
        if isinstance(cached, dict):
            return cached
        return {
            "updatedAt": now_iso(),
            "modelCalled": False,
            "refreshing": True,
            "sources": {},
            "productionContext": {"hasActiveProject": False, "taskBoxCompleted": False},
        }

    endpoints = {
        "quality": "/api/quality/current",
        "versions": "/api/versions",
        "cloud": "/api/cloud/reconciliation",
        "disk": "/api/disk/forecast",
        "credentials": "/api/credentials/status",
        "integrity": "/api/task-integrity",
        "evidence": "/api/incidents/latest/evidence",
    }
    try:
        result: dict[str, Any] = {
            "updatedAt": now_iso(),
            "modelCalled": False,
            "sources": {},
            "productionContext": {"hasActiveProject": False, "taskBoxCompleted": False},
        }
        for key, endpoint in endpoints.items():
            try:
                result[key] = compact_safety_payload(key, control_plane_json(endpoint))
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
            result["productionContext"] = {
                "hasActiveProject": bool((current or {}).get("hasActiveProject")),
                "taskBoxCompleted": bool((current or {}).get("taskBoxCompleted")),
            }
            subtitle_inventory = subtitle_verification_inventory(
                task_id=str((current or {}).get("canonicalTaskId") or (current or {}).get("taskId") or ""),
                production_date=str((current or {}).get("productionDate") or (current or {}).get("date") or ""),
            )
            result["subtitleVerification"] = {
                "generatedAt": subtitle_inventory.get("generatedAt"),
                "total": subtitle_inventory.get("total", 0),
                "counts": subtitle_inventory.get("counts") or {},
            }
            result["sources"]["subtitleVerification"] = {"state": "ok"}
        except Exception as exc:  # pragma: no cover - defensive status aggregation
            result["subtitleVerification"] = {
                "ok": False,
                "error": "source_unavailable",
                "message": f"去字幕质检状态不可用：{exc}",
            }
            result["sources"]["subtitleVerification"] = {"state": "stale", "message": str(exc)}
        try:
            result["autoRecovery"] = compact_safety_payload(
                "autoRecovery", control_plane_json("/api/auto-recovery/status")
            )
            result["sources"]["autoRecovery"] = {"state": "ok"}
        except HTTPException as exc:
            result["autoRecovery"] = {
                "ok": False,
                "error": "source_unavailable",
                "message": str(exc.detail),
            }
            result["sources"]["autoRecovery"] = {"state": "stale", "message": str(exc.detail)}
        SAFETY_CACHE["payload"] = result
        SAFETY_CACHE["expiresAt"] = time.monotonic() + SAFETY_CACHE_TTL_SECONDS
        return result
    finally:
        SAFETY_CACHE_LOCK.release()


def project_gaps(date: str = ""):
    items = list(COLLECTOR.project_download_statuses)
    if date:
        items = [item for item in items if str(item.get("date") or "") == date]
    return {"items": items, "updatedAt": COLLECTOR.last_scan_at}


def control_tasks(request: Request):
    """Expose the receiver queue to every trusted Dashboard device."""
    require_control_permission(request)
    return receiver_json("/api/tasks")


def control_templates(request: Request):
    require_control_permission(request)
    return receiver_json("/api/templates")


def subtitle_verification_current(request: Request):
    require_control_permission(request)
    boxes = task_box_payloads()
    selected = authoritative_active_task_box(boxes)
    current = selected.get("current") if isinstance(selected, dict) else {}
    return subtitle_verification_inventory(
        str((current or {}).get("taskId") or ""),
        str(selected.get("productionDate") or (current or {}).get("productionDate") or ""),
    )


def subtitle_verification_audit(request: Request, productionDate: str = ""):
    require_control_permission(request)
    return subtitle_verification_inventory(production_date=str(productionDate or ""))


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


def control_upload_verify_history_status(request: Request):
    require_control_permission(request)
    return historical_cloud_verification_status()


def pipeline(date: str = ""):
    selected = date or current_date_label()
    stages = pipeline_for_date(selected)
    return {
        "date": selected,
        "availableDates": pipeline_dates(),
        "items": list(stages.values()),
        "updatedAt": COLLECTOR.last_scan_at,
    }


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


def events(limit: int = Query(30, ge=1, le=200)):
    return {"items": STORE.events(limit), "updatedAt": COLLECTOR.last_scan_at}

REQUIRED_PORTS=('COLLECTOR', 'CONFIG', 'HTTPException', 'Path', 'Query', 'Response', 'SAFETY_CACHE', 'SAFETY_CACHE_LOCK', 'SAFETY_CACHE_TTL_SECONDS', 'STORE', 'TASK_BOX_RECEIPT_DIR', 'TASK_BOX_RECONCILIATION_DIR', 'TEST_RESET_STATE_PATH', '_stable_file_id', '_write_json_atomic', 'authoritative_active_task_box', 'control_plane_json', 'csv', 'current_date_label', 'dashboard_payload', 'dashboard_summary_payload', 'hashlib', 'historical_cloud_verification_status', 'is_test_history_task', 'json', 'now_iso', 'os', 'overview_payload', 'parse_time', 'pipeline_dates', 'pipeline_for_date', 'production_capcut_tasks', 'psutil', 'public_task_items', 'read_json_object', 'receiver_json', 'require_control_permission', 'resolve_path', 'safe_int', 'sanitize_public_value', 'subprocess', 'subtitle_verification_inventory', 'task_box_payloads', 'task_category', 'time', 'upload_task_index')
