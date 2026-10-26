"""Explicit bounded snapshot capture; no discovery, credentials or live HTTP."""
from __future__ import annotations
import hashlib,json,os,shutil,sqlite3,tempfile,re,csv,time
from contextlib import closing
from datetime import datetime
from pathlib import Path,PureWindowsPath

SCHEMA=2
TABLES={'tasks','task_history','events','heartbeats','source_health','sqlite_sequence'}
SECRETS={'password','newpassword','oldpassword','invite','authorization','cookie','csrf','secret','signingsecret','webhook','accesstoken','access_token','api_key','apikey','agent_token','agent_token_sha256','invite_hash','password_hash','refresh_token','client_secret','token','authkey','tailscaleauthkey','invitationcode','sessiontoken'}
# Normalized once: rebuilding it per dict key dominated large state scans.
_SECRET_KEYS=frozenset(k.replace('_','') for k in SECRETS)
PRIVATE_FILES={'config.json','task_receiver_config.json','baidu_upload_config.json','.env','notifications.json','agent.json'}

class SnapshotError(ValueError): pass

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def digest_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def relative(value):
    if not isinstance(value,str) or not value or len(value)>240 or chr(92) in value or ':' in value or value.startswith('/') or PureWindowsPath(value).drive or any(p in {'','..','.'} for p in value.split('/')):
        raise SnapshotError('invalid_snapshot_relative_path')
    if value=='snapshot.json':raise SnapshotError('manifest_name_reserved')
    return value

def no_links(path):
    path=Path(path).absolute()
    for item in (path,*path.parents):
        if item.is_symlink() or (hasattr(item,'is_junction') and item.is_junction()):
            raise SnapshotError('snapshot_link_forbidden')
    return path

def safe_facts(value):
    if isinstance(value,dict):
        for key,item in value.items():
            normalized=str(key).lower().replace('-','').replace('_','')
            if normalized in _SECRET_KEYS:raise SnapshotError('credential_field_forbidden')
            safe_facts(item)
    elif isinstance(value,list):
        for item in value:safe_facts(item)
    elif isinstance(value,str) and ('tskey-' in value or 'PRIVATE KEY-----' in value or 'open.feishu.cn/open-apis/bot/v2/hook/' in value or value.lower().startswith('bearer ') or re.search(r'''(?i)(?:^|[\s"'])(?:password|secret|webhook|authorization|access_token|api_key|agent_token|invite_hash)["']*\s*[:=]''',value)):
        raise SnapshotError('credential_value_forbidden')

def sqlite_rows(path):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('BEGIN')
        names=[r[0] for r in db.execute("select name from sqlite_master where type='table' order by name")]
        if set(names)-TABLES:raise SnapshotError('unexpected_ops_table')
        result={}
        for name in names:
            columns=[row[1] for row in db.execute('pragma table_info("'+name+'")')]
            rows=[dict(zip(columns,row)) for row in db.execute('select * from "'+name+'"')]
            safe_facts(rows)
            result[name]=sorted(rows,key=lambda row:canonical(row))
        return result

_ROWS_HASHES={}


def _closed_database(path):
    # Read-only opens of a WAL-mode copy leave an empty -wal behind; an empty
    # WAL/journal means every row is in the main file the key is derived from.
    for suffix in ('-wal','-journal'):
        sibling=path.with_name(path.name+suffix)
        if sibling.exists() and sibling.stat().st_size>0:return False
    return True


def rows_sha256(path,rows=None):
    """sha256 of canonical rows; also enforces the sqlite_rows privacy check.

    One capture hashes the same closed copy several times (alignment checks,
    manifest validation, store publication); ~800k rows took 8 s per pass.
    Only a closed file is cached, keyed by its bytes: a WAL/journal sibling
    means a live database, which is always re-read. Callers that already read
    the rows of a closed file may pass them to seed the cache.
    """
    path=Path(path)
    if rows is not None:
        if not _closed_database(path):raise SnapshotError('rows_seed_requires_closed_database')
        value=hashlib.sha256(canonical(rows)).hexdigest()
        _ROWS_HASHES.clear();_ROWS_HASHES[(digest_file(path),path.stat().st_size)]=value
        return value
    if not _closed_database(path):
        return hashlib.sha256(canonical(sqlite_rows(path))).hexdigest()
    key=(digest_file(path),path.stat().st_size)
    if key not in _ROWS_HASHES:
        value=hashlib.sha256(canonical(sqlite_rows(path))).hexdigest()
        _ROWS_HASHES.clear();_ROWS_HASHES[key]=value
    return _ROWS_HASHES[key]


