"""Bounded, stable-window capture. No production import or source SQL writes.

Only exact reviewed paths are accepted. Directory entries are facts, not media
copies. Database snapshots use a bounded read-only SQLite online backup.
"""
from __future__ import annotations
import hashlib,json,os,re,sqlite3,tempfile,time,stat,math
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
from agent.core.snapshot import Snapshot,SnapshotError,canonical,capture,digest_file,no_links,relative,safe_facts,PRIVATE_FILES,sqlite_rows,rows_sha256
from agent.core.source_profiles import PROFILES,PR49_BEHAVIOR,PR49_HELPER,FRESH_HELPER,SOURCE_HELPER_PROFILES,read_source,validate_fresh_helper_identity
from tools.shadow_capture_errors import CaptureError
from tools.shadow_sqlite_snapshot import online_backup

ROOT_NAMES={'repository','workbench','voice','capcut','downloads','generation','final','drafts','audio','pending-delete'}

_URL=re.compile(r'''https?://[^\s\x00-\x1f"'<>]+''')
_URL_KEY=re.compile(r'token|password|secret|webhook|authorization|cookie|api.?key',re.I)
_FIELD=re.compile(r'token|password|secret|webhook|authorization|cookie|api.?key|invitation',re.I)
# The former leading ["']?[^"'\s]* can match empty, so dropping it never changes
# whether a string matches; it only stops quadratic backtracking on large text.
_PRIVATE_STRING=re.compile(r'''(?i)(?:token|password|secret|webhook|authorization|cookie|api.?key)[^"'\s]*["']\s*[:=]|-----BEGIN .*PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}''')

def _safe(value):
    # safe_facts already walks the whole value; calling it again at every level
    # (as before) rescanned each subtree once per ancestor.
    safe_facts(value)
    _scan(value)

def _scan(value):
    if isinstance(value,str):
        from urllib.parse import urlsplit,parse_qsl
        for url in _URL.findall(value):
            try:parts=urlsplit(url)
            except ValueError:raise CaptureError('invalid_capture_url') from None
            if parts.username or parts.password or any(_URL_KEY.search(key) for key,_ in parse_qsl(parts.query)):raise CaptureError('private_capture_url')
    if isinstance(value,dict):
        for key,child in value.items():
            if _FIELD.search(str(key)):raise CaptureError('private_capture_field')
            _scan(child)
    elif isinstance(value,list):
        for child in value:_scan(child)
    elif isinstance(value,str) and _PRIVATE_STRING.search(value):raise CaptureError('private_capture_string')

SMALL_FILE_LIMIT=1024*1024
SMALL_READ_LIMIT=32*1024*1024
# Small-file hashing (and its privacy scan) may use at most this much of a
# 20-second directory window; later files stay pending instead of the window
# expiring. Measured in-host: 32 MiB took 16 s while the Dashboard was starting.
WINDOW_HASH_SECONDS=6


class ChangeReport:
    def __init__(self):
        self.rows=[];self.counts={};self.rewritten=0;self.sampled=set();self.truncated=False
    def add(self,path,kind,*,rewritten=False):
        self.counts[kind]=self.counts.get(kind,0)+1
        if rewritten:self.rewritten+=1
        key=(path,kind)
        if key not in self.sampled:
            if len(self.rows)<50:self.rows.append({'path':path,'type':kind});self.sampled.add(key)
            else:self.truncated=True
    def report(self):
        return {'changes':list(self.rows),'changeCounts':dict(self.counts),
                'rewrittenSameContentCount':self.rewritten,
                'statOnlyChangeCount':self.counts.get('stat-only',0),
                'changesTruncated':self.truncated}


class SmallReadBudget:
    def __init__(self,limit=SMALL_READ_LIMIT):
        if type(limit) is not int or not 0<=limit<=SMALL_READ_LIMIT:raise CaptureError('small_read_budget_limit')
        self.limit=limit;self.used=0;self.seconds=0.0;self.pending=0;self.deferred=0;self.hash_until=None


def _check_deadline(deadline,clock=time.monotonic):
    if deadline is not None and clock()>deadline:raise CaptureError('capture_window_exceeded')


