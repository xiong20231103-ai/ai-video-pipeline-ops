"""Per-batch compaction of the v3 evidence store, after the batch is concluded.

A batch's raw round-by-round snapshots are needed only until its replay and
comparison are concluded. Compaction keeps the named key snapshots (and every
snapshot outside the batch), retires the other indexes to a small audit folder
and removes objects that no remaining snapshot references.

Default is a dry run. Removal happens only with --apply, run by the user; it
never touches comparison results, diff reports, ready records or old v1/v2
evidence, and it refuses while a capture or store writer holds its lock.
"""
from __future__ import annotations
import argparse,json,os,re,sys
from datetime import datetime,timezone
from pathlib import Path
from agent.core.snapshot import canonical,no_links
from tools.shadow_capture_errors import CaptureError
from tools.shadow_store import referenced_objects

IDENTITY=re.compile('[0-9a-f]{64}')
CONCLUSIONS={'accepted','rejected','incomparable'}
MAX_INDEX=8*1024*1024


def _index(path):
    path=no_links(path)
    if path.stat().st_size>MAX_INDEX:raise CaptureError('chunk_manifest_limit')
    value=json.loads(path.read_bytes())
    if value.get('schema')!=1 or not isinstance(value.get('files'),dict):raise CaptureError('chunk_index_invalid')
    return value


def _verdict(path,drop,keep):
    """The batch conclusion must exist and cover every snapshot being touched."""
    path=no_links(path)
    if path.stat().st_size>1024*1024:raise CaptureError('verdict_size_limit')
    value=json.loads(path.read_text(encoding='utf-8-sig'))
    if (not isinstance(value,dict) or value.get('schema')!=1 or not isinstance(value.get('batchId'),str)
            or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',value['batchId'])
            or value.get('conclusion') not in CONCLUSIONS or not isinstance(value.get('snapshots'),list)):
        raise CaptureError('batch_verdict_invalid')
    if not set(drop)|set(keep)<=set(value['snapshots']):raise CaptureError('batch_verdict_does_not_cover_snapshots')
    return value


def plan_compaction(store,verdict_path,*,drop,keep):
    store=no_links(store)
    drop=list(dict.fromkeys(drop));keep=list(dict.fromkeys(keep))
    if not drop:raise CaptureError('nothing_to_compact')
    if not keep:raise CaptureError('key_snapshot_required')
    if any(not isinstance(i,str) or not IDENTITY.fullmatch(i) for i in drop+keep):raise CaptureError('snapshot_identity_invalid')
    if set(drop)&set(keep):raise CaptureError('snapshot_both_kept_and_dropped')
    verdict=_verdict(verdict_path,drop,keep)
    indexes={p.stem:p for p in (store/'snapshots').glob('*.json')}
    if any(i not in indexes for i in drop+keep):raise CaptureError('snapshot_not_in_store')
    needed=set()
    for identity,path in indexes.items():
        if identity not in drop:needed|=referenced_objects(store,_index(path))
    objects={p.name:p for p in (store/'objects').iterdir() if p.is_file()}
    unreferenced=sorted(set(objects)-needed)
    freed=sum(objects[k].stat().st_size for k in unreferenced)+sum(indexes[i].stat().st_size for i in drop)
    return {'schema':1,'batchId':verdict['batchId'],'conclusion':verdict['conclusion'],
            'dropSnapshots':drop,'keepSnapshots':keep,'remainingSnapshots':len(indexes)-len(drop),
            'objectsRemoved':len(unreferenced),'bytesFreed':freed,'_unreferenced':unreferenced}


def apply_compaction(store,plan,*,now=lambda:datetime.now(timezone.utc).isoformat()):
    store=no_links(store)
    # The capture publisher and the store writer use these exclusive locks.
    lock=store/'.writer.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:raise CaptureError('evidence_store_writer_busy') from None
    try:
        os.close(fd)
        if (store.parent/'.capture-writer.lock').exists():raise CaptureError('capture_writer_busy')
        retired=store/'retired'/plan['batchId'];retired.mkdir(parents=True,exist_ok=True)
        # Indexes first: a crash leaves extra objects (re-runnable), never a
        # published snapshot that points at removed objects.
        for identity in plan['dropSnapshots']:
            os.replace(store/'snapshots'/(identity+'.json'),retired/(identity+'.json'))
        for key in plan['_unreferenced']:(store/'objects'/key).unlink(missing_ok=True)
        record={k:v for k,v in plan.items() if not k.startswith('_')}
        record['appliedAt']=now()
        with (retired/'compaction.json').open('xb') as out:out.write(canonical(record))
        return record
    finally:lock.unlink(missing_ok=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--store',type=Path,required=True)
    parser.add_argument('--verdict',type=Path,required=True)
    parser.add_argument('--drop',action='append',default=[])
    parser.add_argument('--keep',action='append',default=[])
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args(argv)
    try:
        plan=plan_compaction(args.store,args.verdict,drop=args.drop,keep=args.keep)
        result=apply_compaction(args.store,plan) if args.apply else {**{k:v for k,v in plan.items() if not k.startswith('_')},'dryRun':True}
    except (CaptureError,OSError,ValueError) as error:
        print(json.dumps({'state':'refused','code':str(error) if isinstance(error,CaptureError) else 'compaction_input_error'}))
        return 1
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':sys.exit(main())
