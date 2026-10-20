"""Independent WAL projection using original Store algorithms and short commits.

No long scan transaction and no shared SQLite connection across HTTP threads.
The caller supplies an owned candidate path; a seed can only initialize a new DB.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading


def require_plain_path(path):
    path=Path(path).absolute()
    for part in (path,*path.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('projection_link_refused')
    return path


def durable_store(path):
    path=Path(path)
    def factory(schema,*,seed,max_bytes):
        class ProjectionStore(schema):
            def __init__(self):
                self.path=require_plain_path(path);self.lock=threading.RLock();self.closed=False
                self.path.parent.mkdir(parents=True,exist_ok=True)
                if seed is not None:
                    if seed.execute('PRAGMA page_count').fetchone()[0]*seed.execute('PRAGMA page_size').fetchone()[0]>max_bytes:
                        raise ValueError('projection_byte_limit')
                    # O_EXCL forbids overwriting a resumed candidate projection.
                    descriptor=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
                    os.close(descriptor)
                    try:
                        with self.connection() as db:seed.backup(db)
                    except BaseException:
                        self.path.unlink(missing_ok=True)
                        raise
                with self.connection() as db:db.execute('PRAGMA journal_mode=WAL')
                self._init_db()
            def connect(self):
                if self.closed:raise OSError('projection_closed')
                require_plain_path(self.path)
                db=sqlite3.connect(self.path,timeout=10)
                try:
                    db.row_factory=sqlite3.Row
                    page_size=db.execute('PRAGMA page_size').fetchone()[0]
                    if db.execute('PRAGMA page_count').fetchone()[0]*page_size>max_bytes:
                        raise ValueError('projection_byte_limit')
                    db.execute('PRAGMA max_page_count='+str(max_bytes//page_size))
                    return db
                except BaseException:db.close();raise
            @contextmanager
            def connection(self):
                db=self.connect()
                try:yield db;db.commit()
                except BaseException:db.rollback();raise
                finally:db.close()
            def close(self):self.closed=True
        return ProjectionStore()
    return factory
