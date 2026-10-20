"""Explicit verified-snapshot export only; no live discovery, HTTP or worker hook."""
import base64,hashlib,json,csv,io
from fnmatch import fnmatchcase
from pathlib import Path
from contracts.history import HistoryError,record,summary,manifest,sha,MAX_CHUNK
from .snapshot import Snapshot,canonical,sqlite_rows,safe_facts

JSON_EVIDENCE=(
 'repository/data/task-box-completion-receipts/*.json',
 'repository/data/task-box-reconciliation/*.json',
 'repository/data/test_reset_state.json',
 'workbench/handoff/*.json','workbench/handoff/*/*.json','workbench/handoff/*/*/*.json',
 'workbench/ops_pipeline_status.json','workbench/saved_task_box.json',
 'voice/*.json','voice/*.csv','capcut/data/capcut-tasks.json',
 'generation/*/*/generation_records_*.json')

def export_records(snapshot,*,timeline=()):
    snapshot=Snapshot(snapshot.root) # Re-verify hashes immediately before reading.
    records=[];coverage={'dbPresent':False,'jsonFiles':0,'unexportedFiles':[],'timelineEvents':0}
    for logical,metadata in sorted(snapshot.manifest['files'].items()):
        if logical=='repository/data/ops.db' and metadata['kind']=='sqlite':
            coverage['dbPresent']=True
            for table,rows in sqlite_rows(snapshot.root/logical).items():
                key_name={'tasks':'task_id','source_health':'path','sqlite_sequence':'name'}.get(table,'id')
                for row in rows:records.append(record({'kind':'ops.'+table,'key':str(row[key_name]),'value':row}))
        elif any(fnmatchcase(logical,pattern) for pattern in JSON_EVIDENCE) and logical.endswith(('.json','.csv')):
            raw=snapshot.read(logical)
            if logical.endswith('.csv'):safe_facts(list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))))
            else:safe_facts(json.loads(raw));coverage['jsonFiles']+=1
            # Chunk exact evidence bytes; never rewrite their IDs/times/token fields.
            pieces=[raw[i:i+128*1024] for i in range(0,len(raw),128*1024)] or [b'']
            for index,piece in enumerate(pieces):records.append(record({'kind':'evidence','key':logical+'#'+str(index),'value':{'path':logical,'index':index,'parts':len(pieces),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'encoding':'utf-8-csv' if logical.endswith('.csv') else 'utf-8-json','data':base64.b64encode(piece).decode()}}))
        else:coverage['unexportedFiles'].append(logical)
    facts=snapshot.manifest['facts'];reset=facts.get('historyResetGeneration')
    from contracts.history import identifier
    identifier(reset)
    records.append(record({'kind':'reset','key':reset,'value':{'generation':reset,'resetAt':facts.get('historyResetAt')}}))
    aliases={}
    for alias in facts.get('historyAliases',[]):
        row=record({'kind':'alias','key':alias['alias'],'value':alias})
        if alias['alias'] in aliases:raise HistoryError('duplicate_history_alias')
        aliases[alias['alias']]=alias;records.append(row)
    for event in timeline:
        records.append(record({'kind':'timeline','key':event['eventId'],'value':event}));coverage['timelineEvents']+=1
    records.sort(key=lambda item:(item['kind'],item['key']))
    if not coverage['dbPresent']:raise HistoryError('history_ops_snapshot_required')
    summary(records)
    return records,coverage

def build_bundle(snapshot,*,source,sequence,timeline=(),previous=None,base_generation=None,recipes=None):
    normalization={'status':'not-requested','recipeCount':0,'eventCount':len(timeline),'unresolvedCount':None}
    if recipes is not None:
        if timeline:raise HistoryError('history_timeline_recipe_conflict')
        from .history_timeline import normalize_snapshot
        timeline,normalization=normalize_snapshot(snapshot,recipes)
    records,coverage=export_records(snapshot,timeline=timeline)
    coverage['timelineNormalization']=normalization
    base=base_generation;mode='full';operations=[{'op':'upsert','record':row} for row in records]
    if previous is not None:
        # Delta is based on an explicitly retained/acknowledged immutable bundle,
        # not on mutable agent.db copies of HTTP response bodies.
        old=validate_bundle(previous)
        if old['manifest']['source']!=source:raise HistoryError('history_base_source_mismatch')
        if old['manifest']['resetGeneration']!=snapshot.manifest['facts']['historyResetGeneration']:raise HistoryError('history_delta_across_reset_forbidden')
        before={(x['kind'],x['key']):x for x in old['records']};after={(x['kind'],x['key']):x for x in records}
        operations=[{'op':'upsert','record':v} for k,v in after.items() if before.get(k)!=v]
        operations +=[{'op':'delete','kind':k[0],'key':k[1]} for k in before if k not in after]
        operations.sort(key=lambda op:(op.get('record',op)['kind'],op.get('record',op)['key']))
        base=old['generationId'];mode='delta'
    chunks=[];chunk=[];chunk_bytes=2
    for operation in operations:
        size=len(canonical(operation))
        if size+2>MAX_CHUNK:raise HistoryError('history_operation_too_large')
        if chunk and chunk_bytes+size+1>MAX_CHUNK:
            chunks.append(chunk);chunk=[];chunk_bytes=2
        chunk_bytes+=size+(1 if chunk else 0);chunk.append(operation)
    if chunk:chunks.append(chunk)
    descriptor=manifest({'schema':1,'source':source,'sequence':sequence,'resetGeneration':snapshot.manifest['facts']['historyResetGeneration'],'sourceIdentity':snapshot.manifest['sourceIdentity'],'mode':mode,'baseGeneration':base,'chunks':[sha(c) for c in chunks],'summary':summary(records),'coverage':coverage})
    return {'generationId':sha(descriptor),'manifest':descriptor,'chunks':chunks,'records':records}

def validate_bundle(bundle):
    descriptor=manifest(bundle['manifest'])
    if bundle['generationId']!=sha(descriptor) or [sha(c) for c in bundle['chunks']]!=descriptor['chunks'] or summary(sorted(bundle['records'],key=lambda x:(x['kind'],x['key'])))!=descriptor['summary']:raise HistoryError('history_bundle_hash_mismatch')
    return bundle

def write_bundle(bundle,destination):
    # Private explicit export area only; does not create an agent cache or outbox.
    destination=Path(destination)
    if destination.exists():raise HistoryError('history_export_destination_exists')
    destination.mkdir(parents=True)
    for i,chunk in enumerate(bundle['chunks']):(destination/(str(i)+'.json')).write_bytes(canonical(chunk))
    (destination/'manifest.json').write_bytes(canonical({'generationId':bundle['generationId'],'manifest':bundle['manifest']}))
