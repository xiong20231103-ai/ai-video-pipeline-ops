"""Bounded SQLite online backup through an explicit read-only connection."""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from agent.core.snapshot import no_links
from tools.shadow_capture_errors import CaptureError


def online_backup(source, destination, *, max_bytes, timeout_seconds=20, clock=time.monotonic):
    source = no_links(source)
    destination = no_links(destination)
    if (destination.exists() or source == destination or not source.is_file()
            or type(max_bytes) is not int or max_bytes < 1 or not 0 < timeout_seconds <= 60):
        raise CaptureError('online_backup_input_invalid')
    started = clock()
    destination.parent.mkdir(parents=True, exist_ok=True)
    pages_seen = 0
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=0.1)) as incoming, \
                closing(sqlite3.connect(destination)) as outgoing:
            incoming.execute('PRAGMA query_only=ON')
            page_size = incoming.execute('PRAGMA page_size').fetchone()[0]
            if incoming.execute('PRAGMA page_count').fetchone()[0]*page_size > max_bytes:
                raise CaptureError('online_backup_byte_limit')
            def progress(status, remaining, total):
                nonlocal pages_seen
                pages_seen = max(pages_seen, total)
                if total*page_size > max_bytes:
                    raise CaptureError('online_backup_byte_limit')
                if clock()-started > timeout_seconds:
                    raise CaptureError('online_backup_deadline')
            # No BEGIN IMMEDIATE, no producer lock and no checkpoint/VACUUM.
            incoming.backup(outgoing, pages=128, progress=progress, sleep=0.001)
            if outgoing.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise CaptureError('online_backup_integrity_failed')
        if destination.stat().st_size > max_bytes:
            raise CaptureError('online_backup_byte_limit')
        return {'method': 'sqlite-online-readonly', 'bytes': destination.stat().st_size,
                'seconds': clock()-started, 'pages': pages_seen}
    except Exception:
        # Only a newly-created scratch destination may be removed.
        destination.unlink(missing_ok=True)
        raise
