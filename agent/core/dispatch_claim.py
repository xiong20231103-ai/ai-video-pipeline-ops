"""One-shot admission receipts inside the EXISTING execution.db, not a sender.

Only an already-sent row from the existing ExecutionWorker can authorize a
retained-host POST. No new token, task, worker or command queue is introduced.
"""
from contextlib import closing
import json
import math
import re
import sqlite3
import time
from contracts.commands import command
from .projection_store import require_plain_path


class DispatchRejected(ValueError):
    pass


class DispatchClaims:
    def __init__(self,path,ledger_id,*,clock=time.time):
        self.path=require_plain_path(path);self.identity=ledger_id;self.clock=clock
        if not self.path.is_file():raise ValueError('existing_execution_ledger_missing')
    def initialize(self):
        # Called only after reviewed transition startup acquired legacy ownership.
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT ledger_id FROM execution_meta WHERE id=1').fetchone()
            if not row or row[0]!=self.identity:raise ValueError('transition_ledger_identity_changed')
            db.execute('CREATE TABLE IF NOT EXISTS migration_dispatches (id TEXT PRIMARY KEY,digest TEXT NOT NULL,claimed_at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS migration_permits (id TEXT PRIMARY KEY,digest TEXT NOT NULL,expires_at REAL NOT NULL)')
            db.commit()
    def grant(self,job):
        """Called by StagedBackend only AFTER the cloud /start send permit."""
        if not isinstance(job,dict):raise DispatchRejected('execution_contract_rejected')
        try:spec=command(job['target'],job['body'])
        except (KeyError,TypeError,ValueError):raise DispatchRejected('execution_contract_rejected') from None
        if not isinstance(job.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',job['id']):
            raise DispatchRejected('execution_identity_required')
        if spec['source']!='dashboard' or job.get('ledgerId')!=self.identity:
            raise DispatchRejected('execution_identity_mismatch')
        expires=job.get('expiresAt')
        if type(expires) not in (int,float) or not math.isfinite(expires) or expires<=self.clock():
            raise DispatchRejected('execution_expired')
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            meta=db.execute('SELECT ledger_id FROM execution_meta WHERE id=1').fetchone()
            row=db.execute('SELECT digest,state,job FROM executions WHERE id=?',(job['id'],)).fetchone()
            try:stored=json.loads(row[2]) if row else None
            except (TypeError,ValueError):raise DispatchRejected('execution_contract_rejected') from None
            if not meta or meta[0]!=self.identity or not row or row[1]!='sent' or row[0]!=spec['digest'] or stored!=job:
                raise DispatchRejected('execution_not_authorized')
            db.execute('INSERT OR IGNORE INTO migration_permits VALUES(?,?,?)',(job['id'],spec['digest'],expires))
            permit=db.execute('SELECT digest,expires_at FROM migration_permits WHERE id=?',(job['id'],)).fetchone()
            if permit!=(spec['digest'],expires):raise DispatchRejected('execution_contract_mismatch')
            db.commit()
    def claim(self,identifier,ledger_id,target,body):
        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',identifier):
            raise DispatchRejected('execution_identity_required')
        if ledger_id!=self.identity:raise DispatchRejected('execution_identity_mismatch')
        try:spec=command(target,body)
        except ValueError:raise DispatchRejected('execution_contract_rejected') from None
        if spec['source']!='dashboard':raise DispatchRejected('execution_contract_rejected')
        with closing(sqlite3.connect(self.path,timeout=5)) as db:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            meta=db.execute('SELECT ledger_id FROM execution_meta WHERE id=1').fetchone()
            row=db.execute('SELECT digest,state,job FROM executions WHERE id=?',(identifier,)).fetchone()
            if not meta or meta[0]!=self.identity or not row or row[1]!='sent' or not row[2]:
                raise DispatchRejected('execution_not_authorized')
            try:job=json.loads(row[2])
            except (TypeError,ValueError):raise DispatchRejected('execution_contract_rejected') from None
            if not isinstance(job,dict) or job.get('id')!=identifier or job.get('ledgerId')!=self.identity or job.get('source')!='dashboard':
                raise DispatchRejected('execution_identity_mismatch')
            try:bound=command(job['target'],job['body'])
            except (KeyError,ValueError,TypeError):raise DispatchRejected('execution_contract_rejected') from None
            if row[0]!=spec['digest'] or job.get('digest')!=spec['digest'] or bound!=spec:
                raise DispatchRejected('execution_contract_mismatch')
            expires=job.get('expiresAt')
            if type(expires) not in (int,float) or not math.isfinite(expires) or expires<=self.clock():
                raise DispatchRejected('execution_expired')
            if target=='/api/controls/cloud-cleanup/execute' and body['expiresAt']<=self.clock():
                raise DispatchRejected('execution_expired')
            permit=db.execute('SELECT digest,expires_at FROM migration_permits WHERE id=?',(identifier,)).fetchone()
            if not permit or permit[0]!=spec['digest'] or permit[1]!=expires:
                raise DispatchRejected('execution_send_permit_missing')
            changed=db.execute('INSERT OR IGNORE INTO migration_dispatches VALUES(?,?,?)',
                (identifier,spec['digest'],self.clock())).rowcount
            if changed!=1:raise DispatchRejected('execution_already_dispatched')
            db.commit()
        return spec
