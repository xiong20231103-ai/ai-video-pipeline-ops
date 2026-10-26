"""Offline consumer for retained capture queue. Execute only as a separate process."""
from pathlib import Path
import argparse,json,os,re,tempfile
from agent.core.source_profiles import read_source
from agent.core.snapshot import canonical,no_links
from tools.shadow_capture import CaptureError,_safe
from tools.shadow_store import materialize_snapshot,usage
from tools.shadow_compare import compare_reads,compare_history

def compare_ready(evidence,identity,source,*,module,targets=(),approved_scratch_bytes,retained_limit_bytes,
                  read_compare=compare_reads,history_compare=compare_history):
    root=no_links(evidence);source=no_links(source)
    if not re.fullmatch('[a-f0-9]{64}',identity):raise CaptureError('snapshot_identity_invalid')
    if module not in {'R1','R2','R5'}:raise CaptureError('read_module_required')
    if approved_scratch_bytes<1 or retained_limit_bytes<1:raise CaptureError('capacity_required')
    marker=no_links(root/'ready'/(identity+'.json'))
    if marker.stat().st_size>2048:raise CaptureError('ready_marker_limit')
    value=json.loads(marker.read_bytes());_safe(value)
    if value.get('sourceIdentity')!=identity or type(value.get('emitterPid')) is not int or value['emitterPid']==os.getpid():raise CaptureError('separate_replay_process_required')
    index=no_links(root/'store/snapshots'/(identity+'.json'))
    if index.stat().st_size>8*1024*1024:raise CaptureError('manifest_limit')
    manifest=json.loads(index.read_bytes())['snapshot'];total=sum(x['size'] for x in manifest['files'].values())
    # Four scratch copies plus result/SQLite/index overhead; no inferred quota expansion.
    if 4*total+16*1024*1024>approved_scratch_bytes:raise CaptureError('replay_scratch_budget_exhausted')
    if usage(root)+approved_scratch_bytes+4*1024*1024>retained_limit_bytes:raise CaptureError('replay_retained_budget_exhausted')
    if any(root==p or root.is_relative_to(p) or p.is_relative_to(root) for p in [source.parent]):raise CaptureError('replay_source_overlap')
    out=root/'reports'/module/(identity+'.json')
    if out.exists():raise CaptureError('report_already_exists_query_only')
    with tempfile.TemporaryDirectory(prefix='.offline-replay-',dir=root) as folder:
        scratch=Path(folder);snapshot=materialize_snapshot(root/'store',identity,scratch/'snapshot')
        text=read_source(source)
        if module=='R2':report=history_compare(snapshot,scratch/'comparison',source_id='home',sequence=1)
        else:report=read_compare(text,snapshot,scratch/'comparison',list(targets),module=module)
        report={**report,'realShadowPassed':False,'switchAccepted':False,'captureSourceIdentity':identity,'module':module}
        _safe(report);raw=canonical(report)
        if len(raw)>4*1024*1024:raise CaptureError('report_byte_limit')
        out.parent.mkdir(parents=True,exist_ok=True)
        # Publish only the final report. No live state or snapshot is removed.
        temporary=scratch/'report.json';temporary.write_bytes(raw)
        # Hard link is atomic and refuses replacement when another consumer won.
        os.link(temporary,out)
    return report

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--identity',required=True);p.add_argument('--source',type=Path,required=True);p.add_argument('--module',choices=['R1','R2','R5'],required=True);p.add_argument('--target',action='append',default=[]);p.add_argument('--approved-scratch-bytes',type=int,required=True);p.add_argument('--retained-limit-bytes',type=int,required=True)
    a=p.parse_args(argv)
    try:
        result=compare_ready(a.evidence,a.identity,a.source,module=a.module,targets=a.target,approved_scratch_bytes=a.approved_scratch_bytes,retained_limit_bytes=a.retained_limit_bytes)
        print(json.dumps({k:result.get(k) for k in ['module','status','caseCount','mismatchCount','realShadowPassed','switchAccepted']}))
    except Exception:
        print(json.dumps({'status':'blocked','code':'offline_replay_rejected','realShadowPassed':False}));return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
