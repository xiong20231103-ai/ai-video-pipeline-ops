"""Checked-in R1 business logic extracted from f78db5a app.py.

Private implementation: bind per-session namespaces through collection.py.
No original app import, worker entry point, lifecycle or production globals.
R2 receipt and R4 safety routines remain explicit deferred adapters.
"""
from __future__ import annotations
from typing import Any
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


class Store:



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
            # Every scan re-reads ~1,500 sources and they rarely change; an
            # identical row is left alone (no write, no commit). updated_at
            # therefore means "last change", which is what readers sort by.
            if not changed and old["error"] == error:
                return
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
            # A scan re-reads every task (~2,500) and almost all are unchanged;
            # committing each identical row cost ~70 s per scan. Skip the write
            # when every stored column already matches (updated_at = last change).
            if old and not state_changed and all(
                old[column] == task[column] for column in TASK_REQUIRED_COLUMNS
            ) and all(
                old[column] == task.get(column, "") for column in TASK_OPTIONAL_COLUMNS
            ):
                return
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
        local_status = self._json(self.project_download_status_file()) or {}
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


def task_category(state: str) -> str:
    if state in COMPLETED_STATES:
        return "completed"
    if state in FAILED_STATES:
        return "failed"
    if state in WAITING_STATES:
        return "waiting"
    return "running"


def capcut_error_code(row: dict[str, Any]) -> str:
    """Return a stable code for new and legacy CapCut status files."""
    explicit = str(row.get("error_code") or row.get("errorCode") or "").strip()
    if explicit and explicit.lower() != "capcut_failed":
        return explicit
    message = str(row.get("error") or row.get("state_text") or "")
    if "未出现系统文件选择窗口" in message:
        return "CAPCUT_IMPORT_DIALOG_TIMEOUT"
    if "创建本条独立草稿" in message and "剪映主窗口不可用" in message:
        # Compatibility for v0.4.0 status rows written before the client began
        # emitting typed window-transition failures.  New rows carry the code
        # explicitly; this only lets the in-flight DENOR batch recover safely.
        return "CAPCUT_MAIN_WINDOW_TRANSITION_TIMEOUT"
    return explicit or "capcut_failed"


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


def task_box_created_at(batch_id: str) -> datetime | None:
    """Read the creation time embedded in a task box ID.

    Formal/DENOR boxes are ``*-batch-<epoch ms>-<hex>``; older dispatcher
    boxes are ``dispatch-YYYYMMDD-HHMMSS-<hex>``.
    """
    text = str(batch_id or "")
    match = re.search(r"(?<!\d)(\d{13})(?!\d)", text)
    if match:
        try:
            return datetime.fromtimestamp(int(match.group(1)) / 1000)
        except (OverflowError, OSError, ValueError):
            return None
    match = re.search(r"(?<!\d)(\d{8})-(\d{6})(?!\d)", text)
    if match:
        try:
            return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
        except ValueError:
            return None
    return None


