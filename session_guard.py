"""Startup-only Windows console guard, independent of pipeline imports."""
from __future__ import annotations

import ctypes
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SessionDecision:
    allowed: bool
    retry: bool
    reason: str


def decide_session(process_session: int, console_session: int) -> SessionDecision:
    if console_session < 0 or console_session == 0xFFFFFFFF:
        return SessionDecision(False, True, "console_session_transient")
    if process_session <= 0:
        return SessionDecision(False, False, "noninteractive_process")
    if process_session != console_session:
        return SessionDecision(False, False, "not_console_session")
    return SessionDecision(True, False, "console_session_matched")


def native_session_identity() -> tuple[int, int]:
    if os.name != "nt":
        raise OSError("Windows session APIs required")
    from ctypes import wintypes

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.WTSGetActiveConsoleSessionId.argtypes = []
    api.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
    api.GetCurrentProcessId.argtypes = []
    api.GetCurrentProcessId.restype = wintypes.DWORD
    api.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    api.ProcessIdToSessionId.restype = wintypes.BOOL
    session = wintypes.DWORD()
    if not api.ProcessIdToSessionId(api.GetCurrentProcessId(), ctypes.byref(session)):
        raise OSError("Session query failed")
    return int(session.value), int(api.WTSGetActiveConsoleSessionId())


def startup_decision(*, query=None, attempts: int = 5, sleep=time.sleep) -> SessionDecision:
    if not 1 <= attempts <= 10:
        raise ValueError("attempts must be between 1 and 10")
    query = query or native_session_identity
    for attempt in range(attempts):
        try:
            process_session, console_session = query()
            decision = decide_session(process_session, console_session)
        except Exception:
            # Neither exception messages nor command lines belong in diagnostics.
            return SessionDecision(False, False, "session_query_failed")
        if not decision.retry or attempt == attempts - 1:
            return decision
        sleep(0.2)
    raise AssertionError("unreachable")


def record_skip(directory: Path, role: str, reason: str) -> None:
    if role not in {"receiver", "workbench", "dashboard"}:
        raise ValueError("unknown production role")
    if reason not in {"console_session_transient", "noninteractive_process", "not_console_session", "session_query_failed"}:
        raise ValueError("unknown skip reason")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"session-skip-{role}-{uuid.uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as handle:
            json.dump({"schemaVersion": 1, "at": datetime.now(timezone.utc).isoformat(),
                       "role": role, "event": "startup_skipped", "reason": reason}, handle)
    except OSError:
        # Failure to log must not permit a refused application to start.
        pass


def console_startup_allowed(role: str, directory: Path) -> bool:
    decision = startup_decision()
    if not decision.allowed:
        record_skip(directory, role, decision.reason)
    return decision.allowed
