"""Tee existing GET reads into a bounded memory cache; never creates requests.

Integration is explicit and not installed at import. Observer failures cannot
change the caller's return bytes/exceptions, and no credentials/headers are kept.
"""
from __future__ import annotations
import copy,json,threading
from urllib.parse import urlsplit
from tools.shadow_capture import CaptureError,_safe

class ResponseObserver:
 def __init__(self,ports,*,max_body_bytes=3*1024*1024):
  if not ports or max_body_bytes<1:raise CaptureError('explicit_observer_ports_required')
  self.ports={};self.max_body_bytes=max_body_bytes;self.lock=threading.RLock();self.values={};self.failures={};self.pending=set();self.generation=0
  for url,key in ports.items():
   parsed=urlsplit(url)
   if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query or not key.startswith(('receiver:/api/','control:/api/')):raise CaptureError('invalid_observer_port')
   self.ports[url]=key
 def _failed(self,key,code,attempt):
  with self.lock:self.values.pop(key,None);self.pending.discard(attempt);self.failures[key]=code;self.generation+=1
 def _observe(self,key,raw,attempt):
  try:
   value=json.loads(raw.decode('utf-8-sig'));_safe(value)
  except Exception:self._failed(key,'external_body_unusable',attempt);return
  with self.lock:self.values[key]=value;self.pending.discard(attempt);self.failures.pop(key,None);self.generation+=1
 def wrap(self,original):
  observer=self
  def call(request,*args,**kwargs):
   url=request.full_url if hasattr(request,'full_url') else str(request);method=request.get_method() if hasattr(request,'get_method') else 'GET'
   # The original always runs exactly once. POST/non-allowlisted reads are untouched.
   key=observer.ports.get(url) if method=='GET' else None;attempt=None
   if key:
    with observer.lock:
     observer.generation+=1;attempt=observer.generation;observer.values.pop(key,None);observer.pending.add(attempt)
   try:response=original(request,*args,**kwargs)
   except BaseException:
    if key:observer._failed(key,'external_request_failed',attempt)
    raise
   if not key:return response
   class Tee:
    def __init__(self):self.chunks=[];self.total=0;self.done=False
    def __getattr__(self,name):return getattr(response,name)
    def __enter__(self):response.__enter__();return self
    def __exit__(self,*args):
     if not self.done:observer._failed(key,'external_read_incomplete',attempt)
     return response.__exit__(*args)
    def read(self,*read_args,**read_kwargs):
     try:data=response.read(*read_args,**read_kwargs)
     except BaseException:observer._failed(key,'external_read_failed',attempt);raise
     try:
      if not self.done:
       if not isinstance(data,bytes):self.done=True;observer._failed(key,'external_bytes_required',attempt)
       elif self.total+len(data)>observer.max_body_bytes:self.done=True;self.chunks.clear();observer._failed(key,'external_body_limit',attempt)
       else:
        self.total+=len(data);self.chunks.append(data)
        size=read_args[0] if read_args else read_kwargs.get('amt',read_kwargs.get('size',-1))
        if size is None or size<0 or size>0 and not data:
         self.done=True;observer._observe(key,b''.join(self.chunks),attempt);self.chunks.clear()
     except Exception:observer._failed(key,'observer_internal_failure',attempt)
     return data
   return Tee()
  return call
 def facts(self):
  with self.lock:
   if set(self.values)!=set(self.ports.values()) or self.failures or self.pending:raise CaptureError('observed_external_ports_incomplete')
   return copy.deepcopy(self.values)
 def observation(self):
  with self.lock:return {'responses':self.facts(),'observationGeneration':self.generation}
 def status(self):
  with self.lock:return {'expectedPorts':len(set(self.ports.values())),'capturedPorts':len(self.values),'generation':self.generation,'failureCodes':sorted(set(self.failures.values())),'businessRequests':0,'headersStored':False}
