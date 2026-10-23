"""Immutable chunk-deduplicated evidence store with a hard total byte cap.

No source deletion, automatic quota growth, mutable current pointer or service.
A full store refuses new evidence; already published snapshots remain readable.

Chunks are appended in immutable pack files (one pack plus one small index per
publication) instead of one file per chunk: a 126 MiB SQLite snapshot is ~32k
pages, which overflowed the bounded usage walk and made every publication
re-read tens of thousands of files. The total cap bounds the number of packs.
"""
from __future__ import annotations
import hashlib,json,os,re,tempfile
from pathlib import Path
from agent.core.snapshot import Snapshot,canonical,no_links,relative
from tools.shadow_capture import CaptureError,_safe
from tools.shadow_archive import _walk
from tools.shadow_sqlite_snapshot import sqlite_page_size,page_listing_segment,SEGMENT_KEYS
CHUNK=64*1024
KEY=re.compile('[0-9a-f]{64}')
MAX_PACK_INDEX=64*1024*1024

def usage(root):return sum(p.stat().st_size for p in _walk(root)) if root.exists() else 0

# Pack indexes are immutable, so a process keeps the key map and only loads
# indexes it has not seen; any removed index (compaction) rebuilds the map.
_KEYS={}

def _pack_index(path):
 path=no_links(path)
 if path.stat().st_size>MAX_PACK_INDEX:raise CaptureError('pack_index_limit')
 value=json.loads(path.read_bytes())
 if (not isinstance(value,dict) or value.get('schema')!=1 or value.get('pack')!=path.stem
   or not isinstance(value.get('entries'),list) or type(value.get('size')) is not int):raise CaptureError('pack_index_invalid')
 pack=no_links(path.with_suffix('.pack'))
 if pack.stat().st_size!=value['size']:raise CaptureError('stored_chunk_corrupt')
 end=0
 for row in value['entries']:
  if (not isinstance(row,list) or len(row)!=3 or not isinstance(row[0],str) or not KEY.fullmatch(row[0])
    or type(row[1]) is not int or type(row[2]) is not int or row[1]!=end or not 0<row[2]<=CHUNK):raise CaptureError('pack_index_invalid')
  end+=row[2]
 if end!=value['size']:raise CaptureError('pack_index_invalid')
 return value

def stored_keys(store):
 """key -> (pack id, offset, length) for every published pack."""
 store=no_links(store);folder=store/'packs'
 names={p.stem for p in folder.glob('*.idx')} if folder.is_dir() else set()
 state=_KEYS.get(str(store))
 if state is None or not state['packs']<=names:state={'packs':set(),'keys':{}}
 for name in sorted(names-state['packs']):
  for key,offset,length in _pack_index(folder/(name+'.idx'))['entries']:state['keys'].setdefault(key,(name,offset,length))
  state['packs'].add(name)
 _KEYS[str(store)]=state
 return state['keys']

class _Reader:
 """Reads chunks from packs, opening each pack once; verifies every chunk."""
 def __init__(self,store):self.store=no_links(store);self.keys=stored_keys(self.store);self.files={}
 def __enter__(self):return self
 def __exit__(self,*args):
  for stream in self.files.values():stream.close()
 def read(self,key):
  if not isinstance(key,str) or not KEY.fullmatch(key):raise CaptureError('chunk_key_invalid')
  if key not in self.keys:raise CaptureError('stored_chunk_missing')
  pack,offset,length=self.keys[key]
  if pack not in self.files:self.files[pack]=no_links(self.store/'packs'/(pack+'.pack')).open('rb')
  stream=self.files[pack];stream.seek(offset);body=stream.read(length)
  if len(body)!=length or hashlib.sha256(body).hexdigest()!=key:raise CaptureError('stored_chunk_corrupt')
  return body

