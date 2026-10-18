"""Independent scheduled metadata backup worker. No home HTTP POST or execution."""
from datetime import datetime,timezone,timedelta
import hashlib
import http.client
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from agent.backup_crypto import CryptoError
from agent.backup_policy import PolicyError,checked_stat
from contracts.state_files import atomic_json,read_json

LOCAL_TZ=timezone(timedelta(hours=8))
class BackupWorker:
    def __init__(self,agent):
        self.agent=agent;self.state=agent.state_dir;self.event=threading.Event();self.request_id=None
        self.snapshot={'phase':'waiting_configuration'}
    def notify(self,generation):
        if isinstance(generation,str) and len(generation)==32 and all(c in '0123456789abcdef' for c in generation):
            self.request_id=generation;self.event.set()
    def report(self,phase,**metadata):
        value={'schema':1,'phase':phase,'observedAt':datetime.now(timezone.utc).isoformat(),**metadata}
        atomic_json(self.state/'backup-runtime.json',value)
        self.snapshot={key:child for key,child in value.items() if key in {'phase','observedAt','packageId','sourceBytes','ciphertextBytes','completedAt','capturedAt','reason'}}
    def public_state(self):return dict(self.snapshot)
    def clean_scratch(self,scratch):
        scratch.mkdir(parents=True,exist_ok=True);checked_stat(scratch)
        for directory in scratch.iterdir():
            if not directory.name.startswith('ops-backup-'):raise PolicyError('Unexpected backup scratch directory')
            checked_stat(directory)
            if not directory.is_dir():raise PolicyError('Unexpected backup scratch file')
            entries=list(directory.iterdir())
            for item in entries:
                checked_stat(item)
                if not item.is_file() or item.name not in {'ledger.zip','configuration.zip','consistent.sqlite'}:raise PolicyError('Unexpected backup scratch member')
            for item in entries:item.unlink()
            directory.rmdir()
    def local_manifest(self,directory):
        checked_stat(directory);checked_stat(directory/'manifest.json')
        manifest=read_json(directory/'manifest.json')
        if not isinstance(manifest,dict) or manifest.get('packageId')!=directory.name or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}',directory.name):raise PolicyError('Local backup identity mismatch')
        artifacts=manifest.get('artifacts')
        if not isinstance(artifacts,list) or len(artifacts)!=2 or any(not isinstance(p,dict) for p in artifacts) or {p.get('name') for p in artifacts}!={'ledger.cms','configuration.cms'}:raise PolicyError('Unexpected local backup artifact set')
        total=0
        for item in artifacts:
            if type(item.get('bytes')) is not int or not 0<item['bytes']<=600*1024*1024 or not re.fullmatch('[a-f0-9]{64}',str(item.get('sha256'))):raise PolicyError('Invalid local backup metadata')
            path=directory/item['name'];checked_stat(path);total+=item['bytes']
            checksum=hashlib.sha256()
            with path.open('rb') as source:
                while block:=source.read(1024*1024):checksum.update(block)
            if path.stat().st_size!=item['bytes'] or checksum.hexdigest()!=item['sha256']:raise PolicyError('Local backup integrity failed')
        if total>600*1024*1024:raise PolicyError('Local backup budget exceeded')
        return manifest
    def reusable_package(self,outgoing):
        outgoing.mkdir(parents=True,exist_ok=True);checked_stat(outgoing)
        for directory in sorted(outgoing.iterdir()):
            if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}(\.partial)?',directory.name):raise PolicyError('Unexpected backup outgoing directory')
            checked_stat(directory)
            if not directory.is_dir():raise PolicyError('Unexpected outgoing backup member')
            if directory.name.endswith('.partial'):
                for item in directory.iterdir():
                    checked_stat(item)
                    if item.name not in {'ledger.cms','configuration.cms','manifest.json'} or not item.is_file():raise PolicyError('Unexpected partial backup member')
                for item in directory.iterdir():item.unlink()
                directory.rmdir();continue
            self.local_manifest(directory)
            return directory
        return None
    def upload_part(self,package_id,path,size):
        # Stream the ciphertext file; never construct a 100 MB in-memory body.
        with open(path,'rb') as incoming:
            request=urllib.request.Request(self.agent.origin+'/agent/backups/'+package_id+'/'+path.name,
                data=incoming,method='PUT',headers={'Authorization':'Bearer '+self.agent.token,
                'Content-Type':'application/pkcs7-mime','Content-Length':str(size)})
            try:
                with self.agent.transport.open(request,timeout=180) as response:
                    result=json.load(response)
                    if result.get('stored') is not True:raise ValueError('Backup upload was not confirmed')
            except http.client.IncompleteRead:raise OSError('Incomplete cloud backup acknowledgement') from None
    def execute(self,settings,request_id):
        root=self.state/'backup-work';root.mkdir(exist_ok=True)
        scratch=root/'scratch';outgoing=root/'outgoing'
        self.clean_scratch(scratch)
        certificate=Path(settings['recipientCertificate']);openssl=Path(settings['openssl'])
        checked_stat(certificate);checked_stat(openssl)
        if not certificate.is_file() or not openssl.is_file():raise PolicyError('Backup public recipient or existing encryption tool missing')
        # Exactly this public certificate is registered once. Rotation is a
        # separate local cloud-admin operation, never an automatic overwrite.
        public=certificate.read_text(encoding='utf-8')
        self.agent.cloud('/agent/backups/recipient',{'certificate':public})
        pending=self.state/'backup-pending.json'
        if pending.exists():
            data=read_json(pending)
            if not isinstance(data,dict) or not isinstance(data.get('directory'),str):raise PolicyError('Invalid pending backup state')
            package=Path(data['directory'])
            if package.parent!=outgoing.absolute():raise PolicyError('Unexpected pending backup location')
            summary=self.local_manifest(package)
            request_id=data.get('requestId')
        else:
            self.report('creating',requestId=request_id)
            package=self.reusable_package(outgoing)
            if package is None:
                result=subprocess.run([sys.executable,'-B','-m','agent.backup_pack','--state',str(self.state.absolute())],
                    cwd=Path(__file__).resolve().parents[1],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                if result.returncode:raise PolicyError('Metadata backup packer failed without private logging')
                packed=json.loads(result.stdout)
                if not isinstance(packed,dict) or not isinstance(packed.get('directory'),str):raise PolicyError('Invalid packer acknowledgement')
                package=Path(packed['directory'])
            if package.parent!=outgoing.absolute():raise PolicyError('Unexpected packed backup location')
            summary=self.local_manifest(package)
            atomic_json(pending,{'directory':str(package.absolute()),'requestId':request_id})
        reservation=self.agent.cloud('/agent/backups/reserve',summary)
        if reservation.get('packageId')!=summary['packageId']:raise ValueError('Backup reservation identity mismatch')
        self.report('uploading',packageId=summary['packageId'])
        if reservation.get('state')!='published':
            for part in summary['artifacts']:
                if self.agent.stop.is_set():raise OSError('Agent stopping')
                self.upload_part(summary['packageId'],package/part['name'],part['bytes'])
        result=self.agent.cloud('/agent/backups/'+summary['packageId']+'/publish',{'requestId':request_id})
        if result.get('published') is not True:raise ValueError('Backup publication not confirmed')
        complete={'packageId':summary['packageId'],'completedAt':datetime.now(timezone.utc).isoformat(),'capturedAt':summary['completedAt'],'sourceBytes':summary['sourceBytes'],
                  'ciphertextBytes':sum(p['bytes'] for p in summary['artifacts']),'requestId':request_id}
        atomic_json(self.state/'backup-last-success.json',complete)
        self.report('completed',**complete)
        pending.unlink(missing_ok=True)
        # Ciphertext results are cloud-owned after confirmation; no local
        # history archive. Restrict deletion to this exact generated directory.
        if package.parent!=outgoing.absolute() or package.is_symlink():raise PolicyError('Backup cleanup location changed')
        for item in package.iterdir():
            if item.name not in {'ledger.cms','configuration.cms','manifest.json'} or item.is_symlink() or not item.is_file():raise PolicyError('Unexpected backup staging member')
        for item in package.iterdir():item.unlink()
        package.rmdir()
        return complete
    def loop(self):
        retry_after=0
        while not self.agent.stop.is_set():
            settings_path=self.state/'backup-settings.json'
            if not settings_path.exists():
                self.event.wait(5);self.event.clear();continue
            try:
                settings=read_json(settings_path)
                if not isinstance(settings,dict) or settings.get('schema')!=1 or not isinstance(settings.get('roots'),dict) or set(settings['roots'])!={'OPS','WB','VOICE','CAP','GEN','AGENT','PD_E','PD_C'} or not all(isinstance(v,str) for v in settings['roots'].values()) or not isinstance(settings.get('recipientCertificate'),str) or not isinstance(settings.get('openssl'),str):raise ValueError('Invalid backup settings')
                today=datetime.now(LOCAL_TZ);last_path=self.state/'backup-last-success.json'
                last=read_json(last_path) if last_path.exists() else {}
                previous=last.get('capturedAt','')
                date=datetime.fromisoformat(previous).astimezone(LOCAL_TZ).date() if previous else None
                due=today.hour>=3 and date!=today.date()
                requested=self.request_id
                if (due or requested or (self.state/'backup-pending.json').exists()) and time.monotonic()>=retry_after:
                    if not self.agent.authenticated.is_set():self.event.wait(1);self.event.clear();continue
                    complete=self.execute(settings,requested)
                    if self.request_id==complete.get('requestId'):self.request_id=None
                    retry_after=0
            except (OSError,ValueError,PolicyError,CryptoError,urllib.error.HTTPError,subprocess.SubprocessError):
                # Constant status only: JSON/config/OpenSSL errors may contain
                # credentials. Preserve pending ciphertext for a later retry.
                self.report('failed',reason='backup_not_completed_no_private_details_logged')
                retry_after=time.monotonic()+300
            self.event.wait(1);self.event.clear()
