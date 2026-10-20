"""Pinned three-category cleanup bodies; H2 pending_delete remains authoritative.

No app import, scanning loop, purge scheduling or production config discovery.
"""
from __future__ import annotations
from typing import Any
from functools import wraps
def cleanup_source_guard(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        marker = _CLEANUP_SOURCE_STRICT.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _CLEANUP_SOURCE_STRICT.reset(marker)
    return guarded


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
            for child in sorted(folder.rglob("*"), key=str):
                if pending_delete._is_link(child):
                    raise HTTPException(409, "草稿含链接，无法安全盘点")
                if child.is_file():
                    digest.update(str(child.relative_to(folder)).encode())
                    content_hash = hashlib.sha256()
                    with child.open('rb') as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            content_hash.update(block)
                    digest.update(content_hash.digest())
            digest.update(f"{folder.name}\0{stat.st_mtime_ns}\0".encode("utf-8", errors="replace"))
        except OSError:
            digest.update(f"{folder.name}\0missing\0".encode("utf-8", errors="replace"))
    return digest.hexdigest()


def _capcut_draft_inventory(root: Path | None = None) -> dict[str, Any]:
    raw_root = root or capcut_draft_root()
    if pending_delete.forbidden_source(raw_root) or pending_delete.linked_path(raw_root):
        return {"available": False, "message": "草稿根受保护或含链接，禁止清理", "items": []}
    root = raw_root.resolve()
    index_path = root / "root_meta_info.json"
    if pending_delete.forbidden_source(root):
        return {"available": False, "message": "用户永久保护的草稿目录，禁止清理", "items": []}
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
        "message": f"可移入待删区 {len(deletable)} 个，受保护 {len(blocked)} 个",
    }


