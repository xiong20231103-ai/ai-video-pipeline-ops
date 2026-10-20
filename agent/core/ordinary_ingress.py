"""Optional wrapper for the unchanged legacy app; never imports it itself."""
import ipaddress
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from .ordinary import OrdinaryCommands
from .ordinary_fence import FenceRejected
CAPABILITY='/api/migration/r3/capabilities'
SHARED_LEGACY_WRITES=frozenset({
    '/api/controls/capcut-drafts/cleanup',
    '/api/controls/audio-files/recycle',
    '/api/controls/production-files/recycle',
    '/api/controls/cloud-cleanup/execute',
    '/api/controls/testing/reset',
})
def trusted(scope):
    host=(scope.get('client') or ('',0))[0]
    if host in {'127.0.0.1','::1'}:return True
    try:
        ip=ipaddress.ip_address(host)
        return ip in ipaddress.ip_network('100.64.0.0/10') or ip in ipaddress.ip_network('fd7a:115c:a1e0::/48')
    except ValueError:return False
class FencedDashboard:
    def __init__(self,application,fence):self.application=application;self.fence=fence
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.application(scope,receive,send)
        path=scope['path']
        if path==CAPABILITY and scope['method']=='GET':
            if not trusted(scope):return await JSONResponse({'detail':'control_network_required'},status_code=403)(scope,receive,send)
            try:state=await run_in_threadpool(self.fence.status)
            except FenceRejected:return await JSONResponse({'detail':'r3_fence_unavailable'},status_code=503)(scope,receive,send)
            return await JSONResponse({'protocol':1,'fenceId':state['fenceId'],'owner':state['owner'],'legacyWritesBlocked':state['owner']=='candidate'})(scope,receive,send)
        ordinary=OrdinaryCommands.supports(path)
        if scope['method']!='POST' or not (ordinary or path in SHARED_LEGACY_WRITES):return await self.application(scope,receive,send)
        guard=self.fence.guard('legacy') if ordinary else self.fence.shared_write()
        try:await run_in_threadpool(guard.__enter__)
        except FenceRejected as error:
            code=409 if str(error)=='r3_owner_mismatch' else 503
            return await JSONResponse({'detail':'ordinary_commands_owned_by_agent' if code==409 else 'ordinary_writer_unavailable'},status_code=code)(scope,receive,send)
        try:return await self.application(scope,receive,send)
        finally:await run_in_threadpool(guard.__exit__,None,None,None)
