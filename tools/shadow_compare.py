"""Offline paired comparisons. Failure/absent facts are blockers, never zero cases.

Reports retain differing field paths and hashes, not raw production values.
There is no switch, remote transport, process launcher or deployment entry.
"""
from __future__ import annotations
import hashlib,json,base64
from pathlib import Path
from agent.core.snapshot import Snapshot,canonical,sqlite_rows
from agent.core.replay import replay
from agent.core.collection_replay import replay_collection
from agent.core.cleanup import replay_cleanup
from agent.core.comparison import compare
from tools.shadow_capture import CaptureError

READ_MODULES={'R1':replay_collection,'R5':replay_cleanup}

def _delta(old,new):
 rows=compare(old,new)
 # Keep no raw values or credentials in summaries. Full comparison occurs in memory.
 return {'mismatchCount':len(rows),'differingPaths':[row['path'] if isinstance(row,dict) and 'path' in row else str(row).split(':',1)[0] for row in rows[:1000]],'diagnosticsTruncated':len(rows)>1000}

def compare_reads(source,snapshot,scratch,targets,*,module='R1'):
 if module not in READ_MODULES or not targets or len(set(targets))!=len(targets):raise CaptureError('explicit_read_comparison_targets_required')
 snapshot=Snapshot(snapshot.root);scratch=Path(scratch)
 if scratch.exists():raise CaptureError('comparison_scratch_must_be_new')
 base={'schema':1,'module':module,'sourceIdentity':snapshot.manifest['sourceIdentity'],'candidateSourceIdentity':snapshot.manifest['sourceIdentity'],'legacySha256':snapshot.manifest['legacySha256'],'targets':list(targets),'caseCount':0,'mismatchCount':None,'comparable':False,'realShadowPassed':False,'switchAccepted':False}
 if snapshot.manifest['facts'].get('dependencyClosure') is not True:return {**base,'status':'incomplete','blockers':['dependency_closure_not_enforced']}
 try:
  old=replay(source,snapshot,scratch/'old',targets);new=READ_MODULES[module](source,snapshot,scratch/'new',targets)
 except Exception as error:
  # Identical exceptions on two sides must never produce a pass.
  return {**base,'status':'incomplete','blockers':['replay_failed:'+type(error).__name__]}
 delta=_delta(old,new)
 return {**base,**delta,'status':'different' if delta['mismatchCount'] else 'zero-difference','caseCount':len(targets),'comparable':True,'blockers':[],'oldResultSha256':hashlib.sha256(canonical(old)).hexdigest(),'newResultSha256':hashlib.sha256(canonical(new)).hexdigest()}

