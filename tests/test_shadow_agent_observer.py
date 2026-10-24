import json,tempfile,threading,unittest,urllib.error
from types import SimpleNamespace
from unittest.mock import Mock
from pathlib import Path
from agent.readonly import ReadOnlyAgent as Agent
from tools.shadow_agent_observer import AgentReadObserver
from tools.shadow_capture import CaptureError

class Response:
    status=200
    headers={}
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return self.raw

class AgentObserverTests(unittest.TestCase):
    def make(self,observer,raw=b'{"ok":true}'):
        agent=Agent.__new__(Agent);agent.stop=threading.Event();agent.engine=None;agent.read_observer=observer
        agent.ledger_lock=threading.Lock();agent._ledger=SimpleNamespace(source=lambda target:None,note_request=Mock())
        agent.full_read_at={};agent.engine_state='healthy';agent.schedule=SimpleNamespace(active=lambda:False)
        agent.transport=SimpleNamespace(open=Mock(return_value=Response(raw)))
        return agent
    def observer(self):return AgentReadObserver({(8766,'/api/health'):'receiver:/api/health'})
    def test_existing_sized_read_captured_once_without_extra_request(self):
        observer=self.observer();agent=self.make(observer)
        self.assertEqual(agent.home('/api/health',8766),(200,{'ok':True},''))
        self.assertEqual(agent.transport.open.call_count,1)
        self.assertEqual(observer.observation()['responses'],{'receiver:/api/health':{'ok':True}})
    def test_disabled_returns_same_result(self):
        agent=self.make(None);self.assertEqual(agent.home('/api/health',8766),(200,{'ok':True},''));self.assertEqual(agent.transport.open.call_count,1)
    def test_observer_failure_does_not_fail_agent(self):
        observer=Mock();observer.begin.return_value=1;observer.complete.side_effect=RuntimeError('fixture');observer.end.side_effect=RuntimeError('fixture')
        self.assertEqual(self.make(observer).home('/api/health',8766)[0],200)
    def test_credentials_not_retained_and_old_value_invalidated(self):
        observer=self.observer();self.make(observer).home('/api/health',8766)
        self.assertEqual(self.make(observer,b'{"accessToken":"synthetic-only"}').home('/api/health',8766)[0],200)
        with self.assertRaises(CaptureError):observer.observation()
    def test_304_invalidates_body_without_changing_request(self):
        observer=self.observer();agent=self.make(observer);agent.home('/api/health',8766)
        agent._ledger.source=lambda target:{'etag':'fixture'}
        agent.transport.open.side_effect=urllib.error.HTTPError('http://example.invalid',304,'Not Modified',{},None)
        self.assertEqual(agent.home('/api/health',8766),(304,None,'fixture'))
        with self.assertRaises(CaptureError):observer.observation()
    def test_late_response_cannot_overwrite_new_generation(self):
        observer=self.observer();a=observer.begin(8766,'/api/health');b=observer.begin(8766,'/api/health');observer.complete(b,200,b'{"n":2}');observer.complete(a,200,b'{"n":1}')
        self.assertEqual(observer.observation()['responses']['receiver:/api/health'],{'n':2})
    def test_overlap_incomplete_and_body_limit(self):
        observer=self.observer();a=observer.begin(8766,'/api/health');observer.end(a)
        with self.assertRaises(CaptureError):observer.observation()
        a=observer.begin(8766,'/api/health');observer.complete(a,200,b'x'*(observer.limit+1))
        with self.assertRaises(CaptureError):observer.observation()
    def test_read_in_flight_keeps_previous_body_until_it_ends(self):
        observer=self.observer();a=observer.begin(8766,'/api/health');observer.complete(a,200,b'{"n":1}')
        b=observer.begin(8766,'/api/health')
        self.assertEqual(observer.observation()['responses']['receiver:/api/health'],{'n':1})
        observer.end(b)
        with self.assertRaises(CaptureError):observer.observation()
    def test_first_read_in_flight_is_still_incomplete(self):
        observer=self.observer();observer.begin(8766,'/api/health')
        with self.assertRaises(CaptureError):observer.observation()
    def test_unlisted_get_does_not_capture(self):
        observer=self.observer();agent=self.make(observer);self.assertEqual(agent.home('/api/dashboard/summary')[0],200)
        self.assertEqual(observer.serial,0)

if __name__=='__main__':unittest.main()

