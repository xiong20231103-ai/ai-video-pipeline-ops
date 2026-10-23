"""Reviewed optional entry. Only preparation failures authorize legacy fallback."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


def plain_path(value):
    path=Path(value).absolute()
    for part in (path,*path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.stat(),'st_file_attributes',0)&1024):
            raise ValueError('linked_bootstrap_path')
    return path


def read_json(path,limit=1024*1024):
    path=plain_path(path)
    if path.stat().st_size>limit:raise ValueError('bootstrap_json_limit')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verified_settings(path):
    value=read_json(path)
    required={'schema','enabled','mode','sourceCommit','packageRoot','packageManifestSha256','planPath','planSha256'}
    if (not isinstance(value,dict) or set(value)!=required or value['schema']!=1
            or type(value['enabled']) is not bool or value['mode'] not in {'preflight','observe'}
            or not re.fullmatch('[a-f0-9]{40}',value['sourceCommit'])
            or any(not re.fullmatch('[a-f0-9]{64}',value[k]) for k in ('packageManifestSha256','planSha256'))):
        raise ValueError('bootstrap_settings_invalid')
    if value['mode']=='observe' and not value['enabled']:raise ValueError('disabled_use_original_entry')
    if value['mode']=='preflight' and value['enabled']:raise ValueError('preflight_must_be_disabled')
    package=plain_path(value['packageRoot']);manifest_path=package/'shadow-package.json'
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=value['packageManifestSha256']:
        raise ValueError('bootstrap_manifest_hash_mismatch')
    manifest=read_json(manifest_path,2*1024*1024)
    if manifest.get('schema')!=1 or manifest.get('sourceCommit')!=value['sourceCommit'] or not 1<=len(manifest.get('files',{}))<=512:
        raise ValueError('bootstrap_manifest_invalid')
    # A manifest must also exclude stray importable files from an earlier pack.
    # Check every entry without following links; do not import any package yet.
    pending=[package];found=set();entry_count=0
    while pending:
        for entry in pending.pop().iterdir():
            plain_path(entry);entry_count+=1
            if entry_count>1024:raise ValueError('bootstrap_package_entry_limit')
            if entry.is_dir():pending.append(entry)
            elif entry.is_file():found.add(entry.relative_to(package).as_posix())
            else:raise ValueError('bootstrap_special_file')
    if found!=set(manifest['files'])|{'shadow-package.json'}:raise ValueError('bootstrap_unlisted_file')
    total=0
    for name,digest in manifest['files'].items():
        relative=PurePosixPath(name)
        if (not isinstance(name,str) or relative.is_absolute() or '\\' in name or ':' in name
                or '..' in relative.parts or not re.fullmatch('[a-f0-9]{64}',digest)):
            raise ValueError('bootstrap_package_path_invalid')
        source=plain_path(package/name)
        if source.stat().st_size>2*1024*1024:raise ValueError('bootstrap_source_limit')
        raw=source.read_bytes();total+=len(raw)
        if total>32*1024*1024 or hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('bootstrap_source_hash_mismatch')
    for required_file in ['tools/shadow_dashboard_bootstrap.py','tools/shadow_live_runtime.py',
                          'tools/shadow_dashboard_host.py','tools/shadow_sqlite_snapshot.py']:
        if required_file not in manifest['files']:raise ValueError('bootstrap_package_incomplete')
    plan_path=plain_path(value['planPath'])
    if plan_path.stat().st_size>1024*1024 or hashlib.sha256(plan_path.read_bytes()).hexdigest()!=value['planSha256']:
        raise ValueError('bootstrap_plan_hash_mismatch')
    return value,read_json(plan_path),package


PREPARE_FAILED = 75


class PreparationError(RuntimeError):
    """The server entry has not been called; the child will exit before retry."""


def run(settings_path,dashboard_root,*,load_dashboard=None,configure=None,serve=None):
    service_entered=False
    old_path=list(sys.path);namespace=None;old_namespace_path=None
    try:
        settings,spec,package=verified_settings(settings_path)
        root=plain_path(dashboard_root)
        sys.path.insert(0,str(package))
        namespace=importlib.import_module('tools')
        old_namespace_path=list(namespace.__path__)
        namespace.__path__=[str(package/'tools')]
        if configure is None:
            configure=importlib.import_module('tools.shadow_live_runtime').configure
        if load_dashboard is None:
            sys.path.insert(0,str(root))
            def load_dashboard():
                module=importlib.import_module('app')
                if plain_path(module.__file__)!=root/'app.py':raise ValueError('wrong_original_dashboard')
                return module
        dashboard=load_dashboard()
        configure(dashboard,spec,settings['mode'],plain_path(settings_path).parent)
        if serve is None:
            import uvicorn
            serve=uvicorn.run
        options=dict(host=str(dashboard.CONFIG['listen_host']),port=int(dashboard.CONFIG['listen_port']),
                     reload=False,access_log=False)
        # After this boundary even a bind failure, SystemExit or later crash
        # belongs to Dashboard/watchdog semantics. Never authorize another app.
        service_entered=True
        serve(dashboard.app,**options)
        return 0
    except Exception:
        if not service_entered:raise PreparationError('shadow_prepare_failed') from None
        raise
    finally:
        sys.path[:]=old_path
        if namespace is not None and old_namespace_path is not None:
            namespace.__path__=old_namespace_path



def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dashboard-root',type=Path,required=True)
    parser.add_argument('--settings',type=Path,required=True)
    args=parser.parse_args(argv)
    try:return run(args.settings,args.dashboard_root)
    except PreparationError:
        print('{"state":"fallback","code":"shadow_prepare_failed"}')
        return PREPARE_FAILED
    except Exception:
        print('{"state":"failed","code":"dashboard_service_failed"}')
        return 1


if __name__=='__main__':raise SystemExit(main())