def _publish_snapshot(stage, destination, *, timeout=1.0):
    """Publish once, tolerating bounded Windows rename contention.

    A temporary Windows directory handle can deny rename even after all of
    our streams are closed. Keep the validated stage intact; never delete or
    overwrite a destination to make a retry succeed. Permanent errors remain
    errors, and a different source directory cannot be substituted on retry.
    """
    if not 0 <= timeout <= 5:
        raise ValueError('snapshot_publish_timeout_out_of_range')
    stage=no_links(stage);destination=no_links(destination)
    identity=stage.stat()
    if not stage.is_dir():raise SnapshotError('snapshot_stage_not_directory')
    deadline=time.monotonic()+timeout
    while True:
        if destination.exists():raise SnapshotError('snapshot_destination_exists')
        current=no_links(stage).stat()
        if (current.st_dev,current.st_ino)!=(identity.st_dev,identity.st_ino):
            raise SnapshotError('snapshot_stage_identity_changed')
        try:
            # Windows rename refuses an existing target atomically, including
            # an empty directory created after the existence check above.
            os.rename(stage,destination)
            return
        except OSError as error:
            remaining=deadline-time.monotonic()
            if os.name!='nt' or getattr(error,'winerror',None) not in {5,32,33} or remaining<=0:
                raise
            time.sleep(min(0.02,remaining))


def capture(destination,*,files=None,databases=None,facts,frozen_at,legacy_sha256,max_file_bytes=32*1024*1024,max_total_bytes=512*1024*1024):
    files=files or {};databases=databases or {};destination=no_links(destination)
    if destination.exists():raise SnapshotError('snapshot_destination_exists')
    if not isinstance(legacy_sha256,str) or len(legacy_sha256)!=64 or any(c not in '0123456789abcdef' for c in legacy_sha256):raise SnapshotError('legacy_source_hash_required')
    when=datetime.fromisoformat(frozen_at.replace('Z','+00:00'))
    if when.utcoffset() is None:raise SnapshotError('explicit_timezone_required')
    safe_facts(facts);canonical(facts)
    for old,new in facts.get('pathAliases',{}).items():
        relative(new)
        if not isinstance(old,str) or not (PureWindowsPath(old).is_absolute() or Path(old).is_absolute()):raise SnapshotError('invalid_path_alias')
        # A drive root has no name but is a valid explicit capture root; replay
        # translates the longest alias first, so deeper roots still win.
        windows=PureWindowsPath(old)
        if not windows.name and not (windows.drive and str(windows)==windows.anchor):raise SnapshotError('invalid_path_alias')
    for name,node in facts.get('filesystem',{}).items():
        relative(name)
        if node.get('kind') not in {'file','directory'} or type(node.get('size',0)) is not int or node.get('size',0)<0 or type(node.get('mtimeNs',0)) is not int:raise SnapshotError('invalid_filesystem_fact')
    if set(files)&set(databases):raise SnapshotError('duplicate_snapshot_name')
    inputs={relative(k):no_links(v) for k,v in {**files,**databases}.items()}
    if len(inputs)>10000:raise SnapshotError('too_many_snapshot_files')
    for name,source in inputs.items():
        if source==destination or source.is_relative_to(destination) or destination.is_relative_to(source):raise SnapshotError('snapshot_source_destination_overlap')
        if not source.is_file():raise SnapshotError('snapshot_source_missing')
        if source.name.lower() in PRIVATE_FILES or source.suffix.lower() in {'.env','.exe','.dll','.mp4','.wav','.mp3','.zip','.rar'}:raise SnapshotError('non_state_source_forbidden')
        if name not in databases and source.suffix.lower() not in {'.json','.csv','.log','.txt'}:raise SnapshotError('explicit_state_type_required')
    before={name:(p.stat().st_size,p.stat().st_mtime_ns) for name,p in inputs.items()}
    database_before={name:rows_sha256(path) for name,path in inputs.items() if name in databases}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.r0-snapshot-',dir=destination.parent) as folder:
        stage=Path(folder);records={};total=0
        for name,source in inputs.items():
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
            kind='sqlite' if name in databases else 'file'
            if kind=='sqlite':
                with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as db,closing(sqlite3.connect(target)) as output:
                    db.backup(output)
                table_hash=rows_sha256(target)
            else:
                if before[name][0]>max_file_bytes:raise SnapshotError('snapshot_file_too_large')
                with source.open('rb') as stream:body=stream.read(max_file_bytes+1)
                if len(body)>max_file_bytes:raise SnapshotError('snapshot_file_too_large')
                try:safe_facts(body.decode('utf-8-sig'))
                except UnicodeError:pass
                if source.suffix.lower()=='.csv':
                    try:safe_facts({key:None for key in next(csv.reader(body.decode('utf-8-sig').splitlines()),[])})
                    except UnicodeError:pass
                if source.suffix.lower()=='.json':
                    try:safe_facts(json.loads(body.decode('utf-8-sig')))
                    except (UnicodeError,json.JSONDecodeError):pass # Broken JSON is a required replay input.
                target.write_bytes(body)
            total+=target.stat().st_size
            if total>max_total_bytes:raise SnapshotError('snapshot_total_too_large')
            os.utime(target,ns=(before[name][1],before[name][1]))
            records[name]={'kind':kind,'sha256':digest_file(target),'size':target.stat().st_size,'mtimeNs':before[name][1]}
            if kind=='sqlite':records[name]['rowsSha256']=table_hash
        after={name:(p.stat().st_size,p.stat().st_mtime_ns) for name,p in inputs.items()}
        if before!=after:raise SnapshotError('unaligned_capture_window')
        for name,path in inputs.items():
            if name in databases:
                current=rows_sha256(path)
                if current!=database_before[name] or current!=records[name]['rowsSha256']:raise SnapshotError('unaligned_database_window')
            elif digest_file(path)!=records[name]['sha256']:raise SnapshotError('unaligned_file_content')
        manifest={'schema':SCHEMA,'frozenAt':frozen_at,'legacySha256':legacy_sha256,'facts':facts,'files':records,'origin':'explicit-inputs','realBatchEvidence':False}
        manifest['sourceIdentity']=hashlib.sha256(canonical(manifest)).hexdigest()
        encoded=canonical(manifest)+b'\n'
        if len(encoded)>8*1024*1024:raise SnapshotError('snapshot_manifest_too_large')
        (stage/'snapshot.json').write_bytes(encoded)
        Snapshot(stage)
        _publish_snapshot(stage,destination)
    return Snapshot(destination)

