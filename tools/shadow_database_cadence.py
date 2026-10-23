"""Event-driven DB snapshot tickets; all changes still require a change log.

120s minimum is the budget-derived coalescing option, not a claim that deferred
points have an aligned DB. Such points stay incomparable until a matching snap.
"""
import threading
import time


class DatabaseCadence:
    def __init__(self, *, periodic_seconds=600, minimum_seconds=120, clock=time.monotonic):
        if not 120 <= minimum_seconds <= periodic_seconds <= 3600:
            raise ValueError('database_cadence_limits')
        self.periodic=periodic_seconds;self.minimum=minimum_seconds;self.clock=clock
        self.last=None;self.generation=0;self.captured=0;self.lock=threading.RLock()

    def changed(self):
        with self.lock:self.generation+=1;return self.generation

    def due(self):
        with self.lock:
            age=None if self.last is None else self.clock()-self.last
            reason=('initial' if age is None else
                    'change' if self.generation>self.captured and age>=self.minimum else
                    'periodic' if age>=self.periodic else None)
            return None if reason is None else {'generation':self.generation,'reason':reason}

    def committed(self,ticket):
        with self.lock:
            if not 0<=ticket['generation']<=self.generation:raise ValueError('invalid_database_ticket')
            self.captured=max(self.captured,ticket['generation']);self.last=self.clock()

    def status(self):
        with self.lock:
            return {'pendingChanges':self.generation-self.captured,
                    'periodicSeconds':self.periodic,'minimumSeconds':self.minimum,
                    'changesRequireJournal':True,'deferredPointsComparable':False}