def pending_delete_retention_days() -> float:
    try:
        value = float(CONFIG.get("pending_delete_retention_days", pending_delete.DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        value = pending_delete.DEFAULT_RETENTION_DAYS
    return min(max(value, 0.5), 30.0)


def pending_delete_note() -> str:
    days = pending_delete_retention_days()
    label = f"{days:g} 天"
    return f"保留 {label}后自动清除，期间可恢复"


def pending_delete_roots() -> list[Path]:
    roots: list[Path] = []
    try:
        partitions = psutil.disk_partitions(all=False)
    except OSError:
        partitions = []
    for partition in partitions:
        mount = Path(partition.mountpoint)
        if mount.anchor and mount == Path(mount.anchor):
            roots.append(mount / pending_delete.DIRNAME)
    return roots


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
                pending_delete.move(folder, cleanup_id=manifest["cleanupId"], source_kind="capcut_draft",
                                    retention_days=pending_delete_retention_days())
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
            "message": f"已移入待删区 {len(removed)} 个草稿（{pending_delete_note()}）；失败 {len(failed)} 个",
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


@cleanup_source_guard
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
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, "活动任务来源不可确认，禁止清理") from exc

    # The immutable Step 4/5 metadata supplies project identity even after a
    # task has left the current table.
    try:
        for item in COLLECTOR.metadata.values():
            add(item, source="正式任务清单", active=False)
    except (AttributeError, RuntimeError) as exc:
        raise HTTPException(503, "任务引用来源不可确认，禁止清理") from exc

    handoff = read_json_object(resolve_path(str(CONFIG.get("voice_handoff_file") or "")))
    if not isinstance(handoff.get("status"), str):
        raise HTTPException(503, "配音交接状态不可确认，禁止清理")
    handoff_state = str(handoff.get("status") or "").casefold()
    handoff_active = handoff_state not in {"", "completed", "completed_with_errors", "failed", "cancelled"}
    for field in ("completedItems", "failedItems", "items", "tasks"):
        values = handoff.get(field)
        if isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    add(item, source="Fish配音交接", active=handoff_active, state=handoff_state)

    upload = read_json_object(resolve_path(str(CONFIG.get("upload_status_file") or "")))
    if not isinstance(upload.get("tasks"), dict):
        raise HTTPException(503, "上传引用登记格式不可确认，禁止清理")
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
                if pending_delete.forbidden_source(path) or pending_delete.forbidden_source(path.resolve()):
                    protected_reason = "用户永久保护的草稿目录，禁止清理"
                elif pending_delete.linked_path(path):
                    protected_reason = "音频路径含链接或重解析点，禁止清理"
                if active_references and not protected_reason:
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
        "message": f"可移入待删区 {len(deletable)} 个音频；受活动任务保护 {len(blocked)} 个",
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
                pending_delete.move(path, cleanup_id=cleanup_id, source_kind="audio",
                                    retention_days=pending_delete_retention_days())
                removed.append({
                    "audioId": item["audioId"],
                    "name": item["name"],
                    "state": "pending_delete",
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
            "message": f"已移入待删区 {sum(item['state'] == 'pending_delete' for item in removed)} 个音频（{pending_delete_note()}）；失败 {len(failed)} 个",
            "removedCount": len(removed),
            "failedCount": len(failed),
            "removed": removed,
            "failed": failed,
            "updatedAt": now_iso(),
        }
        _write_json_atomic(AUDIO_CLEANUP_STATUS_PATH, result)
        save_control_action("audioCleanup", result)
        return result


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
    if _CLEANUP_SOURCE_STRICT.get() and not isinstance(payload.get("items"), dict):
        raise HTTPException(503, "项目完成状态来源不可确认，禁止清理")
    items = payload.get("items") if isinstance(payload.get("items"), dict) else {}
    return {
        str(task_id): dict(item)
        for task_id, item in items.items()
        if isinstance(item, dict)
    }


def _upload_task_records() -> list[dict[str, Any]]:
    payload = read_json_object(resolve_path(str(CONFIG.get("upload_status_file") or "")))
    tasks = payload.get("tasks")
    if _CLEANUP_SOURCE_STRICT.get() and not isinstance(tasks, (dict, list)):
        raise HTTPException(503, "正式上传登记来源不可确认，禁止清理")
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


@cleanup_source_guard
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
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, "活动任务来源不可确认，禁止清理") from exc
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
    if pending_delete.forbidden_source(path) or pending_delete.forbidden_source(resolved):
        protected_reason = "用户永久保护的草稿目录，禁止清理"
    elif pending_delete.linked_path(path):
        protected_reason = "生产文件路径含链接或重解析点，禁止清理"
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


@cleanup_source_guard
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
        "message": f"可移入待删区 {len(deletable)} 个文件；受保护 {len(blocked)} 个",
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
                pending_delete.move(path, cleanup_id=cleanup_id, source_kind="production_file",
                                    retention_days=pending_delete_retention_days())
                removed.append({
                    "fileId": item["fileId"],
                    "name": item["name"],
                    "state": "pending_delete",
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
                f"已移入待删区 {sum(item['state'] == 'pending_delete' for item in removed)} 个文件（{pending_delete_note()}）；"
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


def load_control_actions() -> dict[str, Any]:
    return read_json_object(CONTROL_ACTIONS_PATH)


def save_control_action(name: str, payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    actions = load_control_actions()
    actions[name] = {**payload, "updatedAt": now_iso()}
    temp = CONTROL_ACTIONS_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(actions, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, CONTROL_ACTIONS_PATH)


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


def control_capcut_drafts(request: Request):
    require_control_permission(request)
    return capcut_draft_inventory_public()


async def control_capcut_drafts_preview(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="草稿选择不是有效 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("draftIds"), list):
        raise HTTPException(status_code=400, detail="请提交要删除的草稿 ID")
    return preview_capcut_draft_cleanup(payload["draftIds"])


async def control_capcut_drafts_cleanup(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="草稿删除请求不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="草稿删除请求无效")
    if payload.get("confirm") != CAPCUT_DRAFT_CLEANUP_CONFIRM:
        raise HTTPException(status_code=400, detail="必须明确确认移入待删区")
    draft_ids = payload.get("draftIds")
    if not isinstance(draft_ids, list):
        raise HTTPException(status_code=400, detail="请提交要删除的草稿 ID")
    return execute_capcut_draft_cleanup(
        draft_ids,
        str(payload.get("snapshotToken") or ""),
        include_unknown=bool(payload.get("includeUnknown")),
    )


def control_capcut_drafts_cleanup_status(request: Request):
    require_control_permission(request)
    status = read_json_object(CAPCUT_DRAFT_CLEANUP_STATUS_PATH)
    return status or {"state": "idle", "message": "尚未手动清理 CapCut 草稿"}


def control_audio_files(request: Request):
    require_control_permission(request)
    return audio_inventory_public()


async def control_audio_files_preview(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="音频选择不是有效 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("audioIds"), list):
        raise HTTPException(status_code=400, detail="请提交要删除的音频 ID")
    return preview_audio_cleanup(payload["audioIds"])


async def control_audio_files_recycle(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="音频删除请求不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="音频删除请求无效")
    if payload.get("confirm") != AUDIO_CLEANUP_CONFIRM:
        raise HTTPException(status_code=400, detail="必须明确确认将音频移入待删区")
    audio_ids = payload.get("audioIds")
    if not isinstance(audio_ids, list):
        raise HTTPException(status_code=400, detail="请提交要删除的音频 ID")
    return execute_audio_cleanup(audio_ids, str(payload.get("snapshotToken") or ""))


def control_audio_files_recycle_status(request: Request):
    require_control_permission(request)
    status = read_json_object(AUDIO_CLEANUP_STATUS_PATH)
    return status or {"state": "idle", "message": "尚未手动清理音频"}


def control_production_files(request: Request):
    require_control_permission(request)
    return production_file_inventory_public()


async def control_production_files_preview(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="生产文件选择不是有效 JSON") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("fileIds"), list):
        raise HTTPException(status_code=400, detail="请提交要删除的生产文件 ID")
    return sanitize_public_value(preview_production_file_cleanup(payload["fileIds"]))


async def control_production_files_recycle(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="生产文件删除请求不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="生产文件删除请求无效")
    if payload.get("confirm") != PRODUCTION_FILE_CLEANUP_CONFIRM:
        raise HTTPException(status_code=400, detail="必须明确确认将生产文件移入待删区")
    file_ids = payload.get("fileIds")
    if not isinstance(file_ids, list):
        raise HTTPException(status_code=400, detail="请提交要删除的生产文件 ID")
    return sanitize_public_value(execute_production_file_cleanup(
        file_ids,
        str(payload.get("snapshotToken") or ""),
    ))


def control_pending_delete_status(request: Request):
    require_control_permission(request)
    return {**pending_delete.summary(pending_delete_roots()), "retentionDays": pending_delete_retention_days(),
            "note": pending_delete_note()}


async def control_pending_delete_empty(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="清空请求不是有效 JSON") from exc
    if not isinstance(payload, dict) or payload.get("confirm") != PENDING_DELETE_EMPTY_CONFIRM:
        raise HTTPException(status_code=400, detail="必须明确确认立即清空待删区")
    result = pending_delete.purge(pending_delete_roots(), everything=True)
    result["message"] = (
        f"已永久清除待删区 {result['removedCount']} 项，释放约 {result['freedBytes'] / 1024 ** 3:.1f} GB"
        + (f"；{len(result['failed'])} 项清除失败" if result["failed"] else "")
    )
    return result


def control_production_files_recycle_status(request: Request):
    require_control_permission(request)
    status = read_json_object(PRODUCTION_FILE_CLEANUP_STATUS_PATH)
    return sanitize_public_value(status or {"state": "idle", "message": "尚未手动清理生产文件"})


async def unhandled_error(_, exc: Exception):
    STORE.event("ApiError", "ERROR", "Dashboard接口异常", {"error": str(exc)})
    return JSONResponse(status_code=500, content={"error": "Dashboard暂时无法读取数据"})


def cloud_cleanup_capabilities():
    if pending_delete_retention_days() != 3:
        raise HTTPException(503, "云端清理要求待删区保留3天")
    return {"protocol": 1, "retentionDays": 3, "forbiddenDraftRootProtected": True}


def _cloud_cleanup_payload(payload):
    if not isinstance(payload, dict) or payload.get("kind") not in {"drafts", "audio", "production", "pending"}:
        raise HTTPException(400, "清理类别无效")
    ids = payload.get("ids")
    if not isinstance(ids, list) or any(not isinstance(value, str) for value in ids):
        raise HTTPException(400, "只能提交服务器对象ID列表")
    if not isinstance(payload.get("includeUnknown", False), bool):
        raise HTTPException(400, "额外确认类型无效")
    kind = payload["kind"]
    limit, length = {"drafts": (500, 160), "audio": (2000, 80), "production": (5000, 80), "pending": (0, 0)}[kind]
    ids = list(dict.fromkeys(value.strip() for value in ids if value.strip()))
    if len(ids) > limit or any(len(value) > length or "/" in value or "\\" in value or re.match(r"^[A-Za-z]:", value) for value in ids):
        raise HTTPException(400, "清理对象标识无效")
    ids = list(dict.fromkeys(value.strip() for value in ids))
    if kind != "pending" and not ids:
        raise HTTPException(400, "请至少选择一个对象")
    return kind, ids, payload.get("includeUnknown", False)


def cloud_cleanup_preview(payload):
    cloud_cleanup_capabilities()
    kind, ids, include_unknown = _cloud_cleanup_payload(payload)
    if kind == "pending":
        with pending_delete.LOCK:
            roots = pending_delete_roots()
            try:
                snapshot = pending_delete.snapshot(roots)
                preview = pending_delete.summary(roots)
            except OSError as exc:
                raise HTTPException(409, "待删区无法安全盘点") from exc
        preview.update(state="preview", snapshotToken=snapshot,
                       selectedCount=preview["count"], deletableCount=preview["count"],
                       blockedCount=preview["needsReview"], message="立即清空将永久删除已核验待删内容，不可恢复")
    else:
        callback = {"drafts": preview_capcut_draft_cleanup, "audio": preview_audio_cleanup,
                    "production": preview_production_file_cleanup}[kind]
        preview = callback(ids)
    confirm = {"drafts": CAPCUT_DRAFT_CLEANUP_CONFIRM, "audio": AUDIO_CLEANUP_CONFIRM,
               "production": PRODUCTION_FILE_CLEANUP_CONFIRM, "pending": PENDING_DELETE_EMPTY_CONFIRM}[kind]
    fields = dict(kind=kind, ids=ids, snapshotToken=preview["snapshotToken"],
                  includeUnknown=include_unknown, confirm=confirm)
    return sanitize_public_value({**preview, **CLOUD_CLEANUP_TICKETS.issue(fields)})


def cloud_cleanup_execute(payload):
    cloud_cleanup_capabilities()
    kind, ids, include_unknown = _cloud_cleanup_payload(payload)
    CLOUD_CLEANUP_TICKETS.consume(payload)
    if kind == "pending":
        with pending_delete.LOCK:
            roots = pending_delete_roots()
            try:
                if pending_delete.snapshot(roots) != payload["snapshotToken"]:
                    raise HTTPException(409, "待删区已变化，请重新预览")
                return sanitize_public_value(pending_delete.purge(roots, everything=True))
            except OSError as exc:
                raise HTTPException(409, "待删区无法安全核验") from exc
    if kind == "drafts":
        result = execute_capcut_draft_cleanup(ids, payload["snapshotToken"], include_unknown=include_unknown)
    elif kind == "audio":
        result = execute_audio_cleanup(ids, payload["snapshotToken"])
    else:
        result = execute_production_file_cleanup(ids, payload["snapshotToken"])
    return sanitize_public_value(result)


def control_cloud_cleanup_capabilities(request: Request):
    require_control_permission(request)
    return cloud_cleanup_capabilities()


async def control_cloud_cleanup_preview(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(400, "预览请求不是有效JSON") from exc
    return cloud_cleanup_preview(payload)


async def control_cloud_cleanup_execute(request: Request):
    require_control_permission(request)
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(400, "执行请求不是有效JSON") from exc
    return cloud_cleanup_execute(payload)

REQUIRED_PORTS=('AUDIO_CLEANUP_BACKUP_DIR', 'AUDIO_CLEANUP_CONFIRM', 'AUDIO_CLEANUP_LOCK', 'AUDIO_CLEANUP_STATUS_PATH', 'AUDIO_EXTENSIONS', 'BASE_DIR', 'CAPCUT_DRAFT_CLEANUP_BACKUP_DIR', 'CAPCUT_DRAFT_CLEANUP_CONFIRM', 'CAPCUT_DRAFT_CLEANUP_STATUS_PATH', 'CAPCUT_DRAFT_LOCK', 'CLOUD_CLEANUP_TICKETS', 'COLLECTOR', 'COMPLETED_STATES', 'CONFIG', 'CONTROL_ACTIONS_PATH', 'DATA_DIR', 'HTTPException', 'JSONResponse', 'LOCAL_PATH_PATTERN', 'PENDING_DELETE_EMPTY_CONFIRM', 'PRODUCTION_FILE_CATEGORY_LABELS', 'PRODUCTION_FILE_CLEANUP_BACKUP_DIR', 'PRODUCTION_FILE_CLEANUP_CONFIRM', 'PRODUCTION_FILE_CLEANUP_INDEX_PATH', 'PRODUCTION_FILE_CLEANUP_LOCK', 'PRODUCTION_FILE_CLEANUP_STATUS_PATH', 'PRODUCTION_VIDEO_EXTENSIONS', 'Path', 'SENSITIVE_KEY_PARTS', 'STORE', '_CLEANUP_SOURCE_STRICT', 'datetime', 'hashlib', 'ipaddress', 'json', 'os', 'pending_delete', 'psutil', 're', 'sqlite3', 'time', 'uuid')
