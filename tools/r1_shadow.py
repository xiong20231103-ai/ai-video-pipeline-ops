"""Explicit offline comparison only. Never starts a collector service."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.core.snapshot import Snapshot,canonical
from agent.core.replay import read_targets,replay
from agent.core.collection_replay import replay_collection
from agent.core.comparison import compare

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True,type=Path);parser.add_argument('--snapshot',required=True,type=Path);parser.add_argument('--scratch',required=True,type=Path);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(argv)
    if args.scratch.exists() or args.out.exists():raise ValueError('new_output_paths_required')
    snapshot=Snapshot(args.snapshot);source=args.source.read_text(encoding='utf-8');targets=read_targets(json.loads((Path(__file__).resolve().parents[1]/'contracts/endpoints.json').read_text(encoding='utf-8')))
    old=replay(source,snapshot,args.scratch/'old',targets);new=replay_collection(source,snapshot,args.scratch/'new',targets)
    delta=compare(old,new)
    result={'module':'R1','mode':'isolated','sourceIdentity':snapshot.manifest['sourceIdentity'],'cases':len(targets),'mismatchCount':len(delta),'differences':delta,'realShadowPassed':False,'switchAccepted':False}
    with args.out.open('xb') as stream:stream.write(canonical(result))
    print(json.dumps({'cases':len(targets),'mismatchCount':len(delta),'realShadowPassed':False,'switchAccepted':False}))
    return int(bool(delta))
if __name__=='__main__':raise SystemExit(main())
