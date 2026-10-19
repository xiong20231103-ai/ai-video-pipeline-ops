"""Durable serialized command queue. Sent/unknown work is never auto-reissued."""
import base64,hashlib,json,secrets,threading,time,uuid
from contracts.cache import cache_key
from contracts.commands import command,canonical,identity,MAX_REPLY,target_from_summary

class CommandError(ValueError):
    def __init__(self,code,status=409):self.code=code;self.status=status;super().__init__(code)

class CommandQueue:
    def __init__(self,store,enabled=False,h3=False,cleanup=False):
        self.store=store;self.enabled=enabled;self.h3=h3;self.cleanup=cleanup;self.changed=threading.Condition()
        with store.db(True) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS commands(
              id TEXT PRIMARY KEY,actor TEXT NOT NULL,request_id TEXT NOT NULL,target TEXT NOT NULL,body TEXT NOT NULL,digest TEXT NOT NULL,
              source TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,lease TEXT,lease_until REAL NOT NULL DEFAULT 0,
              ledger_id TEXT,result TEXT,result_digest TEXT,updated REAL NOT NULL,UNIQUE(actor,request_id));
              CREATE TABLE IF NOT EXISTS command_audit(id INTEGER PRIMARY KEY,at REAL NOT NULL,command_id TEXT NOT NULL,actor TEXT NOT NULL,event TEXT NOT NULL,note TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS command_executor(id INTEGER PRIMARY KEY CHECK(id=1),ledger_id TEXT,enabled INTEGER NOT NULL,last_seen REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS command_cancelled_requests(actor TEXT NOT NULL,request_id TEXT NOT NULL,at REAL NOT NULL,PRIMARY KEY(actor,request_id));
              CREATE TABLE IF NOT EXISTS cleanup_executor(id INTEGER PRIMARY KEY CHECK(id=1),protocol INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS command_gate(id INTEGER PRIMARY KEY CHECK(id=1),paused INTEGER NOT NULL);
              INSERT OR IGNORE INTO command_gate VALUES(1,0);
            ''')
    def audit(self,db,row,event,actor=None,note=''):
        db.execute('INSERT INTO command_audit(at,command_id,actor,event,note) VALUES(?,?,?,?,?)',(self.store.clock(),row['id'],actor or row['actor'],event,note))
    def wake(self):
        with self.changed:self.changed.notify_all()
    def advertise(self,value):
        value=value or {'enabled':False}
        if not isinstance(value,dict) or set(value)-{'enabled','ledgerId','protocol','cleanupProtocol'} or type(value.get('enabled')) is not bool:raise CommandError('invalid_executor_capability',400)
        enabled=value['enabled'];ledger=value.get('ledgerId')
        if 'cleanupProtocol' in value and type(value['cleanupProtocol']) is not int:raise CommandError('invalid_cleanup_capability',400)
        if enabled and (value.get('protocol')!=1 or not isinstance(ledger,str) or len(ledger)!=32 or any(c not in '0123456789abcdef' for c in ledger)):raise CommandError('invalid_executor_capability',400)
        with self.store.db(True) as db:
            db.execute('INSERT OR REPLACE INTO cleanup_executor VALUES(1,?)',(int(enabled and value.get('cleanupProtocol')==1),))
            old=db.execute('SELECT * FROM command_executor WHERE id=1').fetchone()
            if enabled and old and old['ledger_id'] and old['ledger_id']!=ledger:raise CommandError('executor_ledger_change_requires_manual_reconciliation')
            db.execute('INSERT OR REPLACE INTO command_executor VALUES(1,?,?,?)',(ledger if enabled else old['ledger_id'] if old else None,int(enabled),self.store.clock()))
        self.wake()
    def expire(self,db):
        now=self.store.clock()
        for row in db.execute("SELECT id,actor FROM commands WHERE state IN ('queued','leased') AND (expires<=? OR created>?)",(now,now)).fetchall():
            db.execute("UPDATE commands SET state='expired',updated=? WHERE id=?",(now,row['id']));self.audit(db,row,'expired_before_send')
        # Keep the last token until another claim replaces it, so a delayed
        # not-sent receipt can close its own expired pre-send lease safely.
        db.execute("UPDATE commands SET state='queued',lease_until=0 WHERE state='leased' AND lease_until<=?",(now,))
        for row in db.execute("SELECT id,actor FROM commands WHERE state='sent' AND updated<=? AND target NOT LIKE '/api/controls/cloud-cleanup/%'",(now-90,)).fetchall():
            db.execute("UPDATE commands SET state='unknown',updated=? WHERE id=?",(now,row['id']));self.audit(db,row,'result_timeout_unknown_no_retry')
        for row in db.execute("SELECT id,actor FROM commands WHERE state='sent' AND target LIKE '/api/controls/cloud-cleanup/%' AND updated<=?",(now-960,)).fetchall():
            db.execute("UPDATE commands SET state='unknown',updated=? WHERE id=?",(now,row['id']));self.audit(db,row,'cleanup_result_timeout_unknown_no_retry')
    def cleanup_guard(self,body=None):
        if not self.cleanup:raise CommandError('cleanup_milestone_disabled')
        if not self.ready():raise CommandError('home_offline_or_busy')
        with self.store.db() as db:
            cap=db.execute('SELECT protocol FROM cleanup_executor WHERE id=1').fetchone()
            if not cap or cap['protocol']!=1:raise CommandError('cleanup_agent_not_deployed')
            if db.execute("SELECT 1 FROM commands WHERE state='unknown' LIMIT 1").fetchone():raise CommandError('cleanup_unknown_requires_reconciliation')
        now=self.store.clock()
        for target in ('/api/dashboard/summary','/api/controls/cloud-cleanup/capabilities'):
            row=self.store.response(cache_key('GET',target))
            if not row or row['status']!=200 or not 0<=now-row['last_success']<=60:raise CommandError('cleanup_capability_or_summary_stale')
            value=json.loads(row['body'])
            if target.endswith('/capabilities'):
                if not isinstance(value,dict) or type(value.get('protocol')) is not int or value.get('protocol')!=1 or type(value.get('retentionDays')) is not int or value.get('retentionDays')!=3 or value.get('forbiddenDraftRootProtected') is not True:raise CommandError('cleanup_dashboard_not_deployed')
            else:
                source=json.loads(row['source_health']);age=source.get('scanAgeSeconds') if isinstance(source,dict) else None
                if type(age) not in (int,float) or not 0<=age+now-row['last_success']<=60:raise CommandError('cleanup_scan_stale')
        if body and 'expiresAt' in body and not now<body['expiresAt']:raise CommandError('cleanup_preview_expired')
    def cleanup_owner(self,actor,body):
        # The opaque home ticket is never sufficient by itself: bind its exact
        # preview to the authenticated account and the original selected IDs.
        with self.store.db() as db:
            rows=db.execute("SELECT body,result,updated FROM commands WHERE actor=? AND target='/api/controls/cloud-cleanup/preview' AND state='completed' ORDER BY created DESC LIMIT 100",(actor,)).fetchall()
        for row in rows:
            result=json.loads(row['result']) if row['result'] else None
            if not result or result.get('kind')!='http' or result.get('httpStatus')!=200:continue
            try:preview=json.loads(base64.b64decode(result['bodyBase64'],validate=True))
            except (ValueError,KeyError,TypeError):continue
            original=json.loads(row['body'])
            if not isinstance(preview,dict):continue
            if not 0<=self.store.clock()-row['updated']<=120:continue
            if all(preview.get(k)==body.get(k) for k in ('ticket','snapshotToken','expiresAt')) and all(original.get(k,False)==body.get(k,False) for k in ('kind','ids','includeUnknown')):return
        raise CommandError('cleanup_preview_account_or_selection_mismatch')
    def capability(self):
        with self.store.db() as db:executor=db.execute('SELECT * FROM command_executor WHERE id=1').fetchone()
        return bool(self.enabled and executor and executor['enabled'])
    def ready(self):
        with self.store.db() as db:paused=db.execute('SELECT paused FROM command_gate WHERE id=1').fetchone()[0]
        health=self.store.health()
        return not paused and self.capability() and health['agentOnline'] and health['engineState']=='healthy'
    def set_paused(self,value):
        with self.store.db(True) as db:db.execute('UPDATE command_gate SET paused=? WHERE id=1',(int(bool(value)),))
        self.wake()
    def health(self):
        available=self.capability();ready=self.ready();can_continue=False
        if ready and self.h3:
            row=self.store.response(cache_key('GET','/api/dashboard/summary'))
            target=target_from_summary(json.loads(row['body'])) if row else None
            if target:
                try:self.continue_guard({'expectedTarget':target});can_continue=True
                except CommandError:pass
        with self.store.db() as db:
            paused=bool(db.execute('SELECT paused FROM command_gate WHERE id=1').fetchone()[0])
            blocked=db.execute("SELECT state FROM commands WHERE state IN ('sent','unknown') ORDER BY created LIMIT 1").fetchone()
        can_cleanup=False
        if not blocked:
            try:self.cleanup_guard();can_cleanup=True
            except CommandError:pass
        return {'executorAvailable':available,'homeReady':ready,'commandsPaused':paused,'commandBlocker':blocked['state'] if blocked else None,
                'canContinue':can_continue and not blocked,'canCleanup':can_cleanup,'readOnly':not available}
    def resume(self,empty_only=False):
        with self.store.db(True) as db:
            self.expire(db)
            states=('queued','leased','sent','unknown') if empty_only else ('leased','sent','unknown')
            placeholders=','.join('?' for _ in states)
            if db.execute('SELECT 1 FROM commands WHERE state IN ('+placeholders+') LIMIT 1',states).fetchone():raise CommandError('resume_requires_empty_queue' if empty_only else 'resume_requires_drain')
            db.execute('UPDATE command_gate SET paused=0 WHERE id=1')
        self.wake()
    def continue_guard(self,body):
        if not self.h3:raise CommandError('h3_not_deployed')
        row=self.store.response(cache_key('GET','/api/dashboard/summary'))
        if not row or not 0<=self.store.clock()-row['last_success']<=60:raise CommandError('continue_source_stale')
        health=json.loads(row['source_health']);age=health.get('scanAgeSeconds') if isinstance(health,dict) else None
        if type(age) not in (int,float) or not 0<=age+self.store.clock()-row['last_success']<=60:raise CommandError('continue_scan_stale')
        snapshot=json.loads(row['body'])
        automatic=snapshot.get('autoRecovery')
        if not isinstance(automatic,dict) or automatic.get('enabled') is not False:
            raise CommandError('home_auto_recovery_must_be_disabled')
        if automatic.get('state') in {'requested','accepted','running','recovering','persisted','receiver_acknowledged','workbench_acknowledged','executing'}:
            raise CommandError('home_auto_recovery_still_in_flight')
        current=target_from_summary(snapshot)
        if not current or any(body['expectedTarget'].get(k)!=v for k,v in current.items()):raise CommandError('continue_target_changed')
    def enqueue(self,actor,request_id,target,body,ttl=300,public=False):
        identity(request_id);job=command(target,body);body=job['body'];target=job['target']
        if public and job['source']!='receiver':raise CommandError('public_route_forbidden',403)
        now=self.store.clock()
        with self.store.db(True) as db:
            old=db.execute('SELECT * FROM commands WHERE actor=? AND request_id=?',(actor,request_id)).fetchone()
            if old:
                if old['digest']!=job['digest']:raise CommandError('client_request_id_content_conflict')
                return self.public(old)
            if db.execute('SELECT 1 FROM command_cancelled_requests WHERE actor=? AND request_id=?',(actor,request_id)).fetchone():raise CommandError('request_cancelled_before_receipt')
            if not self.capability():raise CommandError('executor_not_deployed_or_disabled',503)
            self.expire(db)
            if db.execute("SELECT count(*) FROM commands WHERE state IN ('queued','leased','sent','unknown')").fetchone()[0]>=100:raise CommandError('command_queue_full',429)
            if target.startswith('/api/controls/cloud-cleanup/'):
                self.cleanup_guard(body)
                if target.endswith('/execute'):self.cleanup_owner(actor,body)
            if target=='/api/control-commands':
                if not self.ready():raise CommandError('home_offline_or_busy')
                self.continue_guard(body)
            if type(ttl) is not int or not 1<=ttl<=300:raise CommandError('invalid_command_ttl',400)
            identifier=secrets.token_urlsafe(32)
            db.execute('INSERT INTO commands(id,actor,request_id,target,body,digest,source,state,created,expires,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (identifier,actor,request_id,job['target'],canonical(body),job['digest'],job['source'],'queued',now,min(now+ttl,now+120,body['expiresAt']) if target=='/api/controls/cloud-cleanup/execute' else now+ttl,now))
            row=db.execute('SELECT * FROM commands WHERE id=?',(identifier,)).fetchone();self.audit(db,row,'queued')
            answer=self.public(row)
        self.wake();return answer
    def public(self,row,include_result=True):
        return {'cloudCommand':True,'cloudCommandId':row['id'],'state':row['state'],'target':row['target'],'actor':row['actor'],
                'createdAt':row['created'],'expiresAt':row['expires'],'updatedAt':row['updated'],'result':json.loads(row['result']) if include_result and row['result'] else None,
                'cancellable':row['state'] in {'queued','leased'},'downstreamCancellationGuaranteed':False}
    def get(self,identifier,public=False):
        with self.store.db(True) as db:
            self.expire(db);row=db.execute('SELECT id,actor,state,source,target,created,expires,updated,result FROM commands WHERE id=?',(identifier,)).fetchone()
            if not row or public and row['source']!='receiver':raise CommandError('command_not_found',404)
            return self.public(row)
    def by_request(self,actor,request_id):
        identity(request_id)
        with self.store.db() as db:row=db.execute('SELECT id FROM commands WHERE actor=? AND request_id=?',(actor,request_id)).fetchone()
        if not row:
            with self.store.db() as db:cancelled=db.execute('SELECT 1 FROM command_cancelled_requests WHERE actor=? AND request_id=?',(actor,request_id)).fetchone()
            if cancelled:return {'state':'cancelled','cancelledBeforeReceipt':True,'result':None,'cloudCommandId':None}
            raise CommandError('request_not_received',404)
        return self.get(row['id'])
    def cancel_request(self,actor,request_id):
        identity(request_id)
        with self.store.db(True) as db:
            row=db.execute('SELECT * FROM commands WHERE actor=? AND request_id=?',(actor,request_id)).fetchone()
            if row and row['state'] not in {'queued','leased','cancelled','expired'}:raise CommandError('already_sent_cannot_guarantee_cancellation')
            db.execute('INSERT OR IGNORE INTO command_cancelled_requests VALUES(?,?,?)',(actor,request_id,self.store.clock()))
            if row and row['state'] in {'queued','leased'}:
                db.execute("UPDATE commands SET state='cancelled',updated=? WHERE id=?",(self.store.clock(),row['id']));self.audit(db,row,'cancelled_by_request_id',actor)
        self.wake();return {'cancelledBeforeSend':True,'lateSubmissionRejected':True}
    def listing(self):
        with self.store.db(True) as db:
            self.expire(db);rows=db.execute('SELECT id,actor,state,target,created,expires,updated FROM commands ORDER BY created DESC LIMIT 100').fetchall()
        return {'items':[self.public(row,include_result=False) for row in rows],'executorAvailable':self.capability(),'homeReady':self.ready()}
    def claim(self,ledger):
        if not self.ready():return None
        with self.store.db(True) as db:
            self.expire(db)
            executor=db.execute('SELECT * FROM command_executor WHERE id=1').fetchone()
            if not executor or executor['ledger_id']!=ledger:raise CommandError('executor_identity_mismatch')
            if db.execute("SELECT 1 FROM commands WHERE state IN ('leased','sent','unknown')").fetchone():return None
            row=db.execute("SELECT * FROM commands WHERE state='queued' ORDER BY created,rowid LIMIT 1").fetchone()
            if not row:return None
            token=uuid.uuid4().hex
            db.execute("UPDATE commands SET state='leased',lease=?,lease_until=?,ledger_id=?,updated=? WHERE id=?",(token,self.store.clock()+60,ledger,self.store.clock(),row['id']))
            self.audit(db,row,'leased')
            return {'id':row['id'],'lease':token,'ledgerId':ledger,'expiresAt':row['expires'],**command(row['target'],json.loads(row['body']))}
    def permit(self,identifier,lease,ledger):
        with self.store.db(True) as db:
            self.expire(db);row=db.execute('SELECT * FROM commands WHERE id=?',(identifier,)).fetchone()
            if not row or row['state']!='leased' or row['lease']!=lease or row['ledger_id']!=ledger:raise CommandError('command_no_send_permit')
            if not self.ready():raise CommandError('home_offline_or_busy')
            if row['target'].startswith('/api/controls/cloud-cleanup/'):
                self.cleanup_guard(json.loads(row['body']))
                if row['target'].endswith('/execute'):self.cleanup_owner(row['actor'],json.loads(row['body']))
            if row['target']=='/api/control-commands':self.continue_guard(json.loads(row['body']))
            db.execute("UPDATE commands SET state='sent',updated=? WHERE id=?",(self.store.clock(),identifier));self.audit(db,row,'send_permitted')
        self.wake();return {'sendPermitted':True,'cloudCommandId':identifier}
    def finish(self,identifier,lease,ledger,result):
        if not isinstance(identifier,str) or not 1<=len(identifier)<=128:raise CommandError('invalid_result_identity',400)
        if not all(isinstance(v,str) and len(v)==32 and all(c in '0123456789abcdef' for c in v) for v in (lease,ledger)):raise CommandError('invalid_result_identity',400)
        if not isinstance(result,dict) or not isinstance(result.get('kind'),str) or result.get('kind') not in {'http','unknown','not_sent'}:raise CommandError('invalid_command_result',400)
        if result['kind']=='http':
            if set(result)!={'kind','httpStatus','bodyBase64','contentType'} or type(result.get('httpStatus')) is not int or not 200<=result['httpStatus']<=599 or not isinstance(result.get('bodyBase64'),str) or not isinstance(result.get('contentType'),str) or len(result['contentType'])>256 or any(ord(c)<32 or ord(c)>126 for c in result['contentType']):raise CommandError('invalid_http_result',400)
            try:raw=base64.b64decode(result['bodyBase64'],validate=True)
            except ValueError:raise CommandError('invalid_result_encoding',400) from None
            if len(raw)>MAX_REPLY:raise CommandError('command_result_too_large',413)
        elif set(result)!={'kind','reason'} or not isinstance(result.get('reason'),str) or result.get('reason') not in {'transport_uncertain','restart_after_send','send_permit_denied','invalid_or_expired','local_result_unavailable','agent_rejected_identity','agent_rejected_contract'}:raise CommandError('invalid_result_reason',400)
        encoded=canonical(result);digest=hashlib.sha256(encoded.encode()).hexdigest()
        with self.store.db(True) as db:
            row=db.execute('SELECT * FROM commands WHERE id=?',(identifier,)).fetchone()
            if not row or row['lease']!=lease or row['ledger_id']!=ledger:raise CommandError('result_identity_mismatch')
            if row['result_digest']:
                if row['result_digest']!=digest:raise CommandError('result_content_conflict')
                return {'recorded':True}
            if result['kind']=='http' and row['state'] not in {'sent','unknown','resolved_unknown'}:raise CommandError('http_result_without_send')
            if row['state'] not in {'queued','leased','sent','unknown','resolved_unknown','expired','cancelled'}:raise CommandError('result_state_conflict')
            state='completed' if result['kind']=='http' else 'unknown' if result['kind']=='unknown' else row['state'] if row['state'] in {'expired','cancelled'} else 'not_sent'
            db.execute('UPDATE commands SET state=?,result=?,result_digest=?,updated=? WHERE id=?',(state,encoded,digest,self.store.clock(),identifier));self.audit(db,row,state)
        if result['kind']=='http':
            self.refresh_source()
            if row['target']=='/api/controls/cloud-cleanup/execute':
                for target in ('/api/controls/capcut-drafts','/api/controls/audio-files','/api/controls/production-files','/api/controls/pending-delete'):
                    self.store.enqueue_read(cache_key('GET',target))
            if row['target']=='/api/control-commands':
                try:local_id=json.loads(raw).get('commandId')
                except (ValueError,AttributeError):local_id=None
                if isinstance(local_id,str) and 1<=len(local_id)<=128:
                    try:self.store.enqueue_read(cache_key('GET','/api/control-commands/'+local_id))
                    except ValueError:pass
        self.wake();return {'recorded':True}
    def refresh_source(self):
        # A successful HTTP exchange is not business completion. Force new GET
        # snapshots and keep source age visible until those requests finish.
        for target in ('/api/dashboard/summary','/api/dashboard','/api/task-boxes/current','/api/controls/tasks','/api/control-commands/current','/api/controls/continue-current/status','/api/controls/upload/verify-history/status'):
            try:self.store.enqueue_read(cache_key('GET',target))
            except ValueError:pass
    def cancel(self,identifier,actor):
        with self.store.db(True) as db:
            self.expire(db);row=db.execute('SELECT * FROM commands WHERE id=?',(identifier,)).fetchone()
            if not row:raise CommandError('command_not_found',404)
            if row['state'] not in {'queued','leased'}:raise CommandError('already_sent_cannot_guarantee_cancellation')
            db.execute("UPDATE commands SET state='cancelled',updated=? WHERE id=?",(self.store.clock(),identifier));self.audit(db,row,'cancelled_before_send',actor)
        self.wake();return self.get(identifier)
    def resolve(self,identifier,actor,note,confirmation):
        if confirmation!='CONFIRMED_HOME_REQUEST_STOPPED' or not isinstance(note,str) or not 10<=len(note)<=1000:raise CommandError('manual_home_reconciliation_required',400)
        with self.store.db(True) as db:
            row=db.execute('SELECT * FROM commands WHERE id=?',(identifier,)).fetchone()
            if not row or row['state']!='unknown':raise CommandError('only_unknown_can_be_resolved')
            db.execute("UPDATE commands SET state='resolved_unknown',updated=? WHERE id=?",(self.store.clock(),identifier));self.audit(db,row,'manual_reconciliation_no_retry',actor,note)
        self.wake();return self.get(identifier)
    def wait_claim(self,ledger,seconds):
        deadline=time.monotonic()+seconds
        while True:
            with self.changed:
                job=self.claim(ledger)
                if job:return job
                remaining=deadline-time.monotonic()
                if remaining<=0:return None
                self.changed.wait(min(.25,remaining))
