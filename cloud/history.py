"""New separate history DB. Immutable generations; never touches console/engine rows."""
import base64,hashlib,json,sqlite3,time,csv,io
from contextlib import contextmanager
from pathlib import Path
from contracts.history import HistoryError,canonical,sha,manifest,record,summary,identifier,safe_facts,MAX_CHUNK,MAX_BYTES,KINDS

class HistoryStore:
    def __init__(self,path,*,clock=time.time,quota_bytes=512*1024*1024,retain_ready=3):
        if type(retain_ready) is not int or not 1<=retain_ready<=8:
            raise ValueError('retain_ready must be between 1 and 8')
        self.path=Path(path);self.clock=clock;self.quota=quota_bytes;self.retain_ready=retain_ready
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sources(source TEXT PRIMARY KEY,active TEXT,highwater INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS generations(id TEXT PRIMARY KEY,source TEXT NOT NULL,seq INTEGER NOT NULL,state TEXT NOT NULL,descriptor TEXT NOT NULL,created REAL NOT NULL,reserved_bytes INTEGER NOT NULL,reserved_rows INTEGER NOT NULL,UNIQUE(source,seq));
            CREATE TABLE IF NOT EXISTS records(generation TEXT NOT NULL,kind TEXT NOT NULL,record_key TEXT NOT NULL,body TEXT NOT NULL,digest TEXT NOT NULL,byte_count INTEGER NOT NULL,PRIMARY KEY(generation,kind,record_key));
            CREATE TABLE IF NOT EXISTS chunks(generation TEXT NOT NULL,position INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(generation,position));
            CREATE TABLE IF NOT EXISTS touched(generation TEXT NOT NULL,kind TEXT NOT NULL,record_key TEXT NOT NULL,PRIMARY KEY(generation,kind,record_key));
            CREATE TABLE IF NOT EXISTS changes(generation TEXT NOT NULL,kind TEXT NOT NULL,record_key TEXT NOT NULL,operation TEXT NOT NULL,PRIMARY KEY(generation,kind,record_key));
            CREATE TABLE IF NOT EXISTS selections(id INTEGER PRIMARY KEY,source TEXT NOT NULL,previous TEXT,target TEXT NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL);
            """)
    @contextmanager
    def db(self,write=False):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            if write:db.execute('BEGIN IMMEDIATE')
            yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def _generation(self,db,generation):
        row=db.execute('SELECT * FROM generations WHERE id=?',(generation,)).fetchone()
        if not row:raise HistoryError('history_generation_missing',404)
        return dict(row)
    def _active(self,db,source):
        row=db.execute('SELECT * FROM sources WHERE source=?',(source,)).fetchone()
        return dict(row) if row else {'source':source,'active':None,'highwater':0}
    def begin(self,descriptor):
        descriptor=manifest(descriptor);generation=sha(descriptor);source=descriptor['source']
        with self.db(True) as db:
            existing=db.execute('SELECT * FROM generations WHERE id=?',(generation,)).fetchone()
            if existing:return self._status(db,generation)
            current=self._active(db,source)
            if descriptor['sequence']<=current['highwater']:raise HistoryError('history_sequence_stale',409)
            if descriptor['baseGeneration']!=current['active']:raise HistoryError('history_base_changed',409)
            self._prune_ready(db,source)
            if db.execute('SELECT count(*) FROM generations WHERE source=?',(source,)).fetchone()[0]>=10:raise HistoryError('history_generation_limit',413)
            reserve_bytes=descriptor['summary']['bytes'];reserve_rows=descriptor['summary']['rowCount']
            if descriptor['mode']=='delta':
                parent=self._generation(db,current['active']);base=json.loads(parent['descriptor'])
                if base['resetGeneration']!=descriptor['resetGeneration']:raise HistoryError('history_delta_across_reset_forbidden',409)
                # Staging may temporarily hold old + new keys before deletion
                # chunks arrive. Reserve this explicitly, not just final size.
                reserve_bytes+=base['summary']['bytes'];reserve_rows+=base['summary']['rowCount']
            reserved=db.execute('SELECT coalesce(sum(reserved_bytes),0) FROM generations').fetchone()[0]
            if reserved+reserve_bytes>self.quota:raise HistoryError('history_quota_exceeded',413)
            try:db.execute('INSERT INTO generations VALUES(?,?,?,?,?,?,?,?)',(generation,source,descriptor['sequence'],'staging',canonical(descriptor).decode(),self.clock(),reserve_bytes,reserve_rows))
            except sqlite3.IntegrityError:raise HistoryError('history_sequence_conflict',409) from None
            if descriptor['mode']=='delta':db.execute('INSERT INTO records SELECT ?,kind,record_key,body,digest,byte_count FROM records WHERE generation=?',(generation,current['active']))
            return self._status(db,generation)
    def _prune_ready(self,db,source):
        """Keep recent ready generations plus active/staging dependencies.

        Selection audit rows remain intact. Deleting a generation intentionally
        invalidates old pinned cursors; callers get history_generation_missing.
        SQLite reuses freed pages; no VACUUM or live source access is performed.
        """
        rows=db.execute("SELECT id FROM generations WHERE source=? AND state='ready' ORDER BY seq DESC",(source,)).fetchall()
        protected={row['id'] for row in rows[:self.retain_ready]}
        protected.add(self._active(db,source)['active'])
        for row in db.execute("SELECT descriptor FROM generations WHERE source=? AND state='staging'",(source,)):
            protected.add(json.loads(row['descriptor'])['baseGeneration'])
        for row in rows:
            generation=row['id']
            if generation in protected:continue
            for table in ('records','chunks','touched','changes'):
                db.execute('DELETE FROM '+table+' WHERE generation=?',(generation,))
            db.execute('DELETE FROM generations WHERE id=?',(generation,))
    def _status(self,db,generation):
        row=self._generation(db,generation);descriptor=json.loads(row['descriptor'])
        received=[r[0] for r in db.execute('SELECT position FROM chunks WHERE generation=? ORDER BY position',(generation,))]
        return {'generationId':generation,'source':row['source'],'state':row['state'],'receivedChunks':received,'expectedChunks':len(descriptor['chunks']),'active':self._active(db,row['source'])['active']==generation}
    def status(self,generation):
        with self.db() as db:return self._status(db,generation)
    def put(self,generation,position,operations):
        if type(position) is not int or not isinstance(operations,list):raise HistoryError('invalid_history_chunk')
        if len(canonical(operations))>MAX_CHUNK:raise HistoryError('history_chunk_too_large',413)
        digest=sha(operations)
        with self.db(True) as db:
            row=self._generation(db,generation);descriptor=json.loads(row['descriptor'])
            if not 0<=position<len(descriptor['chunks']) or descriptor['chunks'][position]!=digest:raise HistoryError('history_chunk_hash_mismatch',409)
            prior=db.execute('SELECT digest FROM chunks WHERE generation=? AND position=?',(generation,position)).fetchone()
            if prior:return self._status(db,generation)
            if row['state']!='staging':raise HistoryError('history_generation_immutable',409)
            if self.clock()-row['created']>86400:raise HistoryError('history_staging_expired',409)
            for operation in operations:
                if not isinstance(operation,dict):raise HistoryError('invalid_history_operation')
                if operation.get('op')=='upsert' and set(operation)=={'op','record'}:
                    value=record(operation['record']);kind,key=value['kind'],value['key']
                    body=canonical(value['value']).decode();fingerprint=sha(value);byte_count=len(canonical(value))
                elif operation.get('op')=='delete' and set(operation)=={'op','kind','key'} and descriptor['mode']=='delta':
                    kind,key=operation['kind'],operation['key']
                    if kind not in KINDS or not isinstance(key,str) or not 1<=len(key)<=512:raise HistoryError('invalid_history_delete')
                    body=fingerprint=None
                else:raise HistoryError('invalid_history_operation')
                try:db.execute('INSERT INTO touched VALUES(?,?,?)',(generation,kind,key))
                except sqlite3.IntegrityError:raise HistoryError('duplicate_history_operation',409) from None
                if body is None:db.execute('DELETE FROM records WHERE generation=? AND kind=? AND record_key=?',(generation,kind,key))
                else:db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?)',(generation,kind,key,body,fingerprint,byte_count))
            used=db.execute('SELECT coalesce(sum(byte_count),0),count(*) FROM records WHERE generation=?',(generation,)).fetchone()
            if used[0]>row['reserved_bytes'] or used[1]>row['reserved_rows']:raise HistoryError('history_dataset_limit',413)
            db.execute('INSERT INTO chunks VALUES(?,?,?)',(generation,position,digest))
            return self._status(db,generation)
    def _records(self,db,generation,kind=None):
        query='SELECT kind,record_key,body FROM records WHERE generation=?';args=[generation]
        if kind is not None:query+=' AND kind=?';args.append(kind)
        for row in db.execute(query+' ORDER BY kind,record_key',args):yield {'kind':row['kind'],'key':row['record_key'],'value':json.loads(row['body'])}
    def _evidence(self,db,generation):
        groups={}
        for item in self._records(db,generation,'evidence'):
            value=item['value']
            if not isinstance(value,dict) or set(value)!={'path','index','parts','sha256','bytes','encoding','data'} or value['encoding'] not in {'utf-8-json','utf-8-csv'} or type(value['index']) is not int or type(value['parts']) is not int or not 1<=value['parts']<=256 or not 0<=value['index']<value['parts'] or item['key']!=value['path']+'#'+str(value['index']):raise HistoryError('invalid_history_evidence')
            groups.setdefault(value['path'],[]).append(value)
        for path,parts in groups.items():
            parts.sort(key=lambda x:x['index']);first=parts[0]
            if len(parts)!=first['parts'] or [x['index'] for x in parts]!=list(range(first['parts'])) or any(any(x[k]!=first[k] for k in ('parts','sha256','bytes','encoding')) for x in parts):raise HistoryError('history_evidence_parts_incomplete',409)
            try:raw=b''.join(base64.b64decode(x['data'],validate=True) for x in parts)
            except (ValueError,TypeError):raise HistoryError('invalid_history_evidence_encoding') from None
            if len(raw)!=first['bytes'] or len(raw)>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=first['sha256']:raise HistoryError('history_evidence_hash_mismatch',409)
            try:safe_facts(list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))) if first['encoding']=='utf-8-csv' else json.loads(raw))
            except (ValueError,UnicodeError,TypeError):raise HistoryError('unsafe_history_evidence') from None
    def _aliases(self,db,generation,reset):
        aliases={item['key']:item['value'] for item in self._records(db,generation,'alias')}
        for alias,value in aliases.items():
            if value['resetGeneration']!=reset:raise HistoryError('history_alias_generation_mismatch',409)
            seen={alias};current=value['canonical']
            while current in aliases:
                if current in seen:raise HistoryError('history_alias_cycle',409)
                seen.add(current);current=aliases[current]['canonical']
        resets=list(self._records(db,generation,'reset'))
        if len(resets)!=1 or resets[0]['key']!=reset or resets[0]['value'].get('generation')!=reset:raise HistoryError('history_reset_evidence_missing',409)
    def finish(self,generation):
        with self.db(True) as db:
            row=self._generation(db,generation);descriptor=json.loads(row['descriptor']);current=self._active(db,row['source'])
            if row['state']=='ready':return self._status(db,generation)
            if self.clock()-row['created']>86400:raise HistoryError('history_staging_expired',409)
            if len(self._status(db,generation)['receivedChunks'])!=len(descriptor['chunks']):raise HistoryError('history_chunks_missing',409)
            if descriptor['baseGeneration']!=current['active'] or row['seq']<=current['highwater']:raise HistoryError('history_base_changed',409)
            if summary(self._records(db,generation))!=descriptor['summary']:raise HistoryError('history_rows_or_counts_mismatch',409)
            self._evidence(db,generation);self._aliases(db,generation,descriptor['resetGeneration'])
            from contracts.timeline import event
            for item in self._records(db,generation,'timeline'):
                event(item['value'])
                if item['key']!=item['value']['eventId']:raise HistoryError('timeline_primary_key_mismatch')
            previous=current['active']
            db.execute("INSERT INTO changes SELECT ?,n.kind,n.record_key,CASE WHEN p.record_key IS NULL THEN 'insert' ELSE 'update' END FROM records n LEFT JOIN records p ON p.generation=? AND p.kind=n.kind AND p.record_key=n.record_key WHERE n.generation=? AND (p.record_key IS NULL OR n.digest<>p.digest)",(generation,previous,generation))
            db.execute("INSERT INTO changes SELECT ?,p.kind,p.record_key,'delete' FROM records p LEFT JOIN records n ON n.generation=? AND n.kind=p.kind AND n.record_key=p.record_key WHERE p.generation=? AND n.record_key IS NULL",(generation,generation,previous))
            db.execute("UPDATE generations SET state='ready',reserved_bytes=?,reserved_rows=? WHERE id=?",(descriptor['summary']['bytes'],descriptor['summary']['rowCount'],generation))
            db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?)',(row['source'],generation,row['seq']))
            db.execute('INSERT INTO selections(source,previous,target,reason,created) VALUES(?,?,?,?,?)',(row['source'],previous,generation,'verified-import',self.clock()))
            self._prune_ready(db,row['source'])
            return self._status(db,generation)
    def source(self,source):
        identifier(source)
        with self.db() as db:
            row=self._active(db,source);active=row['active']
            return {**row,'manifest':json.loads(self._generation(db,active)['descriptor']) if active else None,'legacySourceChanged':False,'realShadowPassed':False,'switchAccepted':False}
    def select(self,source,generation,reason):
        identifier(source)
        if reason!='ROLLBACK_HISTORY_SOURCE':raise HistoryError('history_rollback_confirmation_required')
        with self.db(True) as db:
            row=self._generation(db,generation);current=self._active(db,source)
            if row['source']!=source or row['state']!='ready':raise HistoryError('history_source_not_ready',409)
            db.execute('UPDATE sources SET active=? WHERE source=?',(generation,source))
            db.execute('INSERT INTO selections(source,previous,target,reason,created) VALUES(?,?,?,?,?)',(source,current['active'],generation,reason,self.clock()))
            return {'active':generation,'highwater':current['highwater'],'legacySourceChanged':False}
    def listing(self,source,kind,*,limit=100,after='',generation=None):
        identifier(source)
        if kind not in KINDS or type(limit) is not int or not 1<=limit<=1000 or not isinstance(after,str):raise HistoryError('invalid_history_query')
        if after and generation is None:raise HistoryError('history_pinned_generation_required',409)
        with self.db() as db:
            selected=generation or self._active(db,source)['active']
            if selected is None:return {'generationId':None,'items':[],'next':None}
            row=self._generation(db,selected)
            if row['source']!=source or row['state']!='ready':raise HistoryError('history_source_not_ready',409)
            rows=db.execute('SELECT record_key,body FROM records WHERE generation=? AND kind=? AND record_key>? ORDER BY record_key LIMIT ?',(selected,kind,after,limit+1)).fetchall()
            return {'generationId':selected,'items':[{'key':x['record_key'],'value':json.loads(x['body'])} for x in rows[:limit]],'next':rows[limit-1]['record_key'] if len(rows)>limit else None}
    def changes(self,generation):
        with self.db() as db:
            row=self._generation(db,generation)
            if row['state']!='ready':raise HistoryError('history_source_not_ready',409)
            return [dict(x) for x in db.execute('SELECT kind,record_key,operation FROM changes WHERE generation=? ORDER BY kind,record_key',(generation,))]

    def timeline(self,source,batch_id,project_id,*,generation=None):
        from contracts.timeline import analyze
        identifier(source)
        if not isinstance(batch_id,str) or not batch_id or not isinstance(project_id,str) or not project_id:raise HistoryError('history_project_identity_required')
        with self.db() as db:
            selected=generation or self._active(db,source)['active']
            if selected is None:return {'generationId':None,'analysis':analyze([])}
            row=self._generation(db,selected)
            if row['source']!=source or row['state']!='ready':raise HistoryError('history_source_not_ready',409)
            rows=db.execute("SELECT body FROM records WHERE generation=? AND kind='timeline' AND json_extract(body,'$.batchId')=? AND json_extract(body,'$.projectId')=? ORDER BY record_key LIMIT 20001",(selected,batch_id,project_id)).fetchall()
            if len(rows)>20000:raise HistoryError('history_timeline_query_limit',413)
            return {'generationId':selected,'analysis':analyze([json.loads(x[0]) for x in rows])}

    def discard_staging(self,generation,confirmation):
        if confirmation!='DISCARD_UNSELECTED_STAGING':raise HistoryError('history_discard_confirmation_required')
        with self.db(True) as db:
            row=self._generation(db,generation)
            if row['state']!='staging' or self._active(db,row['source'])['active']==generation:raise HistoryError('history_ready_generation_protected',409)
            for table in ('records','chunks','touched'):db.execute('DELETE FROM '+table+' WHERE generation=?',(generation,))
            db.execute('DELETE FROM generations WHERE id=?',(generation,))
            return {'discarded':generation,'activeUnchanged':True}

    def resolve_alias(self,source,alias,*,generation=None):
        identifier(source);identifier(alias)
        with self.db() as db:
            selected=generation or self._active(db,source)['active']
            if selected is None:return {'generationId':None,'canonical':alias,'trace':[]}
            row=self._generation(db,selected)
            if row['source']!=source or row['state']!='ready':raise HistoryError('history_source_not_ready',409)
            trace=[];current=alias
            while True:
                item=db.execute("SELECT body FROM records WHERE generation=? AND kind='alias' AND record_key=?",(selected,current)).fetchone()
                if item is None:break
                trace.append(current);current=json.loads(item[0])['canonical']
                if current in trace:raise HistoryError('history_alias_cycle',409)
            return {'generationId':selected,'canonical':current,'trace':trace,'resetGeneration':json.loads(row['descriptor'])['resetGeneration']}
