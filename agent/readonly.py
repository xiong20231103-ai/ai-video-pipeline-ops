"""M1a read-only bridge. No command execution, process control or cleanup exists."""
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contracts.cache import cache_key,endpoint
from agent.polling import PollSchedule
from agent.lifecycle import Lifecycle

HOME_HOST='100.92.17.9'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,*args,**kwargs):
        return None

class Ledger:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS versions(target TEXT PRIMARY KEY,version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(target TEXT PRIMARY KEY,payload TEXT NOT NULL,wall REAL NOT NULL,monotonic REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(target TEXT PRIMARY KEY,body TEXT NOT NULL,etag TEXT NOT NULL,scanned TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS request_stats(minute INTEGER NOT NULL,mode TEXT NOT NULL,target TEXT NOT NULL,port INTEGER NOT NULL,reason TEXT NOT NULL,count INTEGER NOT NULL,failures INTEGER NOT NULL,seconds REAL NOT NULL,PRIMARY KEY(minute,mode,target,port,reason));
            ''')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=10); db.row_factory=sqlite3.Row
        try: db.execute('BEGIN IMMEDIATE'); yield db; db.commit()
        except BaseException: db.rollback(); raise
        finally: db.close()
    def source(self,target):
        target=cache_key('GET',target)[4:]
        with self.db() as db:
            row=db.execute('SELECT * FROM sources WHERE target=?',(target,)).fetchone()
            return dict(row) if row else None
    def enqueue(self,target,status,body,etag='',source_health=None):
        target=cache_key('GET',target)[4:]
        with self.db() as db:
            old=db.execute('SELECT version FROM versions WHERE target=?',(target,)).fetchone()
            version=old['version']+1 if old else 1
            db.execute('INSERT OR REPLACE INTO versions VALUES(?,?)',(target,version))
            # Compaction must not discard an unsent base body behind a 304.
            if status==304 and db.execute('SELECT 1 FROM outbox WHERE target=?',(target,)).fetchone(): status=200
            scanned=str(body.get('updatedAt') or '') if isinstance(body,dict) else ''
            if status!=304: db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?)',(target,json.dumps(body),etag,scanned))
            payload={'target':target,'version':version,'status':status,'body':body,'etag':etag,'sourceScannedAt':scanned,'sourceHealth':source_health or {}}
            db.execute('INSERT OR REPLACE INTO outbox VALUES(?,?,?,?)',(target,json.dumps(payload),time.time(),time.monotonic()))
    def next(self):
        with self.db() as db: row=db.execute('SELECT * FROM outbox ORDER BY wall LIMIT 1').fetchone()
        if not row: return None
        payload=json.loads(row['payload'])
        wall_age=time.time()-row['wall']; mono_age=time.monotonic()-row['monotonic']
        payload['captureAgeSeconds']=min(1000000000,max(0,wall_age,mono_age) if wall_age>=0 or mono_age>=0 else 1000000000)
        return payload
    def acknowledge(self,target,version):
        target=cache_key('GET',target)[4:]
        with self.db() as db:
            row=db.execute('SELECT payload FROM outbox WHERE target=?',(target,)).fetchone()
            if row and json.loads(row['payload'])['version']==version: db.execute('DELETE FROM outbox WHERE target=?',(target,))
    def note_request(self,target,port,mode,reason,elapsed,failed):
        minute=int(time.time()//60)
        with self.db() as db:
            db.execute('INSERT INTO request_stats VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(minute,mode,target,port,reason) DO UPDATE SET count=count+1,failures=failures+excluded.failures,seconds=seconds+excluded.seconds',(minute,mode,target,port,reason,int(failed),elapsed))
            db.execute('DELETE FROM request_stats WHERE minute<?',(minute-2880,))

class SingleInstance:
    def __init__(self,path): self.path=Path(path); self.file=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.file=self.path.open('a+b'); self.file.seek(0)
        if self.path.stat().st_size==0: self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self.file.close(); self.file=None; raise RuntimeError('Another home agent is already running') from None
        return self
    def __exit__(self,*args):
        if self.file: self.file.close()

class ReadOnlyAgent:
    def __init__(self,origin,token,state_dir):
        parsed=urllib.parse.urlsplit(origin)
        if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.ts.net') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'','/'}:
            raise ValueError('Cloud origin must be the configured Tailnet HTTPS node')
        self.origin=origin.rstrip('/'); self.token=token
        self.state_dir=Path(state_dir); self.ledger=Ledger(self.state_dir/'agent.db')
        self.stop=threading.Event(); self.home_lock=threading.Lock(); self.engine_state='unknown'; self.worker_failed=False
        self.schedule=PollSchedule()
        self.lifecycle=Lifecycle(self.state_dir)
        self.authenticated=threading.Event()
        # The old summary ETag omits scan clocks and its 304 has no scan header.
        # Periodically read the existing response body, without adding a GET.
        self.full_read_at={}
        # No environment proxy and no redirected bearer token or off-host home GET.
        self.transport=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def cloud(self,path,data=None):
        if self.stop.is_set(): raise OSError('Agent stopping')
        headers={'Authorization':'Bearer '+self.token}
        if data is not None: headers['Content-Type']='application/json'
        request=urllib.request.Request(self.origin+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with self.transport.open(request,timeout=10) as response: return json.load(response)
    def home(self,target,port=8765,conditional=True,reason='periodic'):
        if self.stop.is_set(): raise OSError('Agent stopping')
        target=cache_key('GET',target)[4:]
        if port not in {8765,8766} or port==8766 and target!='/api/health': raise ValueError('Home port is outside the explicit read contract')
        old=self.ledger.source(target); headers={}
        identity=(port,target)
        last_full=self.full_read_at.get(identity)
        if conditional and old and old['etag'] and last_full is not None and 0<=time.monotonic()-last_full<60:
            headers['If-None-Match']=old['etag']
        request=urllib.request.Request('http://'+HOME_HOST+':'+str(port)+target,headers=headers,method='GET')
        timeout=endpoint('GET',urllib.parse.urlsplit(target).path)['timeoutSeconds']
        previous_engine=self.engine_state
        if timeout>=60: self.engine_state='busy'
        started=time.monotonic(); mode='active' if self.schedule.active() else 'idle'; failed=True
        try:
            with self.transport.open(request,timeout=timeout) as response:
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024: raise ValueError('Source response exceeded limit')
                body=json.loads(raw); failed=False
                if response.status==200: self.full_read_at[identity]=time.monotonic()
                return response.status,body,response.headers.get('ETag','')
        except urllib.error.HTTPError as exc:
            if exc.code==304 and old: failed=False; return 304,json.loads(old['body']),old['etag']
            raise
        finally:
            if timeout>=60 and self.engine_state=='busy': self.engine_state=previous_engine
            self.ledger.note_request(target,port,mode,reason,time.monotonic()-started,failed)
    def collect(self,target,conditional=True,reason='periodic'):
        target=cache_key('GET',target)[4:]
        with self.home_lock:
            if self.stop.is_set(): return
            if conditional and self.schedule.recent(target): return
            status,body,etag=self.home(target,conditional=conditional,reason=reason)
            if target=='/api/health':
                _,receiver,_=self.home(target,8766,False,reason)
                if not isinstance(body,dict) or not isinstance(receiver,dict): raise ValueError('Invalid health contracts')
                body={**body,**receiver,'collectorRunning':body.get('collectorRunning',False),'dashboardUpdatedAt':body.get('updatedAt','')}
                status=200
                self.engine_state='healthy' if body.get('ok') and body.get('collectorRunning') else 'unavailable'
            scan_age=None
            if isinstance(body,dict) and body.get('updatedAt'):
                try:
                    scanned=datetime.fromisoformat(str(body['updatedAt']).replace('Z','+00:00'))
                    scan_age=time.time()-scanned.timestamp()
                    if scan_age<0: scan_age=None
                except (ValueError,TypeError,OverflowError): pass
            self.ledger.enqueue(target,status,body,etag,{'engineState':self.engine_state,'scanAgeSeconds':scan_age})
            self.schedule.completed(target)
    def heartbeat_loop(self):
        while not self.stop.is_set():
            try:
                self.schedule.update_viewer(self.cloud('/agent/heartbeat',{'engineState':self.engine_state}))
                self.authenticated.set()
            except urllib.error.HTTPError as exc:
                if exc.code in {401,403}: self.authenticated.clear()
            except (OSError,ValueError): pass
            self.stop.wait(5)
    def upload_loop(self):
        delay=1
        while not self.stop.is_set():
            payload=self.ledger.next()
            if not payload: self.stop.wait(1); continue
            try:
                result=self.cloud('/agent/push',payload)
                if result.get('result') not in {'stored','old_version_ignored'}: raise ValueError('Invalid cache acknowledgement')
                self.ledger.acknowledge(payload['target'],payload['version']); delay=1
            except urllib.error.HTTPError as exc:
                if exc.code==400 and payload['status']==304:
                    # A restored cloud DB may lack the cached base. Re-read, never invent it.
                    try: self.collect(payload['target'],conditional=False,reason='cache-recovery')
                    except (OSError,ValueError): pass
                self.stop.wait(delay); delay=min(60,delay*2)
            except (OSError,ValueError):
                self.stop.wait(delay); delay=min(60,delay*2)
    def demand_loop(self):
        delay=2
        while not self.stop.is_set():
            try:
                result=self.cloud('/agent/fetch-requests'); self.schedule.update_viewer(result)
                self.authenticated.set()
                for item in result.get('items',[]): self.collect(item['target'],reason='on-demand')
                delay=2
            except urllib.error.HTTPError as exc:
                if exc.code in {401,403}: self.authenticated.clear()
                delay=min(60,delay*2)
            except (OSError,ValueError,KeyError): delay=min(60,delay*2)
            self.stop.wait(delay)
    def collection_loop(self):
        while not self.stop.is_set():
            if not self.authenticated.is_set(): self.stop.wait(1); continue
            target=self.schedule.next(datetime.now().astimezone().date())
            if target is None: self.stop.wait(0.5); continue
            try: self.collect(target)
            except (OSError,ValueError): self.engine_state='unavailable'
            self.schedule.completed(target)
    def run(self):
        with SingleInstance(self.state_dir/'agent.lock'):
            requested=self.lifecycle.stop_request()
            if requested:
                self.lifecycle.publish('stopped',requested)
                return
            self.lifecycle.publish('starting')
            def supervise(method):
                try: method()
                except Exception:
                    self.worker_failed=True; self.engine_state='unavailable'; self.stop.set()
            threads=[threading.Thread(target=supervise,args=(method,),daemon=True) for method in [self.heartbeat_loop,self.collection_loop,self.upload_loop,self.demand_loop]]
            for thread in threads: thread.start()
            requested=None;published=0
            try:
                while not self.stop.wait(0.25):
                    requested=self.lifecycle.stop_request()
                    if requested: self.stop.set();break
                    if time.monotonic()-published>=5:
                        self.lifecycle.publish('running');published=time.monotonic()
            except KeyboardInterrupt: self.stop.set()
            # M1a workers are GET-only daemons. Bound total drain time, not 20s
            # per worker; process exit closes outstanding read sockets. Future
            # write execution must add its own drain/unknown-result contract.
            deadline=time.monotonic()+2
            for thread in threads: thread.join(timeout=max(0,deadline-time.monotonic()))
            self.lifecycle.publish('failed' if self.worker_failed else 'stopped',requested,sum(thread.is_alive() for thread in threads))
            if self.worker_failed: raise RuntimeError('Agent worker failed; no home command was retried')

def main():
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'OpsAgent'
    lifecycle=Lifecycle(state)
    if lifecycle.stop_request():
        try:
            with SingleInstance(state/'agent.lock'): lifecycle.publish('stopped',lifecycle.stop_request())
        except RuntimeError: pass  # Another live instance owns its status/lock.
        return
    config=json.loads((state/'config.json').read_text(encoding='utf-8'))
    ReadOnlyAgent(config['cloud_origin'],config['agent_token'],state).run()

if __name__=='__main__': main()