def _publish_pack(store,stage,bodies):
 """Pack first, index second: an index is only visible once its pack is complete."""
 if not bodies:return 0
 entries=[];offset=0;digest=hashlib.sha256()
 with (stage/'pack').open('xb') as out:
  for key,body in bodies.items():
   out.write(body);digest.update(body);entries.append([key,offset,len(body)]);offset+=len(body)
  out.flush();os.fsync(out.fileno())
 name=digest.hexdigest()
 raw=canonical({'schema':1,'pack':name,'size':offset,'entries':entries})
 (stage/'idx').write_bytes(raw)
 folder=store/'packs';folder.mkdir(exist_ok=True)
 if (folder/(name+'.idx')).exists():return 0 # Identical pack already published.
 os.replace(stage/'pack',folder/(name+'.pack'));os.replace(stage/'idx',folder/(name+'.idx'))
 return offset+len(raw)

def put_snapshot(snapshot,store,*,approved_total_bytes,retained_roots=()):
 snapshot=Snapshot(snapshot.root);store=no_links(store)
 for path in [snapshot.root,*map(no_links,retained_roots)]:
  if store==path or store.is_relative_to(path) or path.is_relative_to(store):raise CaptureError('evidence_store_overlap')
 if type(approved_total_bytes) is not int or approved_total_bytes<1:raise CaptureError('explicit_store_quota_required')
 # Single-writer CLI/host: concurrent callers are refused, never race the quota.
 store.mkdir(parents=True,exist_ok=True);lock=store/'.writer.lock'
 try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 except FileExistsError:raise CaptureError('evidence_store_writer_busy') from None
 try:
  os.close(fd);used=usage(store)+sum(usage(no_links(p)) for p in retained_roots)
  if used>=approved_total_bytes:raise CaptureError('evidence_store_quota_exhausted')
  known=stored_keys(store)
  index={'schema':1,'snapshot':snapshot.manifest,'files':{}};new={}
  def add(body):
   key=hashlib.sha256(body).hexdigest()
   if key not in known:new.setdefault(key,body)
   return key
  for name,record in snapshot.manifest['files'].items():
   path=snapshot.root/relative(name)
   # A changed row rewrites one SQLite page; 64 KiB chunks inflated that ~8x.
   page=sqlite_page_size(path) if record.get('kind')=='sqlite' else None
   with path.open('rb') as stream:chunks=[add(body) for body in iter(lambda:stream.read(page or CHUNK),b'')]
   if page:
    segments=[add(page_listing_segment(chunks[i:i+SEGMENT_KEYS])) for i in range(0,len(chunks),SEGMENT_KEYS)]
    index['files'][name]={'pageSize':page,'segments':segments}
   else:index['files'][name]=chunks
  raw=canonical(index)
  if len(raw)>8*1024*1024:raise CaptureError('chunk_manifest_limit')
  destination=store/'snapshots'/(snapshot.manifest['sourceIdentity']+'.json')
  if destination.exists():
   if destination.read_bytes()!=raw:raise CaptureError('snapshot_store_identity_conflict')
   return {'sourceIdentity':snapshot.manifest['sourceIdentity'],'newBytes':0,'deduplicated':True,'realShadowPassed':False}
  # The pack index costs ~90 bytes per new chunk; counted before any write.
  required=len(raw)+sum(map(len,new.values()))+100*len(new)+256
  if used+required>approved_total_bytes:raise CaptureError('evidence_store_quota_exhausted')
  # Staging is counted in the same cap; the pack and index each move once.
  with tempfile.TemporaryDirectory(prefix='.store-stage-',dir=store) as folder:
   stage=Path(folder);written=_publish_pack(store,stage,new)
   (stage/'index.json').write_bytes(raw);(store/'snapshots').mkdir(exist_ok=True)
   os.replace(stage/'index.json',destination) # Publish index only after its chunks.
  return {'sourceIdentity':snapshot.manifest['sourceIdentity'],'newBytes':written+len(raw),'deduplicated':False,'realShadowPassed':False}
 finally:lock.unlink(missing_ok=True)

