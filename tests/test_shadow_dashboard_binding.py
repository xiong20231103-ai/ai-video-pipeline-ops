import io,unittest,urllib.request,urllib.error,urllib.parse
from types import SimpleNamespace
from unittest.mock import Mock
from tools.shadow_agent_observer import AgentReadObserver
from tools.shadow_dashboard_binding import DashboardReadBinding
from tools.shadow_capture import CaptureError
class DashboardBindingTests(unittest.TestCase):
    def setup_binding(self):
        observer=AgentReadObserver({(8766,'/api/health'):'receiver:/api/health'})
        raw=b'{"ok":true}'
        def answer(*args,**kwargs):
            response=io.BytesIO(raw);response.status=200;return response
        opener=Mock(side_effect=answer)
        original=SimpleNamespace(request=SimpleNamespace(urlopen=opener,Request=urllib.request.Request),error=urllib.error,parse=urllib.parse)
        namespace={'urllib':original};binding=DashboardReadBinding(namespace,observer,{'http://127.0.0.1:8766/api/health':(8766,'/api/health')})
        return observer,opener,original,namespace,binding,raw
    def test_exact_original_get_once_and_no_global_patch(self):
        before=urllib.request.urlopen;o,opener,old,n,b,raw=self.setup_binding()
        with n['urllib'].request.urlopen('http://127.0.0.1:8766/api/health') as response:self.assertEqual(raw,response.read())
        self.assertEqual(1,opener.call_count);self.assertTrue(o.observation()['responses']['receiver:/api/health']['ok']);self.assertIs(before,urllib.request.urlopen)
        self.assertIs(urllib.error,n['urllib'].error);b.restore();self.assertIs(old,n['urllib'])
    def test_post_and_unknown_url_not_observed(self):
        o,opener,old,n,b,raw=self.setup_binding()
        for req in [urllib.request.Request('http://127.0.0.1:8766/api/health',data=b'{}'), 'http://127.0.0.1:8766/api/other']:
            with n['urllib'].request.urlopen(req) as response:self.assertEqual(raw,response.read())
        self.assertEqual(2,opener.call_count);self.assertEqual(0,o.serial)
    def test_partial_and_unread_responses_remain_incomplete(self):
        for read in [False,True]:
            o,opener,old,n,b,raw=self.setup_binding()
            with n['urllib'].request.urlopen('http://127.0.0.1:8766/api/health') as response:
                if read:response.read(2)
            with self.assertRaises(CaptureError):o.observation()
    def test_original_error_propagates_and_invalidates(self):
        o,opener,old,n,b,raw=self.setup_binding();opener.side_effect=ValueError('fixture')
        with self.assertRaisesRegex(ValueError,'fixture'):n['urllib'].request.urlopen('http://127.0.0.1:8766/api/health')
        with self.assertRaises(CaptureError):o.observation()
    def test_observer_failure_does_not_change_get_result(self):
        o,opener,old,n,b,raw=self.setup_binding();o.complete=Mock(side_effect=RuntimeError('fixture'))
        with n['urllib'].request.urlopen('http://127.0.0.1:8766/api/health') as response:self.assertEqual(raw,response.read())
    def test_restore_never_overwrites_new_owner(self):
        o,opener,old,n,b,raw=self.setup_binding();n['urllib']=object()
        with self.assertRaises(CaptureError):b.restore()
if __name__=='__main__':unittest.main()
