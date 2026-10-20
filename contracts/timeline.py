"""Evidence-qualified timeline contract and analysis, independent of home/cloud."""
from datetime import datetime,timedelta,timezone
import hashlib,math,re,statistics
from .history import HistoryError,canonical,safe_facts
KINDS={'start','end','failed','human_wait_start','human_wait_end','pause','resume','status'}
PRECISIONS={'exact','observed','reported','heuristic'}
def timestamp(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        if result.utcoffset() is None:raise ValueError()
        return result
    except (ValueError,TypeError,AttributeError):raise HistoryError('timeline_timezone_required') from None
def event(value):
    required={'eventId','batchId','projectId','videoId','stage','attemptId','manifestId','kind','at','precision','uncertaintySeconds','errorCode','source','prefetch','reportedSeconds','outcome'}
    if not isinstance(value,dict) or set(value)!=required:raise HistoryError('invalid_timeline_event')
    for key in ('eventId','batchId','projectId','stage','attemptId'):
        if not isinstance(value[key],str) or not 1<=len(value[key])<=256:raise HistoryError('timeline_identity_required')
    if value['outcome'] not in {'unknown','success','failed'}:raise HistoryError('invalid_timeline_outcome')
    if value['kind'] not in KINDS or value['precision'] not in PRECISIONS or type(value['prefetch']) is not bool:raise HistoryError('invalid_timeline_kind')
    for key in ('videoId','manifestId','errorCode'):
        if not isinstance(value[key],str) or len(value[key])>256:raise HistoryError('invalid_timeline_identity')
    if value['errorCode'] and not re.fullmatch('[A-Z][A-Z0-9_]{1,120}',value['errorCode']):raise HistoryError('invalid_timeline_failure_code')
    timestamp(value['at']);source=value['source']
    if not isinstance(source,dict) or set(source)!={'sourceId','sha256','cursor','version','networkProfile'} or not re.fullmatch('[0-9a-f]{64}',str(source['sha256'])) or not isinstance(source['cursor'],str) or not isinstance(source['sourceId'],str):raise HistoryError('timeline_source_required')
    for key in ('uncertaintySeconds','reportedSeconds'):
        number=value[key]
        if number is not None and (type(number) not in (int,float) or not math.isfinite(number) or number<0):raise HistoryError('invalid_timeline_precision')
    if value['precision']=='exact' and value['uncertaintySeconds']!=0:raise HistoryError('invalid_exact_timeline_precision')
    if value['precision']=='observed' and (value['uncertaintySeconds'] is None or value['uncertaintySeconds']<=0):raise HistoryError('observed_uncertainty_required')
    try:safe_facts(value);canonical(value)
    except (ValueError,TypeError):raise HistoryError('unsafe_timeline_event') from None
    return value
def make_event(identity,kind,at,source,*,stage=None,precision='exact',uncertainty=0,error_code='',prefetch=False,reported=None,line_hash='',outcome='unknown'):
    # sourceId+cursor+line hash are stable across log appends; full-source SHA
    # remains evidence metadata, not a reason to count the same event twice.
    value={'batchId':identity.get('batchId',''),'projectId':identity.get('projectId',''),'videoId':identity.get('videoId',''),'stage':stage or identity.get('stage',''),'attemptId':identity.get('attemptId',''),'manifestId':identity.get('manifestId',''),'kind':kind,'at':at,'precision':precision,'uncertaintySeconds':uncertainty,'errorCode':error_code,'source':source,'prefetch':prefetch,'reportedSeconds':reported,'outcome':outcome}
    key={k:v for k,v in value.items() if k!='source'};key['sourceId']=source['sourceId'];key['cursor']=source['cursor'];key['lineHash']=line_hash
    return event({'eventId':hashlib.sha256(canonical(key)).hexdigest(),**value})
def union_seconds(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if end<start:raise HistoryError('negative_timeline_interval')
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    return sum(b-a for a,b in merged)
def analyze(events):
    unique={};issues=[]
    for item in events:
        event(item)
        if item['eventId'] in unique and unique[item['eventId']]!=item:raise HistoryError('timeline_event_identity_conflict')
        unique[item['eventId']]=item
    groups={}
    for item in unique.values():groups.setdefault(tuple(item[k] for k in ('batchId','projectId','videoId','stage','attemptId','manifestId')),[]).append(item)
    intervals=[];failures=[];waits=[];pauses=[];completed=[]
    for key,items in sorted(groups.items()):
        opened={};ambiguous=set()
        for item in sorted(items,key=lambda e:(timestamp(e['at']),e['source']['cursor'],e['eventId'])):
            at=timestamp(item['at']).timestamp();kind=item['kind']
            if kind=='failed':failures.append({'eventId':item['eventId'],'projectId':item['projectId'],'videoId':item['videoId'],'attemptId':item['attemptId'],'at':item['at'],'errorCode':item['errorCode']})
            start_kind={'start':'start','human_wait_start':'human_wait_start','pause':'pause'}.get(kind)
            if start_kind:
                if start_kind in opened:ambiguous.add(start_kind);issues.append({'code':'duplicate_start','eventId':item['eventId']})
                else:opened[start_kind]=item
            closing={'end':'start','human_wait_end':'human_wait_start','resume':'pause'}.get(kind)
            if closing:
                first=opened.pop(closing,None)
                if first is None:issues.append({'code':'missing_start','eventId':item['eventId']});continue
                elapsed=at-timestamp(first['at']).timestamp()
                exact=first['precision']=='exact' and item['precision']=='exact' and closing not in ambiguous
                error=(first['uncertaintySeconds'] or 0)+(item['uncertaintySeconds'] or 0)
                result={**dict(zip(('batchId','projectId','videoId','stage','attemptId','manifestId'),key)),'start':first['at'],'end':item['at'],'elapsedSeconds':elapsed if exact else None,'observedSpanSeconds':elapsed,'rangeSeconds':[max(0,elapsed-error),elapsed+error] if closing not in ambiguous else None,'precision':'exact' if exact else 'uncertain','reportedSeconds':item['reportedSeconds'],'outcome':item['outcome'],'startEventId':first['eventId'],'endEventId':item['eventId'],'prefetch':first['prefetch'],'version':first['source']['version'],'networkProfile':first['source']['networkProfile'],'stableVersion':first['source']['version']==item['source']['version'] and first['source']['networkProfile']==item['source']['networkProfile']}
                (intervals if closing=='start' else waits if closing=='human_wait_start' else pauses).append(result)
                if kind=='end' and item['outcome']=='success':completed.append(item)
                ambiguous.discard(closing)
        for kind,first in opened.items():issues.append({'code':'open_interval','kind':kind,'eventId':first['eventId'],'start':first['at'],'end':None,'elapsedSeconds':None})
    exact_ranges=[(timestamp(x['start']).timestamp(),timestamp(x['end']).timestamp()) for x in intervals if x['precision']=='exact']
    # Project/video time is interval union, never sums prefetch/parallel spans.
    by_project={};by_video={}
    for x in intervals:
        if x['precision']!='exact':continue
        span=(timestamp(x['start']).timestamp(),timestamp(x['end']).timestamp())
        by_project.setdefault((x['batchId'],x['projectId']),[]).append(span)
        if x['videoId']:by_video.setdefault((x['batchId'],x['projectId'],x['videoId']),[]).append(span)
    for span in intervals:
        blocked=any(wait['batchId']==span['batchId'] and wait['projectId']==span['projectId'] and (not wait['videoId'] or wait['videoId']==span['videoId']) and timestamp(wait['start'])<timestamp(span['end']) and timestamp(wait['end'])>timestamp(span['start']) for wait in waits+pauses)
        failed=any(f['projectId']==span['projectId'] and f['videoId']==span['videoId'] and timestamp(span['start'])<=timestamp(f['at'])<=timestamp(span['end']) for f in failures)
        span['eligibleForEta']=span['precision']=='exact' and span['outcome']=='success' and span['stableVersion'] and not blocked and not failed
    gaps=[];last={}
    for item in sorted(completed,key=lambda e:timestamp(e['at'])):
        key=(item['batchId'],item['projectId'],item['stage']);previous=last.get(key)
        if previous and item['stage']=='capcut' and (timestamp(item['at'])-timestamp(previous['at'])).total_seconds()>900:gaps.append({'projectId':item['projectId'],'start':previous['at'],'end':item['at'],'seconds':(timestamp(item['at'])-timestamp(previous['at'])).total_seconds(),'classification':'heuristic_unclassified_gap','isConfirmedHumanWait':False})
        last[key]=item
    return {'intervals':intervals,'failures':failures,'confirmedHumanWaits':waits,'deliberatePauses':pauses,'unclassifiedGaps':gaps,'issues':issues,'unionElapsedSeconds':union_seconds(exact_ranges),'projects':[{'batchId':k[0],'projectId':k[1],'unionElapsedSeconds':union_seconds(v)} for k,v in by_project.items()],'videos':[{'batchId':k[0],'projectId':k[1],'videoId':k[2],'unionElapsedSeconds':union_seconds(v)} for k,v in by_video.items()],'realShadowPassed':False}
def eta(analysis,remaining,*,version,network_profile,plan=None,paused=False,now=None):
    unavailable=lambda reason:{'available':False,'reason':reason,'seconds':None,'expectedAt':None}
    if paused:return unavailable('user_paused')
    if not version or not network_profile:return unavailable('source_version_unknown')
    if not isinstance(remaining,dict) or any(type(v) is not int or v<0 for v in remaining.values()):return unavailable('remaining_unknown')
    if plan is None or not isinstance(plan,list) or any(not isinstance(w,list) or not w for w in plan):return unavailable('execution_plan_unknown')
    stages=[s for wave in plan for s in wave]
    if len(stages)!=len(set(stages)) or set(stages)!=set(remaining):return unavailable('execution_plan_ambiguous')
    samples={}
    for row in analysis['intervals']:
        if row['eligibleForEta'] and row['elapsedSeconds']>0 and row['version']==version and row['networkProfile']==network_profile:samples.setdefault(row['stage'],[]).append(row['elapsedSeconds'])
    estimates={}
    for stage,count in remaining.items():
        if count==0:estimates[stage]=0;continue
        if len(samples.get(stage,[]))<3:return unavailable('insufficient_same_version_samples')
        estimates[stage]=statistics.median(samples[stage])*count
    seconds=sum(max(estimates[s] for s in wave) for wave in plan)
    return {'available':True,'conditional':True,'assumption':'same_version_network_and_declared_parallel_plan_no_future_failures_or_manual_wait','seconds':seconds,'expectedAt':(timestamp(now)+timedelta(seconds=seconds)).isoformat() if now else None,'version':version,'networkProfile':network_profile,'samples':{s:len(samples.get(s,[])) for s in remaining}}
