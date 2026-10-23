"""Bounded SQLite online backup through an explicit read-only connection."""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from agent.core.snapshot import no_links
from tools.shadow_capture_errors import CaptureError

# Page keys per listing segment. A snapshot index names segments, so an
# unchanged run of pages costs nothing beyond the first snapshot.
SEGMENT_KEYS = 256


def sqlite_page_size(path, *, maximum=64 * 1024):
    """Header page size of a SQLite file, or None for anything else."""
    with no_links(path).open('rb') as stream:
        head = stream.read(100)
    if len(head) < 100 or not head.startswith(b'SQLite format 3\x00'):
        return None
    size = int.from_bytes(head[16:18], 'big')
    size = 65536 if size == 1 else size
    return size if 512 <= size <= maximum and size & (size - 1) == 0 else None


def page_listing_segment(keys):
    return '\n'.join(keys).encode('ascii')


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
            # One uninterrupted backup step avoids restart on intervening commits.
            # No BEGIN IMMEDIATE, no producer lock and no checkpoint/VACUUM.
            incoming.backup(outgoing, pages=-1, progress=progress, sleep=0.001)
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