def task_box_sort_key(box: dict[str, Any]) -> tuple[int, tuple[int, int, int], float, str]:
    """Order task boxes newest production date first, a running box on top.

    The old order (latest ``updatedAt``) let any reconciliation pass move an
    old box to the top, and compared nothing about the production date.
    The label has no year, so it is taken from the box's creation time
    (a box created on 12-31 for production date 1.2 belongs to next year).
    """
    # Only "running" is pinned: old boxes stay "blocked" for good (8.4/8.5
    # with one unfinished item) and must not sit above newer ones.
    open_box = 1 if str(box.get("state") or "") == "running" else 0
    created = task_box_created_at(str(box.get("batchId") or ""))
    reference = created or datetime.fromtimestamp(parse_time(box.get("updatedAt"), time.time()))
    production = (0, 0, 0)
    try:
        month, day = (int(part) for part in str(box.get("productionDate") or "").split(".", 1))
        candidates = []
        for year in (reference.year - 1, reference.year, reference.year + 1):
            try:
                candidates.append(datetime(year, month, day))
            except ValueError:
                continue
        if candidates:
            nearest = min(candidates, key=lambda value: abs((value - reference).total_seconds()))
            production = (nearest.year, month, day)
    except (TypeError, ValueError):
        pass
    created_seconds = created.timestamp() if created else parse_time(box.get("updatedAt"))
    return open_box, production, created_seconds, str(box.get("batchId") or "")


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
            elif pipeline_status == "capcut_draft_release_pending":
                # Every final video is verified, but the workbench will not
                # start the next project until the CapCut draft is released.
                # Counting this as completed moved Safe Continue to the next
                # project, which the workbench refused (2026-10-10 02:01).
                status = "blocked"
                current_step = "第 5 步剪映草稿待清理"
                state_text = "成片已完成，剪映草稿待清理；点安全继续即可清理，不会重新剪辑"
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
            elif pipeline_status == "completed":
                # The workbench marks a project completed only after Step 5
                # verified it.  Upload cleanup can later remove the CapCut
                # rows; without this branch a finished project fell through to
                # "第1/2步完成，等待后续步骤" (10.7 box read 0/8 on 2026-10-09).
                status = "completed"
                current_step = "第5步完成，最终成片已验证"
                state_text = pipeline_state_text or f"完整流程完成 {expected} / {expected}"
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
                "runGroupId": str(raw.get("runGroupId") or ""),
                "batchKind": str(raw.get("batchKind") or ("denor-natural-flow" if str(raw.get("project") or "") == "DENOR" else "formal")),
                "selectedProjects": list(raw.get("selectedProjects") or []),
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
                "finalCompleted": expected if status == "completed" and pipeline_status == "completed"
                else min(expected, safe_int(capcut_state.get("valid"))),
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
            "runGroupId": str(next((item.get("runGroupId") for item in normalized if item.get("runGroupId")), "")),
            "batchKind": str(next((item.get("batchKind") for item in normalized if item.get("batchKind")), "formal")),
            "selectedProjects": sorted({project for item in normalized for project in (item.get("selectedProjects") or [])}),
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
        scope_declared = any(
            str(item.get("runGroupId") or "").strip()
            and isinstance(item.get("selectedProjects"), list)
            and bool(item.get("selectedProjects"))
            for item in normalized
        )
        if box["batchKind"] == "formal" and scope_declared:
            selected_scope = set(box["selectedProjects"] or [])
            # The project selector scopes the batch; it never edits a project's
            # fixed contract count.  Keep deferred projects explicit so the
            # Dashboard cannot present them as missing or failed.
            box["unselectedProjects"] = [project for project in FORMAL_PROJECT_NAMES if project not in selected_scope]
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
        created = task_box_created_at(batch_id)
        if (box["state"] in {"blocked", "idle", "running"} and created is not None
                and (datetime.now() - created).total_seconds() > TASK_BOX_STALE_SECONDS):
            # 8.4, 8.5 and 8.25 each kept one unfinished item for good and sat
            # in the "blocked" list beside live production.  Display only:
            # nothing in the box or the receiver changes.  (updatedAt cannot
            # be used here: every collector pass refreshes it.)
            box["state"] = "stale"
            box["historyWarning"] = "创建已超过 14 天且仍未完成，按历史未完成显示"
        boxes.append(box)
    return sorted(boxes, key=task_box_sort_key, reverse=True)


