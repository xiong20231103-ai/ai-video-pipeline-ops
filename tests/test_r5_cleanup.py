import ast,copy,hashlib,inspect,json,sys,types,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app
import test_ops
import test_cleanup_protections
import test_cloud_cleanup_home
from cleanup_tickets import CleanupTickets
from agent.core.cleanup import CleanupSession,bind_function,replay_cleanup
from agent.core import cleanup_logic
from agent.core.oracle import Oracle
from agent.core.replay import make_fixture,replay,read_targets
from agent.core.comparison import compare

ROOT=Path(__file__).resolve().parents[1]


class CleanupExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r5-fixture-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8')

    def test_exact_source_including_strict_decorators_and_provenance(self):
        manifest=json.loads((ROOT/'tests/fixtures/migration/r5-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['legacySha256'],hashlib.sha256(self.source.encode()).hexdigest())
        old={n.name:n for n in ast.parse(self.source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        new={n.name:n for n in ast.parse(Path(cleanup_logic.__file__).read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        self.assertEqual(75,len(new))
        for row in manifest['functions']:
            original=copy.deepcopy(old[row['name']])
            original.decorator_list=[d for d in original.decorator_list if not(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and isinstance(d.func.value,ast.Name) and d.func.value.id=='app')]
            candidate=new[row['name']]
            self.assertEqual(ast.dump(original,include_attributes=False),ast.dump(candidate,include_attributes=False),row['name'])
            self.assertEqual((candidate.lineno,candidate.end_lineno),(row['candidateStart'],row['candidateEnd']))

    def test_20_profiles_all_28_read_responses_and_effects_match(self):
        profiles=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))
        targets=read_targets(json.loads((ROOT/'contracts/endpoints.json').read_text(encoding='utf-8')))
        for index,(name,profile) in enumerate(profiles.items()):
            with self.subTest(profile=name):
                snapshot=make_fixture(profile,self.source,self.root/str(index)/'snapshot')
                old=replay(self.source,snapshot,self.root/str(index)/'old',targets)
                new=replay_cleanup(self.source,snapshot,self.root/str(index)/'new',targets)
                self.assertEqual([],compare(old,new))
                self.assertFalse(new['realShadowPassed']);self.assertFalse(new['switchAccepted'])

    def test_session_has_private_tickets_context_and_locks_no_live_executor(self):
        one=CleanupSession(vars(app),tickets=CleanupTickets());two=CleanupSession(vars(app),tickets=CleanupTickets())
        for name in ('CAPCUT_DRAFT_LOCK','AUDIO_CLEANUP_LOCK','PRODUCTION_FILE_CLEANUP_LOCK','CLOUD_CLEANUP_TICKETS','_CLEANUP_SOURCE_STRICT'):
            self.assertIsNot(one.namespace[name],two.namespace[name])
        self.assertIs(one.namespace['pending_delete'],app.pending_delete)
        self.assertFalse(hasattr(one,'send'));self.assertFalse(one.capability()['enabled'])
        self.assertFalse(one.capability()['fiveDirectoryExtension'])
        with self.assertRaisesRegex(ValueError,'isolated_evaluation_only'):one.evaluate('audio_inventory_public')
        with self.assertRaisesRegex(ValueError,'missing_cleanup_ports'):CleanupSession({},tickets=CleanupTickets())

    def test_guarded_functions_bind_the_underlying_function_to_new_namespace(self):
        session=CleanupSession(vars(app),tickets=CleanupTickets())
        fn=session.namespace['_production_file_inventory']
        self.assertIs(fn.__globals__,session.namespace)
        self.assertIs(fn.__wrapped__.__globals__,session.namespace)
        self.assertIsNot(fn.__wrapped__,cleanup_logic._production_file_inventory.__wrapped__)


class CandidateCleanupCompatibility(unittest.TestCase):
    def setUp(self):
        session=CleanupSession(vars(app),tickets=CleanupTickets(),isolated=True)
        facade=types.ModuleType('app');facade.__dict__.update(vars(app))
        facade.__dict__.update(session.namespace)
        # Recursively rebind decorated wrapped functions, not just the outer
        # closure: strict-source failures must remain strict in the candidate.
        memo={}
        for name,value in vars(cleanup_logic).items():
            if inspect.isfunction(value) and value.__module__==cleanup_logic.__name__:
                facade.__dict__[name]=bind_function(value,facade.__dict__,memo)
        self.facade=facade
        context=patch.dict(sys.modules,{'app':facade});context.start();self.addCleanup(context.stop)

    def run_existing(self,case_type,name):
        local=dict(vars(sys.modules[case_type.__module__]));local['app']=self.facade
        for key,value in list(local.items()):
            if inspect.isfunction(value) and value.__module__==case_type.__module__:
                fn=types.FunctionType(value.__code__,local,value.__name__,value.__defaults__,value.__closure__);fn.__kwdefaults__=value.__kwdefaults__;local[key]=fn
        attrs={}
        for key,value in vars(case_type).items():
            if inspect.isfunction(value):
                fn=types.FunctionType(value.__code__,local,value.__name__,value.__defaults__,value.__closure__);fn.__kwdefaults__=value.__kwdefaults__;attrs[key]=fn
        bound=type('BoundR5'+case_type.__name__,(unittest.TestCase,),attrs)
        result=unittest.TestResult();bound(name).run(result)
        self.assertEqual([],result.errors,result.errors);self.assertEqual([],result.failures,result.failures)


for case_type in (test_cleanup_protections.CleanupProtectionTests,test_cloud_cleanup_home.CloudCleanupTests):
    for name in vars(case_type):
        if name.startswith('test_'):
            def test(self,_type=case_type,_name=name):self.run_existing(_type,_name)
            setattr(CandidateCleanupCompatibility,'test_candidate_'+name.removeprefix('test_'),test)
del case_type,name,test


if __name__=='__main__':unittest.main()
