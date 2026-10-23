"""CLI for explicit offline evidence operations. No default production paths."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.core.source_profiles import read_source
from tools.shadow_archive import archive_passive,verify_archive,capacity
from tools.shadow_capture import aligned_capture,CaptureError,_safe

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='operation',required=True)
 archive=sub.add_parser('archive-passive');archive.add_argument('--source',required=True,type=Path);archive.add_argument('--out',required=True,type=Path);archive.add_argument('--approved-max-bytes',required=True,type=int)
 verify=sub.add_parser('verify-archive');verify.add_argument('--archive',required=True,type=Path)
 quota=sub.add_parser('capacity');quota.add_argument('--retained-root',required=True,action='append',type=Path);quota.add_argument('--approved-total-bytes',required=True,type=int)
 review=sub.add_parser('review-batch');review.add_argument('--input',required=True,type=Path);review.add_argument('--out',required=True,type=Path)
 campaign=sub.add_parser('review-campaign');campaign.add_argument('--batch-review',required=True,action='append',type=Path);campaign.add_argument('--out',required=True,type=Path)
 capture=sub.add_parser('capture-recorded');capture.add_argument('--plan',required=True,type=Path);capture.add_argument('--source',required=True,type=Path);capture.add_argument('--observations',required=True,type=Path);capture.add_argument('--out',required=True,type=Path)
 compare=sub.add_parser('compare');compare.add_argument('--module',required=True,choices=['R1','R2','R3','R5']);compare.add_argument('--snapshot',required=True,type=Path);compare.add_argument('--source',required=True,type=Path);compare.add_argument('--scratch',required=True,type=Path);compare.add_argument('--out',required=True,type=Path);compare.add_argument('--targets',type=Path);compare.add_argument('--operation-record');compare.add_argument('--recipes',type=Path);compare.add_argument('--history-source',default='home');compare.add_argument('--sequence',type=int,default=1)
 args=parser.parse_args(argv)
 if args.operation in {'review-batch','review-campaign'}:
  from agent.core.snapshot import canonical,no_links,SnapshotError
  from tools.shadow_compare import batch_review,campaign_review
  def read_review(path):
   path=no_links(path)
   if path.stat().st_size>8*1024*1024:raise CaptureError('review_input_size_limit')
   try:
    value=json.loads(path.read_text(encoding='utf-8-sig'));_safe(value)
   except (SnapshotError,UnicodeError,json.JSONDecodeError) as error:raise CaptureError('review_input_rejected') from None
   return value
  if args.operation=='review-batch':
   data=read_review(args.input)
   if not isinstance(data,dict) or set(data)!={'reports','batchId','startedEvidence','completedEvidence'}:raise CaptureError('batch_review_input_schema')
   summary=batch_review(data['reports'],batch_id=data['batchId'],started_evidence=data['startedEvidence'],completed_evidence=data['completedEvidence'])
  else:
   if len(args.batch_review)>100:raise CaptureError('campaign_review_input_limit')
   summary=campaign_review([read_review(p) for p in args.batch_review])
  output=no_links(args.out)
  if output.exists():raise CaptureError('new_review_output_required')
  output.parent.mkdir(parents=True,exist_ok=True)
  with output.open('xb') as f:f.write(canonical(summary))
 elif args.operation=='compare':
  from agent.core.snapshot import Snapshot,no_links,canonical
  from tools.shadow_compare import compare_reads,compare_history
  from tools.shadow_commands import compare_recorded_command
  snapshot=Snapshot(args.snapshot)
  if args.scratch.exists() or args.out.exists():raise CaptureError('new_comparison_outputs_required')
  forbidden=[snapshot.root,no_links(args.source).parent,*[no_links(x) for x in snapshot.manifest['facts'].get('pathAliases',{})]]
  for output in [no_links(args.scratch),no_links(args.out)]:
   if any(output==base or output.is_relative_to(base) or base.is_relative_to(output) for base in forbidden):raise CaptureError('comparison_output_source_overlap')
  source=read_source(args.source)
  if args.module in {'R1','R5'}:
   if not args.targets:raise CaptureError('explicit_targets_file_required')
   targets=json.loads(args.targets.read_text(encoding='utf-8-sig'));summary=compare_reads(source,snapshot,args.scratch,targets,module=args.module)
  elif args.module=='R2':summary=compare_history(snapshot,args.scratch,source_id=args.history_source,sequence=args.sequence,recipes=json.loads(args.recipes.read_text(encoding='utf-8-sig')) if args.recipes else None)
  else:
   if not args.operation_record:raise CaptureError('snapshot_operation_record_required')
   summary=compare_recorded_command(source,snapshot,args.scratch,args.operation_record)
  args.out.parent.mkdir(parents=True,exist_ok=True)
  with args.out.open('xb') as f:f.write(canonical(summary))
 elif args.operation=='archive-passive':
  result=archive_passive(args.source,args.out,max_archive_bytes=args.approved_max_bytes);summary={k:result[k] for k in ['archiveIdentity','bytes','originalsRetained','deletedFiles','comparable','realShadowPassed','switchAccepted']}
 elif args.operation=='verify-archive':
  result=verify_archive(args.archive);summary={'archiveIdentity':result['archiveIdentity'],'files':len(result['files']),'verified':True,'realShadowPassed':False,'switchAccepted':False}
 elif args.operation=='capacity':summary=capacity(args.retained_root,approved_total_bytes=args.approved_total_bytes)
 else:
  def read(path):
   if path.stat().st_size>8*1024*1024:raise CaptureError('observation_descriptor_limit')
   value=json.loads(path.read_text(encoding='utf-8-sig'));_safe(value);return value
  plan=read(args.plan)
  def observation():
   data=read(args.observations)
   if set(data)!={'process','external'}:raise CaptureError('recorded_observation_schema')
   return data
  result=aligned_capture(plan,args.out,source_path=args.source,process_probe=lambda:observation()['process'],http_probe=lambda:observation()['external'])
  summary={'sourceIdentity':result.manifest['sourceIdentity'],'files':len(result.manifest['files']),'dependencyClosure':True,'mode':'recorded-inputs','realShadowPassed':False,'switchAccepted':False}
 print(json.dumps(summary,ensure_ascii=True));return 0
if __name__=='__main__':raise SystemExit(main())
