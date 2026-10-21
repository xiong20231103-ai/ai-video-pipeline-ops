import ast,hashlib,json,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from agent.core.collection import CollectionSession,CollectionError
from agent.core.collection_replay import replay_collection
from agent.core.replay import make_fixture,replay,read_targets
from agent.core.oracle import Oracle
from agent.core.comparison import compare
ROOT=Path(__file__).resolve().parents[1]

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r1-isolated-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8');self.profiles=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))
        self.targets=read_targets(json.loads((ROOT/'contracts/endpoints.json').read_text(encoding='utf-8')))
    def test_all_profiles_read_outputs_and_get_effects_match_old_oracle(self):
        for i,(name,profile) in enumerate(self.profiles.items()):
            with self.subTest(profile=name):
                snapshot=make_fixture(profile,self.source,self.root/('snapshot'+str(i)))
                old=replay(self.source,snapshot,self.root/('old'+str(i)),self.targets)
                new=replay_collection(self.source,snapshot,self.root/('new'+str(i)),self.targets)
                self.assertEqual([],compare(old,new))
                self.assertFalse(new['realShadowPassed']);self.assertFalse(new['switchAccepted'])
    def test_candidate_mutation_is_detected(self):
        snapshot=make_fixture(self.profiles['running'],self.source,self.root/'snapshot')
        old=replay(self.source,snapshot,self.root/'old',self.targets)
        new=replay_collection(self.source,snapshot,self.root/'new',self.targets,mutate=lambda session:session.namespace.update(overview_payload=lambda *args:{'fixtureMutation':True}))
        self.assertTrue(compare(old,new))
    def test_ports_are_required_and_projection_store_has_no_lifecycle(self):
        with self.assertRaisesRegex(CollectionError,'missing_collection_ports'):CollectionSession({})
        snapshot=make_fixture(self.profiles['running'],self.source,self.root/'snapshot')
        with Oracle(self.source,snapshot,self.root/'scratch',collect=False) as env:
            with CollectionSession(env.namespace) as session:
                self.assertEqual(':memory:',session.store.path)
                for method in ('start','stop','run','reset_runtime'):self.assertFalse(hasattr(session.collector,method))
                self.assertFalse(hasattr(session.store,'clear_all'))
                with self.assertRaisesRegex(CollectionError,'unknown_projection'):session.project('enqueue_control_command')
    def test_extracted_bodies_match_pinned_source_except_explicit_lifecycle_removal(self):
        from agent.core import collection_logic
        original=ast.parse(self.source);candidate=ast.parse(Path(collection_logic.__file__).read_text(encoding='utf-8'))
        defs={n.name:n for n in original.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        provenance=json.loads((ROOT/'docs/migration/r1-provenance.json').read_text(encoding='utf-8'))
        for node in candidate.body:
            if not isinstance(node,(ast.FunctionDef,ast.ClassDef)):continue
            old=defs[node.name]
            if isinstance(old,ast.ClassDef):old.body=[n for n in old.body if not isinstance(n,ast.FunctionDef) or n.name not in provenance['excludedMethods'].get(old.name,[])]
            self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(node,include_attributes=False),node.name)

    def test_failed_scan_invalidates_partial_projection_without_file_store(self):
        from unittest.mock import patch
        snapshot=make_fixture(self.profiles['running'],self.source,self.root/'snapshot')
        with Oracle(self.source,snapshot,self.root/'scratch',collect=False) as env:
            with CollectionSession(env.namespace) as session:
                with patch.object(session.collector,'scan',side_effect=ValueError('synthetic_corrupt_input')):
                    with self.assertRaisesRegex(ValueError,'synthetic_corrupt_input'):session.scan()
                with self.assertRaisesRegex(CollectionError,'projection_incomplete'):session.project('pipeline_dates')
                session.scan();self.assertTrue(session.valid)
                self.assertTrue(session.project('pipeline_dates'))
    def test_seed_byte_and_row_limits_refuse_without_truncation(self):
        snapshot=make_fixture(self.profiles['running'],self.source,self.root/'snapshot')
        with Oracle(self.source,snapshot,self.root/'scratch',collect=False) as env:
            seed=sqlite3.connect(':memory:');self.addCleanup(seed.close)
            seed.execute('CREATE TABLE oversized(value BLOB)');seed.execute('INSERT INTO oversized VALUES(zeroblob(100000))');seed.commit()
            with self.assertRaisesRegex(CollectionError,'projection_byte_limit'):CollectionSession(env.namespace,seed=seed,max_bytes=65536)
            with CollectionSession(env.namespace,max_rows=1) as session:
                with self.assertRaisesRegex(CollectionError,'projection_row_limit'):session.scan()
                self.assertFalse(session.valid)
    def test_sessions_do_not_share_mutable_runtime_or_start_workers(self):
        snapshot=make_fixture(self.profiles['running'],self.source,self.root/'snapshot')
        with Oracle(self.source,snapshot,self.root/'scratch',collect=False) as env:
            with CollectionSession(env.namespace) as one,CollectionSession(env.namespace) as two:
                one.namespace['CONFIG']['machine_name']='synthetic-other'
                self.assertNotEqual(one.namespace['CONFIG']['machine_name'],two.namespace['CONFIG']['machine_name'])
                self.assertIsNot(one.collector,two.collector);self.assertIsNot(one.store,two.store)
                self.assertIsNone(one.collector.thread);self.assertIsNone(two.collector.thread)
