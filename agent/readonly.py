"""M1a read-only bridge. No command execution, process control or cleanup exists."""
from contextlib import contextmanager, nullcontext, closing
from datetime import datetime
import json
import http.client
import os
import queue
from pathlib import Path
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contracts.cache import cache_key,endpoint,semantic_hash
from agent.polling import PollSchedule
from agent.lifecycle import Lifecycle

HOME_HOST='100.92.17.9'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,*args,**kwargs):
        return None

class Ledger:
    """Validators and a bounded unsent outbox; response archives live only in cloud."""
    def __init__(self,path,max_outbox_bytes=48*1024*1024):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self.ready=threading.Event(); self.write_lock=threading.RLock(); self.max_outbox_bytes=max_outbox_bytes
        needs_vacuum=False
        with self.db(True) as db:
            needs_vacuum=db.execute('PRAGMA auto_vacuum').fetchone()[0]!=1
            db.executescript('''PRAGMA journal_mode=WAL;
            PRAGMA journal_size_limit=1048576;
            CREATE TABLE IF NOT EXISTS versions(target TEXT PRIMARY KEY,version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(target TEXT PRIMARY KEY,payload TEXT NOT NULL,wall REAL NOT NULL,monotonic REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS source_validators(target TEXT PRIMARY KEY,etag TEXT NOT NULL,semantic_hash TEXT NOT NULL,scanned TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox_sizes(target TEXT PRIMARY KEY,size INTEGER NOT NULL,priority INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS agent_counts(name TEXT PRIMARY KEY,value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS request_stats(minute INTEGER NOT NULL,mode TEXT NOT NULL,target TEXT NOT NULL,port INTEGER NOT NULL,reason TEXT NOT NULL,count INTEGER NOT NULL,failures INTEGER NOT NULL,seconds REAL NOT NULL,PRIMARY KEY(minute,mode,target,port,reason));
            ''')
            migrated=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sources'").fetchone() is not None
            if migrated:
                # One row at a time: do not load the old 33 MB archive into RAM.
                for row in db.execute('SELECT target,body,etag,scanned FROM sources'):
                    db.execute('INSERT OR REPLACE INTO source_validators VALUES(?,?,?,?)',(row['target'],row['etag'],semantic_hash(json.loads(row['body'])),row['scanned']))
                db.execute('DROP TABLE sources')
            db.execute('DELETE FROM outbox_sizes')
            db.execute('INSERT INTO outbox_sizes(target,size) SELECT target,length(CAST(payload AS BLOB)) FROM outbox')
            self._trim(db)
        # Reclaim discarded body pages once, before workers start. Old-version
        # rollback creates an empty legacy sources table and re-reads via GET.
        if migrated or needs_vacuum or self.path.stat().st_size>52*1024*1024:
            with closing(sqlite3.connect(self.path,timeout=10)) as db:
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)'); db.execute('PRAGMA auto_vacuum=FULL'); db.execute('VACUUM')
        self.pruned_at=0
    @contextmanager
    def db(self,write=False):
        # WAL readers must never acquire a reserved writer lock. Serialize own
        # writers before BEGIN; SQLite BUSY/LOCKED alone is retryable I/O.
        with self.write_lock if write else nullcontext():
            db=sqlite3.connect(self.path,timeout=2); db.row_factory=sqlite3.Row
            try:
                db.execute('PRAGMA journal_size_limit=1048576')
                if write: db.execute('BEGIN IMMEDIATE')
                else: db.execute('PRAGMA query_only=ON')
                yield db; db.commit()
            except sqlite3.OperationalError as error:
                db.rollback()
                if getattr(error,'sqlite_errorcode',0)&255 in {sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED}:
                    raise OSError('Local ledger temporarily busy') from None
                raise
            except BaseException: db.rollback(); raise
            finally: db.close()
    def _trim(self,db):
        total=db.execute('SELECT coalesce(sum(size),0) FROM outbox_sizes').fetchone()[0]
        for row in db.execute('SELECT o.target,s.size FROM outbox o JOIN outbox_sizes s USING(target) ORDER BY wall,o.target').fetchall():
            if total<=self.max_outbox_bytes: break
            db.execute('DELETE FROM outbox WHERE target=?',(row['target'],)); db.execute('DELETE FROM outbox_sizes WHERE target=?',(row['target'],)); total-=row['size']
            db.execute("INSERT INTO agent_counts VALUES('outboxDropped',1) ON CONFLICT(name) DO UPDATE SET value=value+1")
    def source(self,target):
        target=cache_key('GET',target)[4:]
        with self.db() as db:
            row=db.execute('SELECT * FROM source_validators WHERE target=?',(target,)).fetchone()
            return dict(row) if row else None
    def enqueue(self,target,status,body,etag='',source_health=None,priority=0):
        target=cache_key('GET',target)[4:]
        scanned=str(body.get('updatedAt') or '') if isinstance(body,dict) else ''
        digest=semantic_hash(body) if status!=304 else ''
        with self.db(True) as db:
            old=db.execute('SELECT version FROM versions WHERE target=?',(target,)).fetchone()
            version=old['version']+1 if old else 1
            db.execute('INSERT OR REPLACE INTO versions VALUES(?,?)',(target,version))
            if status==304:
                source=db.execute('SELECT * FROM source_validators WHERE target=?',(target,)).fetchone()
                if not source: raise ValueError('304 without validator')
                scanned=source['scanned']; digest=source['semantic_hash']
                pending=db.execute('SELECT payload FROM outbox WHERE target=?',(target,)).fetchone()
                # Preserve only an UNSENT body, never a second persistent copy.
                if pending:
                    previous=json.loads(pending['payload'])
                    if previous['status']==200: status=200; body=previous['body']
                if status==304: body=None
            else:
                db.execute('INSERT OR REPLACE INTO source_validators VALUES(?,?,?,?)',(target,etag,digest,scanned))
            payload={'target':target,'version':version,'status':status,'body':body,'etag':etag,'semanticHash':digest,'sourceScannedAt':scanned,'sourceHealth':source_health or {}}
            encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
            db.execute('INSERT OR REPLACE INTO outbox VALUES(?,?,?,?)',(target,encoded,time.time(),time.monotonic()))
            db.execute('INSERT OR REPLACE INTO outbox_sizes VALUES(?,?,?)',(target,len(encoded.encode()),priority))
            self._trim(db)
        self.ready.set()
    def next(self):
        with self.db() as db: row=db.execute('SELECT o.* FROM outbox o JOIN outbox_sizes s USING(target) ORDER BY s.priority DESC,o.wall LIMIT 1').fetchone()
        if not row: return None
        payload=json.loads(row['payload'])
        wall_age=time.time()-row['wall']; mono_age=time.monotonic()-row['monotonic']
        payload['captureAgeSeconds']=min(1000000000,max(0,wall_age,mono_age) if wall_age>=0 or mono_age>=0 else 1000000000)
        return payload
    def acknowledge(self,target,version):
        target=cache_key('GET',target)[4:]
        with self.db(True) as db:
            row=db.execute('SELECT payload FROM outbox WHERE target=?',(target,)).fetchone()
            if row and json.loads(row['payload'])['version']==version:
                db.execute('DELETE FROM outbox WHERE target=?',(target,)); db.execute('DELETE FROM outbox_sizes WHERE target=?',(target,))
    def note_request(self,target,port,mode,reason,elapsed,failed):
        minute=int(time.time()//60)
        with self.db(True) as db:
            db.execute('INSERT INTO request_stats VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(minute,mode,target,port,reason) DO UPDATE SET count=count+1,failures=failures+excluded.failures,seconds=seconds+excluded.seconds',(minute,mode,target,port,reason,int(failed),elapsed))
            if minute-self.pruned_at>=60:
                db.execute('DELETE FROM request_stats WHERE minute<?',(minute-2880,)); self.pruned_at=minute
    def storage(self):
        with self.db() as db:
            pending=db.execute('SELECT count(*),coalesce(sum(size),0) FROM outbox_sizes').fetchone()
            counts=dict(db.execute('SELECT name,value FROM agent_counts'))
        return {'pendingItems':pending[0],'outboxBytes':pending[1],'outboxLimitBytes':self.max_outbox_bytes,'outboxDropped':counts.get('outboxDropped',0),
                'databaseBytes':self.path.stat().st_size,'walBytes':Path(str(self.path)+'-wal').stat().st_size if Path(str(self.path)+'-wal').exists() else 0}

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
        self.state_dir=Path(state_dir); self._ledger=None; self.ledger_lock=threading.Lock()
        self.stop=threading.Event(); self.target_lock=threading.Lock(); self.inflight=set(); self.engine_state='unknown'; self.worker_failed=False
        self.schedule=PollSchedule()
        self.lifecycle=Lifecycle(self.state_dir)
        self.authenticated=threading.Event()
        self.demands=queue.PriorityQueue(maxsize=128); self.pending_demands=set(); self.prefetch_targets=[]; self.slow_demands=[]; self.force_reads=set(); self.paused_targets=set()
        # The old summary ETag omits scan clocks and its 304 has no scan header.
        # Periodically read the existing response body, without adding a GET.
        self.full_read_at={}
        # No environment proxy and no redirected bearer token or off-host home GET.
        self.transport=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    @property
    def ledger(self):
        with self.ledger_lock:
            if self._ledger is None: self._ledger=Ledger(self.state_dir/'agent.db')
            return self._ledger
    def cloud(self,path,data=None):
        if self.stop.is_set(): raise OSError('Agent stopping')
        headers={'Authorization':'Bearer '+self.token}
        if data is not None: headers['Content-Type']='application/json'
        request=urllib.request.Request(self.origin+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with self.transport.open(request,timeout=35 if path.startswith('/agent/fetch-requests?') else 10) as response: return json.load(response)
        except http.client.IncompleteRead: raise OSError('Incomplete cloud response') from None
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
            if exc.code==304 and old: failed=False; return 304,None,old['etag']
            raise
        except http.client.IncompleteRead: raise OSError('Incomplete home response') from None
        finally:
            if timeout>=60 and self.engine_state=='busy': self.engine_state=previous_engine
            self.ledger.note_request(target,port,mode,reason,time.monotonic()-started,failed)
    def collect(self,target,conditional=True,reason='periodic'):
        target=cache_key('GET',target)[4:]
        with self.target_lock:
            if target in self.inflight: return
            self.inflight.add(target)
        try:
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
            scan_stamp=(body.get('updatedAt') if isinstance(body,dict) else None) or ((self.ledger.source(target) or {}).get('scanned') if status==304 else None)
            if scan_stamp:
                try:
                    scanned=datetime.fromisoformat(str(scan_stamp).replace('Z','+00:00'))
                    scan_age=time.time()-scanned.timestamp()
                    if scan_age<0: scan_age=None
                except (ValueError,TypeError,OverflowError): pass
            self.ledger.enqueue(target,status,body,etag,{'engineState':self.engine_state,'scanAgeSeconds':scan_age},priority=10 if reason in {'on-demand','cache-recovery'} else 0)
            self.schedule.completed(target)
        finally:
            with self.target_lock: self.inflight.discard(target)
    def heartbeat_loop(self):
        while not self.stop.is_set():
            try:
                self.schedule.update_viewer(self.cloud('/agent/heartbeat',{'engineState':self.engine_state,'storage':self.ledger.storage()}))
                self.authenticated.set()
            except urllib.error.HTTPError as exc:
                if exc.code in {401,403}: self.authenticated.clear()
            except (OSError,ValueError): pass
            self.stop.wait(5)
    def upload_loop(self):
        delay=1
        while not self.stop.is_set():
            try:
                self.ledger.ready.clear()
                payload=self.ledger.next()
                if not payload: self.ledger.ready.wait(1); continue
                result=self.cloud('/agent/push',payload)
                if result.get('result') not in {'stored','old_version_ignored'}: raise ValueError('Invalid cache acknowledgement')
                self.ledger.acknowledge(payload['target'],payload['version']); delay=1
            except urllib.error.HTTPError as exc:
                if exc.code==400 and payload['status']==304:
                    # A restored cloud DB may lack the cached base. Re-read, never invent it.
                    try: self.queue_demand(payload['target'],force=True)
                    except (OSError,ValueError): pass
                self.stop.wait(delay); delay=min(60,delay*2)
            except (OSError,ValueError):
                self.stop.wait(delay); delay=min(60,delay*2)
    def demand_loop(self):
        delay=0
        while not self.stop.is_set():
            try:
                began=time.monotonic()
                result=self.cloud('/agent/fetch-requests?wait=25'); self.schedule.update_viewer(result)
                self.authenticated.set()
                with self.target_lock:
                    self.prefetch_targets=list(result.get('prefetchTargets',[]))[:10]
                    self.paused_targets={cache_key('GET',target)[4:] for target in result.get('pausedTargets',[])}
                for item in result.get('items',[]): self.queue_demand(item['target'])
                delay=0 if result.get('items') or time.monotonic()-began>=0.25 else 0.25
            except urllib.error.HTTPError as exc:
                if exc.code in {401,403}: self.authenticated.clear()
                delay=min(60,max(1,delay*2))
            except (OSError,ValueError,KeyError): delay=min(60,max(1,delay*2))
            self.stop.wait(delay)
    def queue_demand(self,target,force=False):
        target=cache_key('GET',target)[4:]
        with self.target_lock:
            if force: self.force_reads.add(target)
            if target in self.pending_demands: return
            if len(self.pending_demands)>=128: return
            self.pending_demands.add(target)
            if endpoint('GET',urllib.parse.urlsplit(target).path)['timeoutSeconds']>=60:
                self.slow_demands.append(target)
            else:
                batch=urllib.parse.parse_qs(urllib.parse.urlsplit(target).query).get('batchId')
                self.demands.put_nowait((0 if batch and target.startswith('/api/dashboard?') else 1,time.monotonic_ns(),target))
    def foreground_loop(self):
        while not self.stop.is_set():
            try: _,_,target=self.demands.get(timeout=0.2)
            except queue.Empty: continue
            try: self.collect(target,conditional=target not in self.force_reads,reason='cache-recovery' if target in self.force_reads else 'on-demand')
            except (OSError,ValueError): pass
            finally:
                with self.target_lock: self.pending_demands.discard(target); self.force_reads.discard(target)
                self.demands.task_done()
    def prefetch(self):
        if not self.schedule.active(): return None
        with self.target_lock:
            if self.pending_demands: return None
            while self.prefetch_targets:
                target=self.prefetch_targets.pop(0)
                if target not in self.inflight and not self.schedule.recent(target,60): return target
        return None
    def collection_loop(self):
        while not self.stop.is_set():
            if not self.authenticated.is_set(): self.stop.wait(1); continue
            target=self.schedule.next(datetime.now().astimezone().date()); reason='periodic'
            slow=False
            if target not in {'/api/dashboard/summary','/api/health','/api/dashboard'}:
                with self.target_lock:
                    if self.slow_demands: target=self.slow_demands.pop(0); reason='on-demand'; slow=True
                prefetched=None if slow else self.prefetch()
                if prefetched: target=prefetched; reason='prefetch'
            if target is None: self.stop.wait(0.2); continue
            if reason=='periodic' and target in self.paused_targets:
                self.schedule.completed(target); continue
            try: self.collect(target,conditional=target not in self.force_reads,reason=reason)
            except (OSError,ValueError): self.engine_state='unavailable'
            finally:
                if slow:
                    with self.target_lock: self.pending_demands.discard(target); self.force_reads.discard(target)
            self.schedule.completed(target)
    def run(self):
        with SingleInstance(self.state_dir/'agent.lock'):
            requested=self.lifecycle.stop_request()
            if requested:
                self.lifecycle.publish('stopped',requested)
                return
            self.ledger  # Migrate only after owning the single-instance lock.
            self.lifecycle.publish('starting')
            failure_lock=threading.Lock()
            def supervise(worker,method):
                try: method()
                except Exception as error:
                    try:
                        with failure_lock:
                            if not self.worker_failed:
                                self.worker_failed=True
                                try:self.lifecycle.record_worker_failure(worker,error)
                                except Exception:pass # Diagnostics failure must never print the original exception.
                    finally:self.engine_state='unavailable';self.stop.set()
            methods=(('heartbeat',self.heartbeat_loop),('collection',self.collection_loop),('upload',self.upload_loop),('demand',self.demand_loop),('foreground',self.foreground_loop))
            threads=[threading.Thread(target=supervise,args=(worker,method),daemon=True) for worker,method in methods]
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