def _info(s):
    if getattr(s,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024):raise CaptureError('reparse_point_forbidden')
    if not stat.S_ISREG(s.st_mode) and not stat.S_ISDIR(s.st_mode):raise CaptureError('special_file_forbidden')
    return {'kind':'directory' if stat.S_ISDIR(s.st_mode) else 'file','size':s.st_size if stat.S_ISREG(s.st_mode) else 0,
            'mtimeNs':s.st_mtime_ns,'ctimeNs':s.st_ctime_ns,'inode':s.st_ino,'device':s.st_dev}


def _stat(path):
    path=no_links(path)
    try:return _info(path.lstat())
    except FileNotFoundError:return None


def _read_version(path,limit,*,deadline=None,clock=time.monotonic,on_chunk=None):
    _check_deadline(deadline,clock);path=no_links(path)
    try:
        with path.open('rb') as stream:
            opened=_info(os.fstat(stream.fileno()))
            if opened['kind']!='file' or opened['size']>limit:raise CaptureError('capture_file_limit')
            parts=[];size=0
            while size<limit:
                _check_deadline(deadline,clock)
                raw=stream.read(min(1024*1024,limit-size))
                if not raw:break
                if on_chunk is not None:on_chunk(len(raw))
                parts.append(raw);size+=len(raw)
            final=_info(os.fstat(stream.fileno()))
            if final['size']>limit:raise CaptureError('capture_file_limit')
        return b''.join(parts),opened,final
    except FileNotFoundError:raise CaptureError('state_changed_in_window') from None


def _same_version(a,b):
    keys=('kind','size','mtimeNs','inode','device')
    return a is not None and b is not None and all(a[k]==b[k] for k in keys)


MAX_VOLATILE_FILES=8


def volatile_files(plan):
    """State files whose content legitimately changes every few seconds (heartbeats).

    They are captured as first read; a later change inside the window is reported,
    not treated as a failed window. Removal or a type change still fails it.
    """
    names=plan.get('volatileFiles',[])
    if (not isinstance(names,list) or len(names)>MAX_VOLATILE_FILES or len(set(names))!=len(names)
            or any(not isinstance(n,str) or n not in plan.get('files',{}) for n in names)):
        raise CaptureError('volatile_files_invalid')
    return frozenset(names)


def _read(path,limit,*,changes=None,logical_path=None,deadline=None,clock=time.monotonic,volatile=False):
    raw,opened,closed=_read_version(path,limit,deadline=deadline,clock=clock)
    latest=_stat(path)
    if _same_version(opened,closed) and _same_version(closed,latest):return raw,latest
    second,second_open,second_close=_read_version(path,limit,deadline=deadline,clock=clock)
    second_latest=_stat(path)
    settled=_same_version(second_open,second_close) and _same_version(second_latest,second_close)
    if settled and hashlib.sha256(raw).digest()==hashlib.sha256(second).digest():
        if changes is not None:changes.add(logical_path,'stat-only',rewritten=True)
        return second,second_latest
    if volatile and settled:
        # A complete, settled heartbeat version is the fact as of this read.
        if changes is not None:changes.add(logical_path,'volatile-update')
        return second,second_latest
    if changes is not None:changes.add(logical_path,'content-change')
    raise CaptureError('state_changed_in_window')


def recheck_state(path,raw,before,*,limit,changes,logical_path,deadline=None,clock=time.monotonic,volatile=False):
    latest=_stat(path)
    if latest==before:return latest
    if latest is None:
        changes.add(logical_path,'removed');raise CaptureError('state_changed_in_window')
    if latest['kind']!='file':
        changes.add(logical_path,'type-change');raise CaptureError('state_changed_in_window')
    body,latest=_read(path,limit,deadline=deadline,clock=clock,volatile=volatile)
    if hashlib.sha256(body).digest()!=hashlib.sha256(raw).digest():
        if volatile:
            changes.add(logical_path,'volatile-update');return latest
        changes.add(logical_path,'content-change');raise CaptureError('state_changed_in_window')
    changes.add(logical_path,'stat-only',rewritten=True)
    return latest


