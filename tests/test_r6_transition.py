"""Policy fixtures and temp-only retained-host dispatch. No production clients."""
import base64
from contextlib import contextmanager
import copy
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import types
import unittest
from unittest.mock import Mock,patch
from urllib.parse import urlsplit
from urllib.response import addinfourl
from fastapi import FastAPI,Request
from fastapi.testclient import TestClient
import app
from contracts.commands import command
from contracts.state_files import atomic_json,read_json
from agent.execution import ExecutionLedger,ExecutionWorker
from agent.legacy_host import LegacyRecoveryApp,make_app
from agent.staged_runtime import StagedBackend
from agent.core.dispatch_claim import DispatchClaims,DispatchRejected
from agent.core.transition import Transition,digest
from agent.core.retirement_gate import RULES,required_targets
from agent.core.ordinary_fence import OrdinaryFence
from agent.core.transition import r5_record


def policy_fixture(root,stage,previous=None,now=1000):
    # This is explicitly a policy unit shape, not real batch acceptance.
    report={'schema':1,'build':'inert-build','modules':{},'rules':{r:dict(reviewed=True,positiveCases=1,negativeCases=1,mismatchCount=0) for r in RULES}}
    for module in ('R0','R1','R2','R3','R4','R5'):
        targets=required_targets(module)
        report['modules'][module]=dict(mode='real-shadow',batchStarted=True,batchCompleted=True,batchId='isolated-policy-fixture',
            requiredTargets=targets,effectsOutsideScratch=0,businessRequests=0,windows=[dict(target=t,sourceIdentity='inert',candidateSourceIdentity='inert',comparable=True,caseCount=1,mismatchCount=0) for t in targets])
    path=root/('report-'+stage+'.json');path.write_text(json.dumps(report))
    detail=dict(schema=1,stage=stage,build='inert-build',ledgerId='inert-ledger',approvedBy='unit-fixture',
        expiresAt=now+300,previousSha256=digest(previous) if previous else None,
        shadowReport=str(path),shadowSha256=hashlib.sha256(path.read_bytes()).hexdigest(),historyReadyVerified=True,
        commandsPaused=True,drained=True,leased=0,sent=0,unknown=0,unreconciledRecovery=0,
        autoRecoveryDisabled=True,cleanupEnabled=False,rollbackVerified=True,controlPlaneWriterDisabled=True,legacyFallbacksFenced=True)
    return {'agentState':str(root/'agent'),'transition':detail}


class TransitionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r6-transition-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
    def load(self,plan,now=1000):return Transition(plan,build='inert-build',ledger_id='inert-ledger',clock=lambda:now)
    def commit(self,transition):
        # Bind behavior is tested separately. This shape never starts a service.
        transition.installed={'isolatedPolicyFixture':True};return transition.commit()
    def test_final_retirement_binds_persisted_r5_identity_and_cannot_backdate_it(self):
        state=self.root/'agent';marker=state/'migration/active.json'
        record=dict(schema=1,stage='R5',phase='active',build='build',ledgerId='ledger',
            installedModules=['R0','R1','R2','R3','R4','R5'],sharedState=True,legacyRetired=False,
            acceptedAt='2026-01-01T00:00:00+00:00')
        atomic_json(marker,record)
        review=dict(migrationSha256=digest(record),r5AcceptedAt=record['acceptedAt'])
        self.assertEqual(record,r5_record(state,review,build='build',ledger_id='ledger'))
        for key,value in (('stage','R4'),('phase','prepared'),('build','other'),('ledgerId','other'),
                          ('installedModules',['R5']),('acceptedAt','2025-01-01T00:00:00+00:00')):
            atomic_json(marker,{**record,key:value})
            with self.assertRaises(ValueError):r5_record(state,review,build='build',ledger_id='ledger')
        atomic_json(marker,record)
        with self.assertRaises(ValueError):r5_record(state,{**review,'r5AcceptedAt':'2025-01-01T00:00:00+00:00'},build='build',ledger_id='ledger')
    def test_stage_prefix_cold_restart_and_real_health_start_observation(self):
        previous=None
        for stage in ('R0','R1','R2','R3','R4','R5'):
            plan=policy_fixture(self.root,stage,previous)
            selected=self.load(plan);previous=self.commit(selected)
            self.assertIsNone(previous['acceptedAt']);self.assertEqual('prepared',previous['phase'])
            ready=selected.ready();self.assertEqual('active',ready['phase']);self.assertIsNotNone(ready['acceptedAt'])
            resumed=self.load(plan,now=100000)
            self.assertTrue(resumed.resuming);self.assertEqual(ready,self.commit(resumed))
            previous=ready
        self.assertEqual(6,len(previous['installedModules']))

    def test_real_temp_legacy_factory_and_staged_agent_resume_without_new_collector(self):
        # Load an exact copy of the reviewed app into a new temp repository.
        # Neither TestClient lifespan nor any collector/listener is started.
        legacy=self.root/'legacy';legacy.mkdir();(legacy/'static').mkdir()
        source=Path(app.__file__).read_bytes();(legacy/'app.py').write_bytes(source)
        workbench=self.root/'workbench';workbench.mkdir()
        module=workbench/'recovery_control.py'
        module.write_text("class RecoveryControl:\n def __init__(self,*args):pass\n def request_capabilities(self):return {'protocol':2,'expiryChecked':True,'cancelUnderAuthorityLock':True}\n")
        config=dict(app.CONFIG,workbench_dir=str(workbench))
        (legacy/'config.json').write_text(json.dumps(config))
        state=self.root/'agent';ledger=ExecutionLedger(state/'execution.db')
        fence=OrdinaryFence(self.root/'fence');owner=fence.prepare()
        plan=policy_fixture(self.root,'R0');plan['transition']['ledgerId']=ledger.identity
        plan.update(schema=1,action='R6_LEGACY_START',legacyRoot=str(legacy),
            fenceRoot=str(self.root/'fence'),fenceId=owner['fenceId'],
            legacyAppSha256=hashlib.sha256(source).hexdigest(),recoveryModule=str(module),
            recoveryModuleSha256=hashlib.sha256(module.read_bytes()).hexdigest(),
            recoveryControlDir=str(workbench/'handoff/control'))
        import time
        plan['transition']['expiresAt']=time.time()+300
        with patch('agent.engine_runtime.build_digest',return_value='inert-build'):
            wrapper,_=make_app(plan)
        collector=wrapper.namespace['COLLECTOR']
        self.assertIsNone(collector.thread)
        self.assertIs(wrapper.namespace['STORE'],collector.store)
        self.assertIsNotNone(wrapper.dispatcher)
        client=TestClient(wrapper)
        self.assertEqual(403,client.post('/api/control-commands',json={}).status_code)
        self.assertIsNone(collector.thread)
        path=self.root/'legacy-plan.json';path.write_text(json.dumps(plan))
        atomic_json(state/'migration-settings.json',dict(schema=1,plan=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        backend=StagedBackend(state)
        with patch('agent.engine_runtime.build_digest',return_value='inert-build'):backend.activate()
        self.assertIsNotNone(backend.transition)
        agent=Mock();backend.bind_agent(agent)
        reply=io.BytesIO(b'{"ok":true,"collectorRunning":true}');reply.status=200;reply.headers={}
        agent.transport.open.return_value=reply
        self.assertTrue(backend.available());self.assertEqual(200,backend.get('/api/health')[0])
        self.assertEqual('active',read_json(state/'migration/active.json')['phase'])
        path.write_text('{}')
        self.assertFalse(backend.available())
        atomic_json(state/'engine-settings.json',{})
        from agent.engine_runtime import configured_engine
        conflict=configured_engine(state,'https://fixture.ts.net');conflict.activate()
        self.assertIsNone(conflict.transition)
    def test_skip_malformed_shadow_and_unsafe_queue_are_refused(self):
        with self.assertRaisesRegex(ValueError,'skip_forbidden'):self.load(policy_fixture(self.root,'R5'))
        plan=policy_fixture(self.root,'R0')
        for key,value in (('unknown',1),('expiresAt',999),('cleanupEnabled',True),('controlPlaneWriterDisabled',False)):
            changed=copy.deepcopy(plan);changed['transition'][key]=value
            with self.assertRaises(ValueError):self.load(changed)
        path=Path(plan['transition']['shadowReport']);report=json.loads(path.read_text());report['modules']['R0']['mode']='isolated';path.write_text(json.dumps(report))
        plan['transition']['shadowSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'real_shadow_incomplete'):self.load(plan)
    def test_rollback_resets_r5_clock_and_cannot_reuse_previous_approval(self):
        previous=None
        for stage in ('R0','R1','R2','R3','R4','R5'):
            plan=policy_fixture(self.root,stage,previous);transition=self.load(plan);self.commit(transition);previous=transition.ready()
        rollback=policy_fixture(self.root,'R4',previous,now=2000)
        with self.assertRaisesRegex(ValueError,'skip_forbidden'):self.load(rollback,now=2000)
        rollback['transition']['rollbackApproved']=True
        transition=self.load(rollback,now=2000);self.commit(transition);previous=transition.ready()
        replacement=policy_fixture(self.root,'R5',previous,now=3000)
        transition=self.load(replacement,now=3000);self.commit(transition);new=transition.ready()
        self.assertNotEqual(new['acceptedAt'],'1970-01-01T00:16:40+00:00')
        with self.assertRaises(ValueError):self.load(plan,now=4000)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r6-admission-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.ledger=ExecutionLedger(self.root/'execution.db')
        self.admission=DispatchClaims(self.ledger.path,self.ledger.identity,clock=lambda:1000);self.admission.initialize()
        spec=command('/api/controls/upload/rescan',{})
        self.job={**spec,'id':'inert-dispatch','lease':'inert-lease','ledgerId':self.ledger.identity,'expiresAt':2000}
        self.ledger.receive(self.job);self.ledger.sent(self.job['id'])
    def test_sent_before_cloud_start_is_not_a_home_send_permit(self):
        with self.assertRaisesRegex(DispatchRejected,'send_permit_missing'):
            self.admission.claim(self.job['id'],self.ledger.identity,self.job['target'],{})
        self.admission.grant(self.job)
        self.admission.claim(self.job['id'],self.ledger.identity,self.job['target'],{})
        with self.assertRaisesRegex(DispatchRejected,'already_dispatched'):
            self.admission.claim(self.job['id'],self.ledger.identity,self.job['target'],{})
    def test_wrong_identity_body_expiry_or_acknowledgement_never_claims(self):
        self.admission.grant(self.job)
        for identity,target,body in [('wrong',self.job['target'],{}),(self.ledger.identity,'/api/controls/upload/verify-history',{}),
            (self.ledger.identity,self.job['target'],{'bad':True})]:
            with self.assertRaises(DispatchRejected):self.admission.claim(self.job['id'],identity,target,body)
        self.admission.clock=lambda:2000
        with self.assertRaisesRegex(DispatchRejected,'expired'):self.admission.claim(self.job['id'],self.ledger.identity,self.job['target'],{})
        self.admission.clock=lambda:1000;self.ledger.acknowledge(self.job['id'])
        with self.assertRaises(DispatchRejected):self.admission.claim(self.job['id'],self.ledger.identity,self.job['target'],{})
    def application(self):
        self.calls=[];application=FastAPI()
        @application.post('/api/controls/upload/rescan')
        async def post(request:Request):
            body=await request.json();self.calls.append(body);return {'accepted':True}
        controller=Mock();controller.request_capabilities.return_value=dict(protocol=2,expiryChecked=True,cancelUnderAuthorityLock=True)
        @contextmanager
        def guard():yield
        lease=Mock();lease.guard=guard
        return TestClient(LegacyRecoveryApp(application,{},controller,lease,dispatcher=self.admission))
    def test_retained_http_refuses_control_plane_post_and_admits_one_agent_post(self):
        client=self.application()
        self.assertEqual(403,client.post(self.job['target'],json={}).status_code)
        headers={'X-Ops-Execution-Id':self.job['id'],'X-Ops-Execution-Ledger':self.ledger.identity}
        self.assertEqual(403,client.post(self.job['target'],headers=headers,json={}).status_code)
        self.assertEqual([],self.calls)
        self.admission.grant(self.job)
        self.assertEqual(200,client.post(self.job['target'],headers=headers,json={}).status_code)
        self.assertEqual(409,client.post(self.job['target'],headers=headers,json={}).status_code)
        self.assertEqual([{}],self.calls)
    def test_existing_worker_cloud_permit_then_lost_reply_never_sends_twice(self):
        client=self.application();agent=Mock();agent.state_dir=self.root;agent.stop=threading.Event()
        agent.lifecycle.stop_request.return_value=None;agent.cloud.return_value={'sendPermitted':True}
        backend=StagedBackend(self.root);backend.bind_agent(agent)
        backend.transition=types.SimpleNamespace(identity=self.ledger.identity)
        opened=[]
        def open_request(request,timeout):
            opened.append(request.full_url)
            reply=client.post(urlsplit(request.full_url).path,headers=dict(request.header_items()),content=request.data)
            self.assertEqual(200,reply.status_code)
            raise OSError('inert reply loss after execution')
        agent.transport.open.side_effect=open_request
        worker=ExecutionWorker(agent,ordinary_backend=backend);worker.clock=lambda:1000;worker.enabled=lambda:True
        # Use the existing instance so constructing a second ledger does not
        # correctly classify our fixture's already-sent row as crash recovery.
        worker._ledger=self.ledger
        with self.ledger.db() as db:db.execute("UPDATE executions SET state='received' WHERE id=?",(self.job['id'],))
        with patch.object(backend,'available',return_value=True),patch('agent.staged_runtime.DispatchClaims',return_value=self.admission):
            worker.process(self.job);worker.process(self.job)
        self.assertEqual(1,len(opened));self.assertEqual([{}],self.calls)
        self.assertEqual('unknown',self.ledger.pending()['state'])
