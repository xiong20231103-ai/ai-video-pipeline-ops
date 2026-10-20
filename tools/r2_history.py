"""Manual offline export/import verification. No live discovery or service start."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.core.snapshot import Snapshot,canonical
from agent.core.history_export import build_bundle,write_bundle
from cloud.history import HistoryStore

def main(argv=None):
    parser=argparse.ArgumentParser();commands=parser.add_subparsers(dest='action',required=True)
    export=commands.add_parser('export');export.add_argument('--snapshot',type=Path,required=True);export.add_argument('--source',required=True);export.add_argument('--sequence',type=int,required=True);export.add_argument('--out',type=Path,required=True);export.add_argument('--recipes',type=Path)
    restore=commands.add_parser('verify-import');restore.add_argument('--package',type=Path,required=True);restore.add_argument('--new-db',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.action=='export':
        bundle=build_bundle(Snapshot(args.snapshot),source=args.source,sequence=args.sequence,recipes=json.loads(args.recipes.read_text(encoding='utf-8')) if args.recipes else None);write_bundle(bundle,args.out)
        result={'generationId':bundle['generationId'],'rows':bundle['manifest']['summary']['rowCount'],'coverage':bundle['manifest']['coverage'],'realShadowPassed':False,'switchAccepted':False}
    else:
        if args.new_db.exists():raise ValueError('new_isolated_history_db_required')
        wrapper=json.loads((args.package/'manifest.json').read_text(encoding='utf-8'));store=HistoryStore(args.new_db);reply=store.begin(wrapper['manifest'])
        if reply['generationId']!=wrapper['generationId']:raise ValueError('history_package_identity_mismatch')
        for i in range(reply['expectedChunks']):store.put(reply['generationId'],i,json.loads((args.package/(str(i)+'.json')).read_text(encoding='utf-8')))
        result=store.finish(reply['generationId']);result.update(realShadowPassed=False,switchAccepted=False,legacySourceChanged=False)
    print(json.dumps(result,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
