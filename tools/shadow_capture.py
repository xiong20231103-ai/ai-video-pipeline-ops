"""Bounded, stable-window capture. No production import or source SQL writes.

Only exact reviewed paths are accepted. Directory entries are facts, not media
copies. Database snapshots use a bounded read-only SQLite online backup.
"""
from __future__ import annotations
import hashlib,json,os,re,sqlite3,tempfile,time,stat
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from agent.core.snapshot import Snapshot,SnapshotError,canonical,capture,digest_file,no_links,relative,safe_facts,PRIVATE_FILES,sqlite_rows
from agent.core.source_profiles import PROFILES,PR49,PR49_HELPER
from tools.shadow_capture_errors import CaptureError
from tools.shadow_sqlite_snapshot import online_backup

ROOT_NAMES={'repository','workbench','voice','capcut','downloads','generation','final','drafts','audio','pending-delete'}

def _safe(value):
    safe_facts(value)
    if isinstance(value,str):
        from urllib.parse import urlsplit,parse_qsl
        for url in re.findall(r'''https?://[^\s\x00-\x1f"'<>]+''',value):
            try:parts=urlsplit(url)
            except ValueError:raise CaptureError('invalid_capture_url') from None
            if parts.username or parts.password or any(re.search(r'token|password|secret|webhook|authorization|cookie|api.?key',key,re.I) for key,_ in parse_qsl(parts.query)):raise CaptureError('private_capture_url')
    if isinstance(value,dict):
        for key,child in value.items():
            if re.search(r'token|password|secret|webhook|authorization|cookie|api.?key|invitation',str(key),re.I):raise CaptureError('private_capture_field')
            _safe(child)
    elif isinstance(value,list):
        for child in value:_safe(child)
    elif isinstance(value,str) and re.search(r'''(?i)["']?[^"'\s]*(?:token|password|secret|webhook|authorization|cookie|api.?key)[^"'\s]*["']\s*[:=]|-----BEGIN .*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}''',value):raise CaptureError('private_capture_string')

def _stat(path):
    path=no_links(path)
    try:s=path.lstat()
    except FileNotFoundError:return None
    if getattr(s,'st_file_attributes',0)&getattr(__import__('stat'),'FILE_ATTRIBUTE_REPARSE_POINT',1024):raise CaptureError('reparse_point_forbidden')
    if not stat.S_ISREG(s.st_mode) and not stat.S_ISDIR(s.st_mode):raise CaptureError('special_file_forbidden')
    return {'kind':'directory' if stat.S_ISDIR(s.st_mode) else 'file','size':s.st_size if stat.S_ISREG(s.st_mode) else 0,'mtimeNs':s.st_mtime_ns,'ctimeNs':s.st_ctime_ns,'inode':s.st_ino,'device':s.st_dev}

def _read(path,limit):
    before=_stat(path)
    if not before or before['kind']!='file':raise CaptureError('required_capture_file_missing')
    if before['size']>limit:raise CaptureError('capture_file_limit')
    with path.open('rb') as f:
        opened=os.fstat(f.fileno())
        if (opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns)!=(before['device'],before['inode'],before['size'],before['mtimeNs']):raise CaptureError('capture_open_identity_changed')
        data=f.read(limit+1)
    if len(data)>limit or _stat(path)!=before:raise CaptureError('capture_file_changed')
    return data,before

def _source(roots,spec):
    if not isinstance(spec,dict) or set(spec)!={'root','path'} or spec['root'] not in roots:raise CaptureError('invalid_capture_binding')
    rel=spec['path']
    if rel!='.':relative(rel)
    base=roots[spec['root']];path=no_links(base if rel=='.' else base/rel)
    # Check lexical containment too; links are rejected by no_links, never followed.
    if not path.is_relative_to(base):raise CaptureError('capture_binding_escape')
    return path

