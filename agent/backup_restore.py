"""User-run isolated evidence restore. Never writes original roots or runs apps."""
import argparse
from contextlib import closing
from getpass import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile
from fnmatch import fnmatchcase
from agent.backup_crypto import decrypt,CryptoError
from agent.backup_policy import RULES,PolicyError,checked_stat,default_roots
from agent.backup_setup import DEFAULT_OPENSSL,private_directory

MAX_TOTAL=600*1024*1024
def matching(path,rule):
    pieces=path.split('/');pattern=rule.pattern.split('/')
    return len(pieces)==len(pattern) and all(fnmatchcase(a,b) for a,b in zip(pieces,pattern))
def member_allowed(name):
    if not isinstance(name,str) or '\\' in name or ':' in name:return False
    pieces=name.split('/')
    if any(p in {'','.','..'} or p.endswith((' ','.')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?',p,re.I) for p in pieces):return False
    if len(pieces)<2:return False
    root=pieces[0];relative='/'.join(pieces[1:])
    if root=='CLOUD':return relative in {'console.db','vault.sqlite','config.json'}
    return any(rule.root==root and matching(relative,rule) for rule in RULES)
def extract_verified(archive,target,total_so_far=0):
    # All extracted data sits below evidence/, away from any executable layout.
    with zipfile.ZipFile(archive) as incoming:
        members=incoming.infolist()
        if len(members)>100001:raise PolicyError('Restore member limit exceeded')
        markers=[p for p in members if p.filename=='RESTORE_EVIDENCE_ONLY.json']
        if len(markers)!=1 or markers[0].file_size>32*1024*1024:raise PolicyError('Restore evidence manifest missing/oversized')
        declared=json.loads(incoming.read(markers[0]))
        if not isinstance(declared,dict) or declared.get('automaticExecutionAllowed') is not False or declared.get('restoreMode')!='isolated-evidence-only':raise PolicyError('Restore execution barrier missing')
        entries=declared.get('files')
        if not isinstance(entries,list):raise PolicyError('Invalid restore manifest')
        expected={};seen=set()
        for row in entries:
            if not isinstance(row,dict):raise PolicyError('Invalid restore member metadata')
            name=row.get('path');folded=str(name).casefold()
            if not member_allowed(name) or folded in seen or type(row.get('bytes')) is not int or row['bytes']<0 or not re.fullmatch('[a-f0-9]{64}',str(row.get('sha256'))):raise PolicyError('Unsafe restore member')
            seen.add(folded);expected[name]=row
        actual=[p for p in members if p.filename!='RESTORE_EVIDENCE_ONLY.json']
        if len(actual)!=len(expected) or {p.filename for p in actual}!=set(expected):raise PolicyError('Restore member set differs from manifest')
        total=total_so_far;restored=[]
        for item in actual:
            row=expected[item.filename]
            if item.is_dir() or (item.external_attr>>16)&0o170000==0o120000 or item.file_size!=row['bytes']:raise PolicyError('Restore member type/size mismatch')
            total+=item.file_size
            if total>MAX_TOTAL:raise PolicyError('Restore total limit exceeded')
            destination=target/'evidence'/item.filename
            if destination.exists():raise PolicyError('Restore would overwrite an existing member')
            destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True);checked_stat(destination.parent)
            checksum=hashlib.sha256();size=0
            fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as output,incoming.open(item) as source:
                while block:=source.read(1024*1024):
                    size+=len(block)
                    if size>row['bytes']:raise PolicyError('Restore member exceeded manifest')
                    checksum.update(block);output.write(block)
            if size!=row['bytes'] or checksum.hexdigest()!=row['sha256']:raise PolicyError('Restore member checksum failed')
            if item.filename.endswith(('.db','.sqlite')):
                with closing(sqlite3.connect(destination.absolute().as_uri()+'?mode=ro',uri=True)) as db:
                    db.execute('PRAGMA query_only=ON')
                    if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise PolicyError('Restored database integrity failed')
            restored.append({'path':item.filename,'bytes':size,'sha256':checksum.hexdigest()})
        return restored,total
def restore_package(package,target,certificate,key,password,openssl=DEFAULT_OPENSSL,protected_roots=None):
    package=Path(package).absolute();target=Path(target).absolute();checked_stat(package);checked_stat(target)
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'OpsAgent'
    for root in (protected_roots or default_roots(state).values()):
        original=Path(root).absolute()
        if target==original or target.is_relative_to(original):raise PolicyError('Restore target overlaps a production root')
    if target.exists():raise PolicyError('Restore target must be new')
    manifest_path=package/'manifest.json';checked_stat(manifest_path)
    if manifest_path.stat().st_size>65536:raise PolicyError('Oversized backup manifest')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if not isinstance(manifest,dict) or manifest.get('privateKeyIncluded') is not False or manifest.get('format')!='openssl-cms-aes-256-gcm-rsa-oaep-sha256':raise PolicyError('Unsupported encrypted backup')
    artifacts=manifest.get('artifacts')
    if not isinstance(artifacts,list) or not 1<=len(artifacts)<=2:raise PolicyError('Invalid backup artifacts')
    private_directory(target)
    barrier={'schema':1,'automaticExecutionAllowed':False,'restoreMode':'isolated-evidence-only','verified':False,
             'instructions':'Do not point services at evidence/. Verify media, leases, processes and pending commands manually before any production recovery.'}
    (target/'RESTORE_EVIDENCE_ONLY.json').write_text(json.dumps(barrier,indent=2),encoding='utf-8')
    count=0;total=0;restored=[];names=set()
    with tempfile.TemporaryDirectory(prefix='restore-private-',dir=target) as temporary:
        for item in artifacts:
            if not isinstance(item,dict):raise PolicyError('Invalid encrypted artifact')
            name=item.get('name')
            if name not in {'ledger.cms','configuration.cms','cloud.cms'} or name in names:raise PolicyError('Unexpected encrypted artifact')
            names.add(name);source=package/name;checked_stat(source)
            if type(item.get('bytes')) is not int or source.stat().st_size!=item['bytes'] or not 0<item['bytes']<=MAX_TOTAL or not re.fullmatch('[a-f0-9]{64}',str(item.get('sha256'))):raise PolicyError('Ciphertext size/hash mismatch')
            checksum=hashlib.sha256()
            with source.open('rb') as incoming:
                while block:=incoming.read(1024*1024):checksum.update(block)
            if checksum.hexdigest()!=item['sha256']:raise PolicyError('Ciphertext hash mismatch')
            archive=Path(temporary)/(name+'.zip')
            decrypt(openssl,source,archive,certificate,key,password)
            rows,total=extract_verified(archive,target,total);restored.extend(rows);count+=1
    if names not in ({'ledger.cms','configuration.cms'},{'cloud.cms'}):raise PolicyError('Incomplete backup artifact set')
    barrier.update(verified=True,files=len(restored),bytes=total,artifacts=count)
    (target/'RESTORE_EVIDENCE_ONLY.json').write_text(json.dumps(barrier,indent=2),encoding='utf-8')
    return barrier
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',required=True);parser.add_argument('--target',required=True)
    parser.add_argument('--certificate',required=True);parser.add_argument('--key',required=True)
    args=parser.parse_args()
    password=getpass('Backup recovery passphrase (hidden): ')
    try:result=restore_package(args.package,args.target,args.certificate,args.key,password)
    except (OSError,ValueError,PolicyError,CryptoError,zipfile.BadZipFile,sqlite3.Error):raise SystemExit('Isolated restoration failed; no production writes or execution occurred, no private details logged') from None
    print(json.dumps(result))
if __name__=='__main__':main()