def _small_digest(path,info,budget,*,deadline=None,clock=time.monotonic):
    if info['size']>budget.limit-budget.used:
        budget.pending+=1;return None,info
    if budget.hash_until is not None and clock()>=budget.hash_until:
        budget.pending+=1;budget.deferred+=1;return None,info
    started=clock()
    # Account actual reads, including one replacement retry, before each read.
    def version():
        remaining=budget.limit-budget.used
        if info['size']>remaining:return None
        def account(amount):budget.used+=amount
        raw,opened,closed=_read_version(path,min(remaining,SMALL_FILE_LIMIT),deadline=deadline,clock=clock,on_chunk=account)
        _safe(raw.decode('utf-8-sig'))
        return hashlib.sha256(raw).hexdigest(),opened,closed
    try:
        one=version()
        if one is None:budget.pending+=1;return None,info
        latest=_stat(path)
        if _same_version(one[1],one[2]) and _same_version(one[2],latest):return one[0],latest
        two=version()
        two_latest=_stat(path)
        if two is not None and _same_version(two[1],two[2]) and _same_version(two[2],two_latest) and one[0]==two[0]:return two[0],two_latest
        budget.pending+=1;return None,latest or info
    except (OSError,UnicodeError):
        budget.pending+=1;return None,info
    except CaptureError as error:
        if str(error)=='capture_window_exceeded':raise
        budget.pending+=1;return None,info
    finally:budget.seconds+=clock()-started


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
    media=plan.get('verifiedFinalMedia',[])
    if not isinstance(media,list) or len(media)>10000 or any(not isinstance(n,str) for n in media) or len(set(media))!=len(media):raise CaptureError('invalid_verified_final_media')
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
        if name in trees and path==Path(path.anchor):raise CaptureError('recursive_drive_inventory_forbidden')
        if any(path==p or path.is_relative_to(p) for p in exclusions.values()):raise CaptureError('excluded_capture_input')
        if name in files and (path.name.lower() in PRIVATE_FILES or path.suffix.lower() not in {'.json','.csv','.txt','.log'}):raise CaptureError('state_content_not_allowed')
        if name in databases and (name!='repository/data/ops.db' or spec!={'root':'repository','path':'data/ops.db'}):raise CaptureError('database_not_allowlisted')
    volatile_files(plan)
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
        amount=min(max(0,budget),info['size']-current['offset']);used=0
        try:
            if amount:
                with path.open('rb') as stream:
                    stream.seek(current['offset'])
                    while used<amount:
                        raw=stream.read(min(1024*1024,amount-used));used+=len(raw)
                        if not raw:break
                        current['hash'].update(raw);current['offset']+=len(raw)
            if used!=amount or _stat(path)!=info:
                self.invalidate(path);return None,used
        except OSError:
            self.invalidate(path);return None,used
        if current['offset']!=info['size']:return None,amount
        digest=current['hash'].hexdigest();self.partial.pop(key,None)
        self.values[key]={'identity':dict(info),'sha256':digest}
        return digest,used
    def invalidate(self,path):
        self.values.pop(str(path),None);self.partial.pop(str(path),None)
    def hash(self,path,info):
        key=str(path);previous=self.values.get(key)
        if previous and previous['identity']==info:return previous['sha256'],0
        if key not in self.values and len(self.values)>=self.max_entries:raise CaptureError('digest_cache_limit')
        digest=digest_file(path)
        if _stat(path)!=info:raise CaptureError('metadata_file_changed')
        self.values[key]={'identity':dict(info),'sha256':digest}
        return digest,info['size']

