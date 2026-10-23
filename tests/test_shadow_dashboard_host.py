import asyncio
from contextlib import asynccontextmanager
import io
import json
import threading
import unittest
import urllib.request
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.shadow_agent_observer import AgentReadObserver
from tools.shadow_capture import CaptureError
from tools.shadow_dashboard_binding import DashboardReadBinding
from tools.shadow_dashboard_host import DashboardShadowHost, attach_lifespan


class HostTests(unittest.IsolatedAsyncioTestCase):
    def fixture(self, **options):
        observer = AgentReadObserver({(18790, '/api/recovery/status'): 'control:/api/recovery/status'})
        seen = threading.Event()

        def tick():
            seen.set()
            return {'state': 'captured'}

        publisher = SimpleNamespace(observer=observer, tick=Mock(side_effect=tick))
        opener = Mock(side_effect=lambda *a, **k: self.response())
        original = SimpleNamespace(request=SimpleNamespace(urlopen=opener))
        namespace = {'urllib': original}
        routes = {'http://127.0.0.1:18790/api/recovery/status': (18790, '/api/recovery/status')}
        host = DashboardShadowHost(namespace, publisher, routes, **options)
        return host, namespace, original, publisher, seen

    @staticmethod
    def response():
        response = io.BytesIO(b'{"ready":true}')
        response.status = 200
        return response

    async def wait_tick(self, seen):
        self.assertTrue(await asyncio.to_thread(seen.wait, 2))
        # The event precedes the host's status update; acquire no fake clock sleeps.
        for _ in range(100):
            await asyncio.sleep(0)

    async def test_disabled_is_exact_noop_and_starts_no_thread(self):
        host, namespace, original, publisher, seen = self.fixture()
        app = SimpleNamespace(router=SimpleNamespace(lifespan_context=object()))
        before = app.router.lifespan_context
        with patch('tools.shadow_dashboard_host.threading.Thread', side_effect=AssertionError('no thread')):
            detach = attach_lifespan(app, host)
            self.assertEqual('disabled', host.start()['state'])
        self.assertIs(before, app.router.lifespan_context)
        self.assertIs(original, namespace['urllib'])
        publisher.tick.assert_not_called()
        detach()
        await host.close()

    async def test_live_get_once_capture_thread_and_restore(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        host.start()
        await self.wait_tick(seen)
        with namespace['urllib'].request.urlopen('http://127.0.0.1:18790/api/recovery/status') as response:
            self.assertEqual(b'{"ready":true}', response.read())
        self.assertEqual(1, original.request.urlopen.call_count)
        self.assertEqual({'ready': True}, publisher.observer.observation()['responses']['control:/api/recovery/status'])
        self.assertEqual(0, host.status()['businessRequests'])
        await host.close()
        self.assertIs(original, namespace['urllib'])
        self.assertFalse(host.status()['workerAlive'])

    async def test_maintenance_pauses_without_tick_or_http(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True, maintenance=lambda: True)
        host.start()
        await host.close()
        publisher.tick.assert_not_called()
        original.request.urlopen.assert_not_called()

    async def test_publisher_failure_keeps_original_get_working_and_no_secret_status(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        def fail():
            seen.set()
            raise RuntimeError('private-canary')
        publisher.tick.side_effect = fail
        host.start()
        await self.wait_tick(seen)
        self.assertNotIn('private-canary', json.dumps(host.status()))
        self.assertEqual('shadow_cycle_failed', host.status()['code'])
        with namespace['urllib'].request.urlopen('http://127.0.0.1:18790/api/recovery/status') as response:
            self.assertEqual(b'{"ready":true}', response.read())
        await host.close()

    async def test_quota_block_is_unhealthy_not_observing(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        def blocked():
            seen.set()
            return {'state': 'blocked', 'lastCode': 'arbitrary-private-value'}
        publisher.tick.side_effect = blocked
        host.start()
        await self.wait_tick(seen)
        self.assertEqual('shadow_capture_blocked', host.status()['code'])
        self.assertNotIn('arbitrary', json.dumps(host.status()))
        await host.close()

    async def test_start_failure_restores_and_does_not_break_old_host(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        with patch('tools.shadow_dashboard_host.threading.Thread.start', side_effect=RuntimeError('private-canary')):
            self.assertEqual('shadow_start_failed', host.start()['code'])
        self.assertIs(original, namespace['urllib'])
        await host.close()

    async def test_stop_timeout_is_bounded_and_releases_namespace_without_kill(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True, join_seconds=0.01)
        release = threading.Event()
        def tick():
            seen.set()
            release.wait()
            return {'state': 'captured'}
        publisher.tick.side_effect = tick
        try:
            host.start()
            await self.wait_tick(seen)
            result = await host.close()
            self.assertEqual('shadow_worker_still_stopping', result['code'])
            self.assertIs(original, namespace['urllib'])
        finally:
            release.set()
            await asyncio.to_thread(host.thread.join, 2)
        self.assertFalse(host.status()['workerAlive'])
        self.assertEqual('shadow_worker_still_stopping', host.status()['code'])

    async def test_first_hung_cycle_is_stale_without_restarting_anything(self):
        now = [0]
        host, namespace, original, publisher, seen = self.fixture(enabled=True, clock=lambda: now[0])
        release = threading.Event()
        publisher.tick.side_effect = lambda: (seen.set(), release.wait(), {'state': 'captured'})[-1]
        try:
            host.start()
            await self.wait_tick(seen)
            now[0] = 121
            self.assertTrue(host.status()['stale'])
        finally:
            release.set()
            await host.close()

    async def test_repeated_start_does_not_duplicate_and_stopped_host_cannot_restart(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        host.start()
        thread = host.thread
        host.start()
        self.assertIs(thread, host.thread)
        await host.close()
        # Explicit stopped lifetime cannot be reused by a watchdog.
        host.start()
        self.assertIs(thread, host.thread)
        self.assertFalse(thread.is_alive())

    async def test_restore_does_not_overwrite_new_namespace_owner(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        host.start()
        new_owner = object()
        namespace['urllib'] = new_owner
        self.assertEqual('shadow_restore_owner_changed', (await host.close())['code'])
        self.assertIs(new_owner, namespace['urllib'])

    async def test_original_lifespan_yield_and_error_preserved_and_detachable(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        events = []
        @asynccontextmanager
        async def original_lifespan(app):
            events.append('startup')
            yield {'original': True}
            self.assertFalse(host.status()['workerAlive'])
            events.append('shutdown')
        app = SimpleNamespace(router=SimpleNamespace(lifespan_context=original_lifespan))
        detach = attach_lifespan(app, host)
        with self.assertRaises(CaptureError):
            attach_lifespan(app, host)
        async with app.router.lifespan_context(app) as state:
            self.assertEqual({'original': True}, state)
            await self.wait_tick(seen)
            self.assertIsNot(original, namespace['urllib'])
        self.assertEqual(['startup', 'shutdown'], events)
        detach()
        self.assertIs(original_lifespan, app.router.lifespan_context)

    async def test_application_error_survives_and_attachment_is_removed_after_close(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        @asynccontextmanager
        async def previous(app):
            yield
        app = SimpleNamespace(router=SimpleNamespace(lifespan_context=previous))
        detach = attach_lifespan(app, host)
        with self.assertRaisesRegex(RuntimeError, 'business-error'):
            async with app.router.lifespan_context(app):
                raise RuntimeError('business-error')
        self.assertIs(original, namespace['urllib'])
        detach()

    async def test_failed_original_startup_never_starts_observer(self):
        host, namespace, original, publisher, seen = self.fixture(enabled=True)
        @asynccontextmanager
        async def previous(app):
            raise RuntimeError('original-startup')
            yield
        app = SimpleNamespace(router=SimpleNamespace(lifespan_context=previous))
        attach_lifespan(app, host)
        with self.assertRaisesRegex(RuntimeError, 'original-startup'):
            async with app.router.lifespan_context(app):
                pass
        self.assertIsNone(host.thread)
        publisher.tick.assert_not_called()


class ControlPortTests(unittest.TestCase):
    def test_invalid_limits_cannot_create_busy_loop(self):
        for options in [{'interval_seconds': float('nan')}, {'interval_seconds': float('inf')},
                        {'join_seconds': float('nan')}, {'enabled': 'true'}]:
            with self.assertRaises(CaptureError):
                DashboardShadowHost({}, None, {}, **options)

    def test_control_port_matches_real_loopback_endpoint(self):
        observer = AgentReadObserver({(18790, '/api/recovery/status'): 'control:/api/recovery/status'})
        namespace = {'urllib': SimpleNamespace(request=SimpleNamespace(urlopen=Mock()))}
        binding = DashboardReadBinding(namespace, observer, {'http://127.0.0.1:18790/api/recovery/status': (18790, '/api/recovery/status')})
        binding.restore()

    def test_actual_port_mismatch_remote_control_or_wrong_identity_rejected(self):
        observer = AgentReadObserver({(18790, '/api/recovery/status'): 'control:/api/recovery/status'})
        namespace = {'urllib': SimpleNamespace(request=SimpleNamespace(urlopen=Mock()))}
        for url in ['http://127.0.0.1:8766/api/recovery/status', 'http://example.invalid:18790/api/recovery/status']:
            with self.assertRaises(CaptureError):
                DashboardReadBinding(namespace, observer, {url: (18790, '/api/recovery/status')})
        with self.assertRaises(CaptureError):
            AgentReadObserver({(18790, '/api/recovery/status'): 'receiver:/api/recovery/status'})
        with self.assertRaises(CaptureError):
            AgentReadObserver({(9000, '/api/status'): 'control:/api/status'})


if __name__ == '__main__':
    unittest.main()
