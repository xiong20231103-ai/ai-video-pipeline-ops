"""Bind confirmed evidence to the existing serialized home command queue.

Do not rebuild production templates here. Accept the native submitter's frozen
batch, verify its exact URL set, and retain both the payload and command identity.
"""
import base64
import hashlib
import json
from urllib.parse import quote
from contracts.commands import canonical, identity


class LinkDelivery:
    def __init__(self, evidence, commands):
        self.evidence,self.commands=evidence,commands
        with evidence.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS deliveries(
              id TEXT PRIMARY KEY,actor TEXT NOT NULL,target TEXT NOT NULL,payload TEXT NOT NULL,
              digest TEXT NOT NULL,state TEXT NOT NULL,command_id TEXT,result TEXT,created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS delivery_items(record_id TEXT PRIMARY KEY,delivery_id TEXT NOT NULL);
            ''')

    def prepare(self, actor, request_id, ids, payload, kind, confirm):
        identity(request_id)
        if confirm is not True:
            raise ValueError('explicit_delivery_confirmation_required')
        if not isinstance(ids,list) or not ids or len(ids)>1000 or any(not isinstance(i,str) for i in ids) or len(ids)!=len(set(ids)):
            raise ValueError('invalid_record_selection')
        if kind not in {'daily','replacement'} or not isinstance(payload,dict):
            raise ValueError('invalid_delivery_kind')
        digest=hashlib.sha256(canonical({'ids':sorted(ids),'payload':payload,'kind':kind}).encode()).hexdigest()
        with self.evidence.db() as db:
            old=db.execute('SELECT * FROM deliveries WHERE id=?',(request_id,)).fetchone()
            if old:
                if old['actor']!=actor or old['digest']!=digest:
                    raise ValueError('delivery_request_conflict')
                return dict(old)
            rows=[db.execute('SELECT * FROM records WHERE id=?',(i,)).fetchone() for i in ids]
            if any(not r or r['review']!='confirmed' or r['delivery'] not in {'waiting','failed'} for r in rows):
                raise ValueError('records_not_confirmed_waiting')
            if any(db.execute('SELECT 1 FROM delivery_items WHERE record_id=?',(i,)).fetchone() for i in ids):
                raise ValueError('records_already_reserved_query_original_delivery')
            records=[json.loads(r['payload']) for r in rows]
            expected={r['url'] for r in records}
            if kind=='daily':
                if any(r.get('replace_id') for r in records):
                    raise ValueError('daily_contains_replacement')
                tasks=payload.get('tasks')
                if not isinstance(tasks,list) or not tasks or any(not isinstance(t,dict) or not isinstance(t.get('urls'),list) for t in tasks):
                    raise ValueError('native_frozen_batch_required')
                if any(t.get('isReplenishment') for t in tasks) or payload.get('clientSubmissionId')!=request_id:
                    raise ValueError('stable_native_submission_id_required')
                supplied={u for t in tasks for u in t['urls']}
                target='/api/batches'
            else:
                parents={r.get('home_task_id') for r in records}
                if len(parents)!=1 or not next(iter(parents)) or any(not r.get('replace_id') for r in records):
                    raise ValueError('replacement_parent_required')
                urls=payload.get('urls')
                if not isinstance(urls,list) or set(payload)-{'urls','startNow'} or type(payload.get('startNow',False)) is not bool:
                    raise ValueError('invalid_replenishment_payload')
                supplied=set(urls)
                target='/api/controls/tasks/'+quote(next(iter(parents)),safe='')+'/replenish'
            if supplied!=expected:
                raise ValueError('payload_url_set_mismatch')
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?,?,NULL,NULL,?)',
                       (request_id,actor,target,canonical(payload),digest,'prepared',self.evidence.clock()))
            db.executemany('INSERT INTO delivery_items VALUES(?,?)',[(i,request_id) for i in ids])
            return dict(db.execute('SELECT * FROM deliveries WHERE id=?',(request_id,)).fetchone())

    def dispatch(self, actor, request_id):
        with self.evidence.db() as db:
            row=db.execute('SELECT * FROM deliveries WHERE id=?',(request_id,)).fetchone()
            if not row or row['actor']!=actor:
                raise ValueError('delivery_not_found')
        if row['command_id']:
            return self.status(actor,request_id)
        # Crash between enqueue and persistence is recoverable: same actor+id
        # and identical payload resolve to the ORIGINAL command, never a new send.
        result=self.commands.enqueue(actor,request_id,row['target'],json.loads(row['payload']))
        with self.evidence.db() as db:
            db.execute('UPDATE deliveries SET command_id=?,state=? WHERE id=?',(result['cloudCommandId'],result['state'],request_id))
        return self.status(actor,request_id)

    def status(self, actor, request_id):
        with self.evidence.db() as db:
            row=db.execute('SELECT * FROM deliveries WHERE id=?',(request_id,)).fetchone()
        if not row or row['actor']!=actor:
            raise ValueError('delivery_not_found')
        if not row['command_id']:
            return {'id':request_id,'state':'prepared','sent':False}
        command=self.commands.get(row['command_id'])
        state='awaiting_receipt' if command['state']=='sent' else command['state'];ack=None
        result=command.get('result') or {}
        if state=='completed':
            state='unknown'
            if result.get('kind')=='http' and 200<=result.get('httpStatus',0)<300:
                try:
                    ack=json.loads(base64.b64decode(result['bodyBase64'],validate=True))
                    payload=json.loads(row['payload'])
                    if not isinstance(ack,dict) or ack.get('ok') is not True:
                        raise ValueError()
                    if row['target']=='/api/batches':
                        fingerprint=dict(payload);fingerprint.pop('payloadHash',None)
                        expected_hash=hashlib.sha256(canonical(fingerprint).encode()).hexdigest()
                        task_ids=[t['taskId'] for t in payload['tasks']]
                        if ack.get('clientSubmissionId')!=request_id or ack.get('batchId')!=payload['batchId'] or ack.get('payloadHash')!=expected_hash or ack.get('taskIds')!=task_ids:
                            raise ValueError()
                    elif not isinstance(ack.get('taskId'),str) or not ack['taskId'] or not ack.get('batchId'):
                        raise ValueError()
                    state='sent'
                except (ValueError,TypeError,KeyError):
                    ack=None
            elif result.get('kind')=='http' and 400<=result.get('httpStatus',0)<500:
                state='failed'
        with self.evidence.db() as db:
            db.execute('UPDATE deliveries SET state=?,result=? WHERE id=?',(state,json.dumps(ack) if ack else None,request_id))
            if state=='sent':
                db.execute("UPDATE records SET delivery='sent',cloud_decision=1 WHERE id IN (SELECT record_id FROM delivery_items WHERE delivery_id=?)",(request_id,))
        return {'id':request_id,'state':state,'sent':state=='sent','cloudCommandId':row['command_id'],'receipt':ack}
