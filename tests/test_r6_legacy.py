"""Retained HTTP wrapper only; never imports or starts the installed Dashboard."""
from contextlib import contextmanager
from unittest.mock import Mock,patch
import types
import unittest

from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from agent.legacy_host import LegacyRecoveryApp,LegacyBackgroundGuard
from agent.core.ordinary_fence import FenceRejected


class LegacyWrapperTests(unittest.TestCase):
    def setUp(self):
        self.controller=Mock()
        self.controller.request_capabilities.return_value={
            'protocol':2,'expiryChecked':True,'cancelUnderAuthorityLock':True}
        self.namespace={}
        self.calls=[]
        self.application=FastAPI()
        @self.application.get('/api/health')
        def health():
            self.calls.append('health');return {'ok':True}
        @self.application.post('/api/controls/continue-current')
        def unsafe_continue():
            self.calls.append('unsafe');return {'accepted':True}
        @contextmanager
        def guard():
            self.calls.append('enter')
            try:yield
            finally:self.calls.append('exit')
        self.lease=Mock();self.lease.guard=guard
        self.wrapper=LegacyRecoveryApp(self.application,self.namespace,self.controller,self.lease)

    def test_existing_read_is_fenced_and_unsafe_continue_route_is_disabled(self):
        client=TestClient(self.wrapper)
        self.assertEqual({'ok':True},client.get('/api/health').json())
        self.assertEqual(['enter','health','exit'],self.calls)
        self.assertEqual(405,client.post('/api/controls/continue-current',json={}).status_code)
        self.assertNotIn('unsafe',self.calls)
        self.controller.enqueue_request.assert_not_called()
        self.assertEqual(self.wrapper.transport.submit,self.namespace['request_workbench_continue'])

    def test_unavailable_ownership_never_calls_legacy_http_or_controller(self):
        @contextmanager
        def refused():
            raise OSError('isolated owner unavailable')
            yield
        self.lease.guard=refused
        client=TestClient(self.wrapper)
        for method,target in (('GET','/api/health'),('POST','/api/control-commands/inert/cancel')):
            self.assertEqual(503,client.request(method,target).status_code)
        self.assertEqual([],self.calls)
        self.controller.cancel_request.assert_not_called()
        self.controller.enqueue_request.assert_not_called()

    def test_cancel_uses_protocol_adapter_and_preserves_reconciliation_error(self):
        client=TestClient(self.wrapper)
        with patch.object(self.wrapper.transport,'cancel',side_effect=HTTPException(409,'isolated reconciliation required')) as cancel:
            reply=client.post('/api/control-commands/inert/cancel',json={})
        self.assertEqual(409,reply.status_code)
        self.assertEqual({'detail':'isolated reconciliation required'},reply.json())
        self.assertEqual('inert',cancel.call_args.args[0])
        self.assertEqual(['enter','exit'],self.calls)
        self.controller.enqueue_request.assert_not_called()


class BackgroundGuardTests(unittest.TestCase):
    def fixture(self,*,owned):
        stop=Mock();stop.is_set.side_effect=[False,True]
        collector=types.SimpleNamespace(thread=None,run=Mock(),scan=Mock(),store=Mock(),
            stop_event=stop,config={'scan_interval_seconds':5})
        namespace={'COLLECTOR':collector,'_pending_delete_purge_loop':Mock(),
            'pending_delete':Mock(),'pending_delete_roots':Mock(return_value=['inert-root']),
            'PENDING_DELETE_PURGE_INTERVAL_SECONDS':3600}
        inside=[]
        @contextmanager
        def guard():
            if not owned:raise FenceRejected('isolated standby')
            inside.append(True)
            try:yield
            finally:inside.pop()
        lease=Mock();lease.guard=guard
        result=LegacyBackgroundGuard(namespace,lease);result.install()
        return result,namespace,collector,inside
    def test_candidate_owner_blocks_all_old_background_writes(self):
        guard,n,collector,_=self.fixture(owned=False)
        collector.run()
        collector.scan.assert_not_called();collector.store.event.assert_not_called()
        stop=Mock();stop.is_set.side_effect=[False,True]
        n['_pending_delete_purge_loop'](stop)
        n['pending_delete'].purge.assert_not_called();n['pending_delete_roots'].assert_not_called()
        collector.stop_event.wait.assert_called_once_with(5)
        stop.wait.assert_called_once_with(3600)
    def test_legacy_owner_holds_lease_across_scan_errors_and_retention(self):
        guard,n,collector,inside=self.fixture(owned=True)
        def scan():
            self.assertTrue(inside);raise ValueError('inert scan failure')
        collector.scan.side_effect=scan
        collector.store.event.side_effect=lambda *args:self.assertTrue(inside)
        collector.run()
        self.assertEqual(2,collector.store.event.call_count)
        stop=Mock();stop.is_set.side_effect=[False,True]
        n['pending_delete'].purge.side_effect=lambda roots:self.assertTrue(inside)
        n['_pending_delete_purge_loop'](stop)
        n['pending_delete'].purge.assert_called_once_with(['inert-root'])
        self.assertEqual([],inside)
    def test_install_refuses_running_or_already_wrapped_collector(self):
        guard,n,collector,_=self.fixture(owned=True)
        with self.assertRaisesRegex(ValueError,'already_installed'):guard.install()
        collector.thread=Mock();collector.thread.is_alive.return_value=True
        with self.assertRaisesRegex(ValueError,'already_started'):LegacyBackgroundGuard(n,guard.lease).install()
