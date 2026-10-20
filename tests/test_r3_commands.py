import ast
import asyncio
import base64
import copy
import hashlib
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from starlette.responses import JSONResponse
from agent.core import ordinary, ordinary_logic
from agent.core.ordinary_fence import OrdinaryFence, FenceRejected
from agent.core.ordinary_ingress import FencedDashboard, CAPABILITY, SHARED_LEGACY_WRITES
from agent.execution import ExecutionLedger, ExecutionWorker
from contracts.commands import command
from tools.r3_command_replay import ROOT, ROUTES, CaseEnvironment, FrozenDateTime, replay_case


class R3TestCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='r3-isolated-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    @staticmethod
    def evidence():
        return dict(commandsPaused=True, drained=True, leased=0, sent=0, unknown=0,
                    legacyFenceInstalled=True, fullBatchShadowReviewed=True)

    def fence(self, owner='candidate'):
        fence = OrdinaryFence(self.root/'fence', timeout=.03)
        state = fence.prepare()
        if owner == 'candidate':
            fence.select(owner, expected_id=state['fenceId'], confirmation='R3_OWNER_CHANGE_REVIEWED', evidence=self.evidence())
        return fence

    def candidate(self, fence=None, probe=None):
        case = dict(id='fixture', target='/api/controls/tasks/fixture/start', body={}, scenario='ok')
        env = CaseEnvironment(self.root/('ports-'+str(len(list(self.root.iterdir())))), case)
        fence = fence or self.fence()
        def proof():
            state = fence.status()
            return dict(protocol=1, fenceId=state['fenceId'], owner=state['owner'], legacyWritesBlocked=state['owner']=='candidate')
        return ordinary.OrdinaryCommands(env.ports, fence=fence, fence_probe=probe or proof, clock=lambda:1000)


