"""Retained-process binding against frozen inputs; never a real shadow result."""
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import types
import unittest
from agent.core.oracle import Oracle
from agent.core.replay import make_fixture,replay,read_targets
from agent.core.comparison import compare
from agent.core.staged_modules import install,selected

ROOT=Path(__file__).resolve().parents[1]


def staged_replay(source,snapshot,scratch,targets,stage):
    with Oracle(source,snapshot,scratch,collect=False) as environment:
        namespace=environment.namespace;store=namespace['STORE'];collector=namespace['COLLECTOR']
        locks={k:namespace[k] for k in ('CONTROL_COMMAND_LOCK','CAPCUT_DRAFT_LOCK','AUDIO_CLEANUP_LOCK',
            'PRODUCTION_FILE_CLEANUP_LOCK','_CLEANUP_SOURCE_STRICT','CLOUD_CLEANUP_TICKETS')}
        ports={k:namespace[k] for k in ('system_metrics','process_status','pending_delete_roots')}
        routes=[types.SimpleNamespace(endpoint=fn,dependant=types.SimpleNamespace(call=fn)) for _,fn in environment.registry.routes]
        collector.thread=None
        result=install(namespace,types.SimpleNamespace(routes=routes),stage)
        assert result['installedModules']==list(selected(stage))
        assert namespace['STORE'] is store and namespace['COLLECTOR'] is collector
        assert all(namespace[k] is v for k,v in locks.items())
        assert all(route.endpoint is route.dependant.call for route in routes)
        environment.registry.routes=[(path,route.dependant.call) for (path,_),route in zip(environment.registry.routes,routes)]
        namespace.update(ports)
        if snapshot.manifest['facts'].get('scan',True):collector.scan()
        collector.last_scan_at=snapshot.manifest['frozenAt']
        collector.last_scan_epoch=datetime.fromisoformat(snapshot.manifest['frozenAt'].replace('Z','+00:00')).timestamp()
        collector.thread=types.SimpleNamespace(is_alive=lambda:snapshot.manifest['facts'].get('collectorAlive',False))
        before=environment.effects()
        responses={target:environment.request(target) for target in targets}
        after=environment.effects()
        return {'schema':1,'mode':'isolated','sourceIdentity':snapshot.manifest['sourceIdentity'],
            'legacySha256':snapshot.manifest['legacySha256'],'responses':responses,'effects':{'before':before,'after':after},
            'httpReads':environment.requests,'realShadowPassed':False,'switchAccepted':False}


class StagedModuleTests(unittest.TestCase):
    def test_retained_store_routes_and_all_read_side_effects_match_twenty_profiles(self):
        source=(ROOT/'app.py').read_text(encoding='utf-8')
        profiles=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))
        targets=read_targets(json.loads((ROOT/'contracts/endpoints.json').read_text(encoding='utf-8')))
        with TemporaryDirectory(prefix='r6-staged-golden-') as directory:
            for index,(name,profile) in enumerate(profiles.items()):
                with self.subTest(profile=name):
                    root=Path(directory)/str(index)
                    snapshot=make_fixture(profile,source,root/'snapshot')
                    old=replay(source,snapshot,root/'old',targets)
                    stages=selected('R5') if index==0 else ('R5',)
                    for stage in stages:
                        with self.subTest(stage=stage):
                            new=staged_replay(source,snapshot,root/stage,targets,stage)
                            self.assertEqual([],compare(old,new))

    def test_running_or_already_bound_collector_refuses_without_mutation(self):
        collector=types.SimpleNamespace(thread=types.SimpleNamespace(is_alive=lambda:True))
        namespace={'STORE':object(),'COLLECTOR':collector}
        before=namespace.copy()
        with self.assertRaisesRegex(ValueError,'already_running'):install(namespace,types.SimpleNamespace(routes=[]),'R1')
        self.assertEqual(before,namespace)
        collector.thread=None;collector._ops_staged_modules=('R0',)
        with self.assertRaisesRegex(ValueError,'already_installed'):install(namespace,types.SimpleNamespace(routes=[]),'R1')
        self.assertEqual(before,namespace)
