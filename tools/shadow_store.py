"""Immutable chunk-deduplicated evidence store with a hard total byte cap.

No source deletion, automatic quota growth, mutable current pointer or service.
A full store refuses new evidence; already published snapshots remain readable.
"""
from __future__ import annotations
import hashlib,json,os,tempfile,uuid
from pathlib import Path
from agent.core.snapshot import Snapshot,canonical,no_links,relative,digest_file
from tools.shadow_capture import CaptureError,_safe
from tools.shadow_archive import _walk
CHUNK=64*1024

def usage(root):return sum(p.stat().st_size for p in _walk(root)) if root.exists() else 0

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
  index={'schema':1,'snapshot':snapshot.manifest,'files':{}};new={}
  for name,record in snapshot.manifest['files'].items():
   chunks=[]
   with (snapshot.root/relative(name)).open('rb') as stream:
    for body in iter(lambda:stream.read(CHUNK),b''):
     key=hashlib.sha256(body).hexdigest();chunks.append(key);target=store/'objects'/key
     if target.exists():
      if target.stat().st_size!=len(body) or digest_file(target)!=key:raise CaptureError('stored_chunk_corrupt')
     else:new.setdefault(key,body)
   index['files'][name]=chunks
  raw=canonical(index)
  if len(raw)>8*1024*1024:raise CaptureError('chunk_manifest_limit')
  destination=store/'snapshots'/(snapshot.manifest['sourceIdentity']+'.json')
  if destination.exists():
   if destination.read_bytes()!=raw:raise CaptureError('snapshot_store_identity_conflict')
   return {'sourceIdentity':snapshot.manifest['sourceIdentity'],'newBytes':0,'deduplicated':True,'realShadowPassed':False}
  required=len(raw)+sum(map(len,new.values()))
  if used+required>approved_total_bytes:raise CaptureError('evidence_store_quota_exhausted')
  # Staging is counted in the same preflight cap; each new object moves once.
  with tempfile.TemporaryDirectory(prefix='.store-stage-',dir=store) as folder:
   stage=Path(folder)
   for key,body in new.items():(stage/key).write_bytes(body)
   (stage/'index.json').write_bytes(raw)
   (store/'objects').mkdir(exist_ok=True);(store/'snapshots').mkdir(exist_ok=True)
   for key in new:os.replace(stage/key,store/'objects'/key)
   os.replace(stage/'index.json',destination) # Publish index only after all chunks.
  return {'sourceIdentity':snapshot.manifest['sourceIdentity'],'newBytes':required,'deduplicated':False,'realShadowPassed':False}
 finally:lock.unlink(missing_ok=True)

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
  for name,keys in value['files'].items():
   relative(name);target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);total=0
   with target.open('xb') as output:
    for key in keys:
     if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{64}',key):raise CaptureError('chunk_key_invalid')
     path=no_links(store/'objects'/key)
     if path.stat().st_size>CHUNK:raise CaptureError('stored_chunk_limit')
     body=path.read_bytes()
     if hashlib.sha256(body).hexdigest()!=key:raise CaptureError('stored_chunk_corrupt')
     total+=len(body)
     if total>value['snapshot']['files'][name]['size']:raise CaptureError('materialized_file_limit')
     output.write(body)
   if total!=value['snapshot']['files'][name]['size']:raise CaptureError('materialized_file_size')
  (stage/'snapshot.json').write_bytes(canonical(value['snapshot']));Snapshot(stage);os.replace(stage,destination)
 return Snapshot(destination)
