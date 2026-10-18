"""Daily encrypted cloud database snapshots inside the existing cloud service."""
from contextlib import closing
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import uuid
import zipfile
from cloud.backups import FORMAT,BackupError,digest_file,plain_path
from contracts.backup_crypto import encrypt,CryptoError
from contracts.state_files import atomic_json

TZ=timezone(timedelta(hours=8))
class CloudBackupWorker:
    def __init__(self,vault,database,config,openssl='/usr/bin/openssl'):
        self.vault=vault;self.database=Path(database);self.config=config;self.openssl=Path(openssl)
        self.stop=threading.Event();self.status_path=vault.root/'cloud-backup-status.json'
    def status(self,phase,**metadata):
        atomic_json(self.status_path,{'schema':1,'phase':phase,'observedAt':datetime.now(timezone.utc).isoformat(),**metadata})
    def clean_work(self,work):
        # The deployed service has exactly one worker/backup thread. On service
        # restart its old process tree has exited, so only these owned temporary
        # members may be removed. Never recurse through client-selected paths.
        allowed={'recipient.pem','cloud.zip','console.db','vault.sqlite','cloud.cms'}
        for directory in work.iterdir():
            plain_path(directory)
            if not directory.is_dir() or not directory.name.startswith('cloud-snapshot-'):raise BackupError('unexpected_cloud_backup_work_member')
            entries=list(directory.iterdir())
            for item in entries:
                plain_path(item)
                if not item.is_file() or item.name not in allowed:raise BackupError('unexpected_cloud_backup_work_member')
            for item in entries:item.unlink()
            directory.rmdir()
    def snapshot(self,source,target):
        started=time.monotonic()
        def progress(code,remaining,total):
            if self.stop.is_set() or time.monotonic()-started>120:raise BackupError('cloud_snapshot_interrupted')
            if total>150000:raise BackupError('cloud_snapshot_budget_exceeded')
        with closing(sqlite3.connect(source.absolute().as_uri()+'?mode=ro',uri=True,timeout=5)) as incoming,closing(sqlite3.connect(target)) as outgoing:
            incoming.execute('PRAGMA query_only=ON');incoming.backup(outgoing,pages=128,progress=progress,sleep=.05)
            if outgoing.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise BackupError('cloud_snapshot_integrity_failure')
    def run_once(self):
        recipient=self.vault.recipient()
        if not recipient:self.status('waiting_recipient');return None
        if not self.openssl.is_file():raise BackupError('existing_cloud_openssl_missing')
        work=plain_path(self.vault.root/'cloud-work');work.mkdir(mode=0o700,exist_ok=True)
        self.clean_work(work)
        package_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex
        self.status('creating');started=datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory(prefix='cloud-snapshot-',dir=work) as temporary:
            temporary=Path(temporary);certificate=temporary/'recipient.pem';certificate.write_text(recipient['certificate'],encoding='utf-8')
            archive=temporary/'cloud.zip';manifest=[];total=0
            with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
                for source,name in ((self.database,'console.db'),(self.vault.path,'vault.sqlite')):
                    snapshot=temporary/name;self.snapshot(source,snapshot)
                    size=snapshot.stat().st_size;total+=size
                    output.write(snapshot,'CLOUD/'+name)
                    manifest.append({'path':'CLOUD/'+name,'bytes':size,'sha256':digest_file(snapshot),'sqliteOnlineSnapshot':True})
                configuration=json.dumps(self.config,ensure_ascii=False,separators=(',',':')).encode()
                total+=len(configuration);output.writestr('CLOUD/config.json',configuration)
                manifest.append({'path':'CLOUD/config.json','bytes':len(configuration),'sha256':hashlib.sha256(configuration).hexdigest()})
                output.writestr('RESTORE_EVIDENCE_ONLY.json',json.dumps({'schema':1,'packageId':package_id,'restoreMode':'isolated-evidence-only',
                    'automaticExecutionAllowed':False,'crossFileTransactionGuaranteed':False,'files':manifest}))
            ciphertext=temporary/'cloud.cms';encrypt(self.openssl,archive,ciphertext,certificate)
            summary={'schema':1,'packageId':package_id,'format':FORMAT,'privateKeyIncluded':False,'sourceBytes':total,'startedAt':started,'completedAt':datetime.now(timezone.utc).isoformat(),
                     'artifacts':[{'name':'cloud.cms','bytes':ciphertext.stat().st_size,'sha256':digest_file(ciphertext),'files':len(manifest)}]}
            self.vault.reserve(summary,kind='cloud')
            upload=self.vault.begin_part(package_id,'cloud.cms',ciphertext.stat().st_size)
            try:
                if not upload['stored']:
                    with ciphertext.open('rb') as incoming:
                        while block:=incoming.read(1024*1024):
                            if self.stop.is_set():raise BackupError('cloud_backup_interrupted')
                            upload['handle'].write(block)
                self.vault.finish_part(package_id,'cloud.cms',upload,ciphertext.stat().st_size,summary['artifacts'][0]['sha256'])
                result=self.vault.publish(package_id)
            except BaseException:
                self.vault.abort_part(package_id,'cloud.cms',upload);self.vault.cancel(package_id);raise
        self.status('completed',packageId=package_id)
        return result
    def loop(self):
        while not self.stop.is_set():
            try:
                now=datetime.now(TZ);today=now.date().isoformat()
                already=any(p['kind']=='cloud' and p['date']==today for p in self.vault.catalog()['items'])
                if (now.hour,now.minute)>=(3,30) and not already:self.run_once()
            except (OSError,ValueError,sqlite3.Error,CryptoError):self.status('failed',reason='cloud_backup_not_completed_no_private_details_logged')
            self.stop.wait(60)
    def run(self):
        try:self.loop()
        except Exception as error:
            # Surface a terminal backup-channel defect without formatting any
            # private exception text or taking down the console HTTP service.
            self.status('failed_terminal',exceptionType=type(error).__name__)
