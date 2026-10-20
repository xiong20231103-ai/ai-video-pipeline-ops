"""Real temp SQLite/threads, in-process HTTP and mock cloud; no installed services."""
import asyncio
import base64
from contextlib import contextmanager
import copy
from concurrent.futures import ThreadPoolExecutor,wait
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock,patch
from fastapi import HTTPException
from starlette.responses import JSONResponse,Response
from fastapi.testclient import TestClient
import app
from cleanup_tickets import CleanupTickets
from contracts.commands import command
from agent.execution import ExecutionWorker
from agent.readonly import ReadOnlyAgent
from agent.core.authority_lease import AuthorityLease
from agent.core.composed import ComposedSession
from agent.core.engine_host import EngineHost,CompatibilityApp
from agent.core.ordinary_fence import OrdinaryFence,FenceRejected
from agent.core.projection_store import durable_store
from agent.core.retirement_gate import RULES,switch_blockers,retirement_blockers,required_targets,pre_retirement_blockers


def projection_load(store,*,iterations=20,timeout=60):
    """Exercise real overlapping workers, then join BEFORE Store/temp cleanup.

    This is a correctness check, not a hosted-runner disk-speed benchmark.
    SQLite's per-operation busy timeout is 10 seconds; the old join(5) was
    shorter than one allowed operation and also raced cleanup on assertion.
    A deadline is still enforced; cancellation never turns it into a pass.
    """
    stop=threading.Event();progress=[0]*4;started=time.monotonic()
    def run(index):
        for i in range(iterations):
            if stop.is_set():return
            if index==0:store.event('fixture','INFO',str(i),{})
            else:store.events(10)
            progress[index]+=1
    executor=ThreadPoolExecutor(max_workers=4,thread_name_prefix='r6-projection-check')
    futures=[]
    try:
        futures=[executor.submit(run,index) for index in range(4)]
        _,pending=wait(futures,timeout=timeout)
        if pending:
            raise AssertionError(f'projection workload deadline exceeded: completed={progress}, elapsed={time.monotonic()-started:.3f}s')
        for future in futures:future.result()
        if progress!=[iterations]*4:raise AssertionError(f'projection workload incomplete: {progress}')
        return progress
    finally:
        stop.set()
        # Keep the Store alive through every in-flight operation, even when a
        # worker fails/deadline expires. Do not leave threads using a deleted DB.
        executor.shutdown(wait=True,cancel_futures=True)


class ProjectionLoadLifecycleTests(unittest.TestCase):
    def test_deadline_still_fails_and_waits_for_inflight_operations_before_return(self):
        entered=threading.Event();release=threading.Event();deadline=threading.Event();active=[];lock=threading.Lock()
        class SlowStore:
            def events(self,*args):
                with lock:active.append(threading.current_thread().name)
                try:entered.set();release.wait()
                finally:
                    with lock:active.remove(threading.current_thread().name)
            event=events
        outcome=[]
        def run():
            try:projection_load(SlowStore(),timeout=.05)
            except BaseException as error:outcome.append(error)
        def expired(futures,*,timeout):
            if not entered.wait(2):raise AssertionError('inert worker did not start')
            deadline.set();return set(),set(futures)
        caller=threading.Thread(target=run)
        with patch(__name__+'.wait',side_effect=expired):
            caller.start()
            try:
                self.assertTrue(deadline.wait(3))
                # Expiry is signalled explicitly; no scheduler-speed assumption.
                # The caller still waits for the active operation to be released.
                self.assertTrue(caller.is_alive());self.assertTrue(active)
            finally:release.set();caller.join(3)
        self.assertFalse(caller.is_alive());self.assertEqual([],active)
        self.assertEqual(1,len(outcome));self.assertIsInstance(outcome[0],AssertionError)
        self.assertIn('deadline exceeded',str(outcome[0]))

    def test_worker_error_is_not_swallowed_and_all_other_workers_exit(self):
        active=[];lock=threading.Lock()
        class FailedStore:
            def events(self,*args):
                with lock:active.append(threading.current_thread().name)
                try:raise OSError('inert connection failure')
                finally:
                    with lock:active.remove(threading.current_thread().name)
            event=events
        with self.assertRaisesRegex(OSError,'inert connection failure'):projection_load(FailedStore())
        self.assertEqual([],active)


