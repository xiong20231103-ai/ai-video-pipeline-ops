import asyncio
import io
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import psutil

from tools.shadow_agent_observer import AgentReadObserver
from tools.shadow_dashboard_host import DashboardShadowHost


class StopBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_file_restores_inflight_response_without_changing_host_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            stop=Path(folder)/'STOP';seen=threading.Event()
            original=SimpleNamespace(request=SimpleNamespace(urlopen=Mock()))
            response=io.BytesIO(b'{"ok":true}');response.status=200
            original.request.urlopen.return_value=response
            observer=AgentReadObserver({(18790,'/api/status'):'control:/api/status'})
            def tick():seen.set();return {'state':'captured'}
            publisher=SimpleNamespace(observer=observer,tick=tick)
            namespace={'urllib':original}
            identity=(os.getpid(),psutil.Process(os.getpid()).create_time())
            host=DashboardShadowHost(namespace,publisher,{'http://127.0.0.1:18790/api/status':(18790,'/api/status')},
                                     enabled=True,stop_requested=stop.exists,interval_seconds=30)
            try:
                host.start();self.assertTrue(await asyncio.to_thread(seen.wait,2))
                inflight=namespace['urllib'].request.urlopen('http://127.0.0.1:18790/api/status')
                inflight.__enter__()
                stop.write_text('stop observer only')
                async with asyncio.timeout(4):
                    while host.status()['state']!='stopped':await asyncio.sleep(0.01)
                self.assertEqual(identity,(os.getpid(),psutil.Process(os.getpid()).create_time()))
                self.assertIs(original,namespace['urllib'])
                self.assertEqual(b'{"ok":true}',inflight.read())
                inflight.__exit__(None,None,None)
                original.request.urlopen.assert_called_once()
                stop.unlink()
                host.start()
                self.assertEqual('shadow_restart_requires_new_host',host.status()['code'])
                self.assertFalse(host.status()['workerAlive'])
            finally:await host.close()

    async def test_stop_already_present_never_binds_or_starts_thread(self):
        namespace={'urllib':object()};original=namespace['urllib']
        host=DashboardShadowHost(namespace,None,{},enabled=True,stop_requested=lambda:True)
        self.assertEqual('shadow_stop_latched',host.start()['code'])
        self.assertIsNone(host.thread);self.assertIs(original,namespace['urllib'])
        await host.close()

    async def test_stop_probe_error_after_start_restores_binding_and_latches(self):
        original=SimpleNamespace(request=SimpleNamespace(urlopen=Mock()))
        namespace={'urllib':original};fail=threading.Event();seen=threading.Event()
        observer=AgentReadObserver({(18790,'/api/status'):'control:/api/status'})
        def probe():
            if fail.is_set():raise PermissionError('PRIVATE-EXCEPTION')
            return False
        def tick():seen.set();return {'state':'captured'}
        host=DashboardShadowHost(namespace,SimpleNamespace(observer=observer,tick=tick),
            {'http://127.0.0.1:18790/api/status':(18790,'/api/status')},enabled=True,stop_requested=probe)
        identity=(os.getpid(),psutil.Process().create_time())
        try:
            host.start();self.assertTrue(await asyncio.to_thread(seen.wait,2));fail.set()
            async with asyncio.timeout(4):
                while host.status()['state']!='stopped':await asyncio.sleep(.01)
            self.assertIs(original,namespace['urllib']);self.assertEqual(identity,(os.getpid(),psutil.Process().create_time()))
            self.assertEqual('shadow_stop_probe_failed',host.status()['code'])
            fail.clear();host.start();self.assertEqual('shadow_restart_requires_new_host',host.status()['code'])
            self.assertFalse(host.status()['workerAlive'])
        finally:await host.close()

    async def test_unreadable_control_at_start_never_binds(self):
        original=object();namespace={'urllib':original}
        def probe():raise OSError('private path')
        host=DashboardShadowHost(namespace,None,{},enabled=True,stop_requested=probe)
        self.assertEqual('shadow_stop_probe_failed',host.start()['code'])
        self.assertIs(original,namespace['urllib']);self.assertIsNone(host.thread)
        self.assertTrue(host.stop_event.is_set())


if __name__=='__main__':unittest.main()
