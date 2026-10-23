"""Explicit in-memory observer for existing Agent.home reads; no I/O or credentials."""
import copy,json,threading,re
from tools.shadow_capture import CaptureError,_safe

class AgentReadObserver:
    def __init__(self, ports, *, max_body_bytes=3*1024*1024):
        self.ports=dict(ports)
        if not self.ports or len(self.ports)>16 or max_body_bytes<1 or max_body_bytes>8*1024*1024:raise CaptureError('observer_ports_required')
        for (port,target),key in self.ports.items():
            if port not in {8765,8766} or not target.startswith('/api/') or '?' in target or not re.fullmatch(r'(receiver|control):/api/[A-Za-z0-9_/.:-]+',key):
                raise CaptureError('observer_port_invalid')
        self.limit=max_body_bytes;self.lock=threading.RLock();self.serial=0
        self.pending={};self.values={};self.generations={};self.failures={}
    def begin(self,port,target):
        key=self.ports.get((port,target))
        if not key:return None
        with self.lock:
            self.serial+=1;self.generations[key]=self.serial;self.values.pop(key,None)
            self.pending[self.serial]=key
            return self.serial
    def complete(self,attempt,status,raw):
        with self.lock:
            key=self.pending.get(attempt)
            if key is None:return
            if self.generations[key]!=attempt:
                self.pending.pop(attempt,None);return
            try:
                if status!=200 or not isinstance(raw,bytes) or len(raw)>self.limit:raise ValueError()
                value=json.loads(raw.decode('utf-8-sig'));_safe(value)
            except Exception:
                self.failures[key]='observer_body_rejected';self.pending.pop(attempt,None);return
            self.values[key]=value;self.failures.pop(key,None);self.pending.pop(attempt,None)
    def end(self,attempt):
        with self.lock:
            key=self.pending.pop(attempt,None)
            if key is not None and self.generations[key]==attempt:
                self.values.pop(key,None);self.failures[key]='observer_read_incomplete'
    def observation(self):
        with self.lock:
            if self.pending or self.failures or set(self.values)!=set(self.ports.values()):raise CaptureError('observed_external_ports_incomplete')
            return {'responses':copy.deepcopy(self.values),'observationGeneration':self.serial}
