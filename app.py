from __future__ import annotations

import csv
import json
import os
import socket
import sqlite3
import subprocess
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
DB_PATH = DATA_DIR / "ops.db"
CONFIG_PATH = BASE_DIR / "config.json"

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
    "CleaningDraft": "清理草稿",
    "RecyclingSource": "回收原视频",
    "Completed": "剪辑完成",
    "Failed": "剪辑失败",
}

WAITING_STATES = {"Waiting", "waiting_capcut", "waiting_client", "stopped"}
COMPLETED_STATES = {"Completed", "completed"}
FAILED_STATES = {"Failed", "failed", "validation_failed", "manual_review"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def parse_time(value: Any, fallback: float = 0.0) -> float:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return fallback


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
        "download_root": "",
        "voice_handoff_file": "../TikHub_AI_视频工作台/tools/BatchVoiceClient-Portable/data/last_batch_handoff.json",
        "generation_output_root": "E:/生成视频",
        "capcut_handoff_dir": "../TikHub_AI_视频工作台/handoff/capcut",
        "fourth_step_handoff_dir": "../TikHub_AI_视频工作台/交接记录",
        "final_output_root": "E:/",
        "upload_status_file": "../TikHub_AI_视频工作台/handoff/upload/upload_status.json",
        "scan_interval_seconds": 2,
        "pipeline_live_after_seconds": 15,
        "heartbeat_interval_seconds": 60,
        "offline_after_seconds": 180,
        "simulation_enabled": True,
    }
    if CONFIG_PATH.exists():
        try:
            defaults.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return defaults


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
                    source_file TEXT, source_timestamp REAL, updated_at TEXT
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
            if old and float(old["source_timestamp"] or 0) > float(task["source_timestamp"]):
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
                    source_file,source_timestamp,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(task_id) DO UPDATE SET
                    batch_id=excluded.batch_id,date_label=excluded.date_label,
                    project=excluded.project,material=excluded.material,
                    language=excluded.language,number=excluded.number,sequence=excluded.sequence,
                    video_path=excluded.video_path,audio_path=excluded.audio_path,
                    output_path=excluded.output_path,state=excluded.state,
                    state_text=excluded.state_text,error=excluded.error,
                    source_file=excluded.source_file,source_timestamp=excluded.source_timestamp,
                    updated_at=excluded.updated_at""",
                (
                    task["task_id"], task["batch_id"], task["date_label"], task["project"],
                    task["material"], task["language"], task["number"], task["sequence"],
                    task["video_path"], task["audio_path"], task["output_path"], task["state"],
                    task["state_text"], task["error"], task["source_file"],
                    task["source_timestamp"], now_iso(),
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
            "download": self.empty_stage("等待工作台启动"),
            "voice": self.empty_stage("等待语音任务"),
            "stitch": self.empty_stage("等待拼接任务"),
            "upload": self.empty_stage("等待百度网盘上传"),
        }
        self.pipeline_history: dict[str, dict[str, dict[str, Any]]] = {
            "download": {},
            "voice": {},
            "stitch": {},
            "upload": {},
        }
        self.last_generation_scan_epoch = 0.0
        self.last_download_scan_epoch = 0.0

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
            data = json.loads(raw)
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
        roots = [
            resolve_path(str(self.config["capcut_handoff_dir"])),
            resolve_path(str(self.config["fourth_step_handoff_dir"])),
        ]
        metadata: dict[str, dict[str, Any]] = {}
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*.json"):
                if path.name.endswith(".status.json"):
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
                    metadata[str(item["taskId"])] = {**metadata.get(str(item["taskId"]), {}), **candidate}
        self.metadata = metadata

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
            "error": str(item.get("error") or ""),
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
                    self.store.upsert_task(
                        self.normalize_task(item, path, timestamp, batch_id, date_label)
                    )

        # Tasks not yet claimed by CapCut still appear from the fourth-step record.
        # Metadata fills tasks that CapCut has never claimed. A zero timestamp
        # prevents an older handoff state from overwriting any real client status.
        fallback_timestamp = 0.0
        for task_id, item in self.metadata.items():
            self.store.upsert_task(
                self.normalize_task(
                    item,
                    Path(item.get("_source") or ""),
                    fallback_timestamp,
                    str(item.get("_batch_id") or ""),
                    str(item.get("date") or item.get("_date_label") or ""),
                )
            )

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
        for name in ("download", "voice", "stitch"):
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

    def scan_download_pipeline(self, workbench_live: bool) -> None:
        if time.time() - self.last_download_scan_epoch < 10:
            return
        self.last_download_scan_epoch = time.time()
        root = self.download_root()
        if not root:
            return
        today = datetime.now().astimezone().date()
        today_label = f"{today.month}.{today.day}"
        grouped_files: dict[str, list[Path]] = {}
        for path in root.glob("*/*.mp4"):
            try:
                modified_date = datetime.fromtimestamp(path.stat().st_mtime).astimezone().date()
                label = f"{modified_date.month}.{modified_date.day}"
                grouped_files.setdefault(label, []).append(path)
            except OSError:
                continue
        history: dict[str, dict[str, Any]] = {}
        for date_label, files in grouped_files.items():
            latest = max(files, key=lambda item: item.stat().st_mtime)
            projects: dict[str, int] = {}
            for path in files:
                projects[path.parent.name] = projects.get(path.parent.name, 0) + 1
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
        history_date = ""
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
        if direct_timestamp >= current_timestamp:
            self.pipeline["voice"] = direct

    def scan_generation_pipeline(self, workbench_available: bool) -> None:
        if time.time() - self.last_generation_scan_epoch < 10:
            return
        self.last_generation_scan_epoch = time.time()
        root = resolve_path(str(self.config.get("generation_output_root") or ""))
        if not root.exists():
            return
        paths = list(root.glob("*/*/generation_records_*.json"))
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
            grouped.setdefault(str(item.get("date") or ""), []).append(item)
        history: dict[str, dict[str, Any]] = {}
        for date_label, items in grouped.items():
            total = len(items)
            completed = sum(1 for item in items if item.get("status") == "uploaded")
            failed = sum(1 for item in items if item.get("status") == "failed")
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
            history[date_label] = self.normalize_stage(
                {
                    "state": state,
                    "stateText": text,
                    "total": total,
                    "completed": completed,
                    "failed": failed,
                    "progress": round(
                        sum(int(item.get("progress") or 0) for item in items)
                        / max(total, 1)
                    ),
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
        self.scan_download_pipeline(workbench_available)
        self.scan_voice_pipeline()
        self.scan_generation_pipeline(workbench_available)
        self.scan_upload_pipeline()

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
    result = {"workbench": False, "voice": False, "capcut": False, "upload": False}
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
                f"{latest['project']} / {latest['material']} / {latest['language']}"
                if latest else ""
            ),
            "updatedAt": latest["updated_at"] if latest else "",
            "historyDate": date_label,
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


def pipeline_for_date(date_label: str) -> dict[str, dict[str, Any]]:
    selected = date_label or current_date_label()
    stages: dict[str, dict[str, Any]] = {}
    for key in ("download", "voice", "stitch"):
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
    stages["capcut"] = capcut_stage_for_tasks(STORE.tasks(selected), selected)
    upload_history = COLLECTOR.pipeline_history["upload"].get(selected)
    if upload_history:
        stages["upload"] = dict(upload_history)
    elif selected == current_date_label() and COLLECTOR.pipeline["upload"].get("historyDate") in {"", selected}:
        stages["upload"] = dict(COLLECTOR.pipeline["upload"])
    else:
        stages["upload"] = Collector.empty_stage(f"{selected} 无上传记录")
        stages["upload"]["historyDate"] = selected
        stages["upload"]["source"] = "百度网盘上传状态"
    return decorate_pipeline_stages(stages)


def overview_payload() -> dict[str, Any]:
    tasks = STORE.tasks()
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
    pipeline = {
        **COLLECTOR.pipeline,
        "capcut": capcut_stage,
    }
    pipeline = decorate_pipeline_stages(pipeline)
    return {
        "machine": {
            "name": CONFIG["machine_name"],
            "online": online,
            "status": "Alive" if online else "Machine Offline",
            "lastHeartbeat": heartbeat["created_at"] if heartbeat else None,
        },
        "metrics": COLLECTOR.last_metrics,
        "counts": counts,
        "dates": dates,
        "current": latest,
        "pipeline": pipeline,
        "upload": {
            "configured": COLLECTOR.pipeline["upload"].get("state") != "unconfigured",
            "state": COLLECTOR.pipeline["upload"].get("state"),
            "message": COLLECTOR.pipeline["upload"].get("stateText"),
            "completed": COLLECTOR.pipeline["upload"].get("completed", 0),
            "failed": COLLECTOR.pipeline["upload"].get("failed", 0),
            "total": COLLECTOR.pipeline["upload"].get("total", 0),
        },
        "sourceErrors": STORE.source_errors(),
        "updatedAt": COLLECTOR.last_scan_at,
    }


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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
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
def overview():
    return overview_payload()


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
def tasks(date: str = "", state: str = ""):
    items = STORE.tasks(date, state)
    for item in items:
        item["category"] = task_category(item["state"])
        item["video_name"] = Path(item["video_path"]).name if item["video_path"] else ""
        item["audio_name"] = Path(item["audio_path"]).name if item["audio_path"] else ""
        item["output_name"] = Path(item["output_path"]).name if item["output_path"] else ""
        item.pop("video_path", None)
        item.pop("audio_path", None)
        item.pop("output_path", None)
        item.pop("source_file", None)
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