def rewrite_packs(store,needed):
 """Keep only needed chunks; the caller holds the writer lock. Returns removed count.

 A pack with no needed chunk is removed; a partly needed pack is copied into a
 new pack first and only then removed, so a crash never loses a needed chunk.
 """
 store=no_links(store);folder=store/'packs';removed=0
 if not folder.is_dir():return 0
 for path in sorted(folder.glob('*.idx')):
  entries=_pack_index(path)['entries'];keep=[row for row in entries if row[0] in needed]
  if len(keep)==len(entries):continue
  if keep:
   bodies={}
   with no_links(path.with_suffix('.pack')).open('rb') as stream:
    for key,offset,length in keep:
     stream.seek(offset);body=stream.read(length)
     if hashlib.sha256(body).hexdigest()!=key:raise CaptureError('stored_chunk_corrupt')
     bodies[key]=body
   with tempfile.TemporaryDirectory(prefix='.compact-stage-',dir=store) as stage:_publish_pack(store,Path(stage),bodies)
  path.unlink();path.with_suffix('.pack').unlink(missing_ok=True)
  removed+=len(entries)-len(keep)
 _KEYS.pop(str(store),None)
 return removed

def _object(store,key):
 with _Reader(store) as reader:return reader.read(key)

def entry_keys(store,entry,reader=None):
 """Chunk keys of one indexed file: a plain list, or SQLite page segments."""
 if isinstance(entry,list):return entry
 if (not isinstance(entry,dict) or set(entry)!={'pageSize','segments'} or type(entry['pageSize']) is not int
   or not 512<=entry['pageSize']<=CHUNK or entry['pageSize']&(entry['pageSize']-1) or not isinstance(entry['segments'],list)):
  raise CaptureError('chunk_index_invalid')
 keys=[]
 for segment in entry['segments']:
  rows=(reader.read(segment) if reader else _object(store,segment)).decode('ascii').split('\n')
  if not 1<=len(rows)<=SEGMENT_KEYS:raise CaptureError('chunk_index_invalid')
  keys.extend(rows)
 return keys

def referenced_objects(store,index):
 """Every object one snapshot index needs, segment listings included."""
 keys=set()
 with _Reader(store) as reader:
  for entry in index['files'].values():
   if isinstance(entry,dict):keys.update(entry['segments'])
   keys.update(entry_keys(store,entry,reader))
 return keys

def materialize_snapshot(store,identity,destination):
 store=no_links(store);destination=no_links(destination)
 if destination.exists() or destination==store or destination.is_relative_to(store) or store.is_relative_to(destination):raise CaptureError('fresh_materialization_required')
 import re
 if not isinstance(identity,str) or not re.fullmatch('[0-9a-f]{64}',identity):raise CaptureError('snapshot_identity_invalid')
 p=no_links(store/'snapshots'/(identity+'.json'))
 if p.stat().st_size>8*1024*1024:raise CaptureError('chunk_manifest_limit')
 value=json.loads(p.read_bytes());_safe(value)
 if value.get('schema')!=1 or value.get('snapshot',{}).get('sourceIdentity')!=identity or set(value.get('files',{}))!=set(value['snapshot'].get('files',{})):raise CaptureError('chunk_index_invalid')
 destination.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='.materialize-',dir=destination.parent) as folder:
  stage=Path(folder)/'snapshot';stage.mkdir()
  with _Reader(store) as reader:
   for name,entry in value['files'].items():
    relative(name);target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);total=0
    keys=entry_keys(store,entry,reader)
    with target.open('xb') as output:
     for key in keys:
      body=reader.read(key)
      total+=len(body)
      if total>value['snapshot']['files'][name]['size']:raise CaptureError('materialized_file_limit')
      output.write(body)
    if total!=value['snapshot']['files'][name]['size']:raise CaptureError('materialized_file_size')
  (stage/'snapshot.json').write_bytes(canonical(value['snapshot']));Snapshot(stage);os.replace(stage,destination)
 return Snapshot(destination)
