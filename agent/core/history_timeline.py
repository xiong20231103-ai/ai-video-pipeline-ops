"""Normalize explicit evidence. No filename-only task correlation or automatic recovery."""
import hashlib,json,re
from datetime import datetime,timezone
from contracts.timeline import make_event,timestamp
from contracts.history import HistoryError
from .snapshot import canonical

def capcut_task_events(value,source):
    # Core.cs VideoTask carries immutable ownership and attempt fields.
    identity={'batchId':value.get('ContractBatchId') or value.get('HandoffBatchId') or '', 'projectId':value.get('RemotePipelineTaskId') or '', 'videoId':value.get('CanonicalTaskId') or value.get('Id') or '', 'attemptId':value.get('HandoffAttemptId') or '', 'manifestId':value.get('HandoffManifestId') or '', 'stage':'capcut'}
    events=[];unresolved=[]
    for field,kind in (('StartedAt','start'),('FinishedAt','end')):
        at=value.get(field)
        if not at:
            unresolved.append({'field':field,'reason':'timestamp_missing'});continue
        try:
            timestamp(at)
            events.append(make_event(identity,kind,at,{**source,'cursor':source['cursor']+':'+field},outcome=('success' if str(value.get('State','')).lower()=='completed' else 'failed') if kind=='end' else 'unknown'))
        except HistoryError as error:unresolved.append({'field':field,'reason':error.code})
    if str(value.get('State','')).lower()=='failed':
        code=str(value.get('DraftTransactionErrorCode') or '')
        if not code:
            codes=set(re.findall(r'\b(?:CAPCUT|CAPTION|FFMPEG|SUBTITLE)_[A-Z0-9_]+\b',str(value.get('Error') or '')))
            if len(codes)==1:code=codes.pop()
        if value.get('FinishedAt') and code:
            try:events.append(make_event(identity,'failed',value['FinishedAt'],{**source,'cursor':source['cursor']+':failure'},error_code=code))
            except HistoryError as error:unresolved.append({'field':'failure','reason':error.code})
        else:unresolved.append({'field':'failure','reason':'failure_time_or_code_missing'})
    return events,unresolved

def sampled_task_history(rows,tasks,source,*,uncertainty_seconds=75,identity_by_row=None):
    if type(uncertainty_seconds) not in (int,float) or uncertainty_seconds<=0:raise HistoryError('sampling_interval_required')
    result=[];unresolved=[]
    for row in rows:
        identity=(identity_by_row or {}).get(row.get('id'))
        if identity is None:
            unresolved.append({'rowId':row.get('id'),'reason':'historical_attempt_identity_unproven'});continue
        identity={**identity,'stage':'capcut.'+str(row.get('state','unknown'))}
        try:result.append(make_event(identity,'status',row['recorded_at'],{**source,'cursor':str(row['id'])},precision='observed',uncertainty=uncertainty_seconds))
        except HistoryError as error:unresolved.append({'rowId':row.get('id'),'reason':error.code})
    return result,unresolved

