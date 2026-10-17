"""Code-only agent updates; task control belongs to the explicit PS wrapper."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

FILES=tuple('agent/'+name for name in ('__init__.py','configure.py','launcher.py','metrics.py','polling.py','readonly.py'))+(
    'contracts/__init__.py','contracts/cache.py','contracts/endpoints.json','deploy/agent-run.ps1','deploy/agent-task.ps1')

def reject_link(path):
    for item in (path,*path.parents):
        if item.exists() and (item.is_symlink() or getattr(item.lstat(),'st_file_attributes',0)&0x400):
            raise ValueError('Linked update path refused')

def validate(root,expected=None):
    root=Path(root).absolute();reject_link(root)
    manifest=json.loads((root/'deployment-manifest.json').read_text(encoding='utf-8-sig'))
    commit=manifest.get('commit','')
    if len(commit)!=40 or any(char not in '0123456789abcdef' for char in commit): raise ValueError('Invalid commit')
    if expected and commit!=expected: raise ValueError('Unexpected commit')
    if set(manifest.get('sha256',{}))!=set(FILES): raise ValueError('Unexpected source whitelist')
    for name in FILES:
        path=root/name;reject_link(path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256'][name]:
            raise ValueError('Source hash mismatch')
    return manifest

def copy_code(source,target):
    for name in (*FILES,'deployment-manifest.json'):
        destination=target/name;reject_link(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name(destination.name+'.ops-update')
        if temporary.exists(): raise ValueError('Unexpected code staging file')
        shutil.copyfile(source/name,temporary);temporary.replace(destination)

def prepare(source,target,backup,expected):
    source,target,backup=map(Path,(source,target,backup))
    new=validate(source,expected);old=validate(target)
    reject_link(backup);backup.mkdir(parents=True,exist_ok=False)
    copy_code(target,backup);validate(backup,old['commit'])
    shutil.copyfile(Path(__file__),backup/'agent_source_update.py')
    metadata={'target':str(target.absolute()),'source':str(source.absolute()),'before':old['commit'],'after':new['commit'],'at':datetime.now(timezone.utc).isoformat()}
    (backup/'operation.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return metadata

def apply(source,target,backup,expected):
    source,target,backup=map(Path,(source,target,backup))
    metadata=json.loads((backup/'operation.json').read_text(encoding='utf-8'))
    if str(target.absolute())!=metadata['target'] or expected!=metadata['after']: raise ValueError('Update identity mismatch')
    validate(source,expected);validate(target,metadata['before']);validate(backup,metadata['before'])
    try:
        copy_code(source,target);validate(target,expected)
    except BaseException:
        copy_code(backup,target);validate(target,metadata['before'])
        raise

def restore(backup,target):
    backup,target=map(Path,(backup,target))
    metadata=json.loads((backup/'operation.json').read_text(encoding='utf-8'))
    if str(target.absolute())!=metadata['target']: raise ValueError('Rollback target mismatch')
    validate(backup,metadata['before'])
    reject_link(target)
    current=json.loads((target/'deployment-manifest.json').read_text(encoding='utf-8-sig'))
    if current.get('commit') not in {metadata['before'],metadata['after']} or set(current.get('sha256',{}))!=set(FILES): raise ValueError('Rollback source identity changed')
    copy_code(backup,target);validate(target,metadata['before'])

def probe_lock():
    import os,msvcrt
    path=Path(os.environ['LOCALAPPDATA'])/'OpsAgent/agent.lock'
    with path.open('r+b') as handle:
        handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','apply','restore','probe'])
    parser.add_argument('--source');parser.add_argument('--target',default=r'E:\Backup\ops-agent');parser.add_argument('--backup');parser.add_argument('--commit')
    args=parser.parse_args()
    if Path(args.target).absolute()!=Path(r'E:\Backup\ops-agent').absolute(): raise ValueError('Only independent agent directory allowed')
    if args.action=='probe': probe_lock();return
    if args.action=='prepare': prepare(args.source,args.target,args.backup,args.commit)
    elif args.action=='apply': apply(args.source,args.target,args.backup,args.commit)
    else: restore(args.backup,args.target)
    print('Code-only agent '+args.action+' verified; private configuration was not read.')

if __name__=='__main__':
    try: main()
    except Exception: raise SystemExit('Agent source operation refused or failed; credentials were not read or logged') from None