def attestation_fixture(build,ledger):
    """Policy unit input only; never uploaded or described as real acceptance."""
    review=dict(schema=1,action='R6_SWITCH',build=build,ledgerId=ledger,approvedBy='isolated-test-reviewer',expiresAt=1300,
        commandsPaused=True,drained=True,leased=0,sent=0,unknown=0,unreconciledRecovery=0,
        legacyAutostartDisabled=True,stateImportVerified=True,autoRecoveryDisabled=True,cleanupEnabled=False,rollbackVerified=True,
        r5AcceptedAt='1969-01-01T00:00:00+00:00',r5ContinuousCandidateUse=True,
        r5NoRollbackDuringObservation=True,legacyAvailableThroughObservation=True)
    report={'schema':1,'build':build,'modules':{},'rules':{rule:dict(reviewed=True,positiveCases=1,negativeCases=1,mismatchCount=0) for rule in RULES}}
    for module in ('R0','R1','R2','R3','R4','R5'):
        targets=required_targets(module)
        report['modules'][module]=dict(mode='real-shadow',batchStarted=True,batchCompleted=True,batchId='isolated-policy-fixture',requiredTargets=targets,
            effectsOutsideScratch=0,businessRequests=0,windows=[dict(target=target,sourceIdentity='inert-source',candidateSourceIdentity='inert-source',comparable=True,caseCount=1,mismatchCount=0) for target in targets])
    return review,report


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r6-runtime-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.fence=OrdinaryFence(self.root/'fence',timeout=.1)
        state=self.fence.prepare()
        evidence=dict(commandsPaused=True,drained=True,leased=0,sent=0,unknown=0,legacyFenceInstalled=True,fullBatchShadowReviewed=True)
        self.fence.select('candidate',expected_id=state['fenceId'],confirmation='R3_OWNER_CHANGE_REVIEWED',evidence=evidence)
        self.proof=lambda:{**self.fence.status(),'protocol':1,'legacyWritesBlocked':True}
        self.lease=AuthorityLease(self.fence,self.proof)
        self.session=ComposedSession(vars(app),tickets=CleanupTickets())
        self.addCleanup(self.session.close)
        self.engine=EngineHost(self.session,self.lease,clock=lambda:1000)

    def test_durable_projection_reopens_without_overwrite_or_extra_tables(self):
        path=self.root/'engine'/'projection.db'
        with ComposedSession(vars(app),tickets=CleanupTickets(),store_factory=durable_store(path)) as session:
            session.store.event('fixture','INFO','isolated',{})
            rows=session.rows()
        with ComposedSession(vars(app),tickets=CleanupTickets(),store_factory=durable_store(path)) as session:
            self.assertEqual(rows,session.rows())
            with session.store.connection() as seed:
                with self.assertRaises(FileExistsError):
                    ComposedSession(vars(app),tickets=CleanupTickets(),seed=seed,store_factory=durable_store(path))
        self.assertEqual({'tasks','task_history','events','heartbeats','source_health','sqlite_sequence'},set(rows))

    def test_durable_projection_handles_real_concurrent_reads_and_short_writes(self):
        path=self.root/'projection.db'
        with ComposedSession(vars(app),tickets=CleanupTickets(),store_factory=durable_store(path)) as session:
            active=[];opened=[];lock=threading.Lock();connect=session.store.connect
            class TrackedConnection:
                def __init__(self,db):self.db=db
                def __getattr__(self,name):return getattr(self.db,name)
                def close(self):
                    self.db.close()
                    with lock:active.remove(self)
            def tracked_connect():
                result=TrackedConnection(connect())
                with lock:active.append(result);opened.append(result)
                return result
            with patch.object(session.store,'connect',side_effect=tracked_connect):
                self.assertEqual([20]*4,projection_load(session.store))
            self.assertEqual([],active);self.assertEqual(80,len(opened))
            self.assertEqual(20,len(session.store.events(100)))
        # Successful concurrent work must survive close/reopen, not merely leave
        # a count in an in-memory session. No database cleanup until all joined.
        with ComposedSession(vars(app),tickets=CleanupTickets(),store_factory=durable_store(path)) as reopened:
            self.assertEqual(20,len(reopened.store.events(100)))

    def test_nested_control_plane_callback_does_not_wait_for_its_own_owner_fence(self):
        result=[]
        with self.lease.guard():
            def callback():
                with self.lease.guard():result.append('callback-read')
            thread=threading.Thread(target=callback);thread.start();thread.join(1)
            self.assertFalse(thread.is_alive())
            with self.assertRaises(FenceRejected):self.fence.status()
        self.assertEqual(['callback-read'],result);self.assertEqual('candidate',self.fence.status()['owner'])

    def test_unknown_owner_or_missing_legacy_block_proof_refuses_reads_and_sends(self):
        self.lease.probe=lambda:{'protocol':1,'legacyWritesBlocked':False}
        with self.assertRaises(OSError):self.engine.get('/api/health')
        self.assertEqual({'kind':'not_sent','reason':'send_permit_denied'},self.engine.send(dict(target='/api/controls/upload/rescan',body={},expiresAt=1100)))

    def test_get_route_coercion_bounds_etag_and_error_semantics(self):
        calls=[]
        def events(limit=app.Query(30,ge=1,le=200)):
            calls.append(limit);return {'count':limit}
        self.engine.namespace['events']=events
        self.assertEqual((200,{'count':2},''),self.engine.get('/api/events?limit=2'))
        with self.assertRaises(OSError):self.engine.get('/api/events?limit=201')
        self.assertEqual([2],calls)
        legacy=TestClient(app.app)
        for value in ('201','0','not-an-int'):
            target='/api/events?limit='+value
            self.assertEqual(legacy.get(target).json(),json.loads(self.engine.get_response(target).body))
        self.engine.namespace['health']=lambda:Response(status_code=304,headers={'ETag':'fixture'})
        # Use an actual route's handler name instead of assuming the legacy name.
        row=next(x for x in self.engine.routes if x['path']=='/api/health')
        self.engine.namespace[row['handler']]=lambda:Response(status_code=304,headers={'ETag':'fixture'})
        self.assertEqual((304,None,'fixture'),self.engine.get('/api/health'))
        with self.assertRaises(ValueError):self.engine.get('http://outside.invalid/api/health')

    def test_loopback_compatibility_rejects_every_post_and_external_client(self):
        compatibility=CompatibilityApp(self.engine,'https://fixture.ts.net')
        client=TestClient(compatibility,client=('127.0.0.1',1000))
        self.assertEqual(307,client.get('/',follow_redirects=False).status_code)
        for target in ('/api/control-commands','/api/controls/continue-current','/api/controls/testing/reset','/api/controls/cloud-cleanup/execute'):
            self.assertEqual(405,client.post(target,json={}).status_code)
        external=TestClient(compatibility,client=('100.64.0.2',1000))
        self.assertEqual(403,external.get('/api/health').status_code)

    def test_existing_execution_ledger_remains_the_only_sender_after_lost_reply(self):
        agent=Mock();agent.state_dir=self.root/'agent';agent.stop=threading.Event()
        agent.lifecycle.stop_request.return_value=None;agent.cloud.return_value={'sendPermitted':True}
        agent.transport.open.side_effect=AssertionError('old Dashboard fallback forbidden')
        worker=ExecutionWorker(agent,ordinary_backend=self.engine);worker.clock=lambda:1000;worker.enabled=lambda:True
        target='/api/controls/upload/rescan';spec=command(target,{})
        job={**spec,'id':'isolated-r6-job','lease':'fixture-lease','ledgerId':worker.ledger.identity,'expiresAt':1100}
        with patch.object(self.engine,'_invoke',side_effect=OSError('lost reply')) as invoke:
            worker.process(job);worker.process(job)
            self.assertEqual(1,invoke.call_count)
        self.assertEqual('unknown',worker.ledger.pending()['state']);agent.transport.open.assert_not_called()

    def test_expected_target_and_cleanup_paths_use_candidate_without_fallback(self):
        body={'clientRequestId':'fixture_request_id_1234','expectedTarget':{'batchId':'b','taskId':'t','attemptId':'a'}}
        job={'target':'/api/control-commands','body':body,'expiresAt':1100}
        self.assertTrue(self.engine.supports(job['target']))
        self.assertEqual('not_sent',self.engine.send(job)['kind'])
        self.session.recovery_transport=object()
        with patch.object(self.engine,'_invoke',return_value=JSONResponse({'detail':'target mismatch'},status_code=409)) as invoke:
            result=self.engine.send(job)
            self.assertEqual(409,result['httpStatus']);self.assertEqual(body,invoke.call_args.args[2])
        for target in ('/api/controls/cloud-cleanup/preview','/api/controls/cloud-cleanup/execute'):
            self.assertTrue(self.engine.supports(target))
        self.assertFalse(self.engine.supports('/api/batches'))
        self.assertFalse(self.engine.supports('/api/controls/testing/reset'))

    def test_agent_injection_uses_same_backend_for_reads_and_existing_worker(self):
        agent=ReadOnlyAgent('https://fixture.ts.net','inert-fixture-token',self.root/'agent',engine=self.engine)
        agent.schedule.active=lambda:False
        self.assertIs(agent.execution.ordinary_backend,self.engine)
        with patch.object(self.engine,'get',return_value=(200,{'ok':True},'fixture')) as get,patch.object(agent.transport,'open',side_effect=AssertionError('no old Dashboard')):
            self.assertEqual((200,{'ok':True},'fixture'),agent.home('/api/health'))
            get.assert_called_once()


