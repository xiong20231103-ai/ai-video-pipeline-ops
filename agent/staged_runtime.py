"""Agent bridge for reviewed R0--R5 algorithms in the retained host.

No second collector or sender. Absent settings retain the original behavior;
invalid/present settings never fall back to unadmitted home writes.
"""
import base64
import hashlib
import http.client
import json
import sqlite3
from pathlib import Path
import urllib.error
import urllib.request
from contracts.cache import cache_key,endpoint
from contracts.commands import command
from contracts.state_files import read_json,atomic_json
from .core.engine_host import EngineHost
from .core.projection_store import require_plain_path
from .core.transition import Transition,digest
from .core.dispatch_claim import DispatchClaims
from .execution import post_receipt


class StagedBackend:
    supports=staticmethod(EngineHost.supports)
    def __init__(self,state_dir,*,conflict=False):
        self.state=Path(state_dir);self.conflict=conflict;self.transition=None;self.agent=None
    def bind_agent(self,agent):self.agent=agent
    def activate(self):
        try:
            if self.conflict:raise ValueError('mutually_exclusive_engine_settings')
            pointer=read_json(self.state/'migration-settings.json')
            if not isinstance(pointer,dict) or set(pointer)!={'schema','plan','sha256'} or type(pointer['schema']) is not int or pointer['schema']!=1:
                raise ValueError('transition_pointer_invalid')
            path=require_plain_path(pointer['plan'])
            if path.stat().st_size>2*1024*1024:raise ValueError('transition_plan_too_large')
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=pointer['sha256']:raise ValueError('transition_plan_changed')
            plan=json.loads(raw)
            if require_plain_path(plan['agentState'])!=require_plain_path(self.state):raise ValueError('transition_agent_state_mismatch')
            from .engine_runtime import build_digest,ledger_identity
            identity=ledger_identity(self.state/'execution.db',require_empty=False)
            transition=Transition(plan,build=build_digest(Path(__file__).resolve().parents[1]),ledger_id=identity)
            if not transition.resuming:raise ValueError('transition_host_not_initialized')
            self.transition=transition
            atomic_json(self.state/'engine-runtime.json',{'schema':1,'phase':'legacy-stage','stage':transition.stage,'legacyFallback':False})
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
            self.transition=None
            reason=str(error)
            if not reason.replace('_','').isalnum() or len(reason)>90:reason='transition_activation_failed'
            atomic_json(self.state/'engine-runtime.json',{'schema':1,'phase':'unavailable','reason':reason,'legacyFallback':False})
    def available(self):
        if self.transition is None or self.agent is None or (self.state/'engine-settings.json').exists():return False
        try:
            record=read_json(self.transition.marker)
            pointer=read_json(self.state/'migration-settings.json')
            if not isinstance(pointer,dict) or set(pointer)!={'schema','plan','sha256'} or type(pointer['schema']) is not int or pointer['schema']!=1:return False
            path=require_plain_path(pointer['plan'])
            if path.stat().st_size>2*1024*1024:return False
            raw=path.read_bytes()
            return (isinstance(record,dict) and record.get('planSha256')==self.transition.plan_hash
                and record.get('build')==self.transition.build and record.get('ledgerId')==self.transition.identity
                and record.get('stage')==self.transition.stage and record.get('installedModules')==list(self.transition.modules)
                and record.get('phase') in {'prepared','active'} and record.get('sharedState') is True
                and pointer.get('sha256')==hashlib.sha256(raw).hexdigest() and digest(json.loads(raw))==self.transition.plan_hash)
        except (OSError,ValueError,KeyError,TypeError):return False
    def get(self,target,headers=None):
        if not self.available():raise OSError('transition_unavailable')
        target=cache_key('GET',target)[4:]
        timeout=endpoint('GET',target.split('?',1)[0])['timeoutSeconds']
        request=urllib.request.Request('http://100.92.17.9:8765'+target,headers=headers or {},method='GET')
        try:response=self.agent.transport.open(request,timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code==304:return 304,None,error.headers.get('ETag','') or (headers or {}).get('If-None-Match','')
            raise
        with response:
            raw=response.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:raise ValueError('Source response exceeded limit')
            value=json.loads(raw)
            if target=='/api/health' and response.status==200 and isinstance(value,dict) and value.get('ok') is True and value.get('collectorRunning') is True:
                self.transition.ready()
            return response.status,value,response.headers.get('ETag','')
    def send(self,job):
        if not self.available():return {'kind':'not_sent','reason':'send_permit_denied'}
        try:
            spec=command(job['target'],job['body'])
            DispatchClaims(self.state/'execution.db',self.transition.identity).grant(job)
            result=post_receipt(self.agent.transport,spec,{'X-Ops-Execution-Id':job['id'],
                'X-Ops-Execution-Ledger':self.transition.identity})
            if result['httpStatus']==409:
                try:body=json.loads(base64.b64decode(result['bodyBase64']))
                except (ValueError,TypeError):body={}
                if isinstance(body,dict) and body.get('detail')=='execution_already_dispatched':
                    return {'kind':'unknown','reason':'transport_uncertain'}
            return result
        except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,http.client.HTTPException):return {'kind':'unknown','reason':'transport_uncertain'}
    def collection_loop(self,stop):stop.wait()