def authoritative_active_task_box(boxes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the task box currently owned by Workbench.

    Task boxes are sorted by production date for display.  That order
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
        # A stale Workbench context can point at a task that just reached a
        # terminal state while a newer, already-owned task is still blocked.
        # In that narrow case keep the unique non-terminal box available for
        # Safe Continue.  With no explicit context at all we still return
        # None, so historical rows can never become the current task merely
        # because they were updated recently.
        non_terminal = [
            box for box in boxes
            if isinstance(box, dict)
            and str(box.get("state") or "") not in {"completed", "cancelled", "historical_incomplete_evidence", "stale"}
            and isinstance(box.get("current"), dict)
            and str(box.get("current", {}).get("status") or "") not in {"completed", "cancelled"}
        ]
        if len(non_terminal) == 1:
            return non_terminal[0]
    # Without an explicit Workbench-owned current task there is no safe
    # current production identity.  Do not silently promote the most recently
    # updated historical/running-looking box into the control target.
    return None


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
    has_specific_capcut_failure = any(
        task_category(str(row.get("state") or "")) == "failed"
        for row in capcut_rows
    )
    if (
        not download_gap_active
        and effective_state in {"failed", "blocked", "stalled", "login_required"}
        and str(item.get("error") or state_text).strip()
        and not (pipeline_status in {"blocked_capcut", "capcut_failed"} and has_specific_capcut_failure)
    ):
        structured_code = str(item.get("errorCode") or "").strip()
        if not structured_code:
            # Older workbench snapshots exposed only their pipeline state.
            # Translate the known task-scoped terminal states into the same
            # structured codes used by the auto-recovery allowlist.  Login is
            # deliberately kept as a hard error; an incomplete Fish batch may
            # safely retry only its missing languages.
            structured_code = {
                "blocked_voice": "VOICE_BATCH_INCOMPLETE",
                "voice_failed": "VOICE_BATCH_INCOMPLETE",
                "voice_login_required": "VOICE_LOGIN_REQUIRED",
            }.get(pipeline_status, pipeline_status or status)
        structured_component = (
            "voice" if structured_code.startswith("VOICE_") else
            "stitch" if structured_code.startswith("STITCH_") else
            "capcut" if structured_code.startswith("CAPCUT_") else
            "upload" if structured_code.startswith("UPLOAD_") else
            "workbench"
        )
        errors.append({
            "component": structured_component, "phase": str(item.get("currentPhase") or pipeline_status or "current"),
            "errorCode": structured_code, "status": effective_state,
            "message": str(item.get("error") or state_text),
        })
    for row in capcut_rows:
        if task_category(str(row.get("state") or "")) != "failed":
            continue
        errors.append({
            "component": "capcut", "phase": str(row.get("phase") or "capcut"),
            "errorCode": capcut_error_code(row), "status": "failed",
            "message": str(row.get("error") or row.get("state_text") or "CapCut task failed"),
            "attemptId": str(row.get("attemptId") or row.get("attempt_id") or identity["attemptId"]),
        })
    for row in upload_rows:
        if str(row.get("status") or "").lower() not in {"failed", "blocked"}:
            continue
        errors.append({
            "component": "upload", "phase": str(row.get("phase") or "uploading"),
            "errorCode": str(row.get("errorCode") or row.get("error_code") or "UPLOAD_FAILED"),
            "status": "failed",
            "message": str(row.get("error") or row.get("message") or "Upload task failed"),
            "attemptId": str(row.get("attemptId") or row.get("attempt_id") or identity["attemptId"]),
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
    # A project parked for links stays in view after midnight: on 10-09 the
    # three 10.7 gaps (and their 补链 buttons) vanished once the date changed.
    live_batches = {
        str(box.get("batchId") or "") for box in boxes
        if str(box.get("state") or "") not in {"completed", "cancelled", "stale"}
    }
    gaps = [
        item for item in COLLECTOR.project_download_statuses
        if not selected_date or str(item.get("date") or "") == selected_date
        or (bool(item.get("gapActive")) and str(item.get("batchId") or "") in live_batches)
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
        "health": workbench_health_payload(),
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
                "batchId", "runGroupId", "batchKind", "selectedProjects", "productionDate", "projectCount", "completedProjects",
                "unselectedProjects",
                "totalVideos", "completedVideos", "state", "currentSequence",
                "current", "next", "updatedAt",
            )
        }
        active_public["items"] = [
            {
                key: item.get(key)
                for key in (
                    "taskId", "canonicalTaskId", "runGroupId", "batchKind", "selectedProjects", "sequence", "project", "material",
                    "expected", "downloadCompleted", "finalCompleted", "status",
                    "currentStep", "stateText", "updatedAt",
                )
            }
            for item in active_box.get("items") or []
            if isinstance(item, dict)
        ]
    upload = stages.get("upload") if isinstance(stages.get("upload"), dict) else {}
    try:
        auto_recovery = control_plane_json("/api/auto-recovery/status", timeout=1.5)
    except HTTPException as exc:
        auto_recovery = local_recovery_status()
        auto_recovery.setdefault("controlPlaneError", str(exc.detail))
    summary = {
        "schemaVersion": 3,
        "currentTaskBox": active_public,
        "currentProjectStatus": current_status,
        "currentProjectErrors": current_status.get("errors") or [],
        "health": workbench_health_payload(),
        "pipeline": {
            "date": production_date,
            "items": list(stages.values()),
        },
        "services": service_health_payload(),
        "controls": {"continue": reconciliation_payload(boxes)},
        "autoRecovery": auto_recovery,
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