def validate_plan(plan,destination):
    if not isinstance(plan,dict) or plan.get('schema')!=1:raise CaptureError('capture_plan_schema')
    roots=plan.get('roots',{})
    if not roots or set(roots)-ROOT_NAMES:raise CaptureError('capture_root_not_allowed')
    roots={k:no_links(v) for k,v in roots.items()}
    dest=no_links(destination)
    exclusions={name:_source(roots,spec) for name,spec in plan.get('exclude',{}).items()}
    for name,path in exclusions.items():
        relative(name)
        spec=plan['exclude'][name]
        if name!=spec['root']+'/'+spec['path']:raise CaptureError('excluded_logical_path_mismatch')
        if path in roots.values():raise CaptureError('capture_root_cannot_be_excluded')
    shallow=plan.get('shallow',{})
    for path in roots.values():
        if dest==path or dest.is_relative_to(path) or path.is_relative_to(dest):
            # A drive alias is permitted ONLY with a shallow root and an exact
            # exclusion that contains all outputs. Never a blanket bypass.
            excluded=any(dest==p or dest.is_relative_to(p) for p in exclusions.values())
            shallow_root=any(_source(roots,spec)==path for spec in shallow.values())
            if not (dest.is_relative_to(path) and excluded and shallow_root):raise CaptureError('capture_output_source_overlap')
    if dest.exists():raise CaptureError('new_capture_destination_required')
    files=plan.get('files',{});databases=plan.get('databases',{});absent=plan.get('absent',{});trees=plan.get('trees',{})
    if len(files)+len(databases)+len(absent)+len(trees)>10000:raise CaptureError('capture_binding_limit')
    names=list(files)+list(databases)+list(absent)+list(trees)+list(shallow)
    if len(names)!=len(set(names)):raise CaptureError('duplicate_capture_binding')
    bindings={}
    for name,spec in {**files,**databases,**absent,**trees,**shallow}.items():
        relative(name);path=_source(roots,spec);bindings[name]=path
        if any(path==p or path.is_relative_to(p) for p in exclusions.values()):raise CaptureError('excluded_capture_input')
        if name in files and (path.name.lower() in PRIVATE_FILES or path.suffix.lower() not in {'.json','.csv','.txt','.log'}):raise CaptureError('state_content_not_allowed')
        if name in databases and (name!='repository/data/ops.db' or spec!={'root':'repository','path':'data/ops.db'}):raise CaptureError('database_not_allowlisted')
    return roots,bindings

class DigestCache:
    """Memory only; reuse requires unchanged path, file ID, ctime, mtime and size."""
    def __init__(self,max_entries=10000):self.values={};self.partial={};self.max_entries=max_entries
    def observe(self,path,info,budget):
        key=str(path);previous=self.values.get(key)
        if previous and previous['identity']==info:return previous['sha256'],0
        if key not in self.values and key not in self.partial and len(set(self.values)|set(self.partial))>=self.max_entries:raise CaptureError('digest_cache_limit')
        current=self.partial.get(key)
        if not current or current['identity']!=info:
            current={'identity':dict(info),'hash':hashlib.sha256(),'offset':0};self.partial[key]=current;self.values.pop(key,None)
        amount=min(max(0,budget),info['size']-current['offset'])
        if amount:
            with path.open('rb') as stream:
                stream.seek(current['offset']);raw=stream.read(amount)
            if len(raw)!=amount or _stat(path)!=info:
                self.partial.pop(key,None);raise CaptureError('metadata_file_changed')
            current['hash'].update(raw);current['offset']+=len(raw)
        if current['offset']!=info['size']:return None,amount
        digest=current['hash'].hexdigest();self.partial.pop(key,None)
        self.values[key]={'identity':dict(info),'sha256':digest}
        return digest,amount
    def hash(self,path,info):
        key=str(path);previous=self.values.get(key)
        if previous and previous['identity']==info:return previous['sha256'],0
        if key not in self.values and len(self.values)>=self.max_entries:raise CaptureError('digest_cache_limit')
        digest=digest_file(path)
        if _stat(path)!=info:raise CaptureError('metadata_file_changed')
        self.values[key]={'identity':dict(info),'sha256':digest}
        return digest,info['size']

