"""Offline retention: verified archive first, deletion second, no online API.

Keep current + N latest OTHER committed packages, the current package's parent,
the base and every package/upload belonging to the live holder (even expired).
Archive onto another filesystem so pruning actually frees the console's disk.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import time

from cloud.material_handoff import Handoff, encode
from cloud.material_handoff_admin import backup_control


class PruneError(ValueError):
    pass


def digest_file(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(1024**2),b''):
            sha.update(part)
    return sha.hexdigest()


def _same_filesystem(root,backup_dir):
    existing=backup_dir
    while not existing.exists():
        existing=existing.parent
    return root.stat().st_dev==existing.stat().st_dev


def _payload(root,relative):
    if (not isinstance(relative,str) or '\\' in relative or ':' in relative or
            PurePosixPath(relative).is_absolute() or not relative.endswith('.zip') or
            any(p in ('','.','..') for p in relative.split('/'))):
        raise PruneError('unsafe_prune_payload_path')
    path=root
    for part in relative.split('/'):
        path=path/part
        if path.is_symlink():
            raise PruneError('prune_symlink_forbidden')
    resolved=path.resolve()
    if not resolved.is_relative_to(root) or resolved==root:
        raise PruneError('prune_outside_storage')
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise PruneError('prune_regular_file_required')
    return path


def _snapshot(db):
    return {'state':json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0]),
            'packages':[dict(r) for r in db.execute('SELECT * FROM packages ORDER BY id')],
            'uploads':[dict(r) for r in db.execute('SELECT * FROM uploads ORDER BY path')]}


def _retained(snapshot,keep_recent):
    s=snapshot['state']
    rows={r['id']:r for r in snapshot['packages']}
    keep={x for x in (s['current_package'],s['base_package']) if x}
    current=rows.get(s['current_package'])
    if s['current_package'] and (not current or current['state']!='committed'):
        raise PruneError('current_package_metadata_invalid')
    if current and current['parent_id']:
        if current['parent_id'] not in rows or rows[current['parent_id']]['state']!='committed':
            raise PruneError('current_parent_metadata_invalid')
        keep.add(current['parent_id'])
    recent=sorted((r for r in rows.values() if r['state']=='committed' and r['id']!=s['current_package']),
                  key=lambda r:(r['committed_at'],r['id']),reverse=True)[:keep_recent]
    keep.update(r['id'] for r in recent)
    if s['holder']:
        keep.update(r['id'] for r in rows.values() if Handoff.owns(r,s))
    return keep


def _plan(root,snapshot,keep_recent):
    keep=_retained(snapshot,keep_recent)
    rows=snapshot['packages']
    by_path={}
    for row in rows:
        by_path.setdefault(row['path'],[]).append(row)
    protected={r['path'] for r in rows if r['id'] in keep}
    uploads={r['path']:r for r in snapshot['uploads']}
    files={p.relative_to(root).as_posix() for p in (root/'objects').glob('*.zip')}
    all_paths=set(by_path)|set(uploads)|files
    # An incomplete upload has no package row or uploader column. With any live
    # reservation, conservatively retain all such objects, including expired ones.
    if snapshot['state']['holder']:
        protected.update(p for p in all_paths if p not in by_path)
    plan=[]
    for relative in sorted(all_paths-protected):
        path=_payload(root,relative)
        referenced=by_path.get(relative,[])
        if not path.is_file() and any(r['state']!='pruned' for r in referenced):
            raise PruneError('referenced_package_missing_restore_before_prune')
        # A lost/aborted empty upload can release its reservation after the DB
        # snapshot is verified; there are no payload bytes to destroy.
        if not path.is_file() and relative not in uploads:
            continue
        plan.append({'path':relative,'package_ids':[r['id'] for r in referenced],
                     'expected':[{'sha256':r['sha256'],'bytes':r['bytes']} for r in referenced if r['state']!='pruned'],
                     'missing_before_prune':not path.is_file()})
    return keep,plan


def _sync_directory(path):
    if os.name=='posix':
        fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write_json(path,value):
    with path.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
        stream.flush();os.fsync(stream.fileno())
    _sync_directory(path.parent)


def _journal(folder,event):
    with (folder/'prune-audit.jsonl').open('a',encoding='utf-8') as stream:
        stream.write(encode({'at':time.time(),**event})+'\n')
        stream.flush();os.fsync(stream.fileno())
    _sync_directory(folder)


def _copy_payload(source,target):
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with source.open('rb') as src,target.open('xb') as dst:
        shutil.copyfileobj(src,dst,length=1024**2)
        dst.flush();os.fsync(dst.fileno())
    target.chmod(0o600)


def prune(root,backup_dir,actor,confirm,*,keep_recent=3):
    root,backup_dir=Path(root).resolve(),Path(backup_dir).resolve()
    if (confirm is not True or not isinstance(actor,str) or not 1<=len(actor.strip())<=100 or
            type(keep_recent) is not int or not 0<=keep_recent<=1000 or not (root/'handoff.db').is_file()):
        raise PruneError('offline_prune_confirmation_and_existing_database_required')
    if backup_dir.is_relative_to(root):
        raise PruneError('backup_must_be_outside_handoff_storage')
    if _same_filesystem(root,backup_dir):
        raise PruneError('prune_backup_requires_different_filesystem_to_free_console_disk')
    # First mutation is a fresh, verified control DB backup outside runtime.
    folder,control_sha=backup_control(root,backup_dir,'prune')
    op=folder.name
    _journal(folder,{'action':'prune_begin','actor':actor,'keep_recent':keep_recent,'control_sha256':control_sha})
    h=Handoff(root,check_storage=False)
    removed=0
    removed_bytes=0
    stage='plan'
    try:
        backup=sqlite3.connect(folder/'handoff.db')
        backup.row_factory=sqlite3.Row
        try:
            snapshot=_snapshot(backup)
        finally:
            backup.close()
        with h.tx() as db:
            if _snapshot(db)!=snapshot:
                raise PruneError('handoff_changed_after_backup_cloud_must_be_offline')
            keep,plan=_plan(root,snapshot,keep_recent)
            h.audit(db,'admin:'+actor,'prune_begin',{'operation':op,'backup_path':str(folder),
                     'control_sha256':control_sha,'keep_recent':keep_recent,'protected':sorted(keep),'candidates':len(plan)})
        stage='copy-and-verify'
        total=sum(_payload(root,e['path']).stat().st_size for e in plan if not e['missing_before_prune'])
        if shutil.disk_usage(folder).free<total+64*1024**2:
            raise PruneError('prune_backup_disk_space_low')
        copied=[]
        for entry in plan:
            source=_payload(root,entry['path'])
            archived=dict(entry)
            if not entry['missing_before_prune']:
                size=source.stat().st_size
                sha=digest_file(source)
                if any(item['bytes']!=size or item['sha256']!=sha for item in entry['expected']):
                    raise PruneError('source_package_hash_mismatch_no_deletion')
                destination=folder/'payloads'/entry['path']
                _copy_payload(source,destination)
                if destination.stat().st_size!=size or digest_file(destination)!=sha or digest_file(source)!=sha:
                    raise PruneError('prune_backup_verification_failed_no_deletion')
                archived.update(bytes=size,sha256=sha,backup_path=destination.relative_to(folder).as_posix())
                parent=destination.parent
                while parent.is_relative_to(folder):
                    _sync_directory(parent)
                    if parent==folder:
                        break
                    parent=parent.parent
            else:
                archived.update(bytes=0,sha256=None,backup_path=None)
            copied.append(archived)
            _journal(folder,{'action':'prune_backup_verified','path':entry['path'],
                            'sha256':archived['sha256'],'missing_before_prune':entry['missing_before_prune']})
        # All copies must verify before ANY payload deletion. Keep DB snapshot,
        # immutable plan, per-file hashes and fsynced audit for crash recovery.
        _write_json(folder/'prune-manifest.json',{'operation':op,'actor':actor,'control_sha256':control_sha,
                    'keep_recent':keep_recent,'protected':sorted(keep),'files':copied})
        for entry in copied:
            if entry['backup_path']:
                if digest_file(folder/entry['backup_path'])!=entry['sha256']:
                    raise PruneError('prune_backup_verification_failed_no_deletion')
                if digest_file(_payload(root,entry['path']))!=entry['sha256']:
                    raise PruneError('source_changed_before_prune_no_deletion')
        stage='delete'
        with h.tx() as db:
            if _snapshot(db)!=snapshot:
                raise PruneError('handoff_changed_before_deletion_cloud_must_be_offline')
            h.audit(db,'admin:'+actor,'prune_backups_verified',{'operation':op,'files':len(copied)})
        for entry in copied:
            with h.tx() as db:
                current=_snapshot(db)
                if current!=snapshot:
                    raise PruneError('handoff_changed_during_prune_cloud_must_be_offline')
                retained=_retained(current,keep_recent)
                if retained.intersection(entry['package_ids']):
                    raise PruneError('prune_protected_package_changed')
                source=_payload(root,entry['path'])
                if entry['backup_path']:
                    if digest_file(folder/entry['backup_path'])!=entry['sha256'] or digest_file(source)!=entry['sha256']:
                        raise PruneError('prune_reverification_failed')
                elif source.exists():
                    raise PruneError('previously_missing_upload_appeared')
                # Intent is durable outside this transaction BEFORE unlink.
                _journal(folder,{'action':'prune_delete_intent','path':entry['path'],'sha256':entry['sha256']})
                if entry['backup_path']:
                    source.unlink()
                    _sync_directory(source.parent)
                    removed+=1
                    removed_bytes+=entry['bytes']
                db.execute("UPDATE packages SET state='pruned' WHERE path=?",(entry['path'],))
                db.execute('DELETE FROM uploads WHERE path=?',(entry['path'],))
                h.audit(db,'admin:'+actor,'prune_deleted',{'operation':op,'path':entry['path'],
                        'sha256':entry['sha256'],'bytes':entry['bytes'],'backup_path':str(folder),
                        'missing_before_prune':entry['missing_before_prune']})
                snapshot=_snapshot(db)
            _journal(folder,{'action':'prune_deleted','path':entry['path'],'sha256':entry['sha256']})
        result={'operation':op,'backup_path':str(folder),'control_sha256':control_sha,
                'protected_packages':sorted(keep),'keep_recent':keep_recent,'removed_files':removed,
                'source_bytes_removed':removed_bytes,'storage':h.status()['storage']}
        _write_json(folder/'prune-result.json',result)
        with h.tx() as db:
            h.audit(db,'admin:'+actor,'prune_complete',{'operation':op,'removed_files':removed,'source_bytes_removed':removed_bytes})
        _journal(folder,{'action':'prune_complete','removed_files':removed,'source_bytes_removed':removed_bytes})
        return result
    except Exception as error:
        code=str(error) if isinstance(error,PruneError) else type(error).__name__
        _journal(folder,{'action':'prune_failed','stage':stage,'code':code,'removed_files':removed})
        with h.tx() as db:
            h.audit(db,'admin:'+actor,'prune_failed',{'operation':op,'stage':stage,'code':code,
                    'removed_files':removed,'backup_path':str(folder)})
        raise
