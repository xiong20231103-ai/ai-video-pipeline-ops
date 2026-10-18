"""Ciphertext-only backup vault with durable reservations and bounded retention."""
from contextlib import closing,contextmanager
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

FORMAT='openssl-cms-aes-256-gcm-rsa-oaep-sha256'
LOCAL_TZ=timezone(timedelta(hours=8))
ID=re.compile(r'^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}$')
HEX=re.compile(r'^[a-f0-9]{64}$')
MAX_PACKAGE=600*1024*1024
QUOTA=10_000_000_000

class BackupError(ValueError):
    def __init__(self,code,status=400):self.code=code;self.status=status;super().__init__(code)

def digest_file(path):
    checksum=hashlib.sha256()
    with open(path,'rb') as source:
        while block:=source.read(1024*1024):checksum.update(block)
    return checksum.hexdigest()

def sync_directory(path):
    # Production vault is Linux. Make renamed ciphertext/manifest directory
    # entries durable before committing their publication in SQLite.
    if os.name=='nt':return
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)

def encrypted_cms_header(path):
    # CMS AuthEnvelopedData OID (AES-GCM), allowing streaming BER as emitted by
    # OpenSSL -stream. This rejects accidental plaintext/wrong CMS content;
    # GCM authentication itself can only be checked by the offline private key.
    with open(path,'rb') as source:header=source.read(64)
    if len(header)<4 or header[0]!=0x30:return False
    length=header[1];offset=2
    if length>0x80:
        size=length&0x7f
        if not 1<=size<=8:return False
        offset+=size
    oid=bytes.fromhex('060b2a864886f70d0109100117')
    return header[offset:offset+len(oid)]==oid

def plain_path(path):
    path=Path(path).absolute()
    for parent in (path,*path.parents):
        if parent.is_symlink() or parent.exists() and getattr(parent.lstat(),'st_file_attributes',0)&0x400:
            raise BackupError('backup_link_refused')
    return path

