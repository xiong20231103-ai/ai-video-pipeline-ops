"""Manual additive R0 tooling. Never installs, starts or switches an engine."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.core.snapshot import capture,Snapshot,canonical
from agent.core.replay import replay,read_targets
from agent.core.comparison import compare,evidence_gate

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    cap=sub.add_parser('capture');cap.add_argument('--recipe',type=Path,required=True);cap.add_argument('--out',type=Path,required=True)
    run=sub.add_parser('replay');run.add_argument('--source',type=Path,required=True);run.add_argument('--snapshot',type=Path,required=True);run.add_argument('--scratch',type=Path,required=True);run.add_argument('--out',type=Path,required=True)
    diff=sub.add_parser('compare');diff.add_argument('--expected',type=Path,required=True);diff.add_argument('--actual',type=Path,required=True);diff.add_argument('--out',type=Path,required=True)
    gate=sub.add_parser('gate');gate.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.action=='capture':
        spec=json.loads(args.recipe.read_text(encoding='utf-8'))
        snap=capture(args.out,files=spec.get('files'),databases=spec.get('databases'),facts=spec['facts'],frozen_at=spec['frozenAt'],legacy_sha256=spec['legacySha256'])
        print(json.dumps({'schema':2,'sourceIdentity':snap.manifest['sourceIdentity'],'files':len(snap.manifest['files']),'mode':'isolated','realShadowPassed':False}));return 0
    if args.action=='replay':
        contract=json.loads((Path(__file__).resolve().parents[1]/'contracts/endpoints.json').read_text(encoding='utf-8'))
        result=replay(args.source.read_text(encoding='utf-8'),Snapshot(args.snapshot),args.scratch,read_targets(contract))
    elif args.action=='compare':
        left=json.loads(args.expected.read_text(encoding='utf-8'));right=json.loads(args.actual.read_text(encoding='utf-8'))
        if left.get('sourceIdentity')!=right.get('sourceIdentity'):raise ValueError('unaligned_source_identity')
        changes=compare(left,right);result={'mode':'isolated','mismatchCount':len(changes),'differences':changes,'realShadowPassed':False,'switchAccepted':False}
    else:
        report=json.loads(args.report.read_text(encoding='utf-8'))
        targets=read_targets(json.loads((Path(__file__).resolve().parents[1]/'contracts/endpoints.json').read_text(encoding='utf-8')))
        blockers=evidence_gate(report,targets);print(json.dumps({'blockers':blockers,'switchExecuted':False}));return 1 if blockers else 0
    if args.out.exists():raise ValueError('output_exists_no_overwrite')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('xb') as output:output.write(canonical(result)+b'\n')
    print(json.dumps({'mode':'isolated','targets':len(result.get('responses',{})),'mismatchCount':result.get('mismatchCount'),'realShadowPassed':False,'switchAccepted':False}))
    return 1 if result.get('mismatchCount',0) else 0

if __name__=='__main__':raise SystemExit(main())
