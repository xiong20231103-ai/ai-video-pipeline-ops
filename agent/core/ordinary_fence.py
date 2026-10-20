"""Explicit R3 writer ownership; no process start, listener or auto-initialization."""
from contextlib import contextmanager
import json,os,threading,time,uuid
from pathlib import Path
from contracts.state_files import atomic_json,read_json

class FenceRejected(OSError):pass
_locks={};_registry=threading.Lock()
def _local(path):
    with _registry:return _locks.setdefault(str(path.resolve()).casefold(),threading.Lock())

class OrdinaryFence:
    def __init__(self,root,*,timeout=2):
        self.root=Path(root);self.path=self.root/'owner.json';self.lock_path=self.root/'writer.lock';self.timeout=timeout
    def _paths(self):
        for path in (self.root,self.path,self.lock_path):
            for part in (path,*path.parents):
                if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):raise FenceRejected('r3_fence_link_refused')
    def _read(self):
        self._paths()
        try:value=read_json(self.path)
        except (OSError,ValueError):raise FenceRejected('r3_fence_state_unavailable') from None
        if not isinstance(value,dict) or set(value)!={'schema','fenceId','owner','updatedAt'} or value['schema']!=1 or value['owner'] not in {'legacy','candidate'} or not isinstance(value['fenceId'],str) or len(value['fenceId'])!=32:raise FenceRejected('r3_fence_state_invalid')
        return value
    def prepare(self):
        self._paths()
        if self.path.exists() or self.lock_path.exists():raise FenceRejected('r3_fence_already_initialized')
        self.root.mkdir(parents=True,exist_ok=True)
        with self.lock_path.open('xb') as handle:handle.write(b'0')
        atomic_json(self.path,{'schema':1,'fenceId':uuid.uuid4().hex,'owner':'legacy','updatedAt':time.time()})
        return self._read()
    @contextmanager
    def _lock(self):
        self._paths();local=_local(self.lock_path)
        if not local.acquire(timeout=self.timeout):raise FenceRejected('r3_writer_busy')
        handle=None;locked=False;started=time.monotonic()
        try:
            try:handle=self.lock_path.open('r+b')
            except OSError:raise FenceRejected('r3_fence_not_prepared') from None
            while not locked:
                try:
                    handle.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                    locked=True
                except OSError:
                    if time.monotonic()-started>=self.timeout:raise FenceRejected('r3_writer_busy') from None
                    time.sleep(.02)
            yield
        finally:
            try:
                if handle is not None:
                    if locked:
                        handle.seek(0)
                        if os.name=='nt':
                            import msvcrt
                            msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
                    handle.close()
            finally:local.release()
    @contextmanager
    def guard(self,owner):
        with self._lock():
            state=self._read()
            if owner not in {'legacy','candidate'} or state['owner']!=owner:raise FenceRejected('r3_owner_mismatch')
            yield state
    def status(self):
        with self._lock():return self._read()
    def select(self,owner,*,expected_id,confirmation,evidence):
        # Explicit human-reviewed evidence is required; not cryptographic proof.
        # No CLI or worker invokes this automatically. This is NOT real shadow.
        if owner not in {'legacy','candidate'} or confirmation!='R3_OWNER_CHANGE_REVIEWED':raise FenceRejected('r3_review_required')
        required={'commandsPaused':True,'drained':True,'leased':0,'sent':0,'unknown':0,'legacyFenceInstalled':True,'fullBatchShadowReviewed':True}
        if not isinstance(evidence,dict) or any(type(evidence.get(k)) is not type(v) or evidence[k]!=v for k,v in required.items()):raise FenceRejected('r3_switch_evidence_incomplete')
        with self._lock():
            state=self._read()
            if state['fenceId']!=expected_id:raise FenceRejected('r3_fence_identity_mismatch')
            state={**state,'owner':owner,'updatedAt':time.time()};atomic_json(self.path,state);return state