class ReplayTests(R3TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT/'app.py').read_text(encoding='utf-8')
        cls.cases = json.loads((ROOT/'tests/fixtures/r3/cases.json').read_text(encoding='utf-8'))
        cls.expected = json.loads((ROOT/'tests/fixtures/r3/expected.json').read_text(encoding='utf-8'))

    def test_all_63_frozen_responses_files_events_and_operation_plans_match(self):
        self.assertEqual(63, len(self.cases))
        for i, case in enumerate(self.cases):
            with self.subTest(case=case['id']):
                old = replay_case(self.source, case, self.root/str(i)/'old')
                new = replay_case(self.source, case, self.root/str(i)/'new', candidate=True)
                self.assertEqual(self.expected[case['id']], old)
                self.assertEqual(old, new)
                self.assertFalse(new['realShadowPassed'])
                self.assertFalse(new['switchAccepted'])

    def test_all_bodies_match_pinned_originals_and_provenance_lines(self):
        provenance = json.loads((ROOT/'docs/migration/r3-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['legacySha256'], hashlib.sha256(self.source.encode()).hexdigest())
        original = {n.name:n for n in ast.parse(self.source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        candidate = {n.name:n for n in ast.parse(Path(ordinary_logic.__file__).read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        self.assertEqual(set(candidate), {row['name'] for row in provenance['functions']})
        for row in provenance['functions']:
            old = copy.deepcopy(original[row['name']]); old.decorator_list = []
            new = candidate[row['name']]
            self.assertEqual(ast.dump(old,include_attributes=False), ast.dump(new,include_attributes=False), row['name'])
            self.assertEqual((old.lineno,old.end_lineno),(row['legacyStart'],row['legacyEnd']))
            self.assertEqual((new.lineno,new.end_lineno),(row['candidateStart'],row['candidateEnd']))

    def test_mutated_receiver_result_is_detected(self):
        case = self.cases[0]
        old = replay_case(self.source,case,self.root/'old')
        original = ordinary.OrdinaryCommands.__init__
        def changed(instance,*args,**kwargs):
            original(instance,*args,**kwargs)
            instance.namespace['receiver_json'] = lambda *args,**kwargs:{'fixtureMutation':True}
        with patch.object(ordinary.OrdinaryCommands,'__init__',changed):
            new = replay_case(self.source,case,self.root/'new',candidate=True)
        self.assertNotEqual(old,new)

    def test_upload_request_remains_when_service_cannot_start(self):
        value = self.expected['verify-worker-missing']
        self.assertEqual(503,value['response']['status'])
        files = value['after']['files']
        self.assertIn('workbench/handoff/upload/historical_cloud_verify_request.json',files)
        self.assertEqual('failed',files['data/control_actions.json']['historicalCloudVerification']['state'])

    def test_rescan_backlog_dedup_and_missing_output_counts(self):
        value = self.expected['rescan-backlog']
        self.assertEqual((1,1),(value['response']['body']['candidates'],value['response']['body']['missing']))
        self.assertEqual(1,len(value['after']['launches']))

    def test_running_verification_does_not_overwrite_or_spawn_again(self):
        value = self.expected['verify-already-verifying']
        self.assertEqual('existing-verification',value['response']['body']['commandId'])
        self.assertEqual([],value['after']['launches'])
        self.assertNotIn('workbench/handoff/upload/historical_cloud_verify_request.json',value['after']['files'])

    def test_replay_refuses_changed_source_and_reused_scratch(self):
        case = self.cases[0]
        with self.assertRaisesRegex(ValueError,'source_hash'):
            replay_case(self.source+'\n',case,self.root/'bad',candidate=True)
        replay_case(self.source,case,self.root/'old')
        with self.assertRaisesRegex(ValueError,'scratch_must_be_new'):
            replay_case(self.source,case,self.root/'old')

    def test_replay_local_timezone_is_fixed_even_after_explicit_utc_conversion(self):
        from datetime import timezone
        value = FrozenDateTime.now(timezone.utc)
        self.assertEqual('2026-10-20T04:00:00+00:00',value.isoformat())
        self.assertEqual('2026-10-20T12:00:00+08:00',value.astimezone().isoformat())


class CandidateTests(R3TestCase):
    def test_allowlist_excludes_recovery_cleanup_reset_and_receiver(self):
        for _,target in ROUTES:self.assertTrue(ordinary.OrdinaryCommands.supports(target),target)
        for target in ('/api/batches','/api/control-commands','/api/controls/continue-current',
                       '/api/controls/cloud-cleanup/execute','/api/controls/testing/reset',
                       '/api/controls/tasks/%2e%2e/start','https://fixture.invalid/api/controls/upload/rescan'):
            self.assertFalse(ordinary.OrdinaryCommands.supports(target),target)

    def test_ports_and_isolated_evaluation_require_opt_in(self):
        with self.assertRaisesRegex(ValueError,'missing_ordinary_ports'):ordinary.OrdinaryCommands({})
        with self.assertRaisesRegex(ValueError,'isolated_evaluation_only'):
            self.candidate().evaluate_isolated('/api/controls/upload/rescan',{})

    def test_invalid_proof_never_invokes_or_falls_back(self):
        fence = self.fence()
        for proof in (None,{},dict(protocol=1,fenceId='wrong',owner='candidate',legacyWritesBlocked=True),
                      dict(protocol=1,fenceId=fence.status()['fenceId'],owner='legacy',legacyWritesBlocked=False)):
            candidate = self.candidate(fence=fence,probe=lambda:proof)
            with patch.object(ordinary,'invoke',side_effect=AssertionError('must not execute')):
                result = candidate.send(dict(target='/api/controls/tasks/fixture/start',body={},expiresAt=1100))
            self.assertEqual(dict(kind='not_sent',reason='send_permit_denied'),result)

    def test_invalid_or_expired_deadlines_never_invoke(self):
        candidate = self.candidate()
        for expires in (None,True,'1100',999,1000,float('inf'),float('nan')):
            with patch.object(ordinary,'invoke',side_effect=AssertionError('must not execute')):
                result = candidate.send(dict(target='/api/controls/tasks/fixture/start',body={},expiresAt=expires))
            self.assertEqual(dict(kind='not_sent',reason='invalid_or_expired'),result)

    def test_each_route_keeps_200_400_409_500_final_http_receipts(self):
        candidate = self.candidate()
        for _,target in ROUTES:
            for code in (200,400,409,500):
                async def reply(*args,**kwargs):return JSONResponse({'fixtureStatus':code},status_code=code)
                with patch.object(ordinary,'invoke',side_effect=reply) as invoked:
                    result = candidate.send(dict(target=target,body={},expiresAt=1100))
                self.assertEqual(code,result['httpStatus'])
                self.assertEqual({'fixtureStatus':code},json.loads(base64.b64decode(result['bodyBase64'])))
                invoked.assert_called_once()

    def test_lost_and_oversized_result_are_unknown(self):
        candidate = self.candidate()
        with patch.object(ordinary,'invoke',side_effect=OSError('lost reply')) as invoked:
            result = candidate.send(dict(target='/api/controls/upload/rescan',body={},expiresAt=1100))
        self.assertEqual(dict(kind='unknown',reason='transport_uncertain'),result)
        invoked.assert_called_once()
        async def huge(*args):return JSONResponse({'body':'x'*(ordinary.MAX_REPLY+1)})
        with patch.object(ordinary,'invoke',side_effect=huge):
            self.assertEqual('unknown',candidate.send(dict(target='/api/controls/upload/rescan',body={},expiresAt=1100))['kind'])

    def test_source_has_no_app_import_or_top_level_launch(self):
        tree = ast.parse(Path(ordinary_logic.__file__).read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                self.assertNotEqual('app',getattr(node,'module',None))
                self.assertFalse(any(alias.name=='app' for alias in node.names))
            if isinstance(node,(ast.Assign,ast.AnnAssign,ast.Expr)):
                self.assertFalse(any(isinstance(item,ast.Call) for item in ast.walk(node)))


class DurableExecutorTests(R3TestCase):
    def worker(self,backend):
        agent = Mock(); agent.state_dir = self.root/'state'; agent.stop = threading.Event()
        agent.lifecycle.stop_request.return_value = None
        agent.cloud.return_value = dict(sendPermitted=True)
        agent.transport.open.side_effect = AssertionError('legacy fallback forbidden')
        worker = ExecutionWorker(agent,ordinary_backend=backend)
        worker.clock = lambda:1000; worker.enabled = lambda:True
        return worker,agent

    def job(self,worker,target,identifier):
        return dict(id=identifier,lease='b'*32,ledgerId=worker.ledger.identity,expiresAt=1100,**command(target,{}))

    def test_each_duplicate_and_new_lease_keep_one_execution(self):
        worker,agent = self.worker(self.candidate())
        async def reply(*args):return {'accepted':True}
        for i,(_,target) in enumerate(ROUTES):
            job = self.job(worker,target,'command-'+str(i))
            with patch.object(ordinary,'invoke',side_effect=reply) as invoked:
                worker.process(job); worker.process(dict(job,lease='c'*32)); invoked.assert_called_once()
        agent.transport.open.assert_not_called()

    def test_timeout_only_retries_result_upload_restart_does_not_send(self):
        worker,agent = self.worker(self.candidate())
        job = self.job(worker,'/api/controls/tasks/fixture/start','unknown-command')
        with patch.object(ordinary,'invoke',side_effect=TimeoutError('fixture')) as invoked:
            worker.process(job); worker.process(job)
            self.assertEqual('unknown',json.loads(worker.ledger.pending()['result'])['kind'])
            agent.cloud.return_value = {}
            with self.assertRaisesRegex(ValueError,'acknowledgement'):worker.flush()
            self.assertIsNotNone(worker.ledger.pending())
            agent.cloud.return_value = {'recorded':True}; worker.flush()
            worker._ledger = ExecutionLedger(worker.ledger.path); worker.process(job)
            invoked.assert_called_once()
        agent.transport.open.assert_not_called()

    def test_sent_crash_for_each_route_is_unknown_without_reexecution(self):
        worker,agent = self.worker(self.candidate())
        for i,(_,target) in enumerate(ROUTES):
            job = self.job(worker,target,'crash-'+str(i))
            worker.ledger.receive(job); worker.ledger.sent(job['id'])
            worker._ledger = ExecutionLedger(worker.ledger.path)
            with patch.object(ordinary,'invoke',side_effect=AssertionError('must not execute')):worker.process(job)
            with worker.ledger.db() as db:row=db.execute('SELECT result FROM executions WHERE id=?',(job['id'],)).fetchone()
            self.assertEqual('restart_after_send',json.loads(row['result'])['reason'])
        agent.transport.open.assert_not_called()

    def test_identity_conflict_and_denied_permit_never_call_candidate(self):
        worker,agent = self.worker(self.candidate())
        job = self.job(worker,'/api/controls/tasks/fixture/start','denied-command')
        with patch.object(ordinary,'invoke',side_effect=AssertionError('must not execute')):
            worker.process(dict(job,ledgerId='wrong-ledger'))
            agent.cloud.return_value = {'sendPermitted':False}; worker.process(job)
        agent.transport.open.assert_not_called()
        self.assertEqual('send_permit_denied',json.loads(worker.ledger.pending()['result'])['reason'])

    def test_fence_denial_never_falls_back_to_old_dashboard(self):
        worker,agent = self.worker(self.candidate(fence=self.fence('legacy')))
        worker.process(self.job(worker,'/api/controls/upload/rescan','legacy-owner'))
        self.assertEqual('not_sent',json.loads(worker.ledger.pending()['result'])['kind'])
        agent.transport.open.assert_not_called()

    def test_default_worker_has_no_candidate_or_new_database(self):
        agent = Mock(); agent.state_dir = self.root/'default'
        self.assertIsNone(ExecutionWorker(agent).ordinary_backend)
        self.assertFalse((agent.state_dir/'execution.db').exists())


class FenceTests(R3TestCase):
    def test_prepare_is_legacy_and_never_silently_reinitializes(self):
        fence = self.fence('legacy'); self.assertEqual('legacy',fence.status()['owner'])
        with self.assertRaisesRegex(FenceRejected,'already_initialized'):fence.prepare()
        with self.assertRaisesRegex(FenceRejected,'not_prepared'):
            with OrdinaryFence(self.root/'absent').guard('legacy'):self.fail('entered missing fence')

    def test_each_evidence_field_and_expected_id_required(self):
        fence = self.fence('legacy')
        for field in self.evidence():
            evidence = self.evidence(); evidence[field] = False if isinstance(evidence[field],bool) else 1
            with self.assertRaisesRegex(FenceRejected,'evidence_incomplete'):
                fence.select('candidate',expected_id=fence.status()['fenceId'],confirmation='R3_OWNER_CHANGE_REVIEWED',evidence=evidence)
        with self.assertRaisesRegex(FenceRejected,'identity_mismatch'):
            fence.select('candidate',expected_id='x'*32,confirmation='R3_OWNER_CHANGE_REVIEWED',evidence=self.evidence())

    def test_two_independent_native_lock_handles_cannot_enter_together(self):
        fence = self.fence('legacy'); other = OrdinaryFence(fence.root,timeout=.03)
        with fence.guard('legacy'):
            with patch('agent.core.ordinary_fence._local',return_value=threading.Lock()):
                with self.assertRaisesRegex(FenceRejected,'busy'):
                    with other.guard('legacy'):self.fail('concurrent native writer')
        with other.guard('legacy'):pass

    def test_select_rejects_active_writer_and_rollback_keeps_identity(self):
        fence = self.fence(); state = fence.status()
        with fence.guard('candidate'):
            with self.assertRaisesRegex(FenceRejected,'busy'):
                fence.select('legacy',expected_id=state['fenceId'],confirmation='R3_OWNER_CHANGE_REVIEWED',evidence=self.evidence())
        selected = fence.select('legacy',expected_id=state['fenceId'],confirmation='R3_OWNER_CHANGE_REVIEWED',evidence=self.evidence())
        self.assertEqual(state['fenceId'],selected['fenceId'])
        with self.assertRaisesRegex(FenceRejected,'owner_mismatch'):
            with fence.guard('candidate'):self.fail('wrong owner')
        with fence.guard('legacy'):pass

    def test_corrupt_state_is_fail_closed(self):
        fence = self.fence('legacy'); valid = fence.status()
        for corrupt in ({},dict(valid,owner=[]),dict(valid,schema=True),dict(valid,fenceId='x'*32),dict(valid,updatedAt='wrong')):
            fence.path.write_text(json.dumps(corrupt),encoding='utf-8')
            with self.assertRaisesRegex(FenceRejected,'state_invalid'):
                with fence.guard('legacy'):self.fail('corrupt owner')


class IngressTests(R3TestCase):
    def call(self,wrapper,target,method='POST',client='127.0.0.1'):
        sent = []
        async def send(message):sent.append(message)
        async def receive():return {'type':'http.request','body':b'','more_body':False}
        scope = dict(type='http',path=target,method=method,client=(client,10000),headers=[],query_string=b'')
        asyncio.run(wrapper(scope,receive,send))
        return sent[0]['status'],json.loads(sent[1]['body'])

    def wrapper(self,fence):
        self.calls = []
        async def old(scope,receive,send):
            self.calls.append(scope['path']); await JSONResponse({'legacy':True})(scope,receive,send)
        return FencedDashboard(old,fence)

    def test_candidate_blocks_all_old_ordinary_posts_but_leaves_reads(self):
        wrapper = self.wrapper(self.fence())
        for _,target in ROUTES:self.assertEqual(409,self.call(wrapper,target)[0])
        self.assertEqual([],self.calls)
        self.assertEqual(200,self.call(wrapper,'/api/dashboard','GET')[0])
        self.assertEqual(['/api/dashboard'],self.calls)

    def test_legacy_owner_accepts_old_posts_unprepared_owner_refuses(self):
        wrapper = self.wrapper(self.fence('legacy'))
        self.assertEqual(200,self.call(wrapper,'/api/controls/upload/rescan')[0])
        self.assertEqual(503,self.call(self.wrapper(OrdinaryFence(self.root/'missing')),'/api/controls/upload/rescan')[0])

    def test_capability_checks_network_and_owner(self):
        wrapper = self.wrapper(self.fence())
        self.assertEqual(403,self.call(wrapper,CAPABILITY,'GET','203.0.113.8')[0])
        status,body = self.call(wrapper,CAPABILITY,'GET','100.92.17.9')
        self.assertEqual(200,status)
        self.assertEqual(('candidate',True),(body['owner'],body['legacyWritesBlocked']))

    def test_old_handler_exception_releases_writer_lock(self):
        fence = self.fence('legacy')
        async def broken(*args):raise RuntimeError('fixture')
        with self.assertRaisesRegex(RuntimeError,'fixture'):
            self.call(FencedDashboard(broken,fence),'/api/controls/upload/rescan')
        with fence.guard('legacy'):pass

    def test_shared_cleanup_and_reset_stay_legacy_while_ordinary_owner_is_candidate(self):
        wrapper = self.wrapper(self.fence())
        for target in SHARED_LEGACY_WRITES:
            self.assertEqual(200,self.call(wrapper,target)[0])
        self.assertEqual(set(SHARED_LEGACY_WRITES),set(self.calls))

    def test_shared_control_action_writers_cannot_overlap_a_candidate_write(self):
        fence = self.fence(); wrapper = self.wrapper(fence)
        with fence.guard('candidate'):
            for target in SHARED_LEGACY_WRITES:
                self.assertEqual(503,self.call(wrapper,target)[0])
        self.assertEqual([],self.calls)
        with fence.shared_write():
            with self.assertRaisesRegex(FenceRejected,'busy'):
                with fence.guard('candidate'):self.fail('shared index writers overlap')


if __name__ == '__main__':unittest.main()
