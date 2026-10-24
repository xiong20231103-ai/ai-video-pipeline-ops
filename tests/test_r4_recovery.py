import ast
import copy
import hashlib
import inspect
import json
import sys
import threading
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app
import test_ops
import test_continue_contract
from agent.core import recovery_logic
from agent.core.recovery import RecoverySession,replay_recovery
from agent.core.oracle import Oracle
from agent.core.replay import make_fixture,replay,read_targets
from agent.core.comparison import compare
from agent.core.ordinary import request_for
from agent.core.recovery_transport import RecoveryTransport,require_protocol

ROOT=Path(__file__).resolve().parents[1]


class RecoveryExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r4-isolated-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8')

    def test_exact_bodies_and_all_provenance_lines_match_pinned_source(self):
        manifest=json.loads((ROOT/'tests/fixtures/migration/r4-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['legacySha256'],hashlib.sha256(self.source.encode()).hexdigest())
        original={n.name:n for n in ast.parse(self.source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        candidate={n.name:n for n in ast.parse(Path(recovery_logic.__file__).read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        self.assertEqual(44,len(candidate))
        self.assertEqual(set(candidate),{r['name'] for r in manifest['functions']})
        for row in manifest['functions']:
            old=copy.deepcopy(original[row['name']]);old.decorator_list=[];new=candidate[row['name']]
            self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(new,include_attributes=False),row['name'])
            self.assertEqual((old.lineno,old.end_lineno),(row['legacyStart'],row['legacyEnd']))
            self.assertEqual((new.lineno,new.end_lineno),(row['candidateStart'],row['candidateEnd']))

    def test_all_20_snapshot_profiles_28_get_responses_and_effects_match(self):
        profiles=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))
        targets=read_targets(json.loads((ROOT/'contracts/endpoints.json').read_text(encoding='utf-8')))
        self.assertEqual(20,len(profiles));self.assertEqual(28,len(targets))
        for index,(name,profile) in enumerate(profiles.items()):
            with self.subTest(profile=name):
                snapshot=make_fixture(profile,self.source,self.root/str(index)/'snapshot')
                old=replay(self.source,snapshot,self.root/str(index)/'old',targets)
                new=replay_recovery(self.source,snapshot,self.root/str(index)/'new',targets)
                self.assertEqual([],compare(old,new))
                self.assertFalse(new['realShadowPassed']);self.assertFalse(new['switchAccepted'])

    def test_no_live_candidate_hook_and_missing_ports_refused(self):
        with self.assertRaisesRegex(ValueError,'missing_recovery_ports'):RecoverySession({})
        self.assertFalse(RecoverySession.capability()['enabled'])
        self.assertFalse(RecoverySession.capability()['switchAccepted'])
        self.assertFalse(hasattr(RecoverySession,'send'))

    def test_sessions_have_private_locks_and_health_cache(self):
        profiles=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))
        snapshot=make_fixture(profiles['running'],self.source,self.root/'snapshot')
        with Oracle(self.source,snapshot,self.root/'scratch') as environment:
            one=RecoverySession(environment.namespace);two=RecoverySession(environment.namespace)
            self.assertIsNot(one.namespace['CONTROL_COMMAND_LOCK'],two.namespace['CONTROL_COMMAND_LOCK'])
            one.namespace['_HEALTH_CACHE']['payload']={'mutated':True}
            self.assertIsNone(two.namespace['_HEALTH_CACHE']['payload'])
            with self.assertRaisesRegex(ValueError,'isolated_evaluation_only'):one.evaluate('continue_command_status')


class CandidateCompatibility(unittest.TestCase):
    """Run existing regression assertions against independently bound R4 code.

    Redirect only this test's app reference/patch target. All files, mocked HTTP
    and workbench fixtures remain guarded by tools/run_isolated_tests.py.
    No production app module is imported by the candidate itself.
    """
    def setUp(self):
        session=RecoverySession(vars(app),isolated=True)
        facade=types.ModuleType('app')
        facade.__dict__.update(vars(app));facade.__dict__.update(session.namespace)
        # Let legacy tests' patch('app.x') affect the candidate namespace too.
        for name,value in session.namespace.items():
            if inspect.isfunction(value) and value.__globals__ is session.namespace:
                fn=types.FunctionType(value.__code__,facade.__dict__,value.__name__,value.__defaults__,value.__closure__)
                fn.__kwdefaults__=value.__kwdefaults__;facade.__dict__[name]=fn
        self.facade=facade
        self.module_patch=patch.dict(sys.modules,{'app':facade})
        self.module_patch.start();self.addCleanup(self.module_patch.stop)

    def run_legacy_case(self,case_type,name):
        local_globals=dict(vars(sys.modules[case_type.__module__]));local_globals['app']=self.facade
        for key,value in list(local_globals.items()):
            if inspect.isfunction(value) and value.__module__==case_type.__module__:
                cloned=types.FunctionType(value.__code__,local_globals,value.__name__,value.__defaults__,value.__closure__)
                cloned.__kwdefaults__=value.__kwdefaults__;local_globals[key]=cloned
        attrs={}
        for key,value in vars(case_type).items():
            if inspect.isfunction(value):
                fn=types.FunctionType(value.__code__,local_globals,value.__name__,value.__defaults__,value.__closure__)
                fn.__kwdefaults__=value.__kwdefaults__;attrs[key]=fn
        bound=type('BoundR4'+case_type.__name__,(unittest.TestCase,),attrs)
        result=unittest.TestResult();bound(name).run(result)
        self.assertEqual([],result.errors,result.errors)
        self.assertEqual([],result.failures,result.failures)


OPS_CASES=(
 'test_missing_shared_recovery_module_rejects_before_receiver_start',
 'test_shared_request_identity_conflict_preserves_original_request',
 'test_control_command_expires_when_workbench_does_not_claim',
 'test_executing_step12_command_expires_after_bridge_failure',
 'test_fresh_step12_session_keeps_executing_command_locked',
 'test_continue_enqueues_exact_target_and_reuses_explicit_request_id',
 'test_stale_capcut_mailbox_is_not_overwritten_by_dashboard_request',
 'test_live_capcut_recovery_command_is_not_expired',
 'test_recoverable_draft_waiting_expires_command_immediately',
 'test_continue_keeps_command_when_receiver_cannot_launch_workbench',
 'test_continue_keeps_structured_receiver_startup_error',
 'test_health_reports_open_commands_and_recent_log_errors',
 'test_safe_continue_prefers_workbench_owned_older_unfinished_batch',
 'test_safe_continue_ignores_terminal_workbench_context',
)
for case_type,names in ((test_ops.OpsTests,OPS_CASES),
                        (test_continue_contract.ContinueContractTests,tuple(n for n in vars(test_continue_contract.ContinueContractTests) if n.startswith('test_')))):
    for name in names:
        def test(self,_type=case_type,_name=name):
            self.run_legacy_case(_type,_name)
        setattr(CandidateCompatibility,'test_candidate_'+name.removeprefix('test_'),test)
del case_type,names,name,test


class Protocol2AdapterTests(unittest.TestCase):
    def setUp(self):
        self.session=RecoverySession(vars(app),isolated=True)
        self.n=self.session.namespace
        self.command={'commandId':'continue-fixture','clientRequestId':'fixture-request','state':'persisted',
                      'taskId':'task-1','batchId':'batch-1','productionDate':'10.20','manifestId':'m1',
                      'attemptId':'a1','runGroupId':'r1','batchKind':'formal','selectedProjects':[],
                      'requestedAt':'2026-10-20T12:00:00+08:00','expiresAt':'2026-10-20T12:05:00+08:00'}
        self.saved=[]
        self.n.update(read_control_command=lambda identifier:dict(self.command),
                      write_control_command=lambda value:self.saved.append(dict(value)),
                      _ensure_workbench_for_continue=lambda:{'workbenchReady':True},
                      now_iso=lambda:'2026-10-20T12:01:00+08:00')
        self.controller=types.SimpleNamespace(
            request_capabilities=lambda:{'protocol':2,'expiryChecked':True,'cancelUnderAuthorityLock':True},
            enqueue_request=lambda value:{**value,'state':'requested'},
            cancel_request=lambda identifier,**kwargs:{'commandId':identifier,'state':'cancelled'})
        self.transport=self.session.bind_transport(self.controller)

    def test_protocol_without_expiry_and_cancel_is_rejected(self):
        for value in ({},{'protocol':1},{'protocol':2,'expiryChecked':True}):
            with self.assertRaises(app.HTTPException):require_protocol(types.SimpleNamespace(request_capabilities=lambda:value))

    def test_submit_preserves_original_id_creation_and_deadline(self):
        calls=[]
        self.controller.enqueue_request=lambda value:calls.append(value) or {**value,'state':'requested'}
        result=self.transport.submit(self.command)
        self.assertTrue(result['accepted'])
        for key in ('commandId','requestedAt','expiresAt','taskId','attemptId','manifestId','selectedProjects'):
            self.assertEqual(self.command[key],calls[0][key])

    def test_submit_requires_original_deadline_and_exact_target(self):
        self.controller.enqueue_request=lambda value:self.fail('must not enqueue')
        with self.assertRaises(app.HTTPException):self.transport.submit({**self.command,'attemptId':'wrong'})
        self.command.pop('expiresAt')
        with self.assertRaises(app.HTTPException):self.transport.submit(self.command)

    def test_cancel_updates_dashboard_only_after_authority_ack(self):
        def cancel(identifier,**kwargs):
            self.assertEqual([],self.saved)
            self.assertEqual('a1',kwargs['expected_target']['attemptId'])
            return {'commandId':identifier,'state':'cancelled'}
        self.controller.cancel_request=cancel
        result=self.session.evaluate('cancel_control_command','continue-fixture',request_for('/api/control-commands/continue-fixture/cancel',{}))
        self.assertEqual('cancelled',result['state']);self.assertEqual(1,len(self.saved))

    def test_cancel_refusal_or_lost_ack_never_claims_success(self):
        for result in ({'state':'cancelled','commandId':'wrong'},{'state':'executing','commandId':'continue-fixture'}):
            self.controller.cancel_request=lambda *args,**kwargs:result
            with self.assertRaises(app.HTTPException):self.transport.cancel('continue-fixture',request_for('/api/control-commands/x/cancel',{}))
            self.assertEqual([],self.saved)
        def lost(*args,**kwargs):raise OSError('lost response')
        self.controller.cancel_request=lost
        with self.assertRaises(app.HTTPException):self.transport.cancel('continue-fixture',request_for('/api/control-commands/x/cancel',{}))
        self.assertEqual([],self.saved)

    def test_unknown_and_execution_are_not_cancelled_or_reposted(self):
        self.controller.cancel_request=lambda *args,**kwargs:self.fail('must not cancel')
        for state in ('executing','unknown'):
            self.command['state']=state
            with self.assertRaises(app.HTTPException):self.transport.cancel('continue-fixture',request_for('/api/control-commands/x/cancel',{}))

    def test_expired_or_manual_review_reply_does_not_launch_worker(self):
        self.n['_ensure_workbench_for_continue']=lambda:self.fail('must not start')
        for state in ('expired','cancelled','reconciliation_required'):
            self.controller.enqueue_request=lambda value:{**value,'state':state}
            with self.assertRaises(app.HTTPException):self.transport.submit(self.command)

    def test_protocol_downgrade_after_binding_is_fail_closed(self):
        self.controller.request_capabilities=lambda:{}
        self.controller.enqueue_request=lambda value:self.fail('must not enqueue')
        with self.assertRaises(app.HTTPException):self.transport.submit(self.command)


if __name__=='__main__':unittest.main()
