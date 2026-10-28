"""Durable single-holder handoff control and immutable local package metadata.

No material business tables, task receiver calls, source DB restore or online cleanup.
All holder transitions and the current-package pointer use SQLite transactions.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import shutil
import time

ID = re.compile(r'[A-Za-z0-9_-]{8,100}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
CONFIRMATION = '另一端已停止，未完成操作作废'
GIB = 1024**3
DEFAULT_STORAGE_CAP = 8*GIB
DISK_HEADROOM = 5*GIB


class HandoffError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise HandoffError('invalid_identifier', 400)
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class Handoff:
    def __init__(self, root, *, clock=None, lease_seconds=120, max_package_bytes=2*1024**3,
                 storage_cap_bytes=DEFAULT_STORAGE_CAP, check_storage=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root/'handoff.db'
        if not self.path.exists() and any((self.root/'objects').glob('*.zip')):
            raise RuntimeError('handoff_control_database_missing_preserve_objects_and_recover_offline')
        self.lease_seconds = lease_seconds
        self.max_package_bytes = max_package_bytes
        self.storage_cap_bytes = storage_cap_bytes
        if (type(lease_seconds) is not int or type(max_package_bytes) is not int or type(storage_cap_bytes) is not int or
                not 15 <= lease_seconds <= 900 or not 1 <= max_package_bytes <= 8*1024**3 or storage_cap_bytes<max_package_bytes):
            raise ValueError('invalid_handoff_limits')
        # Fail before schema creation. Offline recovery/prune must remain usable
        # on a full disk; only those explicitly confirmed commands skip startup.
        if check_storage and storage_cap_bytes+DISK_HEADROOM>shutil.disk_usage(self.root).free:
            raise RuntimeError('handoff_storage_cap_plus_5gib_exceeds_free_disk')
        wall, mono = time.time(), time.monotonic()
        self.clock = clock or (lambda: wall + time.monotonic() - mono)
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS packages(
              id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, path TEXT NOT NULL,
              device TEXT NOT NULL, generation TEXT NOT NULL, epoch INTEGER NOT NULL, session_id TEXT NOT NULL,
              parent_id TEXT, state TEXT NOT NULL, uploaded_at REAL NOT NULL, committed_at REAL, summary TEXT);
            CREATE TABLE IF NOT EXISTS requests(
              actor TEXT NOT NULL, action TEXT NOT NULL, request_id TEXT NOT NULL,
              digest TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY(actor,action,request_id));
            CREATE TABLE IF NOT EXISTS audit(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
              actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);''')
            db.execute('CREATE TABLE IF NOT EXISTS uploads(path TEXT PRIMARY KEY, reserved_bytes INTEGER NOT NULL, at REAL NOT NULL)')
            db.execute('INSERT OR IGNORE INTO state VALUES(1,?)', (encode({
                'generation': secrets.token_hex(16), 'epoch': 0, 'holder': None,
                'phase': 'idle', 'session_id': None, 'lease_until': None,
                'last_contact_at': None,
                'current_package': None, 'base_package': None, 'acquire_request_id': None}),))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def tx(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def state(self, db):
        return json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])

    def save(self, db, state):
        db.execute('UPDATE state SET body=? WHERE id=1', (encode(state),))

    def audit(self, db, actor, action, detail):
        db.execute('INSERT INTO audit(at,actor,action,detail) VALUES(?,?,?,?)',
                   (self.clock(), actor, action, encode(detail)))

    def view(self, db, s):
        result = dict(s)
        result.pop('acquire_request_id', None)
        result.pop('session_id', None)
        result['server_time'] = self.clock()
        result['lease_lost'] = s['holder'] is not None and self.clock() >= s['lease_until']
        result['execution_allowed'] = s['phase']=='active' and s['holder'] is not None and not result['lease_lost']
        row = db.execute('SELECT * FROM packages WHERE id=?', (s['current_package'],)).fetchone()
        result['package'] = self.package_view(row) if row else None
        return result

    @staticmethod
    def package_view(row):
        return {**{k: row[k] for k in ('id','sha256','bytes','device','parent_id','state','uploaded_at','committed_at')},
                'summary':json.loads(row['summary']) if row['summary'] else None}

    def status(self):
        with self.db() as db:
            # One read transaction prevents mixing pointer and candidate generations.
            db.execute('BEGIN')
            s = self.state(db)
            result = self.view(db, s)
            result['candidates'] = [self.package_view(r) for r in db.execute(
                "SELECT * FROM packages WHERE state='committed' AND (id=? OR (parent_id IS ? AND generation=? AND epoch=? AND session_id IS ?)) ORDER BY committed_at DESC LIMIT 50",
                (s['current_package'], s['current_package'], s['generation'], s['epoch'], s['session_id']))]
            result['audit'] = [{'seq': r['seq'], 'at': r['at'], 'actor': r['actor'],
                                'action': r['action'], 'detail': json.loads(r['detail'])}
                               for r in db.execute('SELECT * FROM audit ORDER BY seq DESC LIMIT 30')]
            reserved,untracked=self.budget(db)
            used=reserved+untracked
            warning=used*100>self.storage_cap_bytes*70
            result['storage']={'reserved_bytes':used,'used_bytes':used,'untracked_object_bytes':untracked,
                               'cap_bytes':self.storage_cap_bytes,'auto_delete':False,
                               'warning':warning,'warning_threshold_percent':70,
                               'warning_code':'handoff_storage_above_70_percent' if warning else None}
            return result

    def budget(self,db):
        rows=list(db.execute('SELECT path,reserved_bytes FROM uploads'))
        known={r['path'] for r in rows}
        # A restored older control DB may not know newer retained objects. Keep
        # those bytes counted; never remove them or pretend their capacity is free.
        unknown=0
        for path in (self.root/'objects').glob('*.zip'):
            if path.relative_to(self.root).as_posix() not in known and not path.is_symlink():
                try:
                    unknown+=path.stat().st_size
                except FileNotFoundError:
                    pass
        return sum(r['reserved_bytes'] for r in rows),unknown

    def fence(self, db, device, body, phases=None):
        s = self.state(db)
        if (device != s['holder'] or body.get('generation') != s['generation'] or
                type(body.get('epoch')) is not int or body['epoch'] != s['epoch'] or
                body.get('session_id') != s['session_id']):
            raise HandoffError('stale_holder')
        if self.clock() >= s['lease_until']:
            raise HandoffError('lease_expired_manual_takeover_required')
        if phases and s['phase'] not in phases:
            raise HandoffError('invalid_handoff_phase')
        return s

    def request(self, db, actor, action, body, replay_after_fence=None):
        rid = identifier(body.get('request_id'))
        digest = hashlib.sha256(encode(body).encode()).hexdigest()
        row = db.execute('SELECT * FROM requests WHERE actor=? AND action=? AND request_id=?', (actor,action,rid)).fetchone()
        if row:
            if row['digest'] != digest:
                raise HandoffError('request_id_conflict')
            if replay_after_fence:
                replay_after_fence()
            return json.loads(row['result']), digest
        return None, digest

    def receipt(self, db, actor, action, body, digest, answer):
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?)', (actor,action,body['request_id'],digest,encode(answer)))
        return answer

    def acquire(self, device, body):
        if device not in ('office','home'):
            raise HandoffError('unknown_device', 403)
        with self.tx() as db:
            cached, digest = self.request(db, device, 'acquire', body)
            s = self.state(db)
            if cached:
                if s['session_id'] != cached['session_id'] or s['epoch'] != cached['epoch'] or s['generation'] != cached['generation']:
                    raise HandoffError('acquire_receipt_retired')
                self.fence(db, device, cached)
                return self.holder_reply(db, s)
            if s['holder']==device and s['phase']=='preparing' and s['acquire_request_id'] is None:
                if body.get('generation')!=s['generation'] or type(body.get('epoch')) is not int or body['epoch']!=s['epoch']:
                    raise HandoffError('reservation_changed')
                if self.clock()>=s['lease_until']:
                    raise HandoffError('lease_expired_manual_takeover_required')
                s.update(acquire_request_id=body['request_id'], lease_until=self.clock()+self.lease_seconds,last_contact_at=self.clock())
                self.save(db,s)
                return self.receipt(db,device,'acquire',body,digest,self.holder_reply(db,s))
            if s['holder'] is not None:
                raise HandoffError('holder_exists_manual_takeover_if_stopped')
            if not s['current_package'] and device != 'office':
                raise HandoffError('office_baseline_required')
            s.update(holder=device, epoch=s['epoch']+1, phase='preparing',
                     session_id=secrets.token_hex(16), lease_until=self.clock()+self.lease_seconds,
                     base_package=s['current_package'], acquire_request_id=body['request_id'],last_contact_at=self.clock())
            self.save(db, s)
            answer = self.holder_reply(db, s)
            self.audit(db, device, 'acquire', {'epoch':s['epoch'],'base_package':s['base_package']})
            return self.receipt(db, device, 'acquire', body, digest, answer)

    def holder_reply(self, db, s):
        return {**self.view(db, s), 'session_id':s['session_id']}

    def transition(self, device, action, body):
        if action not in ('activate','heartbeat','drain','release'):
            raise HandoffError('invalid_action', 400)
        with self.tx() as db:
            cached, digest = self.request(db, device, action, body,
                None if action=='release' else lambda: self.fence(db,device,body))
            if cached:
                return cached if action=='release' else self.holder_reply(db,self.state(db))
            s = self.fence(db, device, body)
            if action == 'activate':
                if s['phase'] not in ('preparing','active') or body.get('package_id') != s['base_package']:
                    raise HandoffError('restore_package_mismatch')
                if s['base_package'] is None and device != 'office':
                    raise HandoffError('office_baseline_required')
                s['phase'] = 'active'
            elif action == 'drain':
                s['phase'] = 'draining'
            elif action == 'release':
                if s['phase'] != 'draining':
                    raise HandoffError('drain_required')
                row = db.execute('SELECT * FROM packages WHERE id=?', (identifier(body.get('package_id')),)).fetchone()
                if not row or row['state']!='committed' or not self.owns(row,s):
                    raise HandoffError('committed_holder_package_required')
                if row['parent_id'] != s['current_package'] or s['base_package'] != s['current_package']:
                    raise HandoffError('package_parent_changed')
                s.update(current_package=row['id'], holder=None, phase='idle', session_id=None,
                         lease_until=None, base_package=None, acquire_request_id=None)
            if s['holder']:
                s['lease_until'] = self.clock()+self.lease_seconds
            s['last_contact_at']=self.clock()
            self.save(db, s)
            answer = self.holder_reply(db,s)
            if action != 'heartbeat':
                self.audit(db, device, action, {'epoch':s['epoch'],'package_id':body.get('package_id')})
            return self.receipt(db,device,action,body,digest,answer)

    @staticmethod
    def owns(row, s):
        return (row['device']==s['holder'] and row['generation']==s['generation'] and
                row['epoch']==s['epoch'] and row['session_id']==s['session_id'])

    def force(self, actor, body):
        if body.get('confirmation') != CONFIRMATION or body.get('other_device_stopped') is not True:
            raise HandoffError('explicit_stopped_confirmation_required',400)
        reason = body.get('reason')
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=500:
            raise HandoffError('takeover_reason_required',400)
        target = body.get('target_device')
        if target not in ('office','home'):
            raise HandoffError('unknown_device',400)
        with self.tx() as db:
            cached,digest = self.request(db,actor,'force-takeover',body)
            if cached:
                return cached
            s = self.state(db)
            if (body.get('generation')!=s['generation'] or type(body.get('epoch')) is not int or body['epoch']!=s['epoch']):
                raise HandoffError('takeover_view_changed')
            if not s['holder']:
                raise HandoffError('no_holder_use_acquire')
            chosen = body.get('package_id')
            row = db.execute('SELECT * FROM packages WHERE id=?', (chosen,)).fetchone() if isinstance(chosen,str) else None
            if not row or row['state']!='committed' or not (chosen==s['current_package'] or
                    (self.owns(row,s) and row['parent_id']==s['current_package'])):
                raise HandoffError('complete_takeover_package_required')
            old = {k:s[k] for k in ('holder','epoch','session_id','current_package')}
            # Prepare a reservation; the target's token must acquire it before activate.
            s.update(epoch=s['epoch']+1, holder=target, phase='preparing',
                     session_id=secrets.token_hex(16), lease_until=self.clock()+self.lease_seconds,
                     current_package=chosen, base_package=chosen, acquire_request_id=None,last_contact_at=self.clock())
            self.save(db,s)
            self.audit(db,actor,'force-takeover',{'old':old,'new_holder':target,'epoch':s['epoch'],
                'package_id':chosen,'reason':reason,'unknown_operations':'needs_reconcile',
                'receiver_tasks_cancelled':False})
            # Console never receives the device execution session.
            return self.receipt(db,actor,'force-takeover',body,digest,self.view(db,s))

    def register_upload(self, device, fence, package_id, sha256, size, path):
        identifier(package_id)
        if not isinstance(sha256,str) or not SHA.fullmatch(sha256) or type(size) is not int or not 1<=size<=self.max_package_bytes:
            raise HandoffError('invalid_package_size_or_hash',400)
        with self.tx() as db:
            s=self.fence(db,device,fence,('draining',))
            row=db.execute('SELECT * FROM packages WHERE id=?',(package_id,)).fetchone()
            if row:
                if row['sha256']!=sha256 or row['bytes']!=size or not self.owns(row,s):
                    raise HandoffError('immutable_package_conflict')
                return self.package_view(row)
            relative=Path(path).resolve().relative_to(self.root.resolve()).as_posix()
            db.execute('INSERT INTO packages VALUES(?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                (package_id,sha256,size,relative,device,s['generation'],s['epoch'],s['session_id'],
                 s['current_package'],'staged',self.clock()))
            self.audit(db,device,'upload',{'package_id':package_id,'bytes':size,'sha256':sha256,'epoch':s['epoch']})
            return self.package_view(db.execute('SELECT * FROM packages WHERE id=?',(package_id,)).fetchone())

    def reserve_upload(self,device,fence,package_id,sha256,size,path):
        """Reserve disk budget transactionally across concurrent ASGI workers.

        Failed/aborted attempts remain reserved; no silent reclamation/deletion.
        Existing immutable upload retries return its original result without I/O.
        """
        with self.tx() as db:
            s=self.fence(db,device,fence,('draining',))
            row=db.execute('SELECT * FROM packages WHERE id=?',(package_id,)).fetchone()
            if row:
                if row['sha256']!=sha256 or row['bytes']!=size or not self.owns(row,s):
                    raise HandoffError('immutable_package_conflict')
                return self.package_view(row)
            counted,untracked=self.budget(db)
            reserved=counted+untracked
            if reserved+size>self.storage_cap_bytes:
                raise HandoffError('handoff_storage_capacity_requires_backup_and_maintenance',507)
            if shutil.disk_usage(self.root).free<size+64*1024**2:
                raise HandoffError('handoff_disk_space_low',507)
            relative=Path(path).resolve().relative_to(self.root.resolve()).as_posix()
            db.execute('INSERT INTO uploads VALUES(?,?,?)',(relative,size,self.clock()))
            return None

    def uploaded(self, device, fence, package_id):
        with self.db() as db:
            s=self.fence(db,device,fence,('draining',))
            row=db.execute('SELECT * FROM packages WHERE id=?',(identifier(package_id),)).fetchone()
            if not row or not self.owns(row,s):
                raise HandoffError('package_not_found',404)
            return dict(row)

    def commit(self, device, fence, package_id, summary):
        with self.tx() as db:
            s=self.fence(db,device,fence,('draining',))
            row=db.execute('SELECT * FROM packages WHERE id=?',(identifier(package_id),)).fetchone()
            if not row or not self.owns(row,s):
                raise HandoffError('package_not_found',404)
            if row['parent_id']!=s['current_package']:
                raise HandoffError('package_parent_changed')
            if row['state']!='committed':
                db.execute("UPDATE packages SET state='committed',committed_at=?,summary=? WHERE id=?",
                           (self.clock(),encode(summary),package_id))
                self.audit(db,device,'commit',{'package_id':package_id,'epoch':s['epoch']})
            return self.package_view(db.execute('SELECT * FROM packages WHERE id=?',(package_id,)).fetchone())

    def download(self, package_id):
        with self.db() as db:
            row=db.execute("SELECT * FROM packages WHERE id=? AND state='committed'",(identifier(package_id),)).fetchone()
            if not row:
                raise HandoffError('complete_package_not_found',404)
            path=(self.root/row['path']).resolve()
            if not path.is_relative_to(self.root.resolve()) or not path.is_file():
                raise HandoffError('package_storage_unavailable',503)
            return path, self.package_view(row)

    def recovery_generation(self,actor,backup_sha256,*,devices_stopped):
        """Offline admin only, after backup and confirmed device stop/DB restore."""
        if devices_stopped is not True or not SHA.fullmatch(backup_sha256):
            raise HandoffError('recovery_backup_and_stop_confirmation_required',400)
        with self.tx() as db:
            s=self.state(db)
            if s['current_package']:
                path,_=self.download(s['current_package'])
                from cloud.material_package import validate_package
                row=db.execute('SELECT * FROM packages WHERE id=?',(s['current_package'],)).fetchone()
                validate_package(path,dict(row))
            old={k:s[k] for k in ('generation','epoch','holder')}
            s.update(generation=secrets.token_hex(16),epoch=s['epoch']+1,holder=None,
                     phase='idle',session_id=None,lease_until=None,base_package=None,acquire_request_id=None)
            self.save(db,s)
            self.audit(db,actor,'recovery-generation',{'old':old,'generation':s['generation'],
                       'epoch':s['epoch'],'backup_sha256':backup_sha256,'package_id':s['current_package']})
            return self.view(db,s)
