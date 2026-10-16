"""M1a authenticated read-only cache. No home write-command route exists."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError,InvalidHashError
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import HTMLResponse,JSONResponse,RedirectResponse,Response
from fastapi.staticfiles import StaticFiles
from contracts.cache import cache_key
from cloud.store import Store

HASHER=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1)
COOKIE='ops_console_session'
MAX_BODY=8*1024*1024

async def bounded_json(request):
    raw=bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw)>MAX_BODY: raise HTTPException(413,'request_too_large')
    try:
        value=json.loads(raw)
        if not isinstance(value,dict): raise ValueError()
        return value
    except (ValueError,UnicodeError): raise HTTPException(400,'invalid_json_object') from None

def verify(encoded,value):
    try: return HASHER.verify(encoded,value)
    except (VerificationError,InvalidHashError,TypeError): return False

def create_app(config=None,store=None,static_root=None):
    if config is None:
        path=Path(os.environ.get('OPS_CONSOLE_CONFIG','/etc/ops-console/config.json'))
        config=json.loads(path.read_text(encoding='utf-8'))
    if not config.get('origin','').startswith('https://') or len(config.get('agent_token_sha256',''))!=64 or not config.get('invite_hash'):
        raise RuntimeError('Console setup incomplete; use the local setup command without sharing credentials')
    store=store or Store(Path(config.get('state_dir','/var/lib/ops-console'))/'console.db')
    static_root=Path(static_root or Path(__file__).parents[1]/'static')
    application=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
    application.state.store=store
    def session(request):
        row=store.session(request.cookies.get(COOKIE,''))
        if not row: raise HTTPException(401,'login_required')
        return row
    def origin(request):
        if request.headers.get('origin')!=config['origin']: raise HTTPException(403,'origin_rejected')
    def csrf(request,row):
        origin(request)
        if not secrets.compare_digest(request.headers.get('x-csrf-token',''),row['csrf']): raise HTTPException(403,'csrf_rejected')
    def agent(request):
        token=request.headers.get('authorization','')
        digest=hashlib.sha256(token[7:].encode()).hexdigest() if token.startswith('Bearer ') else ''
        if not secrets.compare_digest(digest,config['agent_token_sha256']): raise HTTPException(401,'agent_auth_required')
    def rate(request,kind,maximum):
        if store.limited(kind+':'+str(request.client.host if request.client else 'local'),maximum): raise HTTPException(429,'rate_limited')
    @application.middleware('http')
    async def security(request,call_next):
        if request.method=='POST' and request.headers.get('content-length','').isdigit() and int(request.headers['content-length'])>MAX_BODY:
            return JSONResponse({'detail':'request_too_large'},status_code=413)
        if request.url.path.startswith('/static/') and not store.session(request.cookies.get(COOKIE,'')):
            return JSONResponse({'detail':'login_required'},status_code=401)
        result=await call_next(request)
        result.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
                               'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"})
        return result
    @application.exception_handler(Exception)
    async def error_handler(request,exc):
        return JSONResponse({'detail':'internal_error'},status_code=500)
    application.mount('/static',StaticFiles(directory=static_root),name='static')
    @application.get('/login')
    def login_page():
        return HTMLResponse((Path(__file__).parent/'login.html').read_text(encoding='utf-8'))
    @application.get('/login.js')
    def login_script():
        return Response((Path(__file__).parent/'login.js').read_bytes(),media_type='application/javascript')
    @application.get('/')
    def index(request:Request):
        if not store.session(request.cookies.get(COOKIE,'')): return RedirectResponse('/login',status_code=303)
        page=(static_root/'index.html').read_text(encoding='utf-8')
        # Insert before app.js executes, while leaving the home static files intact.
        page=page.replace('<head>','<head><script src="/cloud-readonly.js"></script>',1)
        return HTMLResponse(page)
    @application.get('/cloud-readonly.js')
    def readonly_script(request:Request):
        session(request)
        return Response((Path(__file__).parent/'readonly.js').read_bytes(),media_type='application/javascript')
    @application.get('/auth/options')
    def options(): return {'registrationOpen':store.user_count()<int(config.get('max_accounts',2))}
    @application.post('/auth/register')
    async def register(request:Request):
        origin(request); rate(request,'register',5); data=await bounded_json(request)
        name=data.get('username'); password=data.get('password'); invitation=data.get('invite')
        if not isinstance(name,str) or not 1<=len(name)<=64 or not isinstance(password,str) or not 12<=len(password)<=256 or not isinstance(invitation,str) or len(invitation)>256:
            raise HTTPException(400,'invalid_registration')
        if not verify(config['invite_hash'],invitation): raise HTTPException(403,'registration_rejected')
        try: store.register(name,HASHER.hash(password),int(config.get('max_accounts',2)))
        except ValueError: raise HTTPException(409,'registration_closed_or_unavailable') from None
        return {'registered':True}
    @application.post('/auth/login')
    async def login(request:Request):
        origin(request); rate(request,'login',10); data=await bounded_json(request)
        name=data.get('username'); password=data.get('password')
        if not isinstance(name,str) or len(name)>64 or not isinstance(password,str) or len(password)>256: raise HTTPException(400,'invalid_login')
        user=store.user(name)
        # Unknown users still perform a password verification to limit enumeration.
        valid=verify(user['password_hash'] if user else config['invite_hash'],password)
        if not user or not valid: raise HTTPException(401,'invalid_login')
        token,_=store.new_session(user['id']); result=JSONResponse({'loggedIn':True})
        result.set_cookie(COOKIE,token,max_age=30*86400,httponly=True,secure=True,samesite='lax',path='/')
        return result
    @application.get('/auth/session')
    def current_session(request:Request):
        row=session(request); return {'username':row['name'],'csrf':row['csrf']}
    @application.post('/auth/logout')
    def logout(request:Request):
        row=session(request); csrf(request,row); store.revoke(request.cookies.get(COOKIE,''))
        result=JSONResponse({'loggedOut':True}); result.delete_cookie(COOKIE,path='/'); return result
    @application.post('/auth/password')
    async def password_change(request:Request):
        row=session(request); csrf(request,row); rate(request,'password',5); data=await bounded_json(request)
        user=store.user(row['name']); new=data.get('newPassword'); old=data.get('oldPassword')
        if not isinstance(old,str) or len(old)>256 or not isinstance(new,str) or not 12<=len(new)<=256 or not verify(user['password_hash'],old): raise HTTPException(400,'password_change_rejected')
        store.change_password(user['id'],HASHER.hash(new)); result=JSONResponse({'changed':True,'loginRequired':True}); result.delete_cookie(COOKIE,path='/'); return result
    @application.get('/console/status')
    def console_status(request:Request): session(request); return store.health()
    @application.get('/ready')
    def ready(request:Request):
        if not request.client or request.client.host not in {'127.0.0.1','::1'} or request.headers.get('host') not in {'127.0.0.1:8000','localhost:8000'}:
            raise HTTPException(403,'local_probe_only')
        return {'ready':True,'mode':'read-only','schema':1}
    @application.post('/agent/heartbeat')
    async def heartbeat(request:Request):
        agent(request); data=await bounded_json(request); state=data.get('engineState','unknown')
        if state not in {'healthy','unavailable','busy','unknown'}: raise HTTPException(400,'invalid_engine_state')
        store.heartbeat(state); return {'received':True}
    @application.get('/agent/fetch-requests')
    def fetch_requests(request:Request): agent(request); return {'items':store.claim_reads()}
    @application.post('/agent/push')
    async def push(request:Request):
        agent(request); data=await bounded_json(request)
        try:
            if not isinstance(data.get('target'),str) or not isinstance(data.get('sourceHealth',{}),dict): raise ValueError()
            return {'result':store.push(data)}
        except (KeyError,ValueError,TypeError): raise HTTPException(400,'invalid_cache_submission') from None
    def cached(request,target):
        try: key=cache_key('GET',target)
        except (ValueError,UnicodeError): raise HTTPException(404,'cache_route_not_available') from None
        row=store.response(key)
        if not row:
            try: request_id=store.enqueue_read(key)
            except ValueError: raise HTTPException(503,'fetch_queue_full') from None
            return JSONResponse({'cloudPending':True,'requestId':request_id,'state':'fetching'},status_code=202,headers={'Retry-After':'2'})
        age=store.clock()-row['last_success']
        if age<0: age=1000000000  # Future persisted clocks are not freshness proof.
        if age>60:
            try: store.enqueue_read(key)
            except ValueError: pass
        tag='W/"'+hashlib.sha256(row['body'].encode()).hexdigest()+'"'
        headers={'ETag':tag,'X-Cache-Version':str(row['version']),'X-Cache-Age-Seconds':str(int(age)),
                 'X-Source-Scanned-At':row['source_scanned_at'],'X-Source-Health':row['source_health'].encode('ascii','backslashreplace').decode(),
                 'X-Last-Success-At':str(row['last_success']),'X-Last-Changed-At':str(row['last_changed'])}
        if request.headers.get('if-none-match')==tag: return Response(status_code=304,headers=headers)
        return Response(row['body'],status_code=row['status'],media_type='application/json',headers=headers)
    @application.get('/api/health')
    def submitter_health(request:Request):
        rate(request,'public-health',300)
        row=store.response(cache_key('GET','/api/health'))
        if not row or store.clock()-row['last_success']>60:
            try: store.enqueue_read(cache_key('GET','/api/health'))
            except ValueError: pass
            return JSONResponse({'ok':False,'code':'home_health_unavailable'},status_code=503)
        data=json.loads(row['body'])
        if not isinstance(data,dict) or not all(key in data for key in ['formalBatchTotal','projectTotals','contractVersion']):
            return JSONResponse({'ok':False,'code':'receiver_contract_unavailable'},status_code=503)
        return cached(request,'/api/health')
    @application.get('/api/{rest:path}')
    def reads(rest:str,request:Request):
        session(request); rate(request,'reads',600)
        return cached(request,request.url.path+('?' + request.url.query if request.url.query else ''))
    @application.post('/api/{rest:path}')
    def no_writes(rest:str,request:Request):
        row=session(request); csrf(request,row)
        raise HTTPException(403,'read_only_milestone; commands_not_enabled')
    return application