def _inventory(plan,bindings,max_entries,max_hash_bytes,digest_cache=None,*,small_budget=None,baseline=None,deadline=None,clock=time.monotonic):
    nodes={};identity={};hashed=0
    excluded=[_source({k:no_links(v) for k,v in plan['roots'].items()},spec) for spec in plan.get('exclude',{}).values()]
    # Normalized prefixes: Path.is_relative_to per entry dominated large trees.
    prefixes=[os.path.normcase(str(base)) for base in excluded]
    def excluded_path(path):
        text=os.path.normcase(str(path))
        return any(text==base or text.startswith(base.rstrip(os.sep)+os.sep) for base in prefixes)
    def store(name,path,info,*,shallow=False):
        nonlocal hashed
        if name in plan.get('verifiedFinalMedia',[]):
            # Directory-entry stat caches need not expose full file IDs on all
            # Windows versions. Obtain real path facts for explicit media only.
            info=_stat(path)
            if info is None:raise CaptureError('directory_changed_in_window')
        _check_deadline(deadline,clock)
        if name in nodes:raise CaptureError('overlapping_metadata_trees')
        if len(nodes)>=max_entries:raise CaptureError('metadata_entry_limit')
        if path.suffix.lower()=='.lock' and info['kind']=='file':
            nodes[name]={'kind':'file','exists':True,'metadataPolicy':'existence-only'}
            identity[name]={'kind':'file','exists':True};return
        node={k:info[k] for k in ('kind','size','mtimeNs','ctimeNs','device','inode')}
        if info['kind']=='file':
            eligible=(not shallow and path.suffix.lower() in {'.json','.txt','.log'} and path.name.lower() not in PRIVATE_FILES and info['size']<=SMALL_FILE_LIMIT)
            previous=(baseline or {}).get(name,{})
            same=previous and {k:v for k,v in previous.items() if k!='contentSha256'}==info
            if small_budget is not None and eligible:
                if same and previous.get('contentSha256'):digest=previous['contentSha256']
                else:digest,info=_small_digest(path,info,small_budget,deadline=deadline,clock=clock)
                node.update({k:info[k] for k in ('kind','size','mtimeNs','ctimeNs','device','inode')})
                if digest is None:node.update(hashPending=True,hashState='content_comparison_pending')
                else:node['contentSha256']=digest;info={**info,'contentSha256':digest}
            elif small_budget is not None and not shallow:
                node.update(hashPending=True,hashState='large_or_media_metadata_only')
            elif not shallow and plan.get('hashMetadataFiles',False):
                if path.name.lower() in PRIVATE_FILES or path.suffix.lower() in {'.env','.dat','.exe','.dll'}:
                    node['hashUnavailable']='private_or_non_evidence_type'
                else:
                    digest,used=(digest_cache or DigestCache()).observe(path,info,max_hash_bytes-hashed);hashed+=used
                    if digest is None:node['hashPending']=True
                    else:node['contentSha256']=digest
        if shallow and info['kind']=='directory':node['contentsCaptured']=False
        identity[name]=info;nodes[name]=node
    def children(path):
        # Ancestors checked once per directory, not once for every sibling.
        # The child stat never follows a link; every reparse/special node is rejected.
        no_links(path)
        rows=[]
        with os.scandir(path) as entries:
            for entry in entries:
                _check_deadline(deadline,clock)
                child=path/entry.name
                if excluded_path(child):continue
                try:info=_info(os.stat(child,follow_symlinks=False))
                except FileNotFoundError:raise CaptureError('directory_changed_in_window') from None
                rows.append((entry.name,child,info))
                if len(rows)+len(nodes)>max_entries:raise CaptureError('metadata_entry_limit')
        return sorted(rows,key=lambda row:row[0])
    for prefix in plan.get('trees',{}):
        pending=[(prefix,bindings[prefix],None)]
        while pending:
            name,path,info=pending.pop();_check_deadline(deadline,clock)
            if info is None:info=_stat(path)
            if info is None:raise CaptureError('metadata_root_missing_use_explicit_absence' if name==prefix else 'directory_changed_in_window')
            if name==prefix and info['kind']!='directory':raise CaptureError('metadata_root_must_be_directory')
            store(name,path,info)
            if info['kind']=='directory':
                rows=children(path)
                if len(rows)+len(nodes)+len(pending)>max_entries:raise CaptureError('metadata_entry_limit')
                pending.extend((name+'/'+leaf,child,node) for leaf,child,node in reversed(rows))
    for prefix in plan.get('shallow',{}):
        path=bindings[prefix];info=_stat(path)
        if info is None or info['kind']!='directory':raise CaptureError('shallow_directory_required')
        if prefix not in nodes:store(prefix,path,info,shallow=True)
        for leaf,child,node in children(path):
            name=prefix+'/'+leaf
            if name not in nodes:store(name,child,node,shallow=True)
        nodes[prefix]['contentsCaptured']=True
    return nodes,identity


