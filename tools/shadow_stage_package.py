"""Stage a reviewed Git-object-only shadow runtime package. Does not install/start."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess
from tools.shadow_capture import CaptureError
from agent.core.snapshot import no_links,canonical

def stage(repository,commit,out):
    repository=no_links(repository);out=no_links(out)
    if not re.fullmatch('[a-f0-9]{40}',commit):raise CaptureError('exact_reviewed_commit_required')
    if out.exists() or out==repository or out.is_relative_to(repository) or repository.is_relative_to(out):raise CaptureError('fresh_package_outside_repository_required')
    def git(*args):return subprocess.check_output(['git','-C',str(repository),*args],stderr=subprocess.DEVNULL)
    if git('rev-parse',commit+'^{commit}').decode().strip()!=commit:raise CaptureError('commit_not_available')
    names=git('ls-tree','-r','--name-only','-z',commit).decode('utf-8').split('\0');files={}
    for name in names:
        if not name:continue
        accepted=(name.startswith(('agent/','contracts/','tools/','cloud/')) and name.endswith('.py')) or name in {'pending_delete.py','cleanup_tickets.py','verified_final.py','requirements.txt','cloud/requirements.txt','cloud/requirements-test.txt'} or (name.startswith('contracts/legacy-') and name.endswith('.txt'))
        if not accepted:continue
        if any(part in {'..','.git','__pycache__'} for part in name.split('/')):raise CaptureError('invalid_package_path')
        mode=git('ls-tree',commit,'--',name).decode().split()[0]
        if mode not in {'100644','100755'}:raise CaptureError('package_link_or_special_file')
        raw=git('show',commit+':'+name)
        if len(raw)>2*1024*1024:raise CaptureError('package_source_limit')
        files[name]=raw
    for required in ['agent/readonly.py','tools/shadow_capture_runtime.py','tools/shadow_replay_worker.py','tools/shadow_agent_observer.py']:
        if required not in files:raise CaptureError('runtime_dependency_missing')
    if sum(map(len,files.values()))>32*1024*1024:raise CaptureError('package_total_limit')
    out.mkdir(parents=True)
    manifest={'schema':1,'sourceCommit':commit,'installed':False,'enabled':False,'realShadowPassed':False,'files':{}}
    for name,raw in sorted(files.items()):
        path=out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        manifest['files'][name]=hashlib.sha256(raw).hexdigest()
    (out/'shadow-package.json').write_bytes(canonical(manifest))
    return {'sourceCommit':commit,'files':len(files),'installed':False,'enabled':False,'realShadowPassed':False}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',required=True,type=Path);p.add_argument('--commit',required=True);p.add_argument('--out',required=True,type=Path);a=p.parse_args(argv)
    try:print(json.dumps(stage(a.repository,a.commit,a.out)))
    except Exception:print('{"state":"blocked","code":"shadow_package_rejected"}');return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
