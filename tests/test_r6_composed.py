import ast,copy,hashlib,inspect,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import app
from cleanup_tickets import CleanupTickets
from agent.core.composed import ComposedSession,replay_composed
from agent.core import compatibility_logic
from agent.core.replay import make_fixture,replay,read_targets
from agent.core.comparison import compare

ROOT=Path(__file__).resolve().parents[1]


class CompositionTests(unittest.TestCase):
    def test_remaining_handlers_have_exact_reviewable_source(self):
        source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8')
        manifest=json.loads((ROOT/'docs/migration/r6-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['legacySha256'],hashlib.sha256(source.encode()).hexdigest())
        old={n.name:n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        new={n.name:n for n in ast.parse(Path(compatibility_logic.__file__).read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        for row in manifest['functions']:
            original=copy.deepcopy(old[row['name']]);original.decorator_list=[]
            self.assertEqual(ast.dump(original,include_attributes=False),ast.dump(new[row['name']],include_attributes=False),row['name'])

    def test_all_modules_share_projection_locks_and_strict_context(self):
        with ComposedSession(vars(app),tickets=CleanupTickets()) as session:
            namespace=session.namespace
            for name in ('dashboard','create_control_command','control_create_task',
                         '_production_file_inventory','dashboard_payload','enqueue_control_command'):
                function=namespace[name]
                self.assertIs(function.__globals__,namespace,name)
                if hasattr(function,'__wrapped__'):
                    self.assertIs(function.__wrapped__.__globals__,namespace,name)
            self.assertIs(namespace['STORE'],session.store)
            self.assertIs(namespace['COLLECTOR'],session.collector)
            self.assertIsNot(namespace['CONTROL_COMMAND_LOCK'],app.CONTROL_COMMAND_LOCK)
            self.assertFalse(session.capability()['enabled'])
            self.assertFalse(hasattr(session,'send'))
            with self.assertRaisesRegex(ValueError,'protocol2_transport_not_bound'):
                namespace['request_workbench_continue']({})

    def test_native_construction_has_no_installed_app_or_config_discovery(self):
        from agent.core.runtime_ports import native_ports
        with TemporaryDirectory(prefix='r6-native-') as directory:
            root=Path(directory)
            ports=native_ports(root,root/'state',{})
            ports['control_plane_json']=lambda *args,**kwargs: {'available':False}
            with ComposedSession(ports,tickets=ports['CLOUD_CLEANUP_TICKETS']) as session:
                self.assertEqual({},session.namespace['CONFIG'])
                self.assertFalse((root/'state').exists())

    def test_twenty_profiles_all_read_handlers_and_side_effects_match(self):
        source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8')
        profiles=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))
        targets=read_targets(json.loads((ROOT/'contracts/endpoints.json').read_text(encoding='utf-8')))
        with TemporaryDirectory(prefix='r6-isolated-') as directory:
            for index,(name,profile) in enumerate(profiles.items()):
                with self.subTest(profile=name):
                    root=Path(directory)/str(index)
                    snapshot=make_fixture(profile,source,root/'snapshot')
                    old=replay(source,snapshot,root/'old',targets)
                    new=replay_composed(source,snapshot,root/'new',targets)
                    self.assertEqual([],compare(old,new))
