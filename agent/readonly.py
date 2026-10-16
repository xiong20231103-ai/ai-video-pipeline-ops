"""M1a read-only bridge. No command execution, process control or cleanup exists."""
from contextlib import contextmanager
from datetime import datetime,timedelta
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contracts.cache import cache_key

class Ledger:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS versions(target TEXT PRIMARY KEY,version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(target TEXT PRIMARY KEY,payload TEXT NOT NULL,wall REAL NOT NULL,monotonic REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(target TEXT PRIMARY KEY,body TEXT NOT NULL,etag TEXT NOT NULL,scanned TEXT NOT NULL);
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
    def cloud(self,path,data=None):
        headers={'Authorization':'Bearer '+self.token}
        if data is not None: headers['Content-Type']='application/json'
        request=urllib.request.Request(self.origin+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with urllib.request.urlopen(request,timeout=10) as response: return json.load(response)
    def home(self,target,port=8765,conditional=True):
        cache_key('GET',target)
        old=self.ledger.source(target); headers={}
        if conditional and old and old['etag']: headers['If-None-Match']=old['etag']
        request=urllib.request.Request('http://127.0.0.1:'+str(port)+target,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=15) as response:
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024: raise ValueError('Source response exceeded limit')
                return response.status,json.loads(raw),response.headers.get('ETag','')
        except urllib.error.HTTPError as exc:
            if exc.code==304 and old: return 304,json.loads(old['body']),old['etag']
            raise
    def collect(self,target,conditional=True):
        with self.home_lock:
            status,body,etag=self.home(target,conditional=conditional)
            if target=='/api/health':
                _,receiver,_=self.home(target,8766,False)
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
    def heartbeat_loop(self):
        while not self.stop.is_set():
            try: self.cloud('/agent/heartbeat',{'engineState':self.engine_state})
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
                    try: self.collect(payload['target'],conditional=False)
                    except (OSError,ValueError): pass
                self.stop.wait(delay); delay=min(60,delay*2)
            except (OSError,ValueError):
                self.stop.wait(delay); delay=min(60,delay*2)
    def demand_loop(self):
        delay=2
        while not self.stop.is_set():
            try:
                requests=self.cloud('/agent/fetch-requests').get('items',[])
                for item in requests: self.collect(item['target'])
                delay=2
            except (OSError,ValueError,KeyError): delay=min(60,delay*2)
            self.stop.wait(delay)
    def collection_loop(self):
        periods={'/api/dashboard/summary':5,'/api/health':30,'/api/dashboard':60,'/api/task-boxes/current':60,'/api/controls/tasks':60,'/api/controls/templates':60,'/api/control-commands/current':60,'/api/controls/continue-current/status':60,'/api/safety':60,'/api/project-gaps':60,'/api/subtitle-verification/current':60}
        schedule={target:0.0 for target in periods}; date_marker=''
        while not self.stop.is_set():
            now=datetime.now().astimezone()
            if date_marker!=now.date().isoformat():
                for target in list(periods):
                    if '?date=' in target: periods.pop(target); schedule.pop(target,None)
                for offset in range(14):
                    date=now-timedelta(days=offset); label=str(date.month)+'.'+str(date.day)
                    for prefix in ['/api/pipeline','/api/task-boxes/history','/api/dashboard']:
                        target=prefix+'?date='+label; periods[target]=600; schedule[target]=time.monotonic()+offset*3
                date_marker=now.date().isoformat()
            due=[target for target in periods if schedule[target]<=time.monotonic()]
            if not due: self.stop.wait(0.5); continue
            target=min(due,key=lambda key:schedule[key])
            try: self.collect(target)
            except (OSError,ValueError): self.engine_state='unavailable'
            schedule[target]=time.monotonic()+periods[target]
    def run(self):
        with SingleInstance(self.state_dir/'agent.lock'):
            def supervise(method):
                try: method()
                except Exception:
                    self.worker_failed=True; self.engine_state='unavailable'; self.stop.set()
            threads=[threading.Thread(target=supervise,args=(method,),daemon=True) for method in [self.heartbeat_loop,self.collection_loop,self.upload_loop,self.demand_loop]]
            for thread in threads: thread.start()
            try:
                while not self.stop.wait(1): pass
            except KeyboardInterrupt: self.stop.set()
            for thread in threads: thread.join(timeout=20)
            if self.worker_failed: raise RuntimeError('Agent worker failed; no home command was retried')

def main():
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'OpsAgent'
    config=json.loads((state/'config.json').read_text(encoding='utf-8'))
    ReadOnlyAgent(config['cloud_origin'],config['agent_token'],state).run()

if __name__=='__main__': main()