def _inventory(plan,bindings,max_entries,max_hash_bytes,digest_cache=None):
    nodes={};identity={};hashed=0
    excluded=[_source({k:no_links(v) for k,v in plan['roots'].items()},spec) for spec in plan.get('exclude',{}).values()]
    def excluded_path(path):return any(path==base or path.is_relative_to(base) for base in excluded)
    for prefix in plan.get('trees',{}):
        pending=[(prefix,bindings[prefix])]
        while pending:
            name,path=pending.pop();info=_stat(path)
            if info is None:raise CaptureError('metadata_root_missing_use_explicit_absence')
            if name==prefix and info['kind']!='directory':raise CaptureError('metadata_root_must_be_directory')
            if name in nodes:raise CaptureError('overlapping_metadata_trees')
            if len(nodes)>=max_entries:raise CaptureError('metadata_entry_limit')
            identity[name]=info;nodes[name]={k:info[k] for k in ('kind','size','mtimeNs','ctimeNs')}
            if info['kind']=='directory':
                children=[]
                for child in path.iterdir():
                    if excluded_path(child):continue
                    children.append(child)
                    if len(children)+len(nodes)+len(pending)>max_entries:raise CaptureError('metadata_entry_limit')
                children.sort(key=lambda p:p.name)
                pending.extend((name+'/'+p.name,p) for p in reversed(children))
            elif plan.get('hashMetadataFiles',False):
                if path.name.lower() in PRIVATE_FILES or path.suffix.lower() in {'.env','.dat','.exe','.dll'}:
                    nodes[name]['hashUnavailable']='private_or_non_evidence_type';continue
                cache=digest_cache or DigestCache()
                digest,used=cache.observe(path,info,max_hash_bytes-hashed);hashed+=used
                if digest is None:nodes[name]['hashPending']=True
                else:nodes[name]['contentSha256']=digest
                if _stat(path)!=info:raise CaptureError('metadata_file_changed')
    # Shallow parents list immediate child identities, but never certify the
    # contents of unvisited children. Recursive trees above own their contents.
    for prefix in plan.get('shallow',{}):
        path=bindings[prefix];info=_stat(path)
        if info is None or info['kind']!='directory':raise CaptureError('shallow_directory_required')
        rows=[(prefix,path,info)]
        for child in sorted(path.iterdir(),key=lambda p:p.name):
            if excluded_path(child):continue
            child_info=_stat(child)
            if child_info is None:raise CaptureError('directory_changed_in_window')
            rows.append((prefix+'/'+child.name,child,child_info))
            if len(rows)+len(nodes)>max_entries:raise CaptureError('metadata_entry_limit')
        for name,child,node in rows:
            if name in nodes:continue
            identity[name]=node;nodes[name]={k:node[k] for k in ('kind','size','mtimeNs','ctimeNs')}
            if node['kind']=='directory':nodes[name]['contentsCaptured']=False
        nodes[prefix]['contentsCaptured']=True
    return nodes,identity

def _observations(process_probe,http_probe):
    processes=process_probe();http=http_probe();generation=None
    if isinstance(http,dict) and set(http)=={'responses','observationGeneration'}:
        generation=http['observationGeneration'];http=http['responses']
        if type(generation) is not int or generation<1:raise CaptureError('invalid_external_observation_generation')
    if not isinstance(processes,dict) or not isinstance(http,dict):raise CaptureError('capture_observation_shape')
    if set(processes)-{'processRecords','processIds','processes','diskUsage'}:raise CaptureError('unexpected_process_fact')
    _safe(processes);_safe(http)
    for row in processes.get('processRecords',[]):
        if type(row.get('pid')) is not int or not isinstance(row.get('create_time'),(int,float)) or not isinstance(row.get('cmdline'),list):raise CaptureError('process_birth_identity_required')
        if any(not isinstance(arg,str) or re.search(r'token|password|secret|webhook|authorization|cookie|api.?key',arg,re.I) for arg in row['cmdline']):raise CaptureError('private_process_argument')
    # Only explicitly recorded GET-port responses; never cookies/headers/credentials.
    if any(not re.fullmatch(r'(receiver|control):/api/[A-Za-z0-9_/?=&%.:-]+',k) for k in http):raise CaptureError('unexpected_external_port')
    return processes,http,generation

