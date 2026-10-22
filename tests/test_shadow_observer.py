import io,json,unittest
from urllib.request import Request
from tools.shadow_observer import ResponseObserver
from tools.shadow_capture import CaptureError
class ObserverTests(unittest.TestCase):
 def test_existing_read_returned_once_and_no_post_observation(self):
  raw=b'{"ok":true}';calls=[]
  def original(request,**kwargs):calls.append(request.get_method());return io.BytesIO(raw)
  observer=ResponseObserver({'http://receiver.fixture.invalid/api/tasks':'receiver:/api/tasks'});wrapped=observer.wrap(original)
  with wrapped(Request('http://receiver.fixture.invalid/api/tasks')) as reply:self.assertEqual(raw,reply.read())
  self.assertEqual({'receiver:/api/tasks':{'ok':True}},observer.facts())
  with wrapped(Request('http://receiver.fixture.invalid/api/tasks',data=b'{}',method='POST')) as reply:self.assertEqual(raw,reply.read())
  self.assertEqual(['GET','POST'],calls);self.assertEqual(0,observer.status()['businessRequests']);self.assertFalse(observer.status()['headersStored'])
 def test_chunked_reads_record_only_complete_json(self):
  raw=b'{"items":[1,2]}';observer=ResponseObserver({'http://receiver.fixture.invalid/api/tasks':'receiver:/api/tasks'});wrapped=observer.wrap(lambda *a,**k:io.BytesIO(raw))
  with wrapped(Request('http://receiver.fixture.invalid/api/tasks')) as reply:
   pieces=[]
   while True:
    chunk=reply.read(3);pieces.append(chunk)
    if not chunk:break
  self.assertEqual(raw,b''.join(pieces));self.assertEqual({'items':[1,2]},observer.facts()['receiver:/api/tasks'])
 def test_private_or_oversized_body_never_enters_cache_but_caller_bytes_unchanged(self):
  for raw,limit in [(b'{"accessToken":"private-canary"}',1024),(b'{"items":[1,2]}',1)]:
   with self.subTest(limit=limit):
    observer=ResponseObserver({'http://receiver.fixture.invalid/api/tasks':'receiver:/api/tasks'},max_body_bytes=limit);wrapped=observer.wrap(lambda *a,**k:io.BytesIO(raw))
    with wrapped(Request('http://receiver.fixture.invalid/api/tasks')) as reply:self.assertEqual(raw,reply.read())
    with self.assertRaises(CaptureError):observer.facts()
    self.assertNotIn('private-canary',json.dumps(observer.status()));self.assertEqual({},observer.values)
 def test_original_error_is_not_hidden_and_invalidates_previous_observation(self):
  observer=ResponseObserver({'http://receiver.fixture.invalid/api/tasks':'receiver:/api/tasks'});failure=OSError('fixture-only')
  def original(*a,**k):raise failure
  with self.assertRaises(OSError) as error:observer.wrap(original)(Request('http://receiver.fixture.invalid/api/tasks'))
  self.assertIs(failure,error.exception)
  with self.assertRaises(CaptureError):observer.facts()

 def test_new_unfinished_request_invalidates_old_cached_reply(self):
  observer=ResponseObserver({'http://receiver.fixture.invalid/api/tasks':'receiver:/api/tasks'});wrapped=observer.wrap(lambda *a,**k:io.BytesIO(b'{"ok":true}'))
  with wrapped(Request('http://receiver.fixture.invalid/api/tasks')) as reply:reply.read()
  self.assertEqual(1,len(observer.facts()));next_reply=wrapped(Request('http://receiver.fixture.invalid/api/tasks'))
  with self.assertRaises(CaptureError):observer.facts()
  with next_reply as reply:reply.read(1)
  with self.assertRaises(CaptureError):observer.facts()

 def test_zero_size_read_is_not_eof_and_cannot_certify_a_valid_prefix(self):
  raw=b'{"ok":true}trailing';observer=ResponseObserver({'http://receiver.fixture.invalid/api/tasks':'receiver:/api/tasks'});wrapped=observer.wrap(lambda *a,**k:io.BytesIO(raw))
  with wrapped(Request('http://receiver.fixture.invalid/api/tasks')) as reply:
   self.assertEqual(b'{"ok":true}',reply.read(11));self.assertEqual(b'',reply.read(0))
   with self.assertRaises(CaptureError):observer.facts()
   reply.read()
  with self.assertRaises(CaptureError):observer.facts()
 def test_concurrent_reads_cannot_certify_while_one_is_pending(self):
  observer=ResponseObserver({'http://receiver.fixture.invalid/api/tasks':'receiver:/api/tasks'});wrapped=observer.wrap(lambda *a,**k:io.BytesIO(b'{"ok":true}'));one=wrapped(Request('http://receiver.fixture.invalid/api/tasks'));two=wrapped(Request('http://receiver.fixture.invalid/api/tasks'))
  with one as response:response.read()
  with self.assertRaises(CaptureError):observer.facts()
  with two as response:response.read()
  self.assertEqual({'ok':True},observer.facts()['receiver:/api/tasks'])
