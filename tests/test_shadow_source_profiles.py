import ast,copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from agent.core.oracle import Oracle
from agent.core.replay import make_fixture,replay
from agent.core.collection_replay import replay_collection
from agent.core.collection import CollectionSession,CollectionError
from agent.core.source_profiles import PR49,F78
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
  self.assertEqual(PR49,hashlib.sha256(self.source.encode()).hexdigest())
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
 def test_new_candidate_helper_cannot_be_relabeled_as_deployed_pr49(self):
  profile=copy.deepcopy(self.profile)
  profile['facts']['captureProof']={'helperHashes':{'verified_final.py':hashlib.sha256((ROOT/'verified_final.py').read_text(encoding='utf-8-sig').encode()).hexdigest()}}
  snap=make_fixture(profile,self.source,self.root/'new-helper-snapshot')
  with self.assertRaisesRegex(SnapshotError,'source_dependency_hash_mismatch'):Oracle(self.source,snap,self.root/'unknown-helper')