def capcut_log_events(text,*,source_id,source_sha,version,network_profile,offset,contexts):
    # Explicit line-range contexts are required and reviewed against manifests.
    # No implicit last-active project or basename-only identity guess.
    events=[];unresolved=[];opened=None
    for number,line in enumerate(text.splitlines(),1):
        match=re.match(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3}) \[(INFO|WARN|ERROR)\] (.*)$',line)
        if not match:continue
        message=match[3];contexts_here=[c for c in contexts if c['firstLine']<=number<=c['lastLine']]
        if len(contexts_here)!=1:
            unresolved.append({'line':number,'reason':'missing_or_ambiguous_identity_context'});opened=None;continue
        context=contexts_here[0];identity=context['identity'];source={'sourceId':source_id,'sha256':source_sha,'cursor':str(number),'version':version,'networkProfile':network_profile}
        at=datetime.fromisoformat(match[1]).replace(tzinfo=timezone(offset)).isoformat()
        digest=hashlib.sha256(line.encode()).hexdigest()
        start=re.search(r': (.+)（第 (\d+) 次）$',message)
        end=re.match(r'^步骤完成: (.+)，耗时 (\d+(?:\.\d+)?)s$',message)
        if start:
            scoped={**identity,'attemptId':identity.get('attemptId','')+':step-'+start[2],'stage':context.get('stageByName',{}).get(start[1],'')}
            if not scoped['stage']:unresolved.append({'line':number,'reason':'unknown_step_name'});opened=None;continue
            events.append(make_event(scoped,'start',at,source,line_hash=digest));opened=(scoped,start[1])
        elif end:
            if opened is None or opened[1]!=end[1] or any(opened[0].get(k)!=identity.get(k) for k in ('batchId','projectId','videoId','manifestId')):unresolved.append({'line':number,'reason':'step_end_identity_unaligned'});continue
            events.append(make_event(opened[0],'end',at,source,reported=float(end[2]),line_hash=digest,outcome='success'));opened=None
        elif '任务失败:' in message:
            codes=re.findall(r'\b(?:CAPCUT|CAPTION|FFMPEG|SUBTITLE)_[A-Z0-9_]+\b',message)
            if len(set(codes))==1:events.append(make_event({**identity,'stage':context.get('stage','capcut')},'failed',at,source,error_code=codes[0],line_hash=digest))
            else:unresolved.append({'line':number,'reason':'missing_or_ambiguous_failure_code'})
    return events,unresolved


def structured_stage_events(rows,*,identity_fields,time_fields,source,stage,precision='exact',uncertainty=0):
    """Explicit mappings for download/subtitle/Fish/stitch/upload JSON/CSV rows.

    The caller must map immutable fields for this evidence version, not guess
    identity from directory name or use current task metadata for old records.
    Missing start/end stays missing and appears in diagnostics.
    """
    events=[];unresolved=[]
    for index,row in enumerate(rows):
        identity={target:str(row.get(field) or '') for target,field in identity_fields.items()}
        identity['stage']=stage
        for kind,field in time_fields.items():
            if kind not in {'start','end','failed','human_wait_start','human_wait_end','pause','resume'}:raise HistoryError('invalid_history_time_mapping')
            at=row.get(field)
            if not at:
                unresolved.append({'row':index,'field':field,'reason':'timestamp_missing'});continue
            try:events.append(make_event(identity,kind,at,{**source,'cursor':source['cursor']+':'+str(index)+':'+field},precision=precision,uncertainty=uncertainty,error_code=str(row.get('errorCode') or '') if kind=='failed' else '',outcome='success' if kind=='end' and str(row.get('status','')).lower() in {'completed','success'} else 'unknown'))
            except HistoryError as error:unresolved.append({'row':index,'field':field,'reason':error.code})
    return events,unresolved

