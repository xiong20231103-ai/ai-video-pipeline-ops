"""Opt-in handoff routes, separate device Bearers and existing console CSRF."""
import hashlib
import os
from pathlib import Path
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.concurrency import run_in_threadpool

from cloud.material_handoff import Handoff, HandoffError, SHA, identifier, DEFAULT_STORAGE_CAP
from cloud.material_package import validate_package

PREFIX='/api/material-handoff/v1'


def mount_handoff(app,config,store,session,csrf,bounded_json,rate):
    if config.get('material_handoff_enabled') is not True:
        return
    hashes=config.get('material_handoff_tokens_sha256',{})
    if (not isinstance(hashes,dict) or set(hashes)!={'office','home'} or
            any(not isinstance(v,str) or not SHA.fullmatch(v) for v in hashes.values()) or
            hashes['office']==hashes['home'] or config['agent_token_sha256'] in hashes.values()):
        raise RuntimeError('handoff_distinct_device_token_hashes_required')
    handoff=Handoff(config.get('material_handoff_dir',Path(store.path).parent/'material-handoff'),
                    clock=store.clock,lease_seconds=config.get('material_handoff_lease_seconds',120),
                    max_package_bytes=config.get('material_handoff_max_bytes',2*1024**3),
                    storage_cap_bytes=config.get('material_handoff_storage_cap_bytes',DEFAULT_STORAGE_CAP))
    app.state.material_handoff=handoff

    def reject(error):
        raise HTTPException(error.status,error.code) from None

    def call(fn,*args):
        try:
            return fn(*args)
        except HandoffError as error:
            reject(error)

    def device(request):
        rate(request,'material-handoff',240)
        if request.headers.get('origin') not in (None,config['origin']):
            raise HTTPException(403,'origin_rejected')
        header=request.headers.get('authorization','')
        value=hashlib.sha256(header[7:].encode()).hexdigest() if header.startswith('Bearer ') and header[7:] else ''
        for identity,digest in hashes.items():
            if secrets.compare_digest(value,digest):
                return identity
        raise HTTPException(401,'handoff_device_auth_required')

    def upload_fence(request):
        value=request.headers.get('x-handoff-epoch','')
        if not value.isascii() or not value.isdecimal() or len(value)>15:
            raise HTTPException(400,'invalid_epoch')
        return {'generation':request.headers.get('x-handoff-generation'),
                'epoch':int(value),'session_id':request.headers.get('x-handoff-session')}

    @app.get(PREFIX+'/status')
    def status(request:Request):
        if request.headers.get('authorization'):
            identity=device(request)
        else:
            session(request)
            identity=None
        result=call(handoff.status)
        result['holder_execution_allowed']=result['execution_allowed']
        result['execution_allowed']=identity is not None and identity==result['holder'] and result['execution_allowed']
        result['caller_device']=identity
        return result

    @app.post(PREFIX+'/acquire')
    async def acquire(request:Request):
        identity=device(request)
        body=await bounded_json(request)
        if set(body)-{'request_id','generation','epoch'}:
            raise HTTPException(400,'unexpected_handoff_fields')
        return call(handoff.acquire,identity,body)

    def mutation(action):
        async def change(request:Request):
            identity=device(request)
            body=await bounded_json(request)
            if set(body)-{'request_id','generation','epoch','session_id','package_id'}:
                raise HTTPException(400,'unexpected_handoff_fields')
            return call(handoff.transition,identity,action,body)
        return change
    for action in ('activate','heartbeat','drain','release'):
        app.add_api_route(PREFIX+'/'+action,mutation(action),methods=['POST'])

    @app.post(PREFIX+'/force-takeover')
    async def force(request:Request):
        # A device token is never accepted as user confirmation.
        row=session(request)
        csrf(request,row)
        rate(request,'material-takeover',10)
        body=await bounded_json(request)
        if set(body)!={'request_id','generation','epoch','target_device','package_id','reason','confirmation','other_device_stopped'}:
            raise HTTPException(400,'unexpected_takeover_fields')
        return call(handoff.force,'user:'+str(row['user_id']),body)

    @app.put(PREFIX+'/packages/{package_id}')
    async def upload(package_id:str,request:Request):
        identity=device(request)
        call(identifier,package_id)
        fence=upload_fence(request)
        with handoff.db() as db:
            call(handoff.fence,db,identity,fence,('draining',))
        sha=request.headers.get('x-package-sha256','')
        length=request.headers.get('x-package-bytes','')
        if not SHA.fullmatch(sha) or not length.isascii() or not length.isdecimal() or len(length)>12:
            raise HTTPException(400,'package_hash_and_size_required')
        size=int(length)
        if not 1<=size<=handoff.max_package_bytes:
            raise HTTPException(413,'package_size_limit')
        declared=request.headers.get('content-length')
        if declared is not None and declared!=str(size):
            raise HTTPException(400,'package_content_length_mismatch')
        # Each attempt uses a fresh object; no overwrite of published package bytes.
        objects=handoff.root/'objects'
        objects.mkdir(exist_ok=True)
        path=objects/(package_id+'-'+secrets.token_hex(12)+'.zip')
        cached=call(handoff.reserve_upload,identity,fence,package_id,sha,size,path)
        if cached:
            return cached
        received=0
        digest=hashlib.sha256()
        # Failure retains an unreferenced object for explicit audited maintenance;
        # it can never be current or downloaded. No automatic deletion here.
        with path.open('xb') as stream:
            async for part in request.stream():
                received+=len(part)
                if received>size:
                    raise HTTPException(413,'package_stream_size_limit')
                digest.update(part)
                stream.write(part)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name=='posix':
            # Persist new directory entries before publishing their DB metadata.
            for directory in (objects,handoff.root):
                fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        if received!=size or digest.hexdigest()!=sha:
            raise HTTPException(400,'package_stream_hash_or_size_mismatch')
        return call(handoff.register_upload,identity,fence,package_id,sha,size,path)

    @app.post(PREFIX+'/packages/{package_id}/commit')
    async def commit(package_id:str,request:Request):
        identity=device(request)
        body=await bounded_json(request)
        if set(body)!={'generation','epoch','session_id'}:
            raise HTTPException(400,'unexpected_commit_fields')
        row=call(handoff.uploaded,identity,body,package_id)
        path=handoff.root/row['path']
        try:
            summary=await run_in_threadpool(validate_package,path,row)
        except HandoffError as error:
            reject(error)
        # Recheck epoch/holder/lease after potentially lengthy archive hashing.
        return call(handoff.commit,identity,body,package_id,summary)

    @app.get(PREFIX+'/packages/{package_id}')
    def download(package_id:str,request:Request):
        device(request)
        path,row=call(handoff.download,package_id)
        return FileResponse(path,media_type='application/zip',filename=package_id+'.zip',
                            headers={'X-Package-SHA256':row['sha256'],'X-Package-Bytes':str(row['bytes'])})

    @app.get('/material-handoff')
    def page(request:Request):
        session(request)
        return HTMLResponse(Path(__file__).with_name('material_handoff.html').read_text(encoding='utf-8'))

    @app.get('/material-handoff.js')
    def script(request:Request):
        session(request)
        return Response(Path(__file__).with_name('material_handoff.js').read_bytes(),media_type='application/javascript')
