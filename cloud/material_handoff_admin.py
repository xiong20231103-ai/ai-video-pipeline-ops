"""Offline backed-up recovery and retention maintenance.

Run only in an approved offline window with both material clients stopped.
Only prune deletes verified archived payloads. Neither action restores a
business database. Online/API cleanup is intentionally not supported.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from cloud.material_handoff import Handoff


def backup_control(root,backup_dir,label):
    root,backup_dir=Path(root).resolve(),Path(backup_dir).resolve()
    database=root/'handoff.db'
    if not database.is_file():
        raise ValueError('existing_handoff_database_required')
    if backup_dir.is_relative_to(root):
        raise ValueError('backup_must_be_outside_handoff_storage')
    folder=backup_dir/('material-handoff-before-'+label+'-'+uuid.uuid4().hex)
    folder.mkdir(parents=True,exist_ok=False,mode=0o700)
    snapshot=folder/'handoff.db'
    source=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    target=sqlite3.connect(snapshot)
    try:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('handoff_backup_integrity_failed')
    finally:
        source.close();target.close()
    digest=hashlib.sha256(snapshot.read_bytes()).hexdigest()
    manifest=folder/'manifest.json'
    manifest.write_text(json.dumps({'file':'handoff.db','sha256':digest,
        'integrity_check':'ok','package_objects_changed':False},indent=2)+'\n',encoding='utf-8')
    for file in (snapshot,manifest):
        with file.open('r+b') as stream:
            os.fsync(stream.fileno())
    if os.name=='posix':
        for directory in (folder,folder.parent):
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    return folder,digest


def recover(root,backup_dir,actor,confirm):
    root=Path(root).resolve()
    if not confirm or not isinstance(actor,str) or not 1<=len(actor.strip())<=100:
        raise ValueError('offline_recovery_confirmation_and_existing_database_required')
    folder,digest=backup_control(root,backup_dir,'recovery')
    result=Handoff(root,check_storage=False).recovery_generation('admin:'+actor,digest,devices_stopped=True)
    return {'backup_path':str(folder/'handoff.db'),'backup_sha256':digest,'integrity_check':'ok',
            'generation':result['generation'],'epoch':result['epoch'],'holder':result['holder']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['recover-generation','prune'])
    parser.add_argument('--root',required=True)
    parser.add_argument('--backup-dir',required=True)
    parser.add_argument('--actor',required=True)
    parser.add_argument('--keep-recent',type=int,default=3)
    parser.add_argument('--confirm-both-devices-stopped-and-cloud-offline',action='store_true')
    args=parser.parse_args()
    if args.action=='prune':
        from cloud.material_handoff_prune import prune
        result=prune(args.root,args.backup_dir,args.actor,
                     args.confirm_both_devices_stopped_and_cloud_offline,keep_recent=args.keep_recent)
    else:
        result=recover(args.root,args.backup_dir,args.actor,
                       args.confirm_both_devices_stopped_and_cloud_offline)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    main()