def workbench_log_events(text,*,source,offset,contexts):
    """Source workbench.py log markers, line-scoped immutable identity required.

    These are log marker boundaries with 1-second resolution, not CPU time.
    Combined step1/2 cannot be split into download/subtitle without per-video
    bridge/run evidence; the label remains download_subtitle.
    """
    result=[];unresolved=[]
    markers=[
        ('后台任务已启动，共','download_subtitle','start'),
        ('第 1/2 步完成，正在按任务指令启动语音客户端','download_subtitle','end'),
        ('第 1/2 步完成，正在按任务指令启动语音客户端','voice','start'),
        ('步骤 3 已完成并交接：','voice','end'),
        ('Remote Step 4 started automatically; waiting for finished videos.','stitch','start'),
        ('第四步已交接到第五步：','stitch','end'),
        ('开始预取下一项目第 1/2 步：','download_subtitle','start'),
        ('预取结束：','download_subtitle','end')]
    for number,line in enumerate(text.splitlines(),1):
        match=re.match(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d) \[pid \d+\] (.*)$',line)
        if not match:continue
        matched=[(prefix,stage,kind) for prefix,stage,kind in markers if match[2].startswith(prefix)]
        if not matched:continue
        selected=[c for c in contexts if c['firstLine']<=number<=c['lastLine']]
        if len(selected)!=1:unresolved.append({'line':number,'reason':'missing_or_ambiguous_identity_context'});continue
        for prefix,stage,kind in matched:
            try:
                identity=selected[0]['identity'];at=datetime.fromisoformat(match[1]).replace(tzinfo=timezone(offset)).isoformat()
                prefetch=prefix.startswith(('开始预取','预取结束'))
                result.append(make_event(identity,kind,at,{**source,'cursor':str(number)+':'+stage+':'+kind},stage=stage,precision='reported',uncertainty=1,prefetch=prefetch,outcome='success' if kind=='end' else 'unknown',line_hash=hashlib.sha256(line.encode()).hexdigest()))
            except HistoryError as error:unresolved.append({'line':number,'reason':error.code})
    return result,unresolved


def normalize_snapshot(snapshot,recipes):
    """Normalize only explicitly declared snapshot inputs; no directory discovery.

    recipe describes the evidence schema/version and reviewed immutable identity
    mapping. Bad recipes fail; unresolved rows/lines are counted, never invented.
    """
    import csv,io
    from .snapshot import safe_facts
    if not isinstance(recipes,list) or len(recipes)>1000:raise HistoryError('invalid_history_recipes')
    safe_facts(recipes);events=[];issues=[]
    offset=timestamp(snapshot.manifest['frozenAt']).utcoffset()
    for recipe in recipes:
        path=recipe['path'];metadata=snapshot.manifest['files'].get(path)
        if metadata is None or metadata['kind']=='sqlite':raise HistoryError('history_recipe_source_undeclared')
        source={'sourceId':path,'sha256':metadata['sha256'],'cursor':'root','version':recipe['version'],'networkProfile':recipe['networkProfile']}
        raw=snapshot.read(path);format=recipe['format'];options=recipe.get('options',{})
        if format=='capcut_log':
            result,unresolved=capcut_log_events(raw.decode('utf-8-sig'),source_id=path,source_sha=source['sha256'],version=source['version'],network_profile=source['networkProfile'],offset=offset,contexts=options['contexts'])
        elif format=='workbench_log':result,unresolved=workbench_log_events(raw.decode('utf-8-sig'),source=source,offset=offset,contexts=options['contexts'])
        elif format in {'capcut_tasks','structured_json','structured_csv'}:
            if format=='structured_csv':rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
            else:
                rows=json.loads(raw)
                for key in options.get('rowsPath',[]):rows=rows[key]
            if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise HistoryError('history_recipe_rows_required')
            result=[];unresolved=[]
            if format=='capcut_tasks':
                for index,row in enumerate(rows):
                    normalized,missing=capcut_task_events(row,{**source,'cursor':str(index)});result.extend(normalized);unresolved.extend({'row':index,**item} for item in missing)
            else:result,unresolved=structured_stage_events(rows,identity_fields=options['identityFields'],time_fields=options['timeFields'],source=source,stage=options['stage'],precision=options.get('precision','exact'),uncertainty=options.get('uncertaintySeconds',0))
        else:raise HistoryError('unsupported_history_recipe_format')
        events.extend(result);issues.extend({'sourceId':path,**issue} for issue in unresolved)
    # Repeated recipe overlapping sources must not silently double-count.
    if len({e['eventId'] for e in events})!=len(events):raise HistoryError('duplicate_history_timeline_recipe')
    return events,{'status':'normalized-with-unresolved' if issues else 'normalized','recipeCount':len(recipes),'eventCount':len(events),'unresolvedCount':len(issues),'unresolved':issues[:200],'omittedDiagnosticCount':max(0,len(issues)-200)}