def reconcile_inventory(nodes,before,after,roots,digest_cache=None,*,changes=None):
    changes=changes if changes is not None else ChangeReport()
    changed=False
    for name in sorted(set(before)|set(after)):
        if name not in before:changes.add(name,'added');changed=True
        elif name not in after:changes.add(name,'removed');changed=True
        elif before[name]['kind']!=after[name]['kind']:changes.add(name,'type-change');changed=True
    if changed:raise CaptureError('directory_changed_in_window')
    for name,old in before.items():
        latest=after[name]
        if old==latest:continue
        nodes[name].update({k:latest[k] for k in ('kind','size','mtimeNs','ctimeNs','device','inode') if k in latest})
        if old['kind']=='directory':
            # Membership and type were checked above. Preserve final timestamps.
            changes.add(name,'stat-only');continue
        if old.get('contentSha256') and old.get('contentSha256')==latest.get('contentSha256'):
            nodes[name]['rewrittenSameContent']=True
            nodes[name]['contentSha256']=latest['contentSha256']
            nodes[name].pop('hashPending',None);nodes[name].pop('hashState',None)
            changes.add(name,'stat-only',rewritten=True);continue
        nodes[name].pop('contentSha256',None)
        nodes[name]['hashPending']=True;nodes[name]['hashState']='writing_or_changed'
        changes.add(name,'content-change' if old.get('contentSha256') and latest.get('contentSha256') else 'stat-unverified')
        if digest_cache is not None:
            alias,_,relative_name=name.partition('/')
            # Invalidate by inventory path when a logical root has a named alias.
            for key in list(digest_cache.values):
                if str(roots[alias]/relative_name)==key:digest_cache.invalidate(Path(key))
    return changes.report()


def measure_directory_stability(plan,destination,*,rounds=3,max_entries=10000,between=lambda:None,clock=time.monotonic):
    if type(rounds) is not int or not 2<=rounds<=20:raise CaptureError('directory_probe_round_limit')
    roots,bindings=validate_plan(plan,destination)
    changes=ChangeReport();budget=SmallReadBudget();timings=[];changed=missing=0
    if not plan.get('trees') and not plan.get('shallow'):
        return {'rounds':0,'directoryChangeFailedRounds':0,'unmeasurableRounds':0,
                'directoryChangeFailureRatio':None,'measurementScope':'no-directory-bindings',
                'activeBatchRateVerified':False,**changes.report(),'smallFileReadBytes':0,
                'smallFileHashSeconds':0,'windows':[]}
    for number in range(rounds):
        started=clock();deadline=started+20;hash_start=budget.seconds;gap=0;entry_count=None
        budget.hash_until=started+WINDOW_HASH_SECONDS
        try:
            nodes,before=_inventory({**plan,'hashMetadataFiles':False},bindings,max_entries,0,
                                    small_budget=budget,deadline=deadline,clock=clock)
            entry_count=len(before);gap_start=clock();between();gap=clock()-gap_start;_check_deadline(deadline,clock)
            after=_inventory({**plan,'hashMetadataFiles':False},bindings,max_entries,0,
                             small_budget=budget,baseline=before,deadline=deadline,clock=clock)[1]
            reconcile_inventory(nodes,before,after,roots,changes=changes)
            _check_deadline(deadline,clock)
            status='measured'
        except CaptureError as error:
            if str(error)=='directory_changed_in_window':changed+=1
            else:missing+=1
            status=str(error)
        except OSError:missing+=1;status='metadata_unavailable'
        seconds=clock()-started
        timings.append({'window':number+1,'seconds':seconds,'hashSeconds':budget.seconds-hash_start,
                        'enumerationAndComparisonSeconds':max(0,seconds-(budget.seconds-hash_start)-gap),
                        'betweenSeconds':gap,'entries':entry_count,
                        'status':status,'within20Seconds':seconds<=20})
    return {'rounds':rounds,'directoryChangeFailedRounds':changed,'unmeasurableRounds':missing,
            'directoryChangeFailureRatio':changed/rounds if not missing else None,
            'measurementScope':'content-aware-directory-windows','activeBatchRateVerified':False,
            **changes.report(),'smallFileReadBytes':budget.used,'smallFileHashSeconds':budget.seconds,
            'smallFileHashPendingCount':budget.pending,'smallFileHashDeferredCount':budget.deferred,'windows':timings,
            'maxWindowSeconds':max(row['seconds'] for row in timings)}


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

