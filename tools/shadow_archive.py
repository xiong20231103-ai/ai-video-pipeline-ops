"""Non-destructive archival and capacity accounting; no source deletion/rotation.

The caller must choose a new destination and approve its byte budget. Archives
never activate a collector, alter its quota, or claim comparable real evidence.
"""
from __future__ import annotations
import hashlib,json,os,re,tempfile
from pathlib import Path
from agent.core.snapshot import canonical,no_links,digest_file,relative
from tools.shadow_capture import CaptureError,_read,_safe,_stat

MUTABLE={'status.json','metadata-index.json','process.json'}
IGNORED={'observer.lock','STOP'}

def _walk(source,limit=30000):
    pending=[no_links(source)];count=0
    while pending:
        base=pending.pop()
        for child in base.iterdir():
            no_links(child);count+=1
            if count>limit:raise CaptureError('archive_inventory_limit')
            if child.is_dir():pending.append(child)
            else:yield child

def _catalog(source):
    source=no_links(source);items={}
    for p in sorted(_walk(source)):
        no_links(p)
        if p.is_dir():continue
        name=p.relative_to(source).as_posix();relative(name)
        if name in IGNORED:continue
        if not (name in MUTABLE or re.fullmatch(r'objects/[0-9a-f]{64}',name) or re.fullmatch(r'samples/[A-Za-z0-9_.-]+\.json',name)):raise CaptureError('unexpected_passive_archive_file')
        info=_stat(p)
        if not info or info['kind']!='file':raise CaptureError('archive_source_not_regular')
        items[name]=info
    if not items:raise CaptureError('empty_passive_archive')
    return items

def capacity(roots,*,approved_total_bytes):
    if type(approved_total_bytes) is not int or approved_total_bytes<1:raise CaptureError('explicit_capacity_budget_required')
    seen=set();used=0
    for source in roots:
        source=no_links(source)
        for p in _walk(source):
            no_links(p)
            if not p.is_file():continue
            key=str(p.absolute()).casefold() if os.name=='nt' else str(p.absolute())
            if key in seen:continue
            seen.add(key);used+=p.stat().st_size
    return {'approvedTotalBytes':approved_total_bytes,'retainedBytes':used,'remainingBytes':max(0,approved_total_bytes-used),'canAllocate':used<approved_total_bytes,'deletedFiles':0,'requiresExplicitNewCaptureRoot':True}

def archive_passive(source,destination,*,max_archive_bytes,max_file_bytes=64*1024*1024):
    source=no_links(source);destination=no_links(destination)
    if source==destination or source.is_relative_to(destination) or destination.is_relative_to(source):raise CaptureError('archive_source_destination_overlap')
    if destination.exists():raise CaptureError('archive_new_destination_required')
    before=_catalog(source);total=sum(r['size'] for r in before.values())
    # Reserve manifest space before creating any output; never overrun a full store.
    if type(max_archive_bytes) is not int or total+1024*1024>max_archive_bytes:raise CaptureError('archive_capacity_exhausted')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.shadow-archive-',dir=destination.parent) as folder:
        stage=Path(folder)/'archive';stage.mkdir();records={}
        for name,info in before.items():
            body,checked=_read(source/name,max_file_bytes)
            if checked!=info:raise CaptureError('archive_source_changed')
            try:_safe(json.loads(body.decode('utf-8-sig')))
            except (UnicodeError,json.JSONDecodeError):raise CaptureError('archive_evidence_not_json') from None
            digest=hashlib.sha256(body).hexdigest()
            if name.startswith('objects/') and digest!=Path(name).name:raise CaptureError('passive_object_hash_mismatch')
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body)
            records[name]={'sha256':digest,'size':len(body)}
        if _catalog(source)!=before or any(digest_file(source/name)!=row['sha256'] for name,row in records.items()):raise CaptureError('archive_source_changed')
        manifest={'schema':1,'kind':'passive-evidence-archive','files':records,'bytes':total,'excludedVolatileFiles':sorted(IGNORED),'originalsRetained':True,'deletedFiles':0,'comparable':False,'realShadowPassed':False,'switchAccepted':False}
        manifest['archiveIdentity']=hashlib.sha256(canonical(manifest)).hexdigest()
        raw=canonical(manifest)
        if total+len(raw)>max_archive_bytes:raise CaptureError('archive_capacity_exhausted')
        (stage/'archive.json').write_bytes(raw)
        verify_archive(stage);os.replace(stage,destination)
    return verify_archive(destination)

def verify_archive(root):
    root=no_links(root)
    raw=(root/'archive.json').read_bytes()
    if len(raw)>8*1024*1024:raise CaptureError('archive_manifest_limit')
    manifest=json.loads(raw);_safe(manifest)
    check=dict(manifest);identity=check.pop('archiveIdentity',None)
    if hashlib.sha256(canonical(check)).hexdigest()!=identity:raise CaptureError('archive_manifest_hash_mismatch')
    if manifest.get('schema')!=1 or manifest.get('kind')!='passive-evidence-archive' or manifest.get('originalsRetained') is not True:raise CaptureError('archive_manifest_invalid')
    for name,row in manifest['files'].items():
        p=no_links(root/relative(name))
        if p.stat().st_size!=row['size'] or digest_file(p)!=row['sha256']:raise CaptureError('archive_file_hash_mismatch')
    actual={p.relative_to(root).as_posix() for p in _walk(root)}
    if actual!=set(manifest['files'])|{'archive.json'}:raise CaptureError('archive_unlisted_file')
    return manifest