def compare_history(snapshot,scratch,*,source_id,sequence,recipes=None):
 """Independent lossless source/import check, not timeline accuracy acceptance."""
 from agent.core.history_export import build_bundle,JSON_EVIDENCE
 from cloud.history import HistoryStore
 from fnmatch import fnmatchcase
 snapshot=Snapshot(snapshot.root);scratch=Path(scratch)
 base={'schema':1,'module':'R2','sourceIdentity':snapshot.manifest['sourceIdentity'],'candidateSourceIdentity':snapshot.manifest['sourceIdentity'],'caseCount':0,'mismatchCount':None,'comparable':False,'realShadowPassed':False,'switchAccepted':False}
 if scratch.exists():raise CaptureError('comparison_scratch_must_be_new')
 try:
  bundle=build_bundle(snapshot,source=source_id,sequence=sequence,recipes=recipes)
  store=HistoryStore(scratch/'history.db');reply=store.begin(bundle['manifest']);generation=reply['generationId']
  for pos,chunk in enumerate(bundle['chunks']):store.put(generation,pos,chunk)
  store.finish(generation)
  def listed(kind):
   rows={};after=''
   while True:
    page=store.listing(source_id,kind,limit=1000,after=after,generation=generation)
    for row in page['items']:
     if row['key'] in rows:raise CaptureError('duplicate_history_result')
     rows[row['key']]=row['value']
    if not page['next']:return rows
    after=page['next']
  differences=[];cases=0
  db=snapshot.manifest['files'].get('repository/data/ops.db')
  if not db or db['kind']!='sqlite':raise CaptureError('history_source_database_missing')
  # Re-read baseline tables directly; do not compare the exporter against itself.
  for table,rows in sqlite_rows(snapshot.root/'repository/data/ops.db').items():
   key_name={'tasks':'task_id','source_health':'path','sqlite_sequence':'name'}.get(table,'id');expected={str(row[key_name]):row for row in rows};actual=listed('ops.'+table);delta=_delta(expected,actual);cases+=len(rows);differences.extend('ops.'+table+':'+p for p in delta['differingPaths'])
  imported=listed('evidence');grouped={}
  for row in imported.values():grouped.setdefault(row['path'],[]).append(row)
  expected_paths={name for name in snapshot.manifest['files'] if name.endswith(('.json','.csv')) and any(fnmatchcase(name,pattern) for pattern in JSON_EVIDENCE)}
  if set(grouped)!=expected_paths:differences.append('history.evidence.paths')
  for name in expected_paths:
   pieces=sorted(grouped.get(name,[]),key=lambda x:x['index'])
   if not pieces or [x['index'] for x in pieces]!=list(range(pieces[0]['parts'])):differences.append(name+':parts');continue
   actual=b''.join(base64.b64decode(x['data'],validate=True) for x in pieces);cases+=1
   if actual!=snapshot.read(name):differences.append(name+':bytes')
  norm=bundle['manifest']['coverage']['timelineNormalization']
  timeline=listed('timeline')
  if recipes and (norm.get('unresolvedCount')!=0 or not timeline):return {**base,'status':'incomplete','blockers':['timeline_sources_unresolved_or_empty'],'losslessSourceCases':cases}
  # Transport/retention parity is separate from validating independently known durations.
  return {**base,'status':'different' if differences else 'lossless-source-match','comparable':True,'caseCount':cases,'mismatchCount':len(differences),'differingPaths':differences[:1000],'timelineEventCount':len(timeline),'timelineAccuracyAccepted':False,'blockers':[],'generationId':generation}
 except Exception as error:return {**base,'status':'incomplete','blockers':['history_compare_failed:'+type(error).__name__]}

def batch_review(reports,*,batch_id,started_evidence,completed_evidence,required_modules=('R1','R2','R3','R5')):
 """Conservative review checklist. Never grants an automatic production switch."""
 blockers=[];modules={};started=started_evidence or {};completed=completed_evidence or {}
 if not batch_id or started.get('batchId')!=batch_id or completed.get('batchId')!=batch_id:blockers.append('batch_boundary_identity_missing_or_mismatched')
 if not started.get('sourceIdentity') or not completed.get('sourceIdentity') or not started.get('observedAt') or not completed.get('observedAt'):blockers.append('batch_boundary_capture_missing')
 if not completed.get('completeTaskIds') or set(started.get('expectedTaskIds',[]))!=set(completed.get('completeTaskIds',[])):blockers.append('complete_batch_tasks_not_observed')
 for module in required_modules:
  rows=[r for r in reports if r.get('module')==module and r.get('batchId')==batch_id]
  good=rows and all(r.get('comparable') is True and type(r.get('mismatchCount')) is int and r['mismatchCount']==0 and type(r.get('caseCount')) is int and r['caseCount']>0 and r.get('sourceIdentity')==r.get('candidateSourceIdentity') and r.get('sourceIdentity') and r.get('dependencyClosureVerified') is True and r.get('observedTriggerIds') and r.get('realBatchEvidence') is True for r in rows)
  if module=='R2' and rows:good=good and all(r.get('timelineAccuracyAccepted') is True for r in rows)
  modules[module]={'status':'ready-for-human-review' if good else 'not-accepted','comparisonWindows':len(rows),'actualTriggers':sum(len(r.get('observedTriggerIds',[])) for r in rows)}
  if not good:blockers.append('missing_actual_trigger_or_comparison:'+module)
 return {'schema':1,'batchId':batch_id,'modules':modules,'blockers':blockers,'readyForHumanReview':not blockers,'realShadowPassed':False,'switchAccepted':False,'requiredRealBatches':2}
