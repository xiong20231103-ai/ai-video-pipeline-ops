"""Transactional users/sessions, response metadata and bounded single-flight reads."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
from contracts.cache import cache_key,semantic_hash

class Store:
    def __init__(self,path,clock=None):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        epoch=time.time(); monotonic=time.monotonic()
        self.clock=clock or (lambda:epoch+time.monotonic()-monotonic)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS responses(key TEXT PRIMARY KEY,version INTEGER NOT NULL,status INTEGER NOT NULL,body TEXT NOT NULL,semantic_hash TEXT NOT NULL,last_success REAL NOT NULL,last_changed REAL NOT NULL,source_scanned_at TEXT NOT NULL,source_health TEXT NOT NULL,source_etag TEXT NOT NULL,last_received REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS fetches(key TEXT PRIMARY KEY,id TEXT UNIQUE NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,lease_until REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS heartbeats(agent_id TEXT PRIMARY KEY,received REAL NOT NULL,engine_state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS rate_limits(bucket TEXT PRIMARY KEY,window REAL NOT NULL,count INTEGER NOT NULL);
            ''')
    @contextmanager
    def db(self,write=False):
        db=sqlite3.connect(self.path,timeout=10); db.row_factory=sqlite3.Row
        try:
            if write: db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally: db.close()
    def limited(self,bucket,limit,seconds=60):
        now=self.clock()
        with self.db(True) as db:
            row=db.execute('SELECT * FROM rate_limits WHERE bucket=?',(bucket,)).fetchone()
            if not row or now-row['window']>=seconds:
                db.execute('INSERT OR REPLACE INTO rate_limits VALUES(?,?,1)',(bucket,now)); return False
            if row['count']>=limit: return True
            db.execute('UPDATE rate_limits SET count=count+1 WHERE bucket=?',(bucket,)); return False
    def register(self,name,password_hash,maximum):
        with self.db(True) as db:
            if db.execute('SELECT count(*) FROM users').fetchone()[0]>=maximum: raise ValueError('registration_closed')
            try: return db.execute('INSERT INTO users(name,password_hash) VALUES(?,?)',(name,password_hash)).lastrowid
            except sqlite3.IntegrityError: raise ValueError('username_unavailable') from None
    def user(self,name):
        with self.db() as db:
            row=db.execute('SELECT * FROM users WHERE name=?',(name,)).fetchone()
            return dict(row) if row else None
    def user_count(self):
        with self.db() as db: return db.execute('SELECT count(*) FROM users').fetchone()[0]
    def new_session(self,user_id):
        token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
        with self.db(True) as db:
            db.execute('DELETE FROM sessions WHERE expires<=?',(self.clock(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user_id,csrf,self.clock()+30*86400))
        return token,csrf
    def session(self,token):
        with self.db() as db:
            row=db.execute('SELECT s.*,u.name FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),self.clock())).fetchone()
            return dict(row) if row else None
    def revoke(self,token):
        with self.db(True) as db: db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def change_password(self,user_id,password_hash):
        with self.db(True) as db:
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash,user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
    def delete_user(self,name):
        with self.db(True) as db:
            row=db.execute('SELECT id FROM users WHERE name=?',(name,)).fetchone()
            if row:
                db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],)); db.execute('DELETE FROM users WHERE id=?',(row['id'],))
    def response(self,key):
        with self.db() as db:
            row=db.execute('SELECT * FROM responses WHERE key=?',(key,)).fetchone()
            return dict(row) if row else None
    def push(self,item):
        key=cache_key('GET',item['target']); version=item['version']; now=self.clock()
        if type(version) is not int or version<1: raise ValueError('invalid_version')
        capture_age=item.get('captureAgeSeconds',0)
        if type(capture_age) not in (int,float) or not 0<=capture_age<=1000000000: raise ValueError('invalid_capture_age')
        obtained=now-capture_age
        source_health=item.get('sourceHealth') or {}
        source_scan=str(item.get('sourceScannedAt') or '')
        source_etag=str(item.get('etag') or '')
        if len(json.dumps(source_health))>4096 or len(source_scan)>128 or len(source_etag)>256 or any(c in source_scan+source_etag for c in '\r\n'):
            raise ValueError('invalid_source_metadata')
        with self.db(True) as db:
            old=db.execute('SELECT * FROM responses WHERE key=?',(key,)).fetchone()
            if old and version<=old['version']: return 'old_version_ignored'
            status=item['status']
            if status==304:
                if not old: raise ValueError('304_without_body')
                body=old['body']; status=old['status']; content_hash=old['semantic_hash']; changed=old['last_changed']
                # 304 success never invents a later underlying source scan.
                source_scan=old['source_scanned_at']
            else:
                if type(status) is not int or not 200<=status<600: raise ValueError('invalid_source_status')
                body=json.dumps(item['body'],ensure_ascii=False,separators=(',',':'),allow_nan=False)
                content_hash=semantic_hash(item['body']); changed=old['last_changed'] if old and old['semantic_hash']==content_hash else obtained
            db.execute('INSERT OR REPLACE INTO responses VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,version,status,body,content_hash,obtained,changed,source_scan,json.dumps(source_health),source_etag,now))
            db.execute('DELETE FROM fetches WHERE key=?',(key,))
        return 'stored'
    def enqueue_read(self,key,maximum=128,ttl=45):
        now=self.clock()
        with self.db(True) as db:
            db.execute('DELETE FROM fetches WHERE expires<=?',(now,))
            row=db.execute('SELECT id FROM fetches WHERE key=?',(key,)).fetchone()
            if row: return row['id']
            if db.execute('SELECT count(*) FROM fetches').fetchone()[0]>=maximum: raise ValueError('fetch_queue_full')
            request_id=secrets.token_urlsafe(24)
            db.execute('INSERT INTO fetches(key,id,state,created,expires) VALUES(?,?,?,?,?)',(key,request_id,'queued',now,now+ttl))
            return request_id
    def claim_reads(self):
        now=self.clock()
        with self.db(True) as db:
            db.execute('DELETE FROM fetches WHERE expires<=?',(now,))
            row=db.execute("SELECT * FROM fetches WHERE state='queued' OR lease_until<=? ORDER BY created LIMIT 1",(now,)).fetchone()
            if not row: return []
            db.execute("UPDATE fetches SET state='leased',lease_until=? WHERE key=?",(now+30,row['key']))
            return [{'id':row['id'],'target':row['key'][4:],'expiresAt':row['expires']}]
    def heartbeat(self,engine_state):
        with self.db(True) as db: db.execute('INSERT OR REPLACE INTO heartbeats VALUES(?,?,?)',('home',self.clock(),engine_state))
    def health(self):
        with self.db() as db: row=db.execute('SELECT * FROM heartbeats WHERE agent_id=?',('home',)).fetchone()
        age=self.clock()-row['received'] if row else None
        if age is not None and age<0: age=None
        return {'agentOnline':age is not None and age<=45,'heartbeatAgeSeconds':age,'engineState':row['engine_state'] if row else 'unknown','canContinue':False,'canCleanup':False,'readOnly':True}
