"""Authenticated console writes and Tailnet-only tokenless submitter ingress."""
import asyncio,hashlib,ipaddress,json
from fastapi import Request,HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from cloud.commands import CommandError

def trusted_tailnet(request):
    if not request.client or request.client.host not in {'127.0.0.1','::1'} or request.headers.get('x-forwarded-proto')!='https':raise HTTPException(403,'trusted_serve_required')
    try:
        address=ipaddress.ip_address(request.headers.get('x-forwarded-for',''))
        if not (address in ipaddress.ip_network('100.64.0.0/10') or address in ipaddress.ip_network('fd7a:115c:a1e0::/48')):raise ValueError()
    except ValueError:raise HTTPException(403,'tailnet_source_required') from None

def mount_commands(app,queue,agent,session,csrf,bounded_json,rate,rate_identity,origin):
    def reject(error):raise HTTPException(error.status,error.code) from None
    def actor(row):return 'user:'+str(row['user_id'])+':'+row['name']
    def call(method,*args,**kwargs):
        try:return method(*args,**kwargs)
        except CommandError as error:reject(error)
        except (ValueError,UnicodeError):raise HTTPException(400,'invalid_command_contract') from None
    @app.get('/console/commands')
    def listing(request:Request):session(request);return call(queue.listing)
    @app.get('/console/commands/request/{request_id}')
    def by_request(request_id:str,request:Request):return call(queue.by_request,actor(session(request)),request_id)
    @app.post('/console/commands/request/{request_id}/cancel')
    def cancel_request(request_id:str,request:Request):
        row=session(request);csrf(request,row);return call(queue.cancel_request,actor(row),request_id)
    @app.post('/console/submission-requests/{request_id}/cancel')
    def cancel_submission_request(request_id:str,request:Request):
        row=session(request);csrf(request,row);trusted_tailnet(request);rate(request,'commands',30)
        return call(queue.cancel_request,'tailnet:'+rate_identity(request),request_id)
    @app.get('/console/commands/{identifier}')
    def status(identifier:str,request:Request):session(request);return call(queue.get,identifier)
    @app.post('/console/commands/{identifier}/cancel')
    def cancel(identifier:str,request:Request):
        row=session(request);csrf(request,row);return call(queue.cancel,identifier,actor(row))
    @app.post('/console/commands/{identifier}/resolve')
    async def resolve(identifier:str,request:Request):
        row=session(request);csrf(request,row);data=await bounded_json(request)
        return call(queue.resolve,identifier,actor(row),data.get('note'),data.get('confirmation'))
    @app.get('/agent/commands')
    async def claim(request:Request,ledgerId:str,wait:int=25):
        agent(request)
        if not 0<=wait<=25:raise HTTPException(400,'invalid_wait')
        try:item=await run_in_threadpool(queue.wait_claim,ledgerId,wait)
        except CommandError as error:reject(error)
        return {'item':item}
    @app.post('/agent/commands/{identifier}/start')
    async def start(identifier:str,request:Request):
        agent(request);data=await bounded_json(request)
        return call(queue.permit,identifier,data.get('lease'),data.get('ledgerId'))
    @app.post('/agent/results')
    async def result(request:Request):
        agent(request);data=await bounded_json(request)
        return call(queue.finish,data.get('id'),data.get('lease'),data.get('ledgerId'),data.get('result'))
    @app.post('/api/batches/validate')
    @app.post('/api/batches')
    async def submission(request:Request):
        if not queue.enabled:raise HTTPException(403,'command_milestone_disabled')
        trusted_tailnet(request)
        if request.headers.get('origin') not in {None,origin}:raise HTTPException(403,'origin_rejected')
        if request.headers.get('content-type','').split(';')[0]!='application/json':raise HTTPException(415,'json_required')
        rate(request,'submissions',20);data=await bounded_json(request)
        client=request.headers.get('x-client-request-id')
        if not client:
            value=data.get('clientSubmissionId') or data.get('batchId')
            if not isinstance(value,str) or not 1<=len(value)<=200:raise HTTPException(400,'client_submission_id_required')
            client=hashlib.sha256((request.url.path+'\n'+value).encode()).hexdigest()
        answer=call(queue.enqueue,'tailnet:'+rate_identity(request),client,request.url.path,data,public=True)
        # Wait at most 25 seconds without occupying the ASGI loop or polling
        # home; the durable receipt remains queryable after disconnect/reload.
        deadline=asyncio.get_running_loop().time()+25
        while answer['state'] in {'queued','leased','sent'} and asyncio.get_running_loop().time()<deadline:
            await asyncio.sleep(.25);answer=await run_in_threadpool(queue.get,answer['cloudCommandId'],True)
        if answer['state']=='completed' and answer['result'] and answer['result']['kind']=='http':
            import base64
            from fastapi.responses import Response
            result=answer['result']
            return Response(base64.b64decode(result['bodyBase64']),status_code=result['httpStatus'],headers={'Content-Type':result['contentType']})
        answer['resultUrl']='/api/submissions/'+answer['cloudCommandId'];answer['cloudReceived']=True
        return JSONResponse(answer,status_code=202,headers={'Retry-After':'1'})
    @app.get('/api/submission-requests/{request_id}')
    def submission_by_request(request_id:str,request:Request):
        trusted_tailnet(request);rate(request,'submission-results',300)
        result=call(queue.by_request,'tailnet:'+rate_identity(request),request_id)
        if not result.get('cancelledBeforeReceipt') and not result['target'].startswith('/api/batches'):raise HTTPException(404,'command_not_found')
        return result
    @app.get('/api/submissions/{identifier}')
    def submission_result(identifier:str,request:Request):
        trusted_tailnet(request);rate(request,'submission-results',300)
        return call(queue.get,identifier,public=True)

    async def enqueue_console(request):
        row=session(request);csrf(request,row);rate(request,'commands',30)
        if not queue.enabled:raise HTTPException(403,'read_only_milestone; commands_not_enabled')
        data=await bounded_json(request)
        client=request.headers.get('x-client-request-id')
        if not client:raise HTTPException(400,'stable_client_request_id_required')
        return JSONResponse(call(queue.enqueue,actor(row),client,request.url.path,data),status_code=202)
    return enqueue_console
