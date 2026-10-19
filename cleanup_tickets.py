"""Process-local, bounded, single-use cleanup preview capabilities."""
import secrets
import copy
import threading
import time
from fastapi import HTTPException


class CleanupTickets:
    def __init__(self, clock=time.time, lifetime=120, monotonic=time.monotonic):
        self.clock = clock
        self.monotonic = monotonic
        self.lifetime = min(120, max(1, lifetime))
        self.lock = threading.RLock()
        self.records = {}

    def issue(self, fields):
        with self.lock:
            now = self.clock()
            self.records = {k: v for k, v in self.records.items()
                            if v[0]['expiresAt'] > now and v[1] > self.monotonic() and v[2] <= now}
            if len(self.records) >= 256:
                raise HTTPException(429, '预览过多，请稍后重试')
            record = {**copy.deepcopy(fields), 'expiresAt': int(now) + self.lifetime}
            ticket = secrets.token_urlsafe(32)
            self.records[ticket] = (record, self.monotonic() + self.lifetime, now)
            return {**copy.deepcopy(record), 'ticket': ticket}

    def consume(self, payload):
        with self.lock:
            ticket = payload.get('ticket')
            entry = self.records.get(ticket) if isinstance(ticket, str) else None
            if not entry or entry[0]['expiresAt'] <= self.clock() or entry[1] <= self.monotonic() or entry[2] > self.clock():
                raise HTTPException(409, '清理预览已过期或失效，请重新预览')
            record = entry[0]
            if any(payload.get(key) != value or type(payload.get(key)) is not type(value)
                   for key, value in record.items()):
                raise HTTPException(409, '清理选择或确认内容已变化，请重新预览')
            del self.records[ticket]
            return record
