"""Authenticated backup APIs; no home commands or plaintext/key endpoints."""
import hashlib
import json
from fastapi import HTTPException,Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from cloud.backups import BackupError

def mount_backups(app,vault,agent,session,csrf,bounded_json):
    def reject(error):raise HTTPException(error.status,error.code) from None
    @app.get('/console/backups')
    def catalog(request:Request):
        session(request);return vault.catalog()
    @app.post('/console/backups/request')
    def request_backup(request:Request):
        row=session(request);csrf(request,row)
        return {'requestId':vault.request(),'state':'queued'}
    @app.post('/console/backups/{package_id}/verify')
    def verify(package_id:str,request:Request):
        row=session(request);csrf(request,row)
        try:return vault.verify(package_id)
        except BackupError as error:reject(error)
    @app.get('/console/backups/{package_id}/{name}')
    def download(package_id:str,name:str,request:Request):
        session(request)
        try:source,part=vault.open_download(package_id,name)
        except BackupError as error:reject(error)
        def blocks():
            try:
                while block:=source.read(1024*1024):yield block
            finally:source.close()
        return StreamingResponse(blocks(),media_type='application/pkcs7-mime',
            headers={'Content-Length':str(part['bytes']),'X-Content-SHA256':part['digest'],
                     'Content-Disposition':'attachment; filename="'+name+'"'},background=BackgroundTask(source.close))
    @app.post('/agent/backups/recipient')
    async def recipient(request:Request):
        agent(request);data=await bounded_json(request)
        try:return await run_in_threadpool(vault.set_recipient,data.get('certificate'))
        except BackupError as error:reject(error)
    @app.post('/agent/backups/reserve')
    async def reserve(request:Request):
        agent(request);data=await bounded_json(request)
        try:return await run_in_threadpool(vault.reserve,data)
        except BackupError as error:reject(error)
    @app.put('/agent/backups/{package_id}/{name}')
    async def put_part(package_id:str,name:str,request:Request):
        agent(request)
        try:length=int(request.headers.get('content-length',''))
        except ValueError:raise HTTPException(411,'backup_length_required') from None
        try:upload=await run_in_threadpool(vault.begin_part,package_id,name,length)
        except BackupError as error:reject(error)
        checksum=hashlib.sha256();received=0
        try:
            async for block in request.stream():
                received+=len(block)
                if received>length:raise BackupError('backup_length_mismatch',413)
                checksum.update(block)
                if not upload['stored']:upload['handle'].write(block)
            if received!=upload['bytes'] or checksum.hexdigest()!=upload['digest']:raise BackupError('backup_digest_or_length_mismatch')
            await run_in_threadpool(vault.finish_part,package_id,name,upload,received,checksum.hexdigest())
        except BaseException as error:
            await run_in_threadpool(vault.abort_part,package_id,name,upload)
            if isinstance(error,BackupError):reject(error)
            raise
        return {'stored':True,'sha256':checksum.hexdigest()}
    @app.post('/agent/backups/{package_id}/publish')
    async def publish(package_id:str,request:Request):
        agent(request);data=await bounded_json(request)
        try:result=await run_in_threadpool(vault.publish,package_id)
        except BackupError as error:reject(error)
        vault.complete_request(data.get('requestId'))
        return result
