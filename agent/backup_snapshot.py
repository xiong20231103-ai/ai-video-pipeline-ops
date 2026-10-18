"""Consistent local metadata bundles, no restore execution or production writes."""
from datetime import datetime,timezone
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from urllib.parse import quote
import zipfile
from agent.backup_policy import PolicyError,checked_stat,inventory
from agent.backup_crypto import encrypt

def identity(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)

def stable_bytes(path,maximum,retries=3):
    for attempt in range(retries):
        before=checked_stat(path)
        if before is None: raise PolicyError('Whitelist file disappeared')
        if before.st_size>maximum: raise PolicyError('Whitelist file grew beyond limit')
        try:
            with open(path,'rb') as handle:
                opened=os.fstat(handle.fileno())
                body=handle.read(maximum+1)
                read_info=os.fstat(handle.fileno())
            after=checked_stat(path)
        except OSError: raise PolicyError('Cannot read whitelist file') from None
        if len(body)<=maximum and after is not None and identity(before)==identity(opened)==identity(read_info)==identity(after):
            return body,after
    raise PolicyError('Whitelist file changed during repeated reads')

def sqlite_snapshot(source,destination,maximum,deadline_seconds=120):
    checked_stat(source)
    uri='file:'+quote(Path(source).absolute().as_posix(),safe='/:')+'?mode=ro'
    deadline=time.monotonic()+deadline_seconds
    page_size=4096
    def progress(status,remaining,total):
        if time.monotonic()>deadline: raise PolicyError('SQLite snapshot deadline exceeded')
        if total*page_size>maximum: raise PolicyError('SQLite snapshot budget exceeded')
    try:
        with closing(sqlite3.connect(uri,uri=True,timeout=5)) as src,closing(sqlite3.connect(destination)) as dst:
            src.execute('PRAGMA query_only=ON')
            page_size=src.execute('PRAGMA page_size').fetchone()[0]
            src.backup(dst,pages=256,progress=progress,sleep=.05)
            if dst.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]: raise PolicyError('SQLite integrity check failed')
    except sqlite3.Error: raise PolicyError('SQLite consistent snapshot failed') from None
    if Path(destination).stat().st_size>maximum: raise PolicyError('SQLite snapshot exceeds limit')
    checked_stat(source)

def create_package(roots,output_directory,private_scratch,openssl,certificate,rules=None):
    """Return opaque ciphertext manifest. Caller supplies an ACL-restricted scratch."""
    from agent.backup_policy import RULES
    output=Path(output_directory).absolute(); scratch=Path(private_scratch).absolute()
    # No backup destination may be inside a production source tree.
    for path in (output,scratch):
        for name,source in roots.items():
            if name=='AGENT':
                allowed=Path(source).absolute()/'backup-work'
                if path==allowed or path.is_relative_to(allowed):continue
            if path.is_relative_to(Path(source).absolute()): raise PolicyError('Backup output overlaps source')
    for path in (output,scratch):
        path.mkdir(parents=True,exist_ok=True); checked_stat(path)
    started=datetime.now(timezone.utc).isoformat()
    selected=inventory(roots,RULES if rules is None else rules)
    import uuid
    package_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex
    publication=output/(package_id+'.partial')
    publication.mkdir(exist_ok=False)
    artifacts=[]
    try:
        with tempfile.TemporaryDirectory(prefix='ops-backup-',dir=scratch) as temporary:
            temporary=Path(temporary); manifests={'ledger':[],'configuration':[]}
            archives={name:zipfile.ZipFile(temporary/(name+'.zip'),'x',zipfile.ZIP_DEFLATED,compresslevel=6) for name in manifests}
            try:
                for row in selected['files']:
                    source=Path(roots[row['root']])/row['relative']
                    group='configuration' if row['secret'] else 'ledger'
                    archive_name=row['root']+'/'+row['relative']
                    if row['sqlite']:
                        target=temporary/'consistent.sqlite'
                        sqlite_snapshot(source,target,row['maximum'])
                        size=target.stat().st_size; digest=hashlib.sha256()
                        with target.open('rb') as incoming,archives[group].open(archive_name,'w',force_zip64=True) as outgoing:
                            while chunk:=incoming.read(1024*1024): digest.update(chunk); outgoing.write(chunk)
                        info=checked_stat(source); target.unlink()
                        checksum=digest.hexdigest()
                    else:
                        body,info=stable_bytes(source,row['maximum'])
                        if source.name.endswith(('.json','.json.last-valid')):
                            try:json.loads(body)
                            except (ValueError,UnicodeError):raise PolicyError('Whitelist JSON is not a complete valid document') from None
                        size=len(body);checksum=hashlib.sha256(body).hexdigest()
                        archives[group].writestr(archive_name,body);del body
                    manifests[group].append({'path':archive_name,'bytes':size,'sha256':checksum,
                        'sourceMtimeNs':info.st_mtime_ns,'sqliteOnlineSnapshot':row['sqlite']})
                ended=datetime.now(timezone.utc).isoformat()
                for group,archive in archives.items():
                    archive.writestr('RESTORE_EVIDENCE_ONLY.json',json.dumps({
                        'schema':1,'packageId':package_id,'restoreMode':'isolated-evidence-only',
                        'automaticExecutionAllowed':False,'consistencyWindow':{'startedAt':started,'endedAt':ended},
                        'crossFileTransactionGuaranteed':False,'files':manifests[group],
                        'optionalMissing':selected['optionalMissing']},ensure_ascii=False,indent=2))
            finally:
                for archive in archives.values(): archive.close()
            for group in manifests:
                encrypted=publication/(group+'.cms')
                encrypt(openssl,temporary/(group+'.zip'),encrypted,certificate)
                digest=hashlib.sha256()
                with encrypted.open('rb') as handle:
                    while chunk:=handle.read(1024*1024): digest.update(chunk)
                artifacts.append({'name':encrypted.name,'bytes':encrypted.stat().st_size,
                    'sha256':digest.hexdigest(),'files':len(manifests[group])})
        summary={'schema':1,'packageId':package_id,'startedAt':started,'completedAt':datetime.now(timezone.utc).isoformat(),
            'format':'openssl-cms-aes-256-gcm-rsa-oaep-sha256','privateKeyIncluded':False,
            'sourceBytes':selected['totalBytes'],'artifacts':artifacts}
        (publication/'manifest.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
        final=output/package_id
        publication.rename(final)
        return final,summary
    except BaseException:
        # No plaintext outside the private TemporaryDirectory. Do not grow a
        # history of failed local ciphertext packages either.
        for item in publication.iterdir():
            if item.name not in {'ledger.cms','configuration.cms','manifest.json'} or item.is_symlink() or not item.is_file():raise PolicyError('Unexpected partial backup member')
        for item in publication.iterdir():item.unlink()
        publication.rmdir()
        raise
