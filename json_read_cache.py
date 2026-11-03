"""Bounded stat-keyed JSON read cache; never used for media/QC byte proofs."""
from __future__ import annotations
import json
import os
import pickle
import threading
from collections import OrderedDict
from pathlib import Path


def file_signature(path):
    stat=path.stat()
    return (stat.st_mtime_ns,stat.st_size,stat.st_ctime_ns,stat.st_dev,stat.st_ino)


class JsonReadCache:
    def __init__(self,max_entries=4096,max_bytes=128*1024*1024):
        self.max_entries=max_entries;self.max_bytes=max_bytes
        self._entries=OrderedDict();self._bytes=0;self._lock=threading.RLock()

    def __len__(self):
        with self._lock:return len(self._entries)

    @staticmethod
    def _key(path):
        # abspath is lexical: unlike resolve(), it does not traverse the disk
        # on every status read. The identity tuple still detects replacement.
        return os.path.normcase(os.path.abspath(str(path)))

    def invalidate(self,path=None):
        with self._lock:
            if path is None:self._entries.clear();self._bytes=0;return
            old=self._entries.pop(self._key(path),None)
            if old:self._bytes-=len(old[1])

    def read(self,path,*,parser=None,encoding='utf-8-sig'):
        path=Path(path) if isinstance(path,(str,bytes)) else path
        key=self._key(path);decode=parser or json.loads
        with self._lock:
            try:
                signature=file_signature(path)
                old=self._entries.get(key)
                if old and old[0]==signature and old[2]==(encoding,parser):
                    self._entries.move_to_end(key)
                    # Only our own serialized JSON values enter this memory-only
                    # pickle; no pickle file/input is ever deserialized.
                    return pickle.loads(old[1])
                self.invalidate(path)
                for _ in range(3):
                    before=file_signature(path)
                    value=decode(path.read_text(encoding=encoding))
                    after=file_signature(path)
                    if before==after:break
                else:raise OSError('JSON source changed during read')
                blob=pickle.dumps(value,protocol=pickle.HIGHEST_PROTOCOL)
                if self.max_entries>0 and len(blob)<=self.max_bytes:
                    self._entries[key]=(after,blob,(encoding,parser));self._bytes+=len(blob)
                    while len(self._entries)>self.max_entries or self._bytes>self.max_bytes:
                        _,removed=self._entries.popitem(last=False);self._bytes-=len(removed[1])
                return value
            except Exception:
                self.invalidate(path)
                raise


JSON_READ_CACHE=JsonReadCache()
