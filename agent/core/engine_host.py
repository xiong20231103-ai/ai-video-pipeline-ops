"""Candidate HTTP compatibility and backend for the ONE existing command worker.

No app import, implicit binding, server start, configuration read or fallback to
the old Dashboard. Construction alone does not enable or deploy this candidate.
"""
from __future__ import annotations
import asyncio
import base64
import inspect
import json
import math
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote,urlsplit
from typing import get_type_hints
from fastapi import FastAPI,HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse,Response,RedirectResponse
from contracts.cache import cache_key
from contracts.commands import command,MAX_REPLY
from .ordinary_fence import FenceRejected


class EngineHost:
    def __init__(self,session,lease,*,clock=time.time):
        self.session=session;self.namespace=session.namespace;self.lease=lease;self.clock=clock
        manifest=json.loads((Path(__file__).parents[2]/'tests/fixtures/migration/r6-provenance.json').read_text(encoding='utf-8'))
        self.routes=tuple(row for row in manifest['routes'] if not row['disabled'])
        self.scan_lock=threading.Lock()
        self.application=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        self.application.add_exception_handler(Exception,self.namespace['unhandled_error'])
        for row in self.routes:
            fn=self.namespace[row['handler']]
            # Keep FastAPI's actual coercion/422 body rather than approximating
            # it in a second handwritten validator. The async boundary executes
            # in the already isolated request thread, without nesting a second
            # thread pool or serializing a 18790 callback behind its caller.
            self.application.add_api_route(row['path'],self._endpoint(fn,row['path'],row['handler']),methods=[row['method']])

    def _endpoint(self,fn,path,handler_name):
        async def endpoint(**kwargs):
            result=self.namespace[handler_name](**kwargs)
            return await result if inspect.isawaitable(result) else result
        hints=get_type_hints(fn,globalns=getattr(fn,'__globals__',self.namespace))
        parameters=[]
        for name,param in inspect.signature(fn).parameters.items():
            annotation=Request if name=='request' else hints.get(name,param.annotation)
            if annotation is inspect.Parameter.empty and '{'+name+'}' in path:annotation=str
            parameters.append(param.replace(annotation=annotation))
        endpoint.__name__=getattr(fn,'__name__','candidate_endpoint')
        endpoint.__signature__=inspect.Signature(parameters,return_annotation=inspect.Signature.empty)
        return endpoint

    def _route(self,method,target):
        path=unquote(urlsplit(target).path,errors='strict')
        for row in self.routes:
            if row['method']!=method:continue
            pattern=re.sub(r'\\\{([A-Za-z_][A-Za-z0-9_]*)\\\}',r'(?P<\1>[^/]+)',re.escape(row['path']))
            match=re.fullmatch(pattern,path)
            if match:return self.namespace[row['handler']],match.groupdict()
        raise HTTPException(404,'候选引擎没有此接口')

    def _invoke(self,method,target,body=None,headers=None):
        parsed=urlsplit(target)
        raw=json.dumps(body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode() if method=='POST' else b''
        request_headers=dict(headers or {})
        if method=='POST':request_headers['Content-Type']='application/json'
        scope={'type':'http','http_version':'1.1','method':method,'scheme':'http',
            'path':unquote(parsed.path),'raw_path':parsed.path.encode(),'query_string':parsed.query.encode(),
            'headers':[(str(k).lower().encode(),str(v).encode()) for k,v in request_headers.items()],
            'client':('127.0.0.1',10000),'server':('candidate-engine',8765),'root_path':''}
        received=False;status=None;response_headers=[];chunks=bytearray();ended=False
        limit=8*1024*1024 if method=='GET' else MAX_REPLY
        async def receive():
            nonlocal received
            if received:return {'type':'http.disconnect'}
            received=True;return {'type':'http.request','body':raw,'more_body':False}
        async def send(message):
            nonlocal status,response_headers,ended
            if message['type']=='http.response.start':status=message['status'];response_headers=message.get('headers',[])
            elif message['type']=='http.response.body':
                chunks.extend(message.get('body',b''))
                if len(chunks)>limit:raise OSError('candidate_reply_exceeded_limit')
                ended=not message.get('more_body',False)
        try:
            asyncio.run(self.application(scope,receive,send))
        except Exception as error:
            # Starlette reraises AFTER sending its handled HTTP500. Preserve
            # that completed HTTP receipt, exactly like a network transport.
            # No complete response means unknown, never a second invocation.
            if not ended:raise OSError('candidate_result_uncertain') from error
        if status is None or not ended:raise OSError('candidate_result_incomplete')
        response=Response(bytes(chunks),status_code=status)
        response.raw_headers=response_headers
        return response

    @staticmethod
    def supports(target):
        try:return command(target,{})['source']=='dashboard'
        except (ValueError,TypeError,UnicodeError):
            # Body validation (expectedTarget/cleanup ticket) is done by the
            # same ExecutionWorker before this seam. Match the closed path set
            # here, without inventing an empty body for those required fields.
            from contracts.commands import RULES
            try:
                parts=urlsplit(target);path=unquote(parts.path,errors='strict')
                return not(parts.scheme or parts.netloc or parts.query or parts.fragment) and any(
                    source=='dashboard' and re.fullmatch(pattern,path) for pattern,source,_ in RULES)
            except (ValueError,TypeError,UnicodeError):return False

    def get_response(self,target,headers=None):
        target=cache_key('GET',target)[4:]
        if not self.session.valid:raise OSError('candidate_projection_unavailable')
        try:
            with self.lease.guard():
                try:return self._invoke('GET',target,headers=headers)
                except HTTPException as error:return JSONResponse({'detail':error.detail},status_code=error.status_code,headers=error.headers)
        except FenceRejected:raise OSError('candidate_authority_unavailable') from None

    def get(self,target,headers=None):
        response=self.get_response(target,headers)
        raw=response.body
        if len(raw)>8*1024*1024:raise ValueError('Source response exceeded limit')
        if response.status_code==304:return 304,None,response.headers.get('etag','')
        if response.status_code!=200:raise OSError('candidate_read_failed:'+str(response.status_code))
        return response.status_code,json.loads(raw),response.headers.get('etag','')

    def send(self,job):
        spec=command(job['target'],job['body'])
        if spec['source']!='dashboard':return {'kind':'not_sent','reason':'send_permit_denied'}
        try:
            with self.lease.guard():
                expires=job.get('expiresAt')
                if type(expires) not in (int,float) or not math.isfinite(expires) or expires<=self.clock():
                    return {'kind':'not_sent','reason':'invalid_or_expired'}
                if not self.session.valid:return {'kind':'not_sent','reason':'send_permit_denied'}
                if spec['target']=='/api/control-commands' and not hasattr(self.session,'recovery_transport'):
                    return {'kind':'not_sent','reason':'send_permit_denied'}
                if spec['target']=='/api/controls/cloud-cleanup/execute' and self.clock()>=spec['body']['expiresAt']:
                    return {'kind':'not_sent','reason':'invalid_or_expired'}
                try:response=self._invoke('POST',spec['target'],spec['body'])
                except HTTPException as error:response=JSONResponse({'detail':error.detail},status_code=error.status_code,headers=error.headers)
                raw=response.body
                if len(raw)>MAX_REPLY:return {'kind':'unknown','reason':'transport_uncertain'}
                return {'kind':'http','httpStatus':response.status_code,
                    'contentType':response.headers.get('content-type','application/json'),
                    'bodyBase64':base64.b64encode(raw).decode('ascii')}
        except FenceRejected:return {'kind':'not_sent','reason':'send_permit_denied'}
        except (OSError,ValueError,TypeError,RuntimeError):
            return {'kind':'unknown','reason':'transport_uncertain'}

    def scan_once(self):
        # Keep original concurrent-read semantics and short per-record commits.
        # Do not hold a DB write transaction or global request lock over a scan.
        with self.scan_lock,self.lease.guard():
            try:self.session.collector.scan();self.session._bounded();self.session.valid=True
            except BaseException:self.session.valid=False;raise

    def collection_loop(self,stop,on_scan=None):
        self.session.collector.thread=threading.current_thread()
        interval=float(self.namespace['CONFIG'].get('scan_interval_seconds',5))
        if not math.isfinite(interval) or not 1<=interval<=3600:raise ValueError('invalid_candidate_scan_interval')
        while not stop.is_set():
            try:self.scan_once()
            except (OSError,ValueError):
                # A failed scan is not fresh data. Retry without enabling writes.
                self.session.valid=False
            if on_scan is not None:on_scan(self.session.valid)
            if stop.wait(interval):break

    def retention_loop(self,stop):
        while not stop.is_set():
            try:
                with self.lease.guard():
                    # Reuse the deployed H2 verifier/retention dates. This is
                    # not everything=True and never introduces a new mover.
                    self.namespace['pending_delete'].purge(self.namespace['pending_delete_roots']())
            except (OSError,ValueError):pass
            if stop.wait(float(self.namespace['PENDING_DELETE_PURGE_INTERVAL_SECONDS'])):break


class CompatibilityApp:
    """Loopback GET-only adapter for old 18790 callers. Never accepts a POST."""
    def __init__(self,engine,cloud_origin):
        parts=urlsplit(cloud_origin)
        if parts.scheme!='https' or not parts.hostname or not parts.hostname.endswith('.ts.net') or parts.username or parts.password or parts.path not in ('','/') or parts.query or parts.fragment:
            raise ValueError('invalid_cloud_origin')
        self.engine=engine;self.origin=cloud_origin.rstrip('/')
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':raise ValueError('compatibility_http_only')
        host=(scope.get('client') or ('',0))[0]
        if host not in {'127.0.0.1','::1'}:response=JSONResponse({'detail':'loopback_only'},status_code=403)
        elif scope['method']!='GET':response=JSONResponse({'detail':'cloud_queue_required'},status_code=405)
        elif scope['path']=='/':response=RedirectResponse(self.origin+'/',status_code=307)
        else:
            target=scope['path']+('?' + scope.get('query_string',b'').decode() if scope.get('query_string') else '')
            try:response=await run_in_threadpool(self.engine.get_response,target,dict(Request(scope).headers))
            except (ValueError,HTTPException):response=JSONResponse({'detail':'unknown_read_contract'},status_code=404)
            except OSError:response=JSONResponse({'detail':'candidate_unavailable'},status_code=503)
        await response(scope,receive,send)