class RetirementEvidenceTests(unittest.TestCase):
    def test_r5_observation_precedes_final_activation_and_is_separate_from_retention(self):
        review=dict(r5AcceptedAt='1970-01-01T00:00:00+00:00',r5ContinuousCandidateUse=True,
            r5NoRollbackDuringObservation=True,legacyAvailableThroughObservation=True)
        self.assertTrue(pre_retirement_blockers(review,now=13*86400))
        self.assertEqual([],pre_retirement_blockers(review,now=14*86400))
        self.assertTrue(pre_retirement_blockers({**review,'r5NoRollbackDuringObservation':False},now=15*86400))
        self.assertTrue(pre_retirement_blockers({**review,'legacyAvailableThroughObservation':False},now=15*86400))
        # Existing post-R6 file retention fields cannot substitute the R5 gate.
        self.assertTrue(pre_retirement_blockers({'switchAcceptedAt':review['r5AcceptedAt'],
            'legacyFilesRetained':True},now=15*86400))
    def test_no_current_isolation_report_can_authorize_switch(self):
        for report in ({},{'mode':'isolated'},{'modules':{m:{'mode':'isolated'} for m in ('R0','R1','R2','R3','R4','R5')}}):
            self.assertTrue(switch_blockers({},report,build='fixture-build',ledger_id='fixture-ledger',now=1000))
        self.assertEqual(77,len(RULES));self.assertEqual(77,len(set(RULES)))
    def test_complete_attestation_shape_and_each_rule_boundary(self):
        review,report=attestation_fixture('fixture-build','fixture-ledger')
        self.assertEqual([],switch_blockers(review,report,build='fixture-build',ledger_id='fixture-ledger',now=1000))
        for rule in RULES:
            changed=copy.deepcopy(report);changed['rules'][rule]['negativeCases']=0
            self.assertIn('rule_not_accepted:'+rule,switch_blockers(review,changed,build='fixture-build',ledger_id='fixture-ledger',now=1000))
        for key,value in (('expiresAt',999),('expiresAt',float('nan')),('unknown',1),('cleanupEnabled',True),('ledgerId','different')):
            changed={**review,key:value}
            self.assertTrue(switch_blockers(changed,report,build='fixture-build',ledger_id='fixture-ledger',now=1000))
    def test_cannot_replace_real_shadow_with_isolation_or_narrowed_targets(self):
        review,report=attestation_fixture('fixture-build','fixture-ledger')
        for module in report['modules']:
            for key,value in (('mode','isolated'),('batchCompleted',False),('requiredTargets',['GET /api/health'])):
                changed=copy.deepcopy(report);changed['modules'][module][key]=value
                self.assertTrue(switch_blockers(review,changed,build='fixture-build',ledger_id='fixture-ledger',now=1000))
            changed=copy.deepcopy(report);changed['modules'][module]['windows'][0]['mismatchCount']=1
            self.assertTrue(switch_blockers(review,changed,build='fixture-build',ledger_id='fixture-ledger',now=1000))
    def test_two_week_retention_and_explicit_human_retirement_cannot_be_skipped(self):
        self.assertTrue(retirement_blockers({},now=2_000_000))
        review={key:True for key in ('continuousCandidateUse','noRollbackDuringObservation','legacyFilesRetained','oneCommandRollbackVerified','userRetirementApproved')}
        review['switchAcceptedAt']='1970-01-01T00:00:00+00:00'
        self.assertTrue(retirement_blockers(review,now=13*86400))
        self.assertEqual([],retirement_blockers(review,now=14*86400))
        review['legacyFilesRetained']=False
        self.assertTrue(retirement_blockers(review,now=15*86400))

    def test_missing_effect_counts_or_nontext_batch_cannot_authorize_switch(self):
        review,report=attestation_fixture('fixture-build','fixture-ledger')
        for field in ('effectsOutsideScratch','businessRequests'):
            for value in (None,False,'0',1):
                changed=copy.deepcopy(report)
                changed['modules']['R5'][field]=value
                self.assertIn('shadow_effect_evidence_missing:R5:'+field,
                    switch_blockers(review,changed,build='fixture-build',ledger_id='fixture-ledger',now=1000))
            changed=copy.deepcopy(report);del changed['modules']['R5'][field]
            self.assertTrue(switch_blockers(review,changed,build='fixture-build',ledger_id='fixture-ledger',now=1000))
        for value in (True,123,'   '):
            changed=copy.deepcopy(report);changed['modules']['R5']['batchId']=value
            self.assertIn('shadow_batch_identity_missing:R5',
                switch_blockers(review,changed,build='fixture-build',ledger_id='fixture-ledger',now=1000))
        for target in ('review','report'):
            changed_review=copy.deepcopy(review);changed_report=copy.deepcopy(report)
            (changed_review if target=='review' else changed_report)['schema']=True
            self.assertTrue(switch_blockers(changed_review,changed_report,build='fixture-build',ledger_id='fixture-ledger',now=1000))


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r6-bootstrap-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_absent_settings_preserve_legacy_but_invalid_settings_never_fall_back(self):
        from agent.engine_runtime import configured_engine
        state=self.root/'agent';state.mkdir()
        self.assertIsNone(configured_engine(state,'https://fixture.ts.net'))
        for raw in ('not json',json.dumps({'schema':1,'enabled':False})):
            (state/'engine-settings.json').write_text(raw)
            engine=configured_engine(state,'https://fixture.ts.net');self.assertIsNotNone(engine)
            engine.activate();self.assertIsNone(engine.host)
            with self.assertRaises(OSError):engine.get('/api/health')
            self.assertEqual('not_sent',engine.send({'target':'/api/controls/upload/rescan','body':{}})['kind'])
            self.assertFalse(json.loads((state/'engine-runtime.json').read_text())['legacyFallback'])
    def test_state_inventory_is_whitelisted_and_omissions_corruption_and_paths_refuse(self):
        from agent.engine_runtime import state_inventory,verify_state_import
        (self.root/'control-commands').mkdir();(self.root/'control-commands'/'inert.json').write_text('{}')
        (self.root/'config.json').write_text('{"password":"inert-fixture-only"}')
        inventory=state_inventory(self.root)
        self.assertEqual(['control-commands/inert.json'],[row['path'] for row in inventory])
        manifest={'schema':1,'complete':True,'files':inventory};verify_state_import(self.root,manifest)
        with self.assertRaisesRegex(ValueError,'unlisted_file'):verify_state_import(self.root,{'schema':1,'complete':True,'files':[]})
        for path in ('../outside.json','config.json','C:/outside.json','control-commands/../config.json'):
            with self.assertRaises(ValueError):verify_state_import(self.root,{'schema':1,'complete':True,'files':[{'path':path,'sha256':'0'*64}]})
        (self.root/'control-commands'/'inert.json').write_text('{"changed":true}')
        with self.assertRaisesRegex(ValueError,'digest_mismatch'):verify_state_import(self.root,manifest)
    def test_reviewed_initialization_and_same_build_resume_preserve_existing_ledger(self):
        """Construct native engine with mocked process/tasks and inert RC module.

        No listener/thread is started and no production acceptance is generated.
        """
        import hashlib
        from agent.engine_runtime import DeferredEngine,SETTINGS
        from agent.execution import ExecutionLedger
        def write(path,value):
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(value),encoding='utf-8')
            return hashlib.sha256(path.read_bytes()).hexdigest()
        state=self.root/'agent';state.mkdir();ledger=ExecutionLedger(state/'execution.db')
        legacy=self.root/'legacy';(legacy/'data').mkdir(parents=True)
        workbench=self.root/'workbench';workbench.mkdir()
        module=workbench/'recovery_control.py'
        module.write_text("class RecoveryControl:\n def __init__(self,*args):pass\n def request_capabilities(self):return {'protocol':2,'expiryChecked':True,'cancelUnderAuthorityLock':True}\n")
        owned=self.root/'engine';owned.mkdir();manifest=self.root/'state-import.json'
        manifest_digest=write(manifest,{'schema':1,'complete':True,'files':[]})
        seed=self.root/'seed.db'
        with ComposedSession(vars(app),tickets=CleanupTickets(),store_factory=durable_store(seed)) as session:
            session.store.event('fixture','INFO','seed preserved',{})
        seed_digest=hashlib.sha256(seed.read_bytes()).hexdigest()
        fence=OrdinaryFence(self.root/'fence');fence_state=fence.prepare()
        fence.select('candidate',expected_id=fence_state['fenceId'],confirmation='R3_OWNER_CHANGE_REVIEWED',
            evidence=dict(commandsPaused=True,drained=True,leased=0,sent=0,unknown=0,legacyFenceInstalled=True,fullBatchShadowReviewed=True))
        config=self.root/'private-config.json'
        config_digest=write(config,{'simulation_enabled':False,'workbench_dir':str(workbench)})
        review,report=attestation_fixture('f'*64,ledger.identity)
        from agent.core.transition import digest as transition_digest
        marker=dict(schema=1,stage='R5',phase='active',build='f'*64,ledgerId=ledger.identity,
            installedModules=['R0','R1','R2','R3','R4','R5'],sharedState=True,legacyRetired=False,
            acceptedAt=review['r5AcceptedAt'],planSha256='isolated-plan')
        write(state/'migration/active.json',marker)
        review['migrationSha256']=transition_digest(marker)
        report_path=self.root/'shadow.json';report_digest=write(report_path,report)
        review_path=self.root/'review.json'
        settings=dict(schema=1,enabled=True,stateRoot=str(owned),legacyRoot=str(legacy),
            legacyScripts=[str(legacy/'app.py')],legacyTasks=[{'name':'inert-old-task','path':'\\'}],
            reviewFile=str(review_path),shadowReport=str(report_path),stateManifest=str(manifest),
            fenceRoot=str(self.root/'fence'),opsConfig=str(config),recoveryModule=str(module),
            recoveryModuleSha256=hashlib.sha256(module.read_bytes()).hexdigest(),recoveryControlDir=str(workbench/'handoff/control'),
            seedDatabase=str(seed),seedSha256=seed_digest)
        self.assertEqual(SETTINGS,set(settings))
        settings_digest=hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        review.update(fenceId=fence_state['fenceId'],settingsSha256=settings_digest,opsConfigSha256=config_digest,
            shadowSha256=report_digest,stateManifestSha256=manifest_digest,seedSha256=seed_digest,recoveryModuleSha256=settings['recoveryModuleSha256'])
        write(review_path,review);write(state/'engine-settings.json',settings)
        with patch('agent.engine_runtime.build_digest',return_value='f'*64),patch('agent.engine_runtime.legacy_tasks_disabled',return_value=True),patch('agent.engine_runtime.legacy_processes_stopped',return_value=True),patch('agent.engine_runtime.time.time',return_value=1000):
            engine=DeferredEngine(state,'https://fixture.ts.net');engine.activate()
            self.assertIsNotNone(engine.host,json.loads((state/'engine-runtime.json').read_text()))
            self.assertFalse(engine.ready.is_set());self.assertFalse(engine.session.valid)
            self.assertEqual('seed preserved',engine.session.store.events(1)[0]['message'])
            engine.session.close()
        with patch('agent.engine_runtime.build_digest',return_value='f'*64),patch('agent.engine_runtime.legacy_tasks_disabled',return_value=True),patch('agent.engine_runtime.legacy_processes_stopped',return_value=True),patch('agent.engine_runtime.time.time',return_value=100000):
            resumed=DeferredEngine(state,'https://fixture.ts.net');resumed.activate()
            self.assertIsNotNone(resumed.host);resumed.session.close()
            self.assertEqual(ledger.identity,ExecutionLedger(state/'execution.db').identity)
            write(config,{'password':'inert-value-must-not-be-logged'})
            refused=DeferredEngine(state,'https://fixture.ts.net');refused.activate();self.assertIsNone(refused.host)
            self.assertNotIn('inert-value-must-not-be-logged',(state/'engine-runtime.json').read_text())
    def test_r6_package_whitelist_matches_build_inputs_and_includes_runtime_ports(self):
        from deploy.agent_source_update import R6_FILES
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(len(R6_FILES),len(set(R6_FILES)))
        for prefix in ('agent','contracts'):
            expected={p.relative_to(root).as_posix() for p in (root/prefix).rglob('*') if p.suffix in {'.py','.json'} and '__pycache__' not in p.parts}
            self.assertTrue(expected.issubset(set(R6_FILES)),expected-set(R6_FILES))