def aligned_capture(plan,destination,*,source_path,process_probe,http_probe,max_file_bytes=32*1024*1024,max_total_bytes=512*1024*1024,max_entries=10000,max_hash_bytes=64*1024*1024,max_window_seconds=20,digest_cache=None,clock=time.monotonic,now=lambda:datetime.now(timezone.utc).isoformat()):
    roots,bindings=validate_plan(plan,destination)
    if max_window_seconds<=0 or max_window_seconds>60:raise CaptureError('capture_window_limit')
    started=clock();opened_at=now();source_path=no_links(source_path)
    if source_path.stat().st_size>2*1024*1024:raise CaptureError('capture_source_byte_limit')
    source=source_path.read_text(encoding='utf-8-sig');source_sha=hashlib.sha256(source.encode()).hexdigest()
    if source_sha not in PROFILES:raise CaptureError('unreviewed_capture_source')
    helper=source_path.with_name('verified_final.py')
    dependency_names=['pending_delete.py','cleanup_tickets.py']+(['verified_final.py'] if source_sha==PR49 else [])
    package_root=Path(__file__).resolve().parents[1];dependency_hashes={}
    for name in dependency_names:
        installed=source_path.with_name(name)
        if not installed.is_file():
            if source_path.parent==package_root:raise CaptureError('capture_dependency_missing')
            continue # Synthetic source-only capture is not live evidence.
        actual=hashlib.sha256(installed.read_text(encoding='utf-8-sig').encode()).hexdigest()
        expected=hashlib.sha256((package_root/name).read_text(encoding='utf-8-sig').encode()).hexdigest()
        if actual!=expected:raise CaptureError('capture_dependency_not_reviewed')
        dependency_hashes[name]=actual
    if source_sha==PR49 and hashlib.sha256(helper.read_text(encoding='utf-8-sig').encode()).hexdigest()!=PR49_HELPER:raise CaptureError('capture_source_dependency_mismatch')
    processes,http,http_generation=_observations(process_probe,http_probe)
    nodes,inventory=_inventory(plan,bindings,max_entries,max_hash_bytes,digest_cache)
    missing={k:_stat(bindings[k]) for k in plan.get('absent',{})}
    if any(v is not None for v in missing.values()):raise CaptureError('declared_absence_exists')
    before={};copied={};database_proofs={};total=0
    # All staging writes are new and outside production roots.
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.aligned-capture-',dir=destination.parent) as folder:
        scratch=Path(folder)
        for name in plan.get('files',{}):
            body,info=_read(bindings[name],max_file_bytes);total+=len(body)
            if total>max_total_bytes:raise CaptureError('capture_total_limit')
            try:
                text=body.decode('utf-8-sig');_safe(text)
                if bindings[name].suffix.lower()=='.json':
                    try:_safe(json.loads(text))
                    except json.JSONDecodeError:pass # Corrupt JSON itself must replay faithfully.
                elif bindings[name].suffix.lower()=='.csv':
                    import csv
                    _safe({key:None for key in next(csv.reader(text.splitlines()),[])})
            except UnicodeError:raise CaptureError('state_content_not_utf8') from None
            target=scratch/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body);os.utime(target,ns=(info['mtimeNs'],info['mtimeNs']))
            copied[name]=target;before[name]=info
        databases={}
        for name in plan.get('databases',{}):
            target=scratch/'database-normalized'/name;target.parent.mkdir(parents=True,exist_ok=True)
            opened=now()
            proof=online_backup(bindings[name],target,max_bytes=max_total_bytes-total,
                                timeout_seconds=max_window_seconds,clock=clock)
            database_proofs[name]={**proof,'openedAt':opened,'closedAt':now()}
            total+=target.stat().st_size
            _safe(sqlite_rows(target));databases[name]=target
        ended_at=now();settings=plan.get('facts',{});_safe(settings)
        if set(settings)-{'machineName','settings','metrics','collectorAlive','scan','historyResetGeneration','historyResetAt','historyAliases'}:raise CaptureError('unexpected_capture_fact')
        facts={**settings,**processes,'http':http,'filesystem':nodes,'pathAliases':{str(p):name for name,p in roots.items()},'dependencyClosure':True,'absentPaths':sorted(missing),'completeDirectoryRoots':sorted(plan.get('trees',{})),'excludedPaths':sorted(plan.get('exclude',{}))}
        facts['captureProof']={'schema':1,'openedAt':opened_at,'closedAt':ended_at,'processSha256':hashlib.sha256(canonical(processes)).hexdigest(),'httpSha256':hashlib.sha256(canonical(http)).hexdigest(),'inventorySha256':hashlib.sha256(canonical(inventory)).hexdigest(),'databaseSnapshotMethod':'sqlite-online-readonly','databaseSnapshots':database_proofs,'externalObservationGeneration':http_generation,'helperHashes':dependency_hashes}
        result=capture(scratch/'package',files=copied,databases=databases,facts=facts,frozen_at=ended_at,legacy_sha256=source_sha,max_file_bytes=max_file_bytes,max_total_bytes=max_total_bytes)
        # Recheck the entire window, including external response bodies and PID birth identity.
        if _observations(process_probe,http_probe)!=(processes,http,http_generation):raise CaptureError('external_or_process_changed')
        if {name:_stat(bindings[name]) for name in before}!=before:raise CaptureError('state_changed_in_window')
        for name,path in copied.items():
            if digest_file(bindings[name])!=digest_file(path):raise CaptureError('state_content_changed_in_window')
        if any(_stat(bindings[name]) is not None for name in missing):raise CaptureError('absence_changed_in_window')
        if _inventory({**plan,'hashMetadataFiles':False},bindings,max_entries,0)[1]!=inventory:raise CaptureError('directory_changed_in_window')
        if any(hashlib.sha256(source_path.with_name(name).read_text(encoding='utf-8-sig').encode()).hexdigest()!=value for name,value in dependency_hashes.items()):raise CaptureError('dependency_changed_in_window')
        if source_path.read_text(encoding='utf-8-sig')!=source or source_sha==PR49 and hashlib.sha256(helper.read_text(encoding='utf-8-sig').encode()).hexdigest()!=PR49_HELPER:raise CaptureError('source_changed_in_window')
        if clock()-started>max_window_seconds:raise CaptureError('capture_window_exceeded')
        os.replace(result.root,destination)
    return Snapshot(destination)
