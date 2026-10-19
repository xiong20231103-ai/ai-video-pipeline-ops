"""Verified source replacement and cooperative stop. No credential reads or task kills."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid
try:import agent_state_io as state_io
except ModuleNotFoundError:from contracts import state_files as state_io

LEGACY_FILES=tuple('agent/'+name for name in ('__init__.py','configure.py','launcher.py','metrics.py','polling.py','readonly.py'))+(
    'contracts/__init__.py','contracts/cache.py','contracts/endpoints.json','deploy/agent-run.ps1','deploy/agent-task.ps1')
PREVIOUS_FILES=LEGACY_FILES+('agent/lifecycle.py','deploy/AgentJobRunner.cs')
CURRENT_FILES=PREVIOUS_FILES+('contracts/state_files.py','deploy/agent-json.ps1')
BACKUP_FILES=CURRENT_FILES+tuple('agent/'+name for name in ('backup_crypto.py','backup_policy.py','backup_setup.py','backup_snapshot.py','backup_runtime.py','backup_pack.py','backup_restore.py'))+('contracts/backup_crypto.py',)

FILES=BACKUP_FILES+('agent/execution.py','contracts/commands.py')

class UpdateError(ValueError):
    def __init__(self,code): self.code=code;super().__init__(code)

def reject_link(path):
    for item in (path,*path.parents):
        if item.is_symlink() or item.exists() and getattr(item.lstat(),'st_file_attributes',0)&0x400:
            raise UpdateError('linked_update_path')

def read_json(path):
    reject_link(Path(path));return state_io.read_json(path)

def validate(root,expected=None):
    root=Path(root).absolute();reject_link(root)
    manifest=read_json(root/'deployment-manifest.json');commit=manifest.get('commit','')
    if len(commit)!=40 or any(char not in '0123456789abcdef' for char in commit): raise UpdateError('invalid_commit')
    if expected and commit!=expected: raise UpdateError('unexpected_commit')
    names=set(manifest.get('sha256',{}))
    if names not in (set(LEGACY_FILES),set(PREVIOUS_FILES),set(CURRENT_FILES),set(BACKUP_FILES),set(FILES)): raise UpdateError('unexpected_source_whitelist')
    for name in names:
        path=root/name;reject_link(path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256'][name]:
            raise UpdateError('source_hash_mismatch')
    return manifest

def copy_code(source,target):
    names=validate(source)['sha256']
    for name in (*names,'deployment-manifest.json'):
        destination=target/name;reject_link(destination)
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.ops-update')
        try:
            shutil.copyfile(source/name,temporary);temporary.replace(destination)
        finally: temporary.unlink(missing_ok=True)
    # Remove only the explicitly known additive runtime files on rollback.
    for name in set(FILES)-set(names):
        destination=target/name;reject_link(destination);destination.unlink(missing_ok=True)

def prepare(source,target,backup,expected):
    source,target,backup=map(Path,(source,target,backup))
    new=validate(source,expected);old=validate(target)
    reject_link(backup);backup.mkdir(parents=True,exist_ok=False)
    copy_code(target,backup);validate(backup,old['commit'])
    shutil.copyfile(Path(__file__),backup/'agent_source_update.py')
    shutil.copyfile(Path(state_io.__file__),backup/'agent_state_io.py')
    metadata={'target':str(target.absolute()),'source':str(source.absolute()),'before':old['commit'],'after':new['commit'],
        'requestId':uuid.uuid4().hex,'at':datetime.now(timezone.utc).isoformat()}
    (backup/'operation.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return metadata

def apply(source,target,backup,expected):
    source,target,backup=map(Path,(source,target,backup));metadata=read_json(backup/'operation.json')
    if str(target.absolute())!=metadata['target'] or expected!=metadata['after']: raise UpdateError('update_identity_mismatch')
    validate(source,expected);validate(target,metadata['before']);validate(backup,metadata['before'])
    try:
        copy_code(source,target);validate(target,expected)
    except BaseException:
        copy_code(backup,target);validate(target,metadata['before']);raise

def restore(backup,target):
    backup,target=map(Path,(backup,target));metadata=read_json(backup/'operation.json')
    if str(target.absolute())!=metadata['target']: raise UpdateError('rollback_target_mismatch')
    validate(backup,metadata['before']);reject_link(target)
    current=read_json(target/'deployment-manifest.json')
    if current.get('commit') not in {metadata['before'],metadata['after']} or set(current.get('sha256',{})) not in (set(LEGACY_FILES),set(PREVIOUS_FILES),set(CURRENT_FILES),set(FILES)):
        raise UpdateError('rollback_source_identity_changed')
    copy_code(backup,target);validate(target,metadata['before'])

def atomic_json(path,value):
    reject_link(path);state_io.atomic_json(path,value)

@contextmanager
def exclusive_agent_lock(state):
    path=Path(state)/'agent.lock';reject_link(path)
    with path.open('a+b') as handle:
        if path.stat().st_size==0: handle.write(b'0');handle.flush()
        handle.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try: yield
        finally:
            handle.seek(0)
            if os.name=='nt': msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)

def begin_stop(state,request_id):
    state=Path(state);reject_link(state)
    if not state.is_dir(): raise UpdateError('private_state_directory_missing')
    runtime=state/'execution-runtime.json'
    if runtime.exists() and read_json(runtime).get('phase') in {'sending','awaiting_ack','unknown'}:
        raise UpdateError('pause_cloud_and_drain_commands_before_update')
    path=state/'maintenance.json'
    if path.exists():
        if read_json(path).get('requestId')!=request_id: raise UpdateError('another_maintenance_request_exists')
    else:
        with path.open('x',encoding='utf-8') as handle:
            json.dump({'schema':1,'requestId':request_id},handle);handle.flush();os.fsync(handle.fileno())
    atomic_json(state/'stop-request.json',{'schema':1,'requestId':request_id,'requestedAt':datetime.now(timezone.utc).isoformat()})

def wait_stopped(state,request_id,timeout=8):
    state=Path(state);started=time.monotonic()
    while True:
        try:
            with exclusive_agent_lock(state): pass
            try: runtime=read_json(state/'agent-runtime.json')
            except (FileNotFoundError,ValueError): runtime={}
            return {'lockFree':True,'elapsedSeconds':time.monotonic()-started,
                'cooperativeAck':runtime.get('phase')=='stopped' and runtime.get('stopRequestId')==request_id}
        except (PermissionError,BlockingIOError):
            if time.monotonic()-started>=timeout: raise UpdateError('graceful_stop_timeout_no_code_replaced') from None
            time.sleep(.1)

def verify_maintenance(state,request_id):
    if read_json(Path(state)/'maintenance.json').get('requestId')!=request_id: raise UpdateError('maintenance_identity_changed')

def finish(state,request_id):
    state=Path(state);verify_maintenance(state,request_id)
    for name in ('stop-request.json','maintenance.json'):
        path=state/name
        if path.exists():
            if read_json(path).get('requestId')!=request_id: raise UpdateError('stop_identity_changed')
            path.unlink()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','prepare','request-stop','wait','apply','restore','finish','probe','bootstrap','bootstrap-restore'])
    parser.add_argument('--source');parser.add_argument('--target',default=r'E:\Backup\ops-agent');parser.add_argument('--backup');parser.add_argument('--commit')
    args=parser.parse_args();target=Path(args.target)
    if target.absolute()!=Path(r'E:\Backup\ops-agent').absolute(): raise UpdateError('independent_directory_only')
    state=Path(os.environ['LOCALAPPDATA'])/'OpsAgent'
    if args.action=='inspect':
        manifest=validate(target)
        print(json.dumps({'commit':manifest['commit'],'supportsGracefulStop':'agent/lifecycle.py' in manifest['sha256']}));return
    if args.action=='prepare':
        metadata=prepare(args.source,target,args.backup,args.commit)
        print(json.dumps({'prepared':True,'requestId':metadata['requestId']}));return
    if args.action=='probe':
        with exclusive_agent_lock(state): pass
        print('{"lockFree":true}');return
    metadata=read_json(Path(args.backup)/'operation.json');request_id=metadata['requestId']
    if metadata['target']!=str(target.absolute()): raise UpdateError('operation_target_mismatch')
    if args.action in {'bootstrap','bootstrap-restore'}:
        import ctypes
        if os.name!='nt' or not ctypes.windll.shell32.IsUserAnAdmin(): raise UpdateError('one_time_migration_requires_elevation')
        with exclusive_agent_lock(state):
            begin_stop(state,request_id)
            if args.action=='bootstrap': apply(args.source,target,args.backup,args.commit)
            else: restore(args.backup,target)
        print(json.dumps({'result':'verified','action':args.action}));return
    if args.action=='request-stop':
        if 'agent/lifecycle.py' not in validate(target)['sha256']: raise UpdateError('legacy_agent_needs_one_time_migration')
        begin_stop(state,request_id)
    elif args.action=='wait': print(json.dumps(wait_stopped(state,request_id)));return
    elif args.action=='finish': finish(state,request_id)
    else:
        verify_maintenance(state,request_id)
        with exclusive_agent_lock(state):
            if args.action=='apply': apply(args.source,target,args.backup,args.commit)
            else: restore(args.backup,target)
    print(json.dumps({'result':'verified','action':args.action}))

if __name__=='__main__':
    try: main()
    except Exception as error:
        print(json.dumps({'result':'refused','reason':error.code if isinstance(error,UpdateError) else type(error).__name__}),flush=True)
        raise SystemExit(1) from None
