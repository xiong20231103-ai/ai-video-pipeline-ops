"""No production imports/process launches. Synthetic original-app and PID probes."""
import asyncio
from contextlib import asynccontextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tools import shadow_dashboard_bootstrap as bootstrap
from tools import shadow_live_runtime as live
from tools.shadow_process_preflight import probe_processes


def dump(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_psutil(private=False, denied=False):
    host=os.getpid()
    class Process:
        def __init__(self,pid):self.pid=pid
        def children(self,recursive):return []
        def create_time(self):return 123.0
        def as_dict(self,attrs):
            if denied:raise PermissionError('private exception must not escape')
            return dict(pid=self.pid,ppid=1,name='fixture',exe='fixture-python',username='fixture-user',
                        cmdline=['python','--password','PRIVATE-CANARY'] if private else ['python','fixture.py'],create_time=123.0)
    connections=[SimpleNamespace(pid=host,status='LISTEN',laddr=SimpleNamespace(port=p)) for p in (8765,8766,18790)]
    return SimpleNamespace(Process=Process,net_connections=lambda **kw:connections)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.package=self.root/'package';self.package.mkdir()
        self.names=['tools/shadow_dashboard_bootstrap.py','tools/shadow_live_runtime.py',
                    'tools/shadow_dashboard_host.py','tools/shadow_sqlite_snapshot.py']
        hashes={}
        for name in self.names:
            file=self.package/name;file.parent.mkdir(exist_ok=True);file.write_text('# inert fixture\n')
            hashes[name]=hashlib.sha256(file.read_bytes()).hexdigest()
        self.commit='a'*40
        manifest_hash=dump(self.package/'shadow-package.json',dict(schema=1,sourceCommit=self.commit,files=hashes))
        self.plan=self.root/'plan.json';plan_hash=dump(self.plan,{'fixture':True})
        self.settings=self.root/'settings.json'
        self.value=dict(schema=1,enabled=False,mode='preflight',sourceCommit=self.commit,packageRoot=str(self.package),
                        packageManifestSha256=manifest_hash,planPath=str(self.plan),planSha256=plan_hash)
        dump(self.settings,self.value)

    def test_verified_package_runs_same_original_app_and_restores_import_paths(self):
        app=FastAPI();dashboard=SimpleNamespace(app=app,CONFIG=dict(listen_host='127.0.0.1',listen_port=8765))
        old_path=list(sys.path);namespace=__import__('tools');old_namespace=list(namespace.__path__)
        calls=[]
        def configure(module,spec,mode,control):
            self.assertIs(dashboard,module);self.assertEqual('preflight',mode);self.assertEqual({'fixture':True},spec)
        self.assertEqual(0,bootstrap.run(self.settings,self.root,load_dashboard=lambda:dashboard,configure=configure,
                         serve=lambda app,**kw:calls.append((app,kw))))
        self.assertIs(app,calls[0][0]);self.assertFalse(calls[0][1]['reload'])
        self.assertEqual(old_path,sys.path);self.assertEqual(old_namespace,list(namespace.__path__))

    def test_setup_failure_cleans_import_paths_without_serving(self):
        before=list(sys.path)
        def failed(*args):raise RuntimeError('private message')
        with self.assertRaises(RuntimeError):
            bootstrap.run(self.settings,self.root,load_dashboard=lambda:None,configure=failed,serve=failed)
        self.assertEqual(before,sys.path)

    def test_only_preparation_failure_maps_to_75(self):
        with patch.object(bootstrap,'run',side_effect=bootstrap.PreparationError('fixed')),patch('builtins.print'):
            self.assertEqual(75,bootstrap.main(['--settings','fixture','--dashboard-root','fixture']))
        with patch.object(bootstrap,'run',side_effect=RuntimeError('after-service')),patch('builtins.print'):
            self.assertEqual(1,bootstrap.main(['--settings','fixture','--dashboard-root','fixture']))

    def test_serve_exception_and_bind_system_exit_never_become_preparation_failure(self):
        dashboard=SimpleNamespace(app=object(),CONFIG={'listen_host':'127.0.0.1','listen_port':8765})
        for error in (RuntimeError('after-service'),SystemExit(1),KeyboardInterrupt()):
            def serve(*args,**kwargs):raise error
            with self.assertRaises(type(error)) as found:
                bootstrap.run(self.settings,self.root,load_dashboard=lambda:dashboard,configure=lambda *args:None,serve=serve)
            self.assertNotIsInstance(found.exception,bootstrap.PreparationError)

    def test_source_or_plan_tampering_rejected_before_app_import(self):
        for target in [self.package/self.names[0],self.plan]:
            before=target.read_bytes();target.write_bytes(before+b' ')
            with self.assertRaises(ValueError):bootstrap.verified_settings(self.settings)
            target.write_bytes(before)

    def test_stray_importable_file_rejected(self):
        (self.package/'tools/stray.py').write_text('# unreviewed leftover')
        with self.assertRaisesRegex(ValueError,'bootstrap_unlisted_file'):bootstrap.verified_settings(self.settings)

    def test_preflight_cannot_enable_observation(self):
        self.value['enabled']=True;dump(self.settings,self.value)
        with self.assertRaisesRegex(ValueError,'preflight_must_be_disabled'):bootstrap.verified_settings(self.settings)
        with self.assertRaisesRegex(live.CaptureError,'observation_requires_reviewed_preflight'):
            live.configure(None,{},'observe',self.root)


class HostPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        repository=self.root/'repository';(repository/'data').mkdir(parents=True)
        self.state=repository/'data/state.json';dump(self.state,{'state':'paused'})
        self.db=repository/'data/ops.db'
        with closing(sqlite3.connect(self.db)) as connection:connection.execute('create table fixture (id integer)')
        source=repository/'app.py';source.write_text('# unchanged original fixture')
        self.dashboard=SimpleNamespace(__file__=str(source),psutil=fake_psutil())
        self.spec=dict(source=str(source),evidenceRoot=str(self.root/'new'),archivedRoot=str(self.root/'old'),
                       approvedBytes=2*1024**3,maxCaptureBytes=1024**2,
                       capturePlan={'schema':1,'roots':{'repository':str(repository)},
                           'files':{'repository/data/state.json':{'root':'repository','path':'data/state.json'}},
                           'databases':{'repository/data/ops.db':{'root':'repository','path':'data/ops.db'}},
                           'absent':{'repository/data/absent.json':{'root':'repository','path':'data/absent.json'}}})
        self.control=self.root/'control'
        self.environment=patch.dict(os.environ,{'LOCALAPPDATA':str(self.root/'local')});self.environment.start();self.addCleanup(self.environment.stop)

    def test_disabled_report_never_claims_install_or_real_evidence(self):
        before={p:p.read_bytes() for p in [self.state,self.db]}
        report=live.run_preflight(self.dashboard,self.spec,self.control)
        self.assertFalse(report['enabled']);self.assertFalse(report['installationPermitted'])
        self.assertFalse(report['productionBudgetVerified']);self.assertFalse(report['realShadowPassed'])
        self.assertEqual('blocked',report['technicalPreflight']) # no actual agent runtime supplied
        self.assertFalse(report['processProbe']['preflight']['complete'])
        self.assertGreater(report['measuredSingleRoundReadBytes'],0)
        self.assertIsNone(report['forecast12hBytes'])
        self.assertEqual('sqlite-online-readonly',report['databases'][0]['method'])
        self.assertFalse((self.root/'new').exists());self.assertFalse((self.root/'old').exists())
        for path,raw in before.items():self.assertEqual(raw,path.read_bytes())
        self.assertFalse(list(self.control.glob('.disabled-preflight-*')))
        self.assertEqual(1,len(list(self.control.glob('preflight-*.json'))))

    def test_false_absence_and_missing_required_state_reported(self):
        self.state.unlink();(self.db.parent/'absent.json').write_text('{}')
        report=live.run_preflight(self.dashboard,self.spec,self.control)
        self.assertEqual({'required_file_missing','declared_absence_exists'}, {x['code'] for x in report['missingPaths']})

    def test_private_state_rejected_without_recording_content(self):
        dump(self.state,{'password':'PRIVATE-CANARY'})
        with self.assertRaises(Exception):live.run_preflight(self.dashboard,self.spec,self.control)
        self.assertFalse(self.control.exists())

    def test_control_cannot_write_old_archive_or_new_evidence(self):
        for name in ('archivedRoot','evidenceRoot'):
            folder=Path(self.spec[name])/'control'
            with self.assertRaisesRegex(live.CaptureError,'preflight_control_overlap'):
                live.run_preflight(self.dashboard,self.spec,folder)
            self.assertFalse(folder.exists())

    def test_preflight_failure_cannot_break_original_health_or_lifespan(self):
        events=[]
        @asynccontextmanager
        async def original(app):
            events.append('start');yield;events.append('stop')
        app=FastAPI(lifespan=original)
        @app.get('/api/health')
        def health():return {'ok':True}
        dashboard=SimpleNamespace(app=app)
        self.control.mkdir()
        # Force preflight failure inside the optional worker, never the real app.
        def bad(*args):raise RuntimeError('PRIVATE-CANARY')
        with patch.object(live,'run_preflight',bad):
            live.configure(dashboard,{},'preflight',self.control)
            with TestClient(app) as client:
                self.assertEqual({'ok':True},client.get('/api/health').json())
                import time
                deadline=time.monotonic()+4
                while not list(self.control.glob('preflight-failed-*.json')) and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(list(self.control.glob('preflight-failed-*.json')))
                self.assertEqual(200,client.get('/api/health').status_code)
        self.assertEqual(['start','stop'],events)
        self.assertNotIn('PRIVATE-CANARY',''.join(p.read_text() for p in self.control.iterdir()))


class ProcessProbeTests(unittest.TestCase):
    def test_dynamic_identity_and_birth(self):
        report=probe_processes(fake_psutil(),agent_pid=os.getpid())
        self.assertTrue(report['preflight']['complete'])
        self.assertEqual([os.getpid()],report['processIds'])
        self.assertEqual(123.0,report['processRecords'][0]['create_time'])

    def test_missing_agent_not_complete(self):
        report=probe_processes(fake_psutil())
        self.assertFalse(report['preflight']['complete'])

    def test_private_argv_and_denied_fields_not_saved(self):
        for psutil in (fake_psutil(private=True),fake_psutil(denied=True)):
            report=probe_processes(psutil,agent_pid=os.getpid())
            self.assertEqual([],report['processRecords']);self.assertFalse(report['preflight']['complete'])
            self.assertNotIn('PRIVATE-CANARY',json.dumps(report))


if __name__=='__main__':unittest.main()
