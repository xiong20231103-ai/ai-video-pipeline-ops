"""Share one held cross-process owner fence across this process's HTTP threads.

Allows the 18790 control plane to call back through a different request thread
while preserving writer ownership until all nested/concurrent operations finish.
Original per-domain locks still serialize their own state updates. A single
ExecutionWorker is still the only command sender; this does not create a worker.
"""
from contextlib import contextmanager
import threading


class AuthorityLease:
    def __init__(self,fence,probe,*,owner='candidate'):
        if owner not in {'candidate','legacy'}:raise ValueError('invalid_authority_owner')
        self.fence=fence;self.probe=probe;self.owner=owner;self.lock=threading.Lock();self.count=0;self.context=None
    @contextmanager
    def guard(self):
        from .ordinary_fence import FenceRejected
        with self.lock:
            if not self.count:
                proof=self.probe()
                context=self.fence.guard(self.owner)
                state=context.__enter__()
                try:
                    if (not isinstance(proof,dict) or proof.get('protocol')!=1
                        or proof.get('fenceId')!=state['fenceId'] or proof.get('owner')!=self.owner
                        or proof.get('legacyWritesBlocked' if self.owner=='candidate' else 'candidateWritesBlocked') is not True):
                        raise FenceRejected('r6_legacy_writes_not_blocked')
                except BaseException:
                    context.__exit__(None,None,None)
                    raise
                self.context=context
            self.count+=1
        try:yield
        finally:
            with self.lock:
                self.count-=1
                if not self.count:
                    context=self.context;self.context=None
                    context.__exit__(None,None,None)