class Snapshot:
    def __init__(self,root):
        self.root=no_links(root)
        try:
            if (self.root/'snapshot.json').stat().st_size>8*1024*1024:raise SnapshotError('snapshot_manifest_too_large')
            self.manifest=json.loads((self.root/'snapshot.json').read_text(encoding='utf-8'))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise SnapshotError('snapshot_manifest_required') from exc
        if not isinstance(self.manifest,dict) or self.manifest.get('schema')!=SCHEMA:raise SnapshotError('snapshot_schema_unsupported')
        manifest=dict(self.manifest);identity=manifest.pop('sourceIdentity',None)
        if hashlib.sha256(canonical(manifest)).hexdigest()!=identity:raise SnapshotError('snapshot_manifest_hash_mismatch')
        if not isinstance(manifest.get('facts'),dict) or not isinstance(manifest.get('files'),dict) or len(manifest['files'])>10000:raise SnapshotError('snapshot_manifest_fields_invalid')
        safe_facts(manifest['facts'])
        for name,record in manifest['files'].items():
            if not isinstance(record,dict) or record.get('kind') not in {'file','sqlite'}:raise SnapshotError('snapshot_file_kind_invalid')
            path=no_links(self.root/relative(name))
            if path.stat().st_size!=record['size'] or digest_file(path)!=record['sha256']:raise SnapshotError('snapshot_file_hash_mismatch')
            if record['kind']=='sqlite' and rows_sha256(path)!=record['rowsSha256']:raise SnapshotError('snapshot_rows_hash_mismatch')
    def read(self,name):
        if name not in self.manifest['files']:raise SnapshotError('undeclared_snapshot_file')
        return (self.root/relative(name)).read_bytes()
    def json(self,name):return json.loads(self.read(name).decode('utf-8-sig'))
    def materialize(self,destination):
        target=Path(destination)
        if target.exists():raise SnapshotError('replay_destination_exists')
        target.mkdir(parents=True)
        for name,record in self.manifest['files'].items():
            out=target/relative(name);out.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.root/name,out)
            os.utime(out,ns=(record['mtimeNs'],record['mtimeNs']))
        for name,node in self.manifest['facts'].get('filesystem',{}).items():
            relative(name)
            if name in self.manifest['files']:continue
            out=target/name;out.parent.mkdir(parents=True,exist_ok=True)
            if node.get('kind')=='directory':out.mkdir(exist_ok=True)
            elif node.get('kind')=='file':out.touch()
            else:raise SnapshotError('invalid_filesystem_fact')
        return target
