"""R3 candidate behind one existing ExecutionWorker; dormant unless injected.

No listener, scheduling, discovery, config read, worker or ledger of its own.
"""
from __future__ import annotations
import asyncio,base64,copy,inspect,json,math,re,types,http.client
from urllib.parse import unquote
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi import HTTPException
from contracts.commands import command,canonical,MAX_REPLY
from . import ordinary_logic

ROUTES=(
 (r'/api/controls/tasks/create','control_create_task'),
 (r'/api/controls/tasks/(?P<task_id>[^/]+)/replenish','control_replenish_task'),
 (r'/api/controls/tasks/(?P<task_id>[^/]+)/start','control_start_task'),
 (r'/api/controls/tasks/(?P<task_id>[^/]+)/cancel','control_cancel_task'),
 (r'/api/controls/upload/rescan','control_upload_rescan'),
 (r'/api/controls/upload/verify-history','control_upload_verify_history'))

def route(target):
    path=unquote(target,errors='strict')
    for pattern,name in ROUTES:
        match=re.fullmatch(pattern,path)
        if match:return name,match.groupdict()
    raise ValueError('not_an_r3_ordinary_command')

def request_for(target,body,client='127.0.0.1',*,raw=None):
    raw=canonical(body).encode() if raw is None else raw
    async def receive():return {'type':'http.request','body':raw,'more_body':False}
    return Request({'type':'http','method':'POST','path':unquote(target),'query_string':b'','headers':[(b'content-type',b'application/json')],'client':(client,10000),'server':('isolated-command',8765),'scheme':'http'},receive)

async def invoke(namespace,target,body,*,client='127.0.0.1',raw=None):
    name,args=route(target);args['request']=request_for(target,body,client,raw=raw)
    try:
        value=namespace[name](**args)
        if inspect.isawaitable(value):value=await value
        return value
    except HTTPException as error:return JSONResponse({'detail':error.detail},status_code=error.status_code,headers=error.headers)
    except Exception as error:
        # Match the old HTTP exception boundary, including its ApiError event.
        # A broken error sink must propagate as uncertain, never a not_sent lie.
        return await namespace['unhandled_error'](None,error)

class OrdinaryCommands:
    def __init__(self,ports,*,fence=None,fence_probe=None,clock=None,isolated=False):
        missing=set(ordinary_logic.REQUIRED_PORTS)-set(ports)
        if missing:raise ValueError('missing_ordinary_ports:'+','.join(sorted(missing)))
        self.namespace={'__builtins__':__builtins__,'__name__':'ordinary_candidate'}
        self.namespace.update({k:copy.deepcopy(v) if isinstance(v,(dict,list,set)) else v for k,v in ports.items() if k in ordinary_logic.REQUIRED_PORTS})
        for name,fn in vars(ordinary_logic).items():
            if inspect.isfunction(fn) and fn.__module__==ordinary_logic.__name__:
                cloned=types.FunctionType(fn.__code__,self.namespace,fn.__name__,fn.__defaults__,fn.__closure__)
                cloned.__kwdefaults__=fn.__kwdefaults__;cloned.__annotations__=fn.__annotations__;self.namespace[name]=cloned
        self.fence=fence;self.fence_probe=fence_probe;self.clock=clock or self.namespace['time'].time;self.isolated=isolated
    @staticmethod
    def supports(target):
        try:spec=command(target,{});route(spec['target']);return spec['source']=='dashboard'
        except (ValueError,TypeError,UnicodeError):return False
    def evaluate_isolated(self,target,body,*,client='127.0.0.1',raw=None):
        if not self.isolated:raise ValueError('isolated_evaluation_only')
        return asyncio.run(invoke(self.namespace,target,body,client=client,raw=raw))
    def send(self,job):
        spec=command(job['target'],job['body']);route(spec['target'])
        if spec['source']!='dashboard' or self.fence is None or self.fence_probe is None:return {'kind':'not_sent','reason':'send_permit_denied'}
        from .ordinary_fence import FenceRejected
        try:
            proof=self.fence_probe();state=self.fence.status()
            if not isinstance(proof,dict) or proof.get('protocol')!=1 or proof.get('fenceId')!=state['fenceId'] or proof.get('owner')!='candidate' or proof.get('legacyWritesBlocked') is not True:return {'kind':'not_sent','reason':'send_permit_denied'}
        except (OSError,ValueError,HTTPException,http.client.HTTPException):return {'kind':'not_sent','reason':'send_permit_denied'}
        try:
            with self.fence.guard('candidate'):
                expires=job.get('expiresAt')
                if type(expires) not in (int,float) or not math.isfinite(expires) or expires<=self.clock():return {'kind':'not_sent','reason':'invalid_or_expired'}
                try:
                    value=asyncio.run(invoke(self.namespace,spec['target'],spec['body']))
                    response=value if isinstance(value,JSONResponse) else JSONResponse(value)
                    raw=response.body
                    if len(raw)>MAX_REPLY:raise OSError('ordinary_result_exceeded_bound')
                    return {'kind':'http','httpStatus':response.status_code,'contentType':response.headers.get('content-type','application/json'),'bodyBase64':base64.b64encode(raw).decode('ascii')}
                except (OSError,ValueError,TypeError,RuntimeError) as error:
                    raise OSError('ordinary_result_uncertain') from error
        except FenceRejected:return {'kind':'not_sent','reason':'send_permit_denied'}
        except OSError:
            # The durable ExecutionWorker already marked this command sent.
            # Invocation or response serialization may have followed a write;
            # retain an unknown receipt and never fall back to the old POST.
            return {'kind':'unknown','reason':'transport_uncertain'}