class BackupVault:
    def __init__(self,root,clock=time.time,quota=QUOTA):
        self.root=plain_path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.clock=clock;self.quota=quota;self.path=self.root/'vault.sqlite'
        self.deletions={}
        with self.db(True) as db:
            db.executescript('''PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS packages(id TEXT PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,day TEXT NOT NULL,expires REAL NOT NULL,bytes INTEGER NOT NULL,manifest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS parts(package_id TEXT NOT NULL,name TEXT NOT NULL,bytes INTEGER NOT NULL,digest TEXT NOT NULL,state TEXT NOT NULL,token TEXT,lease REAL NOT NULL DEFAULT 0,PRIMARY KEY(package_id,name),FOREIGN KEY(package_id) REFERENCES packages(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at REAL NOT NULL,code TEXT NOT NULL,package_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY CHECK(id=1),generation TEXT NOT NULL,requested REAL NOT NULL,completed REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS recipient(id INTEGER PRIMARY KEY CHECK(id=1),digest TEXT NOT NULL,certificate TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS agent_state(id INTEGER PRIMARY KEY CHECK(id=1),received REAL NOT NULL,body TEXT NOT NULL);
            ''')
        self.reap_trash()
    @contextmanager
    def db(self,write=False):
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
            if write:db.execute('BEGIN IMMEDIATE')
            staged=[];self.deletions[id(db)]=staged
            try:
                yield db;db.commit()
            except BaseException:
                db.rollback()
                for original,trash in reversed(staged):
                    if trash.exists() and not original.exists():trash.rename(original);sync_directory(self.root)
                raise
            else:
                for original,trash in staged:
                    try:self._erase_directory(trash)
                    except OSError:
                        # Durable metadata is already committed. Keep a bounded
                        # known trash directory and account for its bytes until
                        # a later retry, never advertise it as recoverable.
                        pass
            finally:self.deletions.pop(id(db),None)
    def directory(self,package_id):
        if not isinstance(package_id,str) or not ID.fullmatch(package_id):raise BackupError('invalid_package_id')
        target=plain_path(self.root/package_id)
        if target.parent!=self.root:raise BackupError('backup_path_refused')
        return target
    def event(self,db,code,package_id=''):
        db.execute('INSERT INTO events(at,code,package_id) VALUES(?,?,?)',(self.clock(),code,package_id))
        db.execute('DELETE FROM events WHERE id NOT IN(SELECT id FROM events ORDER BY id DESC LIMIT 100)')
    def _members(self,directory):
        plain_path(directory)
        children=list(directory.iterdir())
        for path in children:
            plain_path(path)
            if not path.is_file() or not (path.name in {'ledger.cms','configuration.cms','cloud.cms','manifest.json'} or re.fullmatch(r'\.(ledger|configuration|cloud)\.cms\.[a-f0-9]{32}\.partial',path.name)):
                raise BackupError('unexpected_backup_member',500)
        return children
    def _erase_directory(self,directory):
        if not directory.absolute().is_relative_to(self.root) or directory==self.root:raise BackupError('backup_path_refused')
        for path in self._members(directory):path.unlink()
        directory.rmdir()
        sync_directory(self.root)
    def _trash(self):
        return [p for p in self.root.iterdir() if p.name.startswith('.deleting-') and ID.fullmatch(p.name[len('.deleting-'):])]
    def trash_bytes(self,ignore=()):
        total=0
        for directory in self._trash():
            if directory in ignore:continue
            try:members=self._members(directory)
            except FileNotFoundError:continue # another committed GC finished
            for member in members:
                try:total+=member.stat().st_size
                except FileNotFoundError:continue
        return total
    def reap_trash(self):
        # The SQL writer lock also excludes another worker's uncommitted
        # rename. After a crash, roll back its rename or finish committed GC.
        with self.db(True) as db:
            for trash in self._trash():
                package_id=trash.name[len('.deleting-'):];original=self.directory(package_id)
                row=db.execute('SELECT id FROM packages WHERE id=?',(package_id,)).fetchone()
                if row:
                    if original.exists():raise BackupError('backup_gc_identity_conflict',500)
                    trash.rename(original);sync_directory(self.root)
                else:
                    try:self._erase_directory(trash)
                    except OSError:self.event(db,'backup_gc_retry_required',package_id)
    def _remove(self,db,row,reason):
        # No recursive delete: a package has only known regular files. Never
        # follow links or delete a parent/root chosen from client input.
        directory=self.directory(row['id'])
        if directory.exists():
            self._members(directory)
            trash=self.root/('.deleting-'+row['id'])
            if trash.exists():raise BackupError('backup_gc_pending',507)
            directory.rename(trash);self.deletions[id(db)].append((directory,trash));sync_directory(self.root)
        self.event(db,reason,row['id']);db.execute('DELETE FROM packages WHERE id=?',(row['id'],))
    def _expire(self,db):
        now=self.clock()
        rows=db.execute("SELECT * FROM packages WHERE state='reserved' AND expires<=? AND NOT EXISTS(SELECT 1 FROM parts WHERE package_id=packages.id AND lease>?)",(now,now)).fetchall()
        for row in rows:self._remove(db,row,'expired_incomplete_backup')
    def _retained(self,rows):
        selected=set();daily={};monthly={};cloud={}
        for row in sorted(rows,key=lambda r:(r['day'],r['created']),reverse=True):
            if row['kind']=='cloud':
                cloud.setdefault(row['day'],row['id'])
            else:
                daily.setdefault(row['day'],row['id'])
                if row['day'].endswith('-01'):monthly.setdefault(row['day'][:7],row['id'])
        selected.update(list(daily.values())[:30]);selected.update(list(monthly.values())[:3]);selected.update(list(cloud.values())[:14])
        return selected
    def _retention(self,db):
        rows=db.execute("SELECT * FROM packages WHERE state='published' ORDER BY created DESC").fetchall()
        keep=self._retained(rows)
        for row in rows:
            if row['id'] not in keep:self._remove(db,row,'retention_removed')
    def _space(self,db,needed):
        self._expire(db);self._retention(db)
        staged={trash for original,trash in self.deletions[id(db)]}
        used=db.execute('SELECT coalesce(sum(bytes),0) FROM packages').fetchone()[0]+self.trash_bytes(staged)
        if needed>self.quota:raise BackupError('backup_exceeds_quota',507)
        rows=db.execute("SELECT * FROM packages WHERE state='published' ORDER BY created").fetchall()
        newest={}
        for row in sorted(rows,key=lambda r:(r['day'],r['created'])):newest[row['kind']]=row['id']
        # Prefer old daily backups; keep at least the newest of each kind.
        candidates=sorted((r for r in rows if newest[r['kind']]!=r['id']),key=lambda r:(r['kind']=='home' and r['day'].endswith('-01'),r['created']))
        planned=[]
        for row in candidates:
            if used+needed<=self.quota:break
            planned.append(row);used-=row['bytes']
        if used+needed>self.quota:raise BackupError('backup_quota_full',507)
        for row in planned:self._remove(db,row,'quota_removed_old_backup')
    def normalize(self,manifest,kind):
        if not isinstance(manifest,dict) or manifest.get('schema')!=1 or manifest.get('format')!=FORMAT or manifest.get('privateKeyIncluded') is not False:raise BackupError('invalid_backup_manifest')
        package_id=manifest.get('packageId');self.directory(package_id)
        expected={'ledger.cms','configuration.cms'} if kind=='home' else {'cloud.cms'}
        parts=manifest.get('artifacts')
        if not isinstance(parts,list) or len(parts)!=len(expected):raise BackupError('invalid_backup_parts')
        names=set();normalized=[];total=0
        for item in parts:
            if not isinstance(item,dict):raise BackupError('invalid_backup_part')
            name=item.get('name');size=item.get('bytes');checksum=item.get('sha256');count=item.get('files',0)
            if not isinstance(name,str) or name not in expected or name in names or type(size) is not int or not 1<=size<=MAX_PACKAGE or not isinstance(checksum,str) or not HEX.fullmatch(checksum) or type(count) is not int or not 0<=count<=100000:raise BackupError('invalid_backup_part')
            names.add(name);total+=size;normalized.append({'name':name,'bytes':size,'sha256':checksum,'files':count})
        if names!=expected or total>MAX_PACKAGE:raise BackupError('backup_size_limit',413)
        source_bytes=manifest.get('sourceBytes',0)
        if type(source_bytes) is not int or not 0<=source_bytes<=MAX_PACKAGE:raise BackupError('invalid_source_size')
        times={}
        for field in ('startedAt','completedAt'):
            value=manifest.get(field)
            try:
                if not isinstance(value,str) or len(value)>64:raise ValueError()
                parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
                if parsed.tzinfo is None or parsed.timestamp()>self.clock()+300:raise ValueError()
            except (ValueError,TypeError,OverflowError):raise BackupError('invalid_backup_capture_time') from None
            times[field]=value
        if datetime.fromisoformat(times['completedAt'].replace('Z','+00:00'))<datetime.fromisoformat(times['startedAt'].replace('Z','+00:00')):raise BackupError('invalid_backup_capture_time')
        return {'schema':1,'packageId':package_id,'format':FORMAT,'privateKeyIncluded':False,'sourceBytes':source_bytes,**times,'artifacts':sorted(normalized,key=lambda p:p['name'])}
    def reserve(self,manifest,kind='home'):
        if kind not in {'home','cloud'}:raise BackupError('invalid_backup_kind')
        self.reap_trash()
        manifest=self.normalize(manifest,kind);package_id=manifest['packageId'];encoded=json.dumps(manifest,sort_keys=True,separators=(',',':'))
        now=self.clock();required=sum(p['bytes'] for p in manifest['artifacts'])+len(encoded.encode())
        with self.db(True) as db:
            old=db.execute('SELECT * FROM packages WHERE id=?',(package_id,)).fetchone()
            if old:
                if old['manifest']!=encoded or old['kind']!=kind:raise BackupError('backup_id_content_conflict',409)
                if old['state']=='reserved':
                    # Identical content can resume after a long network outage;
                    # capture date remains unchanged, only the upload lease renews.
                    db.execute('UPDATE packages SET expires=? WHERE id=?',(now+3600,package_id))
                    self.directory(package_id).mkdir(exist_ok=True)
                return {'packageId':package_id,'state':old['state'],'idempotent':True}
            self._space(db,required)
            day=datetime.fromisoformat(manifest['completedAt'].replace('Z','+00:00')).astimezone(LOCAL_TZ).date().isoformat()
            db.execute('INSERT INTO packages VALUES(?,?,?,?,?,?,?,?)',(package_id,kind,'reserved',now,day,now+3600,required,encoded))
            for part in manifest['artifacts']:db.execute('INSERT INTO parts(package_id,name,bytes,digest,state) VALUES(?,?,?,?,?)',(package_id,part['name'],part['bytes'],part['sha256'],'pending'))
        # Failed disk GC does not grant physical space for a new upload.
        with self.db(True) as db:
            used=db.execute('SELECT coalesce(sum(bytes),0) FROM packages').fetchone()[0]+self.trash_bytes()
            if used>self.quota:
                db.execute('DELETE FROM packages WHERE id=?',(package_id,));self.event(db,'backup_gc_blocks_reservation',package_id)
        if used>self.quota:raise BackupError('backup_gc_blocks_reservation',507)
        self.directory(package_id).mkdir(exist_ok=True)
        sync_directory(self.root)
        return {'packageId':package_id,'state':'reserved','idempotent':False}
    def begin_part(self,package_id,name,length):
        self.directory(package_id)
        with self.db(True) as db:
            row=db.execute('SELECT p.*,b.state AS package_state,b.expires FROM parts p JOIN packages b ON b.id=p.package_id WHERE p.package_id=? AND p.name=?',(package_id,name)).fetchone()
            if not row:raise BackupError('backup_part_not_reserved',404)
            if type(length) is not int or length!=row['bytes']:raise BackupError('backup_length_mismatch',413)
            if row['state']=='stored':return {'stored':True,'digest':row['digest'],'bytes':row['bytes']}
            now=self.clock()
            if row['package_state']!='reserved' or row['expires']<=now:raise BackupError('backup_reservation_expired',409)
            if row['lease']>now:raise BackupError('backup_part_busy',409)
            directory=self.directory(package_id)
            # Expired uploads may have left partial files after a process crash.
            # Remove only this part's fixed-name, expired private staging files;
            # otherwise repeated retries could grow beyond the reservation.
            for old in self._members(directory):
                if re.fullmatch(r'\.'+re.escape(name)+r'\.[a-f0-9]{32}\.partial',old.name):old.unlink()
            final=directory/name
            if final.exists():
                if final.stat().st_size==row['bytes'] and digest_file(final)==row['digest']:
                    db.execute("UPDATE parts SET state='stored',token=NULL,lease=0 WHERE package_id=? AND name=?",(package_id,name))
                    return {'stored':True,'digest':row['digest'],'bytes':row['bytes']}
                final.unlink() # Only an unpublished, invalid part can be retried.
            token=uuid.uuid4().hex
            db.execute('UPDATE parts SET token=?,lease=? WHERE package_id=? AND name=?',(token,now+600,package_id,name))
        temporary=self.directory(package_id)/('.'+name+'.'+token+'.partial')
        try:descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except OSError:
            with self.db(True) as db:db.execute('UPDATE parts SET token=NULL,lease=0 WHERE package_id=? AND name=? AND token=?',(package_id,name,token))
            raise
        return {'stored':False,'token':token,'path':temporary,'handle':os.fdopen(descriptor,'wb'),'bytes':row['bytes'],'digest':row['digest']}
    def abort_part(self,package_id,name,upload):
        if upload.get('stored'):return
        upload['handle'].close();upload['path'].unlink(missing_ok=True)
        with self.db(True) as db:db.execute('UPDATE parts SET token=NULL,lease=0 WHERE package_id=? AND name=? AND token=?',(package_id,name,upload['token']))
    def finish_part(self,package_id,name,upload,received,checksum):
        if upload.get('stored'):return
        upload['handle'].flush();os.fsync(upload['handle'].fileno());upload['handle'].close()
        if received!=upload['bytes'] or checksum!=upload['digest']:
            self.abort_part(package_id,name,upload);raise BackupError('backup_digest_or_length_mismatch')
        if not encrypted_cms_header(upload['path']):
            self.abort_part(package_id,name,upload);raise BackupError('backup_requires_encrypted_cms')
        with self.db(True) as db:
            row=db.execute('SELECT p.token,b.expires FROM parts p JOIN packages b ON b.id=p.package_id WHERE p.package_id=? AND p.name=?',(package_id,name)).fetchone()
            if not row or row['token']!=upload['token'] or row['expires']<=self.clock():raise BackupError('backup_upload_lease_lost',409)
            os.replace(upload['path'],self.directory(package_id)/name)
            sync_directory(self.directory(package_id))
            db.execute("UPDATE parts SET state='stored',token=NULL,lease=0 WHERE package_id=? AND name=?",(package_id,name))
    def publish(self,package_id):
        self.directory(package_id)
        with self.db(True) as db:
            row=db.execute('SELECT * FROM packages WHERE id=?',(package_id,)).fetchone()
            if not row:raise BackupError('backup_not_found',404)
            if row['state']!='published' and row['expires']<=self.clock():raise BackupError('backup_reservation_expired',409)
            if db.execute("SELECT count(*) FROM parts WHERE package_id=? AND state!='stored'",(package_id,)).fetchone()[0]:raise BackupError('backup_incomplete',409)
            directory=self.directory(package_id)
            for part in db.execute('SELECT * FROM parts WHERE package_id=?',(package_id,)):
                path=plain_path(directory/part['name'])
                if path.stat().st_size!=part['bytes'] or digest_file(path)!=part['digest']:raise BackupError('backup_disk_integrity_failure',500)
            if row['state']=='published':return {'packageId':package_id,'published':True}
            target=directory/'manifest.json'
            if target.exists():
                if target.read_text(encoding='utf-8')!=row['manifest']:raise BackupError('backup_manifest_disk_conflict',500)
            else:
                with target.open('x',encoding='utf-8') as handle:handle.write(row['manifest']);handle.flush();os.fsync(handle.fileno())
            sync_directory(directory)
            db.execute("UPDATE packages SET state='published' WHERE id=?",(package_id,))
            self._retention(db)
            self.event(db,'backup_published',package_id)
        with self.db() as db:retained=db.execute("SELECT 1 FROM packages WHERE id=? AND state='published'",(package_id,)).fetchone() is not None
        return {'packageId':package_id,'published':True,'retained':retained}
    def catalog(self):
        with self.db() as db:
            rows=db.execute("SELECT * FROM packages WHERE state='published' ORDER BY created DESC").fetchall()
            used=db.execute('SELECT coalesce(sum(bytes),0) FROM packages').fetchone()[0]+self.trash_bytes()
            events=[dict(r) for r in db.execute('SELECT at,code,package_id FROM events ORDER BY id DESC LIMIT 20')]
            recipient=db.execute('SELECT digest FROM recipient WHERE id=1').fetchone()
            state=db.execute('SELECT * FROM agent_state WHERE id=1').fetchone()
        return {'items':[{'packageId':r['id'],'kind':r['kind'],'createdAt':r['created'],'date':r['day'],'bytes':r['bytes'],'manifest':json.loads(r['manifest'])} for r in rows],
                'usedReservedBytes':used,'quotaBytes':self.quota,'retainedDates':sorted({r['day'] for r in rows}),'events':events,'recipientConfigured':bool(recipient),
                'agentState':json.loads(state['body']) if state else None,'agentStateReceivedAt':state['received'] if state else None}
    def note_agent_state(self,value):
        allowed={'phase','observedAt','packageId','sourceBytes','ciphertextBytes','completedAt','capturedAt','reason'}
        if not isinstance(value,dict) or set(value)-allowed or len(json.dumps(value))>4096:raise BackupError('invalid_backup_state')
        if not isinstance(value.get('phase'),str) or value.get('phase') not in {'waiting_configuration','creating','uploading','completed','failed'}:raise BackupError('invalid_backup_state')
        for key,child in value.items():
            if key in {'sourceBytes','ciphertextBytes'}:
                if type(child) is not int or not 0<=child<=MAX_PACKAGE:raise BackupError('invalid_backup_state')
            elif not isinstance(child,str) or len(child)>128 or any(ord(c)<32 for c in child):raise BackupError('invalid_backup_state')
        with self.db(True) as db:db.execute('INSERT OR REPLACE INTO agent_state VALUES(1,?,?)',(self.clock(),json.dumps(value)))
    def open_download(self,package_id,name):
        with self.db(True) as db:
            if name=='manifest.json':
                package=db.execute("SELECT manifest FROM packages WHERE id=? AND state='published'",(package_id,)).fetchone()
                if not package:raise BackupError('backup_not_found',404)
                path=plain_path(self.directory(package_id)/name)
                encoded=package['manifest'].encode()
                if digest_file(path)!=hashlib.sha256(encoded).hexdigest():raise BackupError('backup_disk_integrity_failure',500)
                source=open(path,'rb')
                return source,{'bytes':len(encoded),'digest':hashlib.sha256(encoded).hexdigest()}
            row=db.execute("SELECT p.* FROM parts p JOIN packages b ON b.id=p.package_id WHERE p.package_id=? AND p.name=? AND b.state='published'",(package_id,name)).fetchone()
            if not row:raise BackupError('backup_not_found',404)
            path=plain_path(self.directory(package_id)/name)
            descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0));source=os.fdopen(descriptor,'rb')
            if os.fstat(source.fileno()).st_size!=row['bytes']:source.close();raise BackupError('backup_disk_integrity_failure',500)
            return source,dict(row)
    def verify(self,package_id):
        with self.db() as db:
            row=db.execute("SELECT manifest FROM packages WHERE id=? AND state='published'",(package_id,)).fetchone()
        if not row:raise BackupError('backup_not_found',404)
        manifest=json.loads(row['manifest']);parts=[]
        for item in manifest['artifacts']:
            source,metadata=self.open_download(package_id,item['name'])
            checksum=hashlib.sha256()
            with source:
                while block:=source.read(1024*1024):checksum.update(block)
            matches=checksum.hexdigest()==metadata['digest']
            parts.append({'name':item['name'],'matches':matches,'sha256':checksum.hexdigest()})
        return {'packageId':package_id,'verified':all(item['matches'] for item in parts),'parts':parts}
    def request(self):
        with self.db(True) as db:
            old=db.execute('SELECT * FROM requests WHERE id=1').fetchone()
            if old and old['completed']==0:return old['generation']
            generation=uuid.uuid4().hex
            db.execute('INSERT OR REPLACE INTO requests VALUES(1,?,?,0)',(generation,self.clock()))
        return generation
    def pending_request(self):
        with self.db() as db:row=db.execute('SELECT generation FROM requests WHERE id=1 AND completed=0').fetchone()
        return row['generation'] if row else None
    def complete_request(self,generation):
        if not isinstance(generation,str):return
        with self.db(True) as db:db.execute('UPDATE requests SET completed=? WHERE id=1 AND generation=?',(self.clock(),generation))
    def recipient(self):
        with self.db() as db:row=db.execute('SELECT * FROM recipient WHERE id=1').fetchone()
        return dict(row) if row else None
    def set_recipient(self,certificate):
        if not isinstance(certificate,str) or not 100<=len(certificate)<=16384 or not certificate.startswith('-----BEGIN CERTIFICATE-----') or not certificate.rstrip().endswith('-----END CERTIFICATE-----') or 'PRIVATE KEY' in certificate:raise BackupError('invalid_public_certificate')
        digest=hashlib.sha256(certificate.encode()).hexdigest()
        with self.db(True) as db:
            old=db.execute('SELECT * FROM recipient WHERE id=1').fetchone()
            if old and old['digest']!=digest:raise BackupError('backup_recipient_change_requires_local_admin',409)
            db.execute('INSERT OR IGNORE INTO recipient VALUES(1,?,?)',(digest,certificate))
        return {'recipientSha256':digest}
    def cancel(self,package_id):
        with self.db(True) as db:
            row=db.execute("SELECT * FROM packages WHERE id=? AND state='reserved'",(package_id,)).fetchone()
            if not row:return
            if db.execute('SELECT 1 FROM parts WHERE package_id=? AND lease>?',(package_id,self.clock())).fetchone():raise BackupError('backup_upload_active',409)
            self._remove(db,row,'incomplete_backup_cancelled')
