"""Reversible cleanup: move files into a same-volume pending-delete area.

Every move is recorded before it happens and verified file by file after it
happens. Nothing here ever falls back to a permanent delete; the only
permanent delete is ``purge``, which removes moves whose retention expired (or
all verified moves when the user explicitly empties the area).
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

DIRNAME = ".ops-pending-delete"
RECORD_NAME = "pending-delete.json"
DEFAULT_RETENTION_DAYS = 3
LOCK = threading.RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _write_record(path: Path, record: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _is_link(path: Path) -> bool:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & reparse)


def area_root(path: Path) -> Path:
    """The pending-delete area on the same volume as ``path``."""
    return Path(Path(path).anchor) / DIRNAME


def _inventory(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        info = path.stat()
        return [{"relative": "", "size": info.st_size, "fileId": info.st_ino}]
    files: list[dict[str, Any]] = []
    for current, directories, names in os.walk(path):
        for name in directories:
            if _is_link(Path(current) / name):
                raise OSError("目录内含链接或重解析点，拒绝移动")
        for name in names:
            item = Path(current) / name
            if _is_link(item):
                raise OSError("目录内含链接或重解析点，拒绝移动")
            info = item.stat()
            files.append({
                "relative": item.relative_to(path).as_posix(),
                "size": info.st_size,
                "fileId": info.st_ino,
            })
    return files


def _verify(source: Path, target: Path, files: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    if source.exists():
        problems.append("来源仍然存在")
    if not target.exists():
        return problems + ["待删区中找不到目标"]
    for entry in files:
        moved = target / entry["relative"] if entry["relative"] else target
        try:
            info = moved.stat()
        except OSError:
            problems.append(f"缺少文件：{entry['relative'] or target.name}")
            continue
        if info.st_size != entry["size"] or info.st_ino != entry["fileId"]:
            problems.append(f"文件身份不符：{entry['relative'] or target.name}")
    return problems


def move(
    path: Path,
    *,
    cleanup_id: str,
    source_kind: str,
    retention_days: float = DEFAULT_RETENTION_DAYS,
    rename: Callable[[Path, Path], None] = os.rename,
) -> dict[str, Any]:
    """Move one file or directory into the pending-delete area and verify it.

    Raises OSError (never deletes) when the move is refused, fails, or cannot
    be verified. The record next to the moved item keeps the evidence.
    """
    source = Path(path)
    if not source.is_absolute():
        raise OSError("只接受绝对路径")
    if not source.exists():
        raise OSError("来源不存在")
    if _is_link(source) or any(_is_link(parent) for parent in source.parents if parent != Path(parent.anchor)):
        raise OSError("路径含链接或重解析点，拒绝移动")
    root = area_root(source)
    if source == root or root in source.parents:
        raise OSError("来源已在待删区内")
    with LOCK:
        files = _inventory(source)
        slot = root / cleanup_id / uuid.uuid4().hex[:12]
        slot.mkdir(parents=True)
        if os.stat(source).st_dev != os.stat(slot).st_dev:
            slot.rmdir()
            raise OSError("待删区与来源不在同一磁盘，拒绝跨盘移动")
        target = slot / source.name
        moved_at = _now()
        record: dict[str, Any] = {
            "schemaVersion": 1,
            "cleanupId": cleanup_id,
            "sourceKind": source_kind,
            "source": str(source),
            "target": str(target),
            "isDirectory": source.is_dir(),
            "files": files,
            "sizeBytes": sum(entry["size"] for entry in files),
            "movedAt": moved_at.isoformat(),
            "retainUntil": (moved_at + timedelta(days=retention_days)).isoformat(),
            "state": "moving",
        }
        record_path = slot / RECORD_NAME
        _write_record(record_path, record)
        try:
            rename(source, target)
        except OSError as exc:
            record.update(state="move_failed", error=str(exc))
            _write_record(record_path, record)
            raise OSError(f"移入待删区失败：{exc}") from exc
        problems = _verify(source, target, files)
        if problems:
            record.update(state="verify_failed", problems=problems)
            _write_record(record_path, record)
            raise OSError("移入待删区后核验失败：" + "；".join(problems[:3]))
        record["state"] = "moved"
        _write_record(record_path, record)
        return record


def _records(roots: Iterable[Path]) -> list[tuple[Path, dict[str, Any]]]:
    found: list[tuple[Path, dict[str, Any]]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for record_path in root.glob(f"*/*/{RECORD_NAME}"):
            try:
                found.append((record_path, json.loads(record_path.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
    return found


def summary(roots: Iterable[Path]) -> dict[str, Any]:
    moved = [record for _, record in _records(roots) if record.get("state") == "moved"]
    retain = sorted(str(record.get("retainUntil") or "") for record in moved)
    return {
        "count": len(moved),
        "sizeBytes": sum(int(record.get("sizeBytes") or 0) for record in moved),
        "nextPurgeAt": retain[0] if retain else "",
        "needsReview": sum(1 for _, record in _records(roots) if record.get("state") in {"verify_failed", "restore_failed"}),
    }


def purge(roots: Iterable[Path], *, everything: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """Permanently remove verified moves whose retention expired (or all of them).

    Records in any state other than ``moved`` are kept for review.
    """
    current = now or _now()
    removed = 0
    freed = 0
    failed: list[str] = []
    with LOCK:
        for record_path, record in _records(roots):
            if record.get("state") != "moved":
                continue
            try:
                due = datetime.fromisoformat(str(record.get("retainUntil")))
            except ValueError:
                continue
            if not everything and due > current:
                continue
            slot = record_path.parent
            try:
                shutil.rmtree(slot)
            except OSError as exc:
                failed.append(f"{record.get('source')}: {exc}")
                continue
            removed += 1
            freed += int(record.get("sizeBytes") or 0)
            cleanup_dir = slot.parent
            try:
                cleanup_dir.rmdir()
            except OSError:
                pass
    return {"removedCount": removed, "freedBytes": freed, "failed": failed}


def restore(record_path: Path) -> dict[str, Any]:
    """Move one verified item back to where it came from; never overwrites."""
    with LOCK:
        record = json.loads(Path(record_path).read_text(encoding="utf-8"))
        if record.get("state") != "moved":
            raise OSError("只有已核验的待删内容可以恢复")
        source = Path(record["source"])
        target = Path(record["target"])
        if source.exists():
            raise OSError("原位置已有同名内容，拒绝覆盖")
        source.parent.mkdir(parents=True, exist_ok=True)
        os.rename(target, source)
        problems = _verify(target, source, record["files"])
        if problems:
            record.update(state="restore_failed", problems=problems)
            _write_record(Path(record_path), record)
            raise OSError("恢复后核验失败：" + "；".join(problems[:3]))
        record.update(state="restored", restoredAt=_now().isoformat())
        _write_record(Path(record_path), record)
        return record
