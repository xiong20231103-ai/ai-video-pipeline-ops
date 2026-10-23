"""Synthetic files only: never capture production or perform live HTTP."""
import copy,hashlib,json,os,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from tools.shadow_capture import aligned_capture,CaptureError
from tools.shadow_archive import archive_passive,verify_archive,capacity
from agent.core.snapshot import canonical,SnapshotError
from agent.core.sandbox import SandboxIO
from contextlib import ExitStack

ROOT=Path(__file__).resolve().parents[1]
class AlignedCaptureTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.live=self.root/'live';self.live.mkdir();self.state=self.live/'state.json';self.state.write_text('{"items":[]}',encoding='utf-8')
  self.source=self.root/'app.py';self.source.write_text((ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8'),encoding='utf-8',newline='\n')
  self.plan={'schema':1,'roots':{'workbench':str(self.live)},'files':{'workbench/state.json':{'root':'workbench','path':'state.json'}},'trees':{'workbench/metadata':{'root':'workbench','path':'metadata'}},'absent':{'workbench/missing.json':{'root':'workbench','path':'missing.json'}},'facts':{'historyResetGeneration':'fixture-reset','scan':False}}
  (self.live/'metadata').mkdir();(self.live/'metadata/output.mp4').write_bytes(b'fake-media-never-run')
  self.process={'processRecords':[{'pid':123,'name':'python.exe','cmdline':['python.exe','workbench.py'],'create_time':1700000000.0}],'processIds':[123]}
  self.http={'receiver:/api/pipeline/snapshot':{'ok':True,'items':[]}}
 def capture(self,**kwargs):return aligned_capture(self.plan,self.root/'snapshot',source_path=self.source,process_probe=lambda:copy.deepcopy(self.process),http_probe=lambda:copy.deepcopy(self.http),**kwargs)
 def test_exact_current_source_is_captured_without_normalizing_byte_identity(self):
  from agent.core.source_profiles import D6A7211_CRLF
  self.source.write_bytes((ROOT/'contracts/legacy-app-d6a7211-crlf.txt').read_bytes())
  self.source.with_name('verified_final.py').write_bytes((ROOT/'contracts/legacy-verified-final-pr49.txt').read_bytes())
  snap=self.capture()
  self.assertEqual(D6A7211_CRLF,snap.manifest['legacySha256'])
 def test_current_source_one_byte_cr_deletion_fails_capture(self):
  raw=(ROOT/'contracts/legacy-app-d6a7211-crlf.txt').read_bytes()
  self.source.write_bytes(raw.replace(b'\r\n',b'\n',1))
  with self.assertRaisesRegex(CaptureError,'unreviewed_capture_source'):self.capture()
 def test_current_source_rejects_uncovered_helper(self):
  self.source.write_bytes((ROOT/'contracts/legacy-app-d6a7211-crlf.txt').read_bytes())
  self.source.with_name('verified_final.py').write_bytes((ROOT/'verified_final.py').read_bytes())
  with self.assertRaisesRegex(CaptureError,'capture_dependency_not_reviewed'):self.capture()
 def test_aligned_snapshot_contains_exact_content_absence_process_and_external_facts(self):
  snap=self.capture();facts=snap.manifest['facts']
  self.assertEqual(self.state.read_bytes(),snap.read('workbench/state.json'));self.assertTrue(facts['dependencyClosure']);self.assertEqual(['workbench/missing.json'],facts['absentPaths']);self.assertEqual(self.http,facts['http']);self.assertEqual(self.process['processRecords'],facts['processRecords']);self.assertFalse(snap.manifest['realBatchEvidence'])
  self.assertEqual('sqlite-online-readonly',facts['captureProof']['databaseSnapshotMethod']);self.assertNotIn('workbench/metadata/output.mp4',snap.manifest['files']);self.assertEqual('file',facts['filesystem']['workbench/metadata/output.mp4']['kind'])
 def test_media_digest_is_explicit_bounded_and_not_media_copy(self):
  self.plan['hashMetadataFiles']=True;snap=self.capture();node=snap.manifest['facts']['filesystem']['workbench/metadata/output.mp4'];self.assertTrue(node['hashPending']);self.assertEqual('large_or_media_metadata_only',node['hashState']);self.assertNotIn('contentSha256',node)
  self.assertFalse((snap.root/'workbench/metadata/output.mp4').exists())
 def test_media_hash_budget_publishes_explicit_pending_digest(self):
  self.plan['hashMetadataFiles']=True
  snap=self.capture(max_hash_bytes=1)
  self.assertTrue(snap.manifest['facts']['filesystem']['workbench/metadata/output.mp4']['hashPending'])
  self.assertTrue((self.root/'snapshot').exists())
 def test_growing_export_does_not_reject_entire_aligned_capture(self):
  from unittest.mock import patch
  import tools.shadow_capture as capture_module
  original=capture_module._inventory;calls=[]
  self.plan['hashMetadataFiles']=True
  def inventory(*args,**kw):
   calls.append(1)
   if len(calls)==2:
    with (self.live/'metadata/output.mp4').open('ab') as stream:stream.write(b'export-growing')
   return original(*args,**kw)
  with patch.object(capture_module,'_inventory',side_effect=inventory):snap=self.capture()
  node=snap.manifest['facts']['filesystem']['workbench/metadata/output.mp4']
  self.assertTrue(node['hashPending']);self.assertEqual('writing_or_changed',node['hashState'])
  self.assertNotIn('contentSha256',node);self.assertEqual(len(b'fake-media-never-runexport-growing'),node['size'])
 def test_digest_cache_never_reuses_after_file_identity_changes(self):
  from tools.shadow_capture import DigestCache,_stat
  cache=DigestCache();file=self.live/'metadata/output.mp4';old=_stat(file);one,used=cache.hash(file,old);two,reused=cache.hash(file,_stat(file));self.assertEqual(one,two);self.assertGreater(used,0);self.assertEqual(0,reused)
  file.write_bytes(b'new-media-content');new,_=cache.hash(file,_stat(file));self.assertNotEqual(one,new)
 def test_changed_external_reply_rejects_complete_window(self):
  calls=[]
  def probe():calls.append(1);return {'receiver:/api/health':{'ok':len(calls)==1}}
  with self.assertRaisesRegex(CaptureError,'external_or_process_changed'):aligned_capture(self.plan,self.root/'snapshot',source_path=self.source,process_probe=lambda:self.process,http_probe=probe)
  self.assertFalse((self.root/'snapshot').exists())
 def test_external_aba_generation_change_rejects_identical_bodies(self):
  calls=[]
  def probe():calls.append(1);return {'responses':self.http,'observationGeneration':len(calls)}
  with self.assertRaisesRegex(CaptureError,'external_or_process_changed'):aligned_capture(self.plan,self.root/'snapshot',source_path=self.source,process_probe=lambda:self.process,http_probe=probe)
 def test_pid_reuse_is_a_mismatch_even_when_pid_unchanged(self):
  calls=[]
  def probe():calls.append(1);v=copy.deepcopy(self.process);v['processRecords'][0]['create_time']+=len(calls);return v
  with self.assertRaisesRegex(CaptureError,'external_or_process_changed'):aligned_capture(self.plan,self.root/'snapshot',source_path=self.source,process_probe=probe,http_probe=lambda:self.http)
 def test_file_change_directory_addition_and_absence_creation_reject(self):
  for change in ['state','directory','absence']:
   with self.subTest(change=change),TemporaryDirectory() as tmp:
    out=Path(tmp)/'snapshot';calls=[]
    def probe():
     calls.append(1)
     if len(calls)==2:
      if change=='state':self.state.write_text('{"items":[1]}',encoding='utf-8')
      elif change=='directory':(self.live/'metadata/new.mp4').write_bytes(b'fixture')
      else:(self.live/'missing.json').write_text('{}',encoding='utf-8')
     return self.http
    with self.assertRaises(CaptureError):aligned_capture(self.plan,out,source_path=self.source,process_probe=lambda:self.process,http_probe=probe)
    self.assertFalse(out.exists())
 def test_credentials_in_content_or_process_arguments_are_rejected(self):
  self.state.write_text('{"accessToken":"fixture-must-not-copy"}',encoding='utf-8')
  with self.assertRaises((CaptureError,SnapshotError)):self.capture()
  self.assertFalse((self.root/'snapshot').exists());self.state.write_text('{}',encoding='utf-8');self.process['processRecords'][0]['cmdline']=['python','--token','fixture-must-not-copy']
  with self.assertRaisesRegex(CaptureError,'private_process_argument'):self.capture()
 def test_private_files_unknown_roots_overlap_and_unknown_source_reject(self):
  plan=copy.deepcopy(self.plan);plan['files']['workbench/config.json']={'root':'workbench','path':'config.json'}
  with self.assertRaisesRegex(CaptureError,'not_allowed'):aligned_capture(plan,self.root/'out',source_path=self.source,process_probe=lambda:self.process,http_probe=lambda:self.http)
  with self.assertRaisesRegex(CaptureError,'overlap'):aligned_capture(self.plan,self.live/'out',source_path=self.source,process_probe=lambda:self.process,http_probe=lambda:self.http)
  self.source.write_text('unreviewed source',encoding='utf-8')
  with self.assertRaisesRegex(CaptureError,'unreviewed'):self.capture()
 def test_sqlite_source_connection_is_readonly_and_live_bytes_unchanged(self):
  db=self.live/'data/ops.db';db.parent.mkdir()
  with sqlite3.connect(db) as conn:conn.execute('CREATE TABLE tasks(task_id TEXT)');conn.execute('INSERT INTO tasks VALUES(?)',('fixture',))
  conn.close()
  before=db.read_bytes();self.plan['roots']['repository']=str(self.live);self.plan['databases']={'repository/data/ops.db':{'root':'repository','path':'data/ops.db'}}
  import unittest.mock
  original=sqlite3.connect;calls=[]
  def connect(path,*args,**kwargs):
   calls.append(str(path))
   if str(path).startswith(db.absolute().as_uri()):self.assertIn('mode=ro',str(path));self.assertTrue(kwargs.get('uri'))
   else:self.assertNotEqual(db.absolute(),Path(path).absolute())
   return original(path,*args,**kwargs)
  with unittest.mock.patch('sqlite3.connect',side_effect=connect):snap=self.capture()
  self.assertTrue(calls);self.assertEqual(before,db.read_bytes());self.assertFalse(Path(str(db)+'-shm').exists());self.assertEqual('sqlite',snap.manifest['files']['repository/data/ops.db']['kind'])
 def test_budget_exceeded_and_existing_destination_never_overwrite(self):
  with self.assertRaisesRegex(CaptureError,'file_limit'):self.capture(max_file_bytes=1)
  self.capture()
  with self.assertRaisesRegex(CaptureError,'new_capture'):self.capture()

class DependencyClosureTests(unittest.TestCase):
 def test_undeclared_absence_is_not_accepted_as_a_missing_fact(self):
  with TemporaryDirectory() as tmp,ExitStack() as stack:
   root=Path(tmp);guard=SandboxIO(root,stack,{},(),strict_reads=True,absent_paths=['known-missing.json']).install()
   self.assertFalse((root/'known-missing.json').exists())
   with self.assertRaisesRegex(PermissionError,'undeclared_frozen_fact'):(root/'never-captured.json').exists()
   self.assertTrue(guard.denied)
 def test_scratch_writes_and_declared_parent_directories_remain_possible(self):
  with TemporaryDirectory() as tmp,ExitStack() as stack:
   root=Path(tmp);SandboxIO(root,stack,{},(),strict_reads=True,absent_paths=['nested/missing.json']).install()
   self.assertFalse((root/'nested/missing.json').exists());p=root/'generated.json';p.write_text('{}');self.assertEqual('{}',p.read_text())

class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.source=self.root/'source';(self.source/'objects').mkdir(parents=True);(self.source/'samples').mkdir();body=canonical({'status':'fixture'});self.digest=hashlib.sha256(body).hexdigest();(self.source/'objects'/self.digest).write_bytes(body);(self.source/'samples/fixture.json').write_bytes(canonical({'files':[self.digest],'comparable':False}));(self.source/'status.json').write_bytes(canonical({'quotaExhausted':True}));(self.source/'observer.lock').write_bytes(b'0')
 def test_full_store_archives_without_deletion_or_claiming_real_shadow(self):
  before={p.relative_to(self.source).as_posix():p.read_bytes() for p in self.source.rglob('*') if p.is_file()};out=self.root/'archive';manifest=archive_passive(self.source,out,max_archive_bytes=2*1024*1024)
  self.assertTrue(manifest['originalsRetained']);self.assertEqual(0,manifest['deletedFiles']);self.assertFalse(manifest['comparable']);self.assertFalse(manifest['realShadowPassed']);self.assertEqual(before,{p.relative_to(self.source).as_posix():p.read_bytes() for p in self.source.rglob('*') if p.is_file()});self.assertEqual(manifest,verify_archive(out))
 def test_corruption_capacity_and_unlisted_private_file_reject(self):
  with self.assertRaisesRegex(CaptureError,'capacity'):archive_passive(self.source,self.root/'archive',max_archive_bytes=1)
  self.assertFalse((self.root/'archive').exists());(self.source/'objects'/self.digest).write_bytes(b'{}')
  with self.assertRaisesRegex(CaptureError,'hash_mismatch'):archive_passive(self.source,self.root/'archive',max_archive_bytes=2*1024*1024)
  (self.source/'config.json').write_text('{}')
  with self.assertRaisesRegex(CaptureError,'unexpected_passive'):archive_passive(self.source,self.root/'archive',max_archive_bytes=2*1024*1024)
 def test_archived_bytes_are_verified_and_existing_output_is_protected(self):
  out=self.root/'archive';archive_passive(self.source,out,max_archive_bytes=2*1024*1024)
  with self.assertRaisesRegex(CaptureError,'new_destination'):archive_passive(self.source,out,max_archive_bytes=2*1024*1024)
  (out/'status.json').write_text('{}')
  with self.assertRaisesRegex(CaptureError,'hash_mismatch'):verify_archive(out)
 def test_capacity_counts_retained_files_without_inventing_free_space(self):
  result=capacity([self.source,self.source],approved_total_bytes=1);self.assertFalse(result['canAllocate']);self.assertEqual(0,result['remainingBytes']);self.assertEqual(0,result['deletedFiles'])