def _verified_media(plan,nodes,inventory,roots,budget,*,deadline,clock):
    """Explicit media only, fresh single-open digest; no cached/partial reuse."""
    from agent.core.verified_final_replay import ALIGNMENT
    names=plan.get('verifiedFinalMedia',[])
    if not isinstance(names,list) or len(names)>10000 or any(not isinstance(n,str) for n in names) or len(set(names))!=len(names):raise CaptureError('invalid_verified_final_media')
    proofs={};used=0
    for name in names:
        relative(name)
        info=inventory.get(name)
        if not info or info.get('kind')!='file' or Path(name).suffix.lower() not in {'.mp4','.mov','.mkv'}:raise CaptureError('verified_final_media_not_in_inventory')
        root,rel=name.split('/',1)
        path=no_links(roots[root]/rel)
        node=nodes[name]
        if info['size']>budget-used:
            node.update(hashPending=True,hashState='verified_final_digest_budget_pending');continue
        before=_stat(path)
        digest=hashlib.sha256();amount=0
        with path.open('rb') as stream:
            opened=_info(os.fstat(stream.fileno()))
            while amount<info['size']:
                _check_deadline(deadline,clock)
                block=stream.read(min(1024*1024,info['size']-amount))
                if not block:break
                amount+=len(block);digest.update(block)
            closed=_info(os.fstat(stream.fileno()))
        used+=amount;after=_stat(path)
        # Windows path stat and fd stat can expose different ctime semantics.
        # Compare each API's ctime to itself, never manufacture a shared value.
        common=('kind','size','mtimeNs','inode','device')
        same_object=before is not None and all(before[k]==opened[k] for k in common)
        if not (before==after==info and opened==closed and same_object and amount==info['size']):
            node.update(hashPending=True,hashState='verified_final_writing');continue
        value=digest.hexdigest()
        node.update(contentSha256=value,hashPending=False)
        node.pop('hashState',None)
        proofs[name]={'alignment':ALIGNMENT,'sha256':value,'readBytes':amount,
                      'before':before,'after':after,'opened':opened,'closed':closed}
    return proofs,used


def aligned_capture(plan,destination,**options):
    """Refusals carry the bounded change report (logical plan names and change
    types only, never paths or contents) so a host can say what moved."""
    changes=ChangeReport()
    try:return _aligned_capture(plan,destination,changes=changes,**options)
    except CaptureError as error:
        error.diagnostics={'changes':changes.report()['changes'][:20]}
        raise


