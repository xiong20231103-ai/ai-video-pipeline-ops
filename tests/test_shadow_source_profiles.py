import ast,copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from agent.core.oracle import Oracle
from agent.core.replay import make_fixture,replay
from agent.core.collection_replay import replay_collection
from agent.core.collection import CollectionSession,CollectionError
from agent.core.source_profiles import PR49,F78,D6A7211_CRLF,SUBTITLE_IDLE,SUBTITLE_IDLE_CRLF,PIP_CONSOLE,PIP_CONSOLE_CRLF,CAPCUT_IMAGE,read_source
from agent.core.snapshot import SnapshotError
from agent.core.comparison import compare
ROOT=Path(__file__).resolve().parents[1]

class ShadowSourceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.source=(ROOT/'app.py').read_text(encoding='utf-8')
  self.profile=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))['running']
 def snapshot(self,hash_fact='a'*64):
  profile=copy.deepcopy(self.profile);profile['facts']['scan']=False
  node={'kind':'file','size':100,'mtimeNs':1700000000000000000}
  if hash_fact is not None:node['contentSha256']=hash_fact
  profile['facts']['filesystem']={'final':{'kind':'directory','size':0,'mtimeNs':1700000000000000000},'final/video.mp4':node}
  profile['files']['reports/qc.json']={'status':'passed','taskId':'child','canonicalTaskId':'parent','fileName':'video.mp4','fileSize':100,'sha256':'a'*64}
  return make_fixture(profile,self.source,self.root/'snapshot')
 def metadata(self,env):
  return {'taskId':'child','remotePipelineTaskId':'parent','status':'failed','productionStatus':'completed','draftReleaseStatus':'released','qualityStatus':'passed','qualityReportPath':str(env.root/'reports/qc.json'),'finalOutputPath':str(env.root/'final/video.mp4')}
 def test_registered_current_source_and_candidate_normalizer_match_ast(self):
  from agent.core.collection_verified_final import normalize_task
  import inspect,textwrap
  tree=ast.parse(self.source);old=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Collector')
  node=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name=='normalize_task')
  extracted=ast.parse(textwrap.dedent(inspect.getsource(normalize_task))).body[0]
  self.assertEqual(ast.dump(node,include_attributes=False),ast.dump(extracted,include_attributes=False))
  self.assertEqual(CAPCUT_IMAGE,hashlib.sha256(self.source.encode()).hexdigest())
 def test_metadata_hash_port_supports_both_old_and_candidate_without_media_reads(self):
  snap=self.snapshot()
  with Oracle(self.source,snap,self.root/'old',collect=False) as env:
   env.namespace['COLLECTOR'].metadata={'child':self.metadata(env)}
   old=env.namespace['COLLECTOR'].normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
   with CollectionSession(env.namespace,source_sha=PR49) as candidate:
    candidate.collector.metadata={'child':self.metadata(env)}
    new=candidate.collector.normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
   self.assertEqual('completed',old['state'],env.missing_hash_facts);self.assertEqual(old,new)
   self.assertEqual([],env.io.denied)
 def test_missing_hash_does_not_silently_become_equal_failed_results(self):
  snap=self.snapshot(None)
  with self.assertRaisesRegex(SnapshotError,'missing_frozen_content_hash'):
   with Oracle(self.source,snap,self.root/'old',collect=False) as env:
    env.namespace['COLLECTOR'].metadata={'child':self.metadata(env)}
    env.namespace['COLLECTOR'].normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
 def test_conflicting_qc_digest_stays_failed(self):
  snap=self.snapshot('b'*64)
  with Oracle(self.source,snap,self.root/'old',collect=False) as env:
   env.namespace['COLLECTOR'].metadata={'child':self.metadata(env)}
   row=env.namespace['COLLECTOR'].normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
   self.assertEqual('failed',row['state'])
 def test_unknown_source_and_dependency_drift_are_rejected(self):
  snap=self.snapshot()
  with self.assertRaisesRegex(SnapshotError,'legacy_source_hash_mismatch'):Oracle(self.source+'\n#unregistered',snap,self.root/'unknown')
  with patch('agent.core.source_profiles.PR49_HELPER','0'*64):
   with self.assertRaisesRegex(SnapshotError,'source_dependency_hash_mismatch'):Oracle(self.source,snap,self.root/'bad-helper')
 def test_new_profile_read_replay_retains_real_gate_false(self):
  snap=make_fixture(self.profile,self.source,self.root/'snapshot')
  targets=['/api/dashboard/summary','/api/task-boxes/current']
  old=replay(self.source,snap,self.root/'old',targets)
  new=replay_collection(self.source,snap,self.root/'new',targets)
  self.assertEqual([],compare(old,new));self.assertFalse(new['realShadowPassed'])
 def test_unsupported_collection_profile_does_not_fall_back(self):
  snap=self.snapshot()
  with Oracle(self.source,snap,self.root/'old',collect=False) as env:
   with self.assertRaisesRegex(CollectionError,'unsupported_collection_source'):CollectionSession(env.namespace,source_sha='0'*64)
 def test_frozen_helper_binding_is_scoped_and_restored(self):
  import sys,verified_final
  from agent.core.source_profiles import legacy_verified_final_source,PR49_HELPER
  self.assertEqual(PR49_HELPER,hashlib.sha256(legacy_verified_final_source().encode()).hexdigest())
  original=verified_final
  snap=self.snapshot()
  with Oracle(self.source,snap,self.root/'old',collect=False):
   self.assertIsNot(original,sys.modules['verified_final'])
  self.assertIs(original,sys.modules['verified_final'])
 def test_new_helper_requires_explicit_identity_facts(self):
  profile=copy.deepcopy(self.profile)
  profile['facts']['captureProof']={'helperHashes':{'verified_final.py':hashlib.sha256((ROOT/'verified_final.py').read_text(encoding='utf-8-sig').encode()).hexdigest()}}
  snap=make_fixture(profile,self.source,self.root/'new-helper-snapshot')
  with self.assertRaisesRegex(SnapshotError,'verified_final_identity_fact_required'):Oracle(self.source,snap,self.root/'unknown-helper')

 def test_exact_current_crlf_archive_uses_existing_pr49_oracle_and_candidate(self):
  raw=(ROOT/'contracts/legacy-app-d6a7211-crlf.txt').read_bytes()
  self.assertEqual(D6A7211_CRLF,hashlib.sha256(raw).hexdigest())
  self.assertEqual(PR49,hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest())
  self.source=read_source(ROOT/'contracts/legacy-app-d6a7211-crlf.txt')
  snap=self.snapshot()
  with Oracle(self.source,snap,self.root/'old',collect=False) as env:
   self.assertEqual(D6A7211_CRLF,env.source_sha)
   env.namespace['COLLECTOR'].metadata={'child':self.metadata(env)}
   old=env.namespace['COLLECTOR'].normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
   with CollectionSession(env.namespace,source_sha=D6A7211_CRLF) as candidate:
    candidate.collector.metadata={'child':self.metadata(env)}
    new=candidate.collector.normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
   self.assertEqual('completed',old['state']);self.assertEqual(old,new)
 def test_subtitle_idle_archive_preserves_pinned_business_source(self):
  raw=(ROOT/'contracts/legacy-app-subtitle-idle-crlf.txt').read_bytes()
  self.assertEqual(SUBTITLE_IDLE_CRLF,hashlib.sha256(raw).hexdigest())
  old_source=raw.decode('utf-8').replace('\r\n','\n')
  self.assertEqual(SUBTITLE_IDLE,hashlib.sha256(old_source.encode()).hexdigest())
  old_tree=ast.parse(old_source);current_tree=ast.parse((ROOT/'contracts/legacy-app-pip-console-crlf.txt').read_text(encoding='utf-8'))
  # Between these two historical archives only the startup guard differs.
  self.assertEqual(ast.dump(current_tree.body[1],include_attributes=False),
                   ast.dump(ast.parse('import os as _guard_os').body[0],include_attributes=False))
  self.assertIsInstance(current_tree.body[2],ast.If)
  business=ast.Module(body=current_tree.body[:1]+current_tree.body[3:],type_ignores=[])
  self.assertEqual(ast.dump(old_tree,include_attributes=False),ast.dump(business,include_attributes=False))
  self.source=read_source(ROOT/'contracts/legacy-app-subtitle-idle-crlf.txt');snap=self.snapshot()
  with Oracle(self.source,snap,self.root/'old',collect=False) as env:
   self.assertEqual(SUBTITLE_IDLE_CRLF,env.source_sha)
   env.namespace['COLLECTOR'].metadata={'child':self.metadata(env)}
   old=env.namespace['COLLECTOR'].normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
   with CollectionSession(env.namespace,source_sha=SUBTITLE_IDLE_CRLF) as candidate:
    candidate.collector.metadata={'child':self.metadata(env)}
    new=candidate.collector.normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
   self.assertEqual('completed',old['state']);self.assertEqual(old,new)
 def test_historical_pip_console_archive_retains_closed_replay(self):
  raw=(ROOT/'contracts/legacy-app-pip-console-crlf.txt').read_bytes()
  self.assertEqual(PIP_CONSOLE_CRLF,hashlib.sha256(raw).hexdigest())
  self.assertEqual(PIP_CONSOLE,hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest())
  self.source=raw.decode('utf-8');snap=self.snapshot()
  with Oracle(self.source,snap,self.root/'pip-current',collect=False) as env:
   self.assertEqual(PIP_CONSOLE_CRLF,env.source_sha)
   with CollectionSession(env.namespace,source_sha=PIP_CONSOLE_CRLF) as candidate:
    self.assertIsNotNone(candidate.collector)
 def test_pip_archive_single_byte_mutation_remains_rejected(self):
  raw=(ROOT/'contracts/legacy-app-pip-console-crlf.txt').read_bytes()
  self.source=raw.replace(b'\r\n',b'\n',1).decode('utf-8');snap=self.snapshot()
  with self.assertRaisesRegex(SnapshotError,'legacy_source_hash_mismatch'):
   Oracle(self.source,snap,self.root/'pip-modified')
 def test_single_byte_cr_deletion_is_rejected_even_with_matching_manifest(self):
  raw=(ROOT/'contracts/legacy-app-d6a7211-crlf.txt').read_bytes()
  modified=raw.replace(b'\r\n',b'\n',1)
  self.assertEqual(len(raw)-1,len(modified))
  self.source=modified.decode('utf-8');snap=self.snapshot()
  with self.assertRaisesRegex(SnapshotError,'legacy_source_hash_mismatch'):
   Oracle(self.source,snap,self.root/'modified')
 def test_current_archive_requires_new_helper_identity_facts(self):
  self.source=read_source(ROOT/'contracts/legacy-app-d6a7211-crlf.txt')
  self.test_new_helper_requires_explicit_identity_facts()

 def test_current_source_has_only_reviewed_pr81_business_delta(self):
  old=ast.parse((ROOT/'contracts/legacy-app-pip-console-crlf.txt').read_text(encoding='utf-8'))
  current=ast.parse(self.source)
  names={'_capcut_draft_processes','process_status'}
  replacements={n.name:n for n in current.body if isinstance(n,ast.FunctionDef) and n.name in names}
  self.assertEqual(names,set(replacements))
  for index,node in enumerate(old.body):
   if isinstance(node,ast.FunctionDef) and node.name in names:old.body[index]=replacements[node.name]
  self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(current,include_attributes=False))
  from agent.core import compatibility_logic
  import inspect,textwrap
  candidate=ast.parse(textwrap.dedent(inspect.getsource(compatibility_logic.process_status))).body[0]
  self.assertEqual(ast.dump(replacements['process_status'],include_attributes=False),ast.dump(candidate,include_attributes=False))
