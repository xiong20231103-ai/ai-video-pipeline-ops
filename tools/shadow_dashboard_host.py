"""Opt-in Dashboard lifespan attachment. No import of app, activation or I/O.

An idle-window bootstrap must supply a reviewed publisher and exact GET routes.
Replay and watchdog process control are deliberately outside the live host.
"""
from contextlib import asynccontextmanager
import asyncio
import math
import threading
import time

from tools.shadow_capture import CaptureError
from tools.shadow_dashboard_binding import DashboardReadBinding


class DashboardShadowHost:
    def __init__(self, namespace, publisher, routes, *, enabled=False,
                 maintenance=lambda: False, stop_requested=lambda: False, interval_seconds=60,
                 join_seconds=2, clock=time.monotonic):
        if (type(enabled) is not bool
                or not isinstance(interval_seconds, (int, float))
                or not math.isfinite(interval_seconds) or not 30 <= interval_seconds <= 3600
                or not isinstance(join_seconds, (int, float))
                or not math.isfinite(join_seconds) or not 0 < join_seconds <= 5):
            raise CaptureError('shadow_host_limits_invalid')
        self.namespace = namespace
        self.publisher = publisher
        self.routes = dict(routes)
        self.enabled = enabled
        self.maintenance = maintenance
        self.stop_requested = stop_requested
        self.owner_loop = None
        self.interval = interval_seconds
        self.join_seconds = join_seconds
        self.clock = clock
        self.stop_event = threading.Event()
        self.thread = None
        self.binding = None
        self.started = False
        self.state = 'disabled' if not enabled else 'dormant'
        self.code = None
        self.last_cycle = None
        self.cycle_started = None
        self.lock = threading.RLock()

    def _state(self, state, code=None):
        with self.lock:
            self.state, self.code = state, code

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                if self._stop_from_control():
                    return
                if self.maintenance():
                    self._state('paused', 'shadow_maintenance')
                else:
                    result = self.publisher.tick()
                    if self._stop_from_control():
                        return
                    if self.stop_event.is_set():
                        break
                    if result.get('state') == 'blocked':
                        self._state('blocked', 'shadow_capture_blocked')
                    else:
                        self._state('observing')
                with self.lock:
                    self.last_cycle = self.clock()
            except Exception:
                # Neither live exception values nor caller-supplied status enter logs.
                self._state('blocked', 'shadow_cycle_failed')
            # STOP is checked while idle too; no extra HTTP or process control.
            remaining = self.interval
            while remaining > 0 and not self.stop_event.wait(min(1, remaining)):
                remaining -= min(1, remaining)
                try:
                    if self._stop_from_control():
                        return
                except Exception:
                    self._state('blocked', 'shadow_stop_probe_failed')

    def _stop_from_control(self):
        if not self.stop_requested():
            return False
        self.stop_event.set()
        if self.owner_loop is not None and self.owner_loop.is_running():
            asyncio.run_coroutine_threadsafe(self.close(), self.owner_loop)
        else:
            # Synchronous fixture/startup contexts have no application loop.
            asyncio.run(self.close())
        return True

    def start(self):
        with self.lock:
            if not self.enabled:
                return self.status()
            if self.stop_event.is_set():
                self._state('blocked', 'shadow_restart_requires_new_host')
                return self.status()
            if self.started:
                return self.status()
            self.started = True
            try:
                try:
                    self.owner_loop = asyncio.get_running_loop()
                except RuntimeError:
                    self.owner_loop = None
                if self.stop_requested():
                    self.stop_event.set()
                    self._state('stopped', 'shadow_stop_latched')
                    return self.status()
                self.binding = DashboardReadBinding(self.namespace, self.publisher.observer, self.routes)
                self.thread = threading.Thread(target=self._loop, name='dashboard-shadow-capture', daemon=True)
                self.cycle_started = self.clock()
                self.thread.start()
            except Exception:
                self._restore()
                self._state('blocked', 'shadow_start_failed')
            return self.status()

    def _restore(self):
        if self.binding is None:
            return True
        try:
            self.binding.restore()
            self.binding = None
            return True
        except Exception:
            # Never overwrite a newer namespace owner, even during rollback.
            return False

    async def close(self):
        self.stop_event.set()
        thread = self.thread
        join_failed = False
        own_worker = thread is threading.current_thread()
        if thread is not None and thread.is_alive() and not own_worker:
            # Joining cannot block the Dashboard event loop or its heartbeat.
            try:
                await asyncio.to_thread(thread.join, self.join_seconds)
            except Exception:
                join_failed = True
        restored = self._restore()
        if not restored:
            self._state('blocked', 'shadow_restore_owner_changed')
        elif join_failed:
            self._state('blocked', 'shadow_worker_join_failed')
        elif thread is not None and thread.is_alive() and not own_worker:
            self._state('blocked', 'shadow_worker_still_stopping')
        else:
            self._state('stopped' if self.enabled else 'disabled')
        return self.status()

    def status(self):
        with self.lock:
            alive = bool(self.thread and self.thread.is_alive())
            last = self.last_cycle if self.last_cycle is not None else self.cycle_started
            stale = alive and last is not None and self.clock() - last > 2 * self.interval
            return {'schema': 1, 'state': self.state, 'code': self.code,
                    'enabled': self.enabled, 'workerAlive': alive, 'stale': stale,
                    'businessRequests': 0, 'productionWrites': False,
                    'realShadowPassed': False, 'switchAccepted': False}


def attach_lifespan(app, host):
    """Retain the original app/lifespan; do nothing when disabled.

    Must be called before serving, never injected into a running Dashboard.
    The returned detach function is used only after shutdown, not as hot reload.
    """
    if not host.enabled:
        return lambda: None
    router = app.router
    previous = router.lifespan_context
    if getattr(previous, '_ops_shadow_attachment', False):
        raise CaptureError('shadow_lifespan_already_attached')

    @asynccontextmanager
    async def lifespan(application):
        try:
            # Original startup runs first. No capture after original startup fails.
            async with previous(application) as state:
                host.start()
                try:
                    yield state
                finally:
                    # Original collector is still alive until capture has stopped.
                    await host.close()
        finally:
            # Also covers original shutdown failures without swallowing them.
            if not host.stop_event.is_set():
                await host.close()

    lifespan._ops_shadow_attachment = True
    router.lifespan_context = lifespan

    def detach():
        if host.thread is not None and host.thread.is_alive():
            raise CaptureError('shadow_detach_before_stop')
        if router.lifespan_context is not lifespan:
            raise CaptureError('shadow_lifespan_owner_changed')
        router.lifespan_context = previous

    return detach