def _aligned_capture(plan,destination,*,changes,source_path,process_probe,http_probe,max_file_bytes=32*1024*1024,max_total_bytes=512*1024*1024,max_entries=10000,max_hash_bytes=64*1024*1024,max_window_seconds=20,digest_cache=None,volatile_http=(),clock=time.monotonic,now=lambda:datetime.now(timezone.utc).isoformat()):
    roots,bindings=validate_plan(plan,destination)
    if type(max_window_seconds) not in (int,float) or not math.isfinite(max_window_seconds) or not 0<max_window_seconds<=20:raise CaptureError('capture_window_limit')
    started=clock();deadline=started+max_window_seconds;small_budget=SmallReadBudget();opened_at=now();source_path=no_links(source_path)
    small_budget.hash_until=started+WINDOW_HASH_SECONDS
    if source_path.stat().st_size>2*1024*1024:raise CaptureError('capture_source_byte_limit')
    source=read_source(source_path);source_sha=hashlib.sha256(source.encode()).hexdigest()
    if source_sha not in PROFILES:raise CaptureError('unreviewed_capture_source')
    helper=source_path.with_name('verified_final.py')
    dependency_names=['pending_delete.py','cleanup_tickets.py']+(['verified_final.py'] if source_sha in PR49_BEHAVIOR else [])
    package_root=Path(__file__).resolve().parents[1];dependency_hashes={};dependency_identities={}
    for name in dependency_names:
        installed=source_path.with_name(name)
        if not installed.is_file():
            if source_path.parent==package_root:raise CaptureError('capture_dependency_missing')
            continue # Synthetic source-only capture is not live evidence.
        identity=_stat(installed)
        if not identity or identity['size']>2*1024*1024:raise CaptureError('capture_dependency_byte_limit')
        raw=installed.read_bytes()
        actual=hashlib.sha256(raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n').encode()).hexdigest()
        expected=actual if name=='verified_final.py' and (source_sha,actual) in SOURCE_HELPER_PROFILES else hashlib.sha256((package_root/name).read_text(encoding='utf-8-sig').encode()).hexdigest()
        if name=='verified_final.py' and (source_sha,actual) not in SOURCE_HELPER_PROFILES:raise CaptureError('capture_dependency_not_reviewed')
        if actual!=expected:raise CaptureError('capture_dependency_not_reviewed')
        if _stat(installed)!=identity:raise CaptureError('dependency_changed_in_window')
        dependency_identities[name]={**identity,'sha256':hashlib.sha256(raw).hexdigest()}
        if name=='verified_final.py' and actual==FRESH_HELPER:
            validate_fresh_helper_identity(dependency_identities[name])
        dependency_hashes[name]=actual
    if source_sha in PR49_BEHAVIOR and not helper.is_file():raise CaptureError('capture_source_dependency_mismatch')
    processes,http,http_generation=_observations(process_probe,http_probe)
    nodes,inventory=_inventory(plan,bindings,max_entries,max_hash_bytes,digest_cache,small_budget=small_budget,deadline=deadline,clock=clock)
    fresh=dependency_hashes.get('verified_final.py')==FRESH_HELPER
    media_limit=min(max_hash_bytes,64*1024*1024)
    # Reserve the other half for a fresh closing digest, including same-stat
    # overwrites. A stat-only closing check cannot align this helper's behavior.
    media_proofs,media_bytes=_verified_media(plan,nodes,inventory,roots,media_limit//2,deadline=deadline,clock=clock) if fresh else ({},0)
    missing={k:_stat(bindings[k]) for k in plan.get('absent',{})}
    if any(v is not None for v in missing.values()):raise CaptureError('declared_absence_exists')
    before={};copied={};database_proofs={};total=0
    # All staging writes are new and outside production roots.
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.aligned-capture-',dir=destination.parent) as folder:
        scratch=Path(folder)
        volatile=volatile_files(plan)
        for name in plan.get('files',{}):
            body,info=_read(bindings[name],max_file_bytes,changes=changes,logical_path=name,deadline=deadline,clock=clock,volatile=name in volatile);total+=len(body)
            if total>max_total_bytes:raise CaptureError('capture_total_limit')
            try:body.decode('utf-8-sig')
            except UnicodeError:raise CaptureError('state_content_not_utf8') from None
            target=scratch/'inputs'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body);os.utime(target,ns=(info['mtimeNs'],info['mtimeNs']))
            copied[name]=target;before[name]=info
        databases={}
        for name in plan.get('databases',{}):
            target=scratch/'database-normalized'/name;target.parent.mkdir(parents=True,exist_ok=True)
            opened=now()
            proof=online_backup(bindings[name],target,max_bytes=max_total_bytes-total,
                                timeout_seconds=max(.001,deadline-clock()),clock=clock)
            database_proofs[name]={**proof,'openedAt':opened,'closedAt':now()}
            total+=target.stat().st_size
            databases[name]=target
        # Recheck the entire window, including external response bodies and PID birth identity.
        latest_processes,latest_http,latest_generation=_observations(process_probe,http_probe)
        # Processes and non-volatile responses must not change in the window. A
        # declared volatile route (e.g. a status summary stamped with servedAt and
        # polled every few seconds) only has to stay completely observed; the
        # response from the window start is the captured fact.
        stable=set(http)-set(volatile_http)
        if (latest_processes!=processes or set(latest_http)!=set(http)
                or any(latest_http[key]!=http[key] for key in stable)
                or (latest_generation!=http_generation and not set(http)<=set(volatile_http))):
            raise CaptureError('external_or_process_changed')
        volatile_updates=sorted(key for key in set(http)&set(volatile_http) if latest_http[key]!=http[key])
        for name,path in copied.items():
            recheck_state(bindings[name],path.read_bytes(),before[name],limit=max_file_bytes,
                          changes=changes,logical_path=name,deadline=deadline,clock=clock,volatile=name in volatile)
        if any(_stat(bindings[name]) is not None for name in missing):raise CaptureError('absence_changed_in_window')
        latest=_inventory({**plan,'hashMetadataFiles':False},bindings,max_entries,0,small_budget=small_budget,baseline=inventory,deadline=deadline,clock=clock)[1]
        reconcile_inventory(nodes,inventory,latest,roots,digest_cache,changes=changes)
        closing,closing_bytes=_verified_media({**plan,'verifiedFinalMedia':list(media_proofs)},nodes,latest,roots,media_limit-media_bytes,deadline=deadline,clock=clock) if fresh else ({},0)
        media_bytes+=closing_bytes
        for name in list(media_proofs):
            if (latest.get(name)!=media_proofs[name]['after'] or name not in closing
                    or closing[name]['sha256']!=media_proofs[name]['sha256']):
                del media_proofs[name];nodes[name].pop('contentSha256',None)
                nodes[name].update(hashPending=True,hashState='verified_final_changed_in_window')
            else:
                media_proofs[name]['windowClose']=closing[name]
        if any(hashlib.sha256(source_path.with_name(name).read_text(encoding='utf-8-sig').encode()).hexdigest()!=value for name,value in dependency_hashes.items()):raise CaptureError('dependency_changed_in_window')
        if any({**_stat(source_path.with_name(name)),'sha256':hashlib.sha256(source_path.with_name(name).read_bytes()).hexdigest()}!=identity for name,identity in dependency_identities.items()):raise CaptureError('dependency_changed_in_window')
        if read_source(source_path)!=source:raise CaptureError('source_changed_in_window')
        if clock()-started>max_window_seconds:raise CaptureError('capture_window_exceeded')
        # The window is closed; these copies no longer change. Scanning them here
        # keeps the same refusal before packaging without spending window time.
        for name,path in copied.items():
            text=path.read_bytes().decode('utf-8-sig');_safe(text)
            if path.suffix.lower()=='.json':
                try:_safe(json.loads(text))
                except json.JSONDecodeError:pass # Corrupt JSON itself must replay faithfully.
            elif path.suffix.lower()=='.csv':
                import csv
                _safe({key:None for key in next(csv.reader(text.splitlines()),[])})
        for path in databases.values():
            rows=sqlite_rows(path);_safe(rows);rows_sha256(path,rows)
        ended_at=now();settings=plan.get('facts',{});_safe(settings)
        if set(settings)-{'machineName','settings','metrics','collectorAlive','scan','historyResetGeneration','historyResetAt','historyAliases'}:raise CaptureError('unexpected_capture_fact')
        facts={**settings,**processes,'http':http,'filesystem':nodes,'pathAliases':{str(p):name for name,p in roots.items()},'dependencyClosure':True,'absentPaths':sorted(missing),'completeDirectoryRoots':sorted(plan.get('trees',{})),'excludedPaths':sorted(plan.get('exclude',{}))}
        facts['captureProof']={'schema':1,'openedAt':opened_at,'closedAt':ended_at,'processSha256':hashlib.sha256(canonical(processes)).hexdigest(),'httpSha256':hashlib.sha256(canonical(http)).hexdigest(),'inventorySha256':hashlib.sha256(canonical(inventory)).hexdigest(),'databaseSnapshotMethod':'sqlite-online-readonly','databaseSnapshots':database_proofs,'externalObservationGeneration':http_generation,'externalVolatileUpdates':volatile_updates,'helperHashes':dependency_hashes}
        facts['captureProof']['helperIdentities']=dependency_identities
        if fresh:
            facts['verifiedFinalMedia']=media_proofs
            facts['captureProof']['verifiedFinalDigestReadBytes']=media_bytes
        facts['captureProof'].update(inventoryEndSha256=hashlib.sha256(canonical(latest)).hexdigest(),
            metadataComparisonPolicy='directory-membership-type-state-content',
            stabilityChanges=changes.report(),smallFileReadBytes=small_budget.used,smallFileHashSeconds=small_budget.seconds,
            mediaHashPendingCount=sum(bool(node.get('hashPending')) for node in nodes.values()))
        result=capture(scratch/'package',files=copied,databases=databases,facts=facts,frozen_at=ended_at,legacy_sha256=source_sha,max_file_bytes=max_file_bytes,max_total_bytes=max_total_bytes)
        os.replace(result.root,destination)
    return Snapshot(destination)
