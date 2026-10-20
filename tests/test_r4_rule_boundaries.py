"""Concrete R4 boundary assertions; temporary files and explicit frozen ports."""
import copy
import json
import tempfile
import types
import unittest
from datetime import datetime,timezone
from pathlib import Path

import app
from agent.core.recovery import RecoverySession
from agent.core.ordinary import request_for


class RecoveryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='r4-rules-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.now=2000000000
        self.target={'taskId':'current-task','batchId':'current-box','productionDate':'10.20',
                     'manifestId':'m1','attemptId':'a1','runGroupId':'r1','batchKind':'formal','selectedProjects':['b','a']}
        collector=types.SimpleNamespace(receiver_control_ready=True,receiver_data_updated_at='',
            receiver_reconciliation_state='healthy',project_download_statuses=[],pipeline={},active_workbench_task_id=lambda:'current-task')
        ports={**vars(app),'BASE_DIR':self.root,'CONTROL_COMMAND_DIR':self.root/'commands',
               'CONFIG':{'workbench_dir':str(self.root/'workbench'),'voice_handoff_file':str(self.root/'voice.json')},
               'COLLECTOR':collector,'time':types.SimpleNamespace(time=lambda:self.now),
               'STORE':types.SimpleNamespace(tasks=lambda *args:[],event=lambda *args:None)}
        self.session=RecoverySession(ports,isolated=True);self.n=self.session.namespace
        self.n['now_iso']=lambda:self.stamp(self.now)
        self.n['process_status']=lambda:{'capcut':False}
        self.n['task_box_payloads']=lambda:[self.box()]
        self.n['authoritative_active_task_box']=lambda boxes:boxes[0] if boxes else None
        self.n['current_date_label']=lambda:'10.20'
        self.n['pipeline_for_date']=lambda *args:{'voice':{'total':3,'completed':2},'stitch':{'total':3,'completed':1}}
        self.n['production_capcut_tasks']=lambda *args,**kwargs:[]
        self.n['upload_task_index']=lambda:{}

    @staticmethod
    def stamp(epoch):return datetime.fromtimestamp(epoch,timezone.utc).isoformat()

    def box(self,**changes):
        current={**self.target,'expected':3,'status':'blocked','currentStep':'CapCut','downloadCompleted':3,'finalCompleted':1}
        return {**self.target,'current':{**current,**changes},'items':[current]}

    def command(self,**changes):
        return {**self.target,'commandId':'continue-fixture','state':'persisted',
                'requestedAt':self.stamp(self.now-10),'persistedAt':self.stamp(self.now-10),
                'expiresAt':self.stamp(self.now+290),**changes}

    def write(self,path,value):self.n['_write_json_atomic'](path,value)
    def mailbox(self,value):self.write(self.n['continue_command_file'](),value)
    def persist(self,value):self.n['write_control_command'](value)

    def test_r4_01_network_boundary_local_tailnet_and_public(self):
        for host in ('127.0.0.1','::1','100.64.0.1','fd7a:115c:a1e0::1'):
            self.n['require_control_permission'](request_for('/api/control-commands',{},host))
        for host in ('192.0.2.1','100.63.255.255','100.128.0.1','not-an-ip'):
            with self.assertRaises(app.HTTPException):self.n['require_control_permission'](request_for('/api/control-commands',{},host))

    def test_r4_02_03_no_control_when_receiver_or_active_context_missing(self):
        self.assertEqual('current-task',self.n['_current_continue_target']()['taskId'])
        self.n['COLLECTOR'].receiver_control_ready=False
        with self.assertRaises(app.HTTPException):self.n['_current_continue_target']()
        self.n['COLLECTOR'].receiver_control_ready=True;self.n['authoritative_active_task_box']=lambda boxes:None
        with self.assertRaises(app.HTTPException):self.n['_current_continue_target']()

    def test_r4_04_05_scope_signatures_and_legacy_manifest_compatibility(self):
        signature=self.n['_continue_target_signature']
        self.assertEqual(signature(self.target),signature({**self.target,'selectedProjects':['a','b','a',' ']}))
        changed=self.n['_continue_target_changed']
        for field in ('taskId','batchId','productionDate','manifestId','attemptId','runGroupId','batchKind','selectedProjects'):
            value=['other'] if field=='selectedProjects' else 'other'
            self.assertTrue(changed(self.target,{**self.target,field:value}),field)
        legacy={**self.target,'manifestId':'','attemptId':''}
        self.assertFalse(changed(legacy,self.target))

    def test_r4_06_archive_preserves_original_and_retired_mailbox(self):
        path=self.n['continue_command_file']();original=self.command(state='recovering');self.write(path,original)
        retired=self.n['_expire_continue_command'](path,original,'fixture-stale-target')
        archives=list((path.parent/'history').glob('*.json'));self.assertEqual(1,len(archives))
        saved=json.loads(archives[0].read_text(encoding='utf-8'))
        self.assertEqual(original['taskId'],saved['taskId']);self.assertEqual('recovering',saved['state'])
        self.assertEqual('expired',retired['state']);self.assertEqual('fixture-stale-target',saved['archiveReason'])

    def test_r4_07_08_inflight_and_legacy_mailbox_converge_without_second_request(self):
        self.n['request_workbench_continue']=lambda target:self.fail('must not enqueue again')
        active=self.command(clientRequestId='original');self.persist(active)
        self.assertEqual(active,self.n['enqueue_control_command'](self.target,'another-id'))
        self.assertEqual(active,self.n['enqueue_control_command'](self.target,'original'))
        for path in (self.root/'commands').glob('*.json'):path.unlink()
        self.mailbox(self.command(state='running',startedAt=self.stamp(self.now-2)))
        result=self.n['enqueue_control_command'](self.target,'new-id')
        self.assertEqual('continue-fixture',result['commandId']);self.assertEqual('executing',result['state'])

    def test_r4_09_request_failure_keeps_persisted_command_and_original_identity(self):
        def refused(target):
            saved=self.n['read_control_command'](target['commandId'])
            self.assertEqual('persisted',saved['state']);self.assertEqual('current-task',saved['taskId'])
            raise app.HTTPException(503,'fixture')
        self.n['request_workbench_continue']=refused
        result=self.n['enqueue_control_command'](self.target,'request-fixed')
        self.assertEqual('persisted',result['state']);self.assertEqual('request-fixed',result['clientRequestId'])
        self.assertEqual(result,self.n['enqueue_control_command'](self.target,'request-fixed'))

    def test_r4_12_mailbox_mapping_requires_exact_command_id(self):
        for source,expected in {'requested':'receiver_acknowledged','accepted':'workbench_acknowledged',
             'running':'executing','recovering':'executing','completed':'completed','blocked':'blocked','failed':'blocked','expired':'expired','cancelled':'expired'}.items():
            self.persist(self.command());self.mailbox(self.command(state=source))
            self.assertEqual(expected,self.n['_sync_queued_command_from_mailbox']()['state'])
        self.persist(self.command());self.mailbox(self.command(commandId='unrelated',state='completed'))
        self.assertEqual('persisted',self.n['_sync_queued_command_from_mailbox']()['state'])

    def test_r4_13_14_15_ttl_does_not_terminate_running_or_fresh_recovery(self):
        for age,expected in ((90,'persisted'),(91,'expired')):
            self.persist(self.command(persistedAt=self.stamp(self.now-age)))
            self.assertEqual(expected,self.n['_sync_queued_command_from_mailbox']()['state'])
        self.persist(self.command(state='executing',expiresAt=self.stamp(self.now-1),startedAt=self.stamp(self.now-10)))
        self.assertEqual('executing',self.n['_sync_queued_command_from_mailbox']()['state'])
        for delta,expected in ((0,'workbench_acknowledged'),(1,'expired')):
            self.persist(self.command(state='workbench_acknowledged',expiresAt=self.stamp(self.now-delta)))
            self.assertEqual(expected,self.n['_sync_queued_command_from_mailbox']()['state'])

    def test_r4_16_17_fish_terminal_requires_task_and_nonolder_timestamp(self):
        original=self.command(state='executing',startedAt=self.stamp(self.now-20))
        self.persist(original)
        for owner,terminal,expired in (('other',self.now,False),('current-task',self.now-21,False),('current-task',self.now,True)):
            self.write(self.root/'voice.json',{'status':'failed','canonicalTaskIds':[owner],'finishedAt':self.stamp(terminal)})
            self.assertEqual(expired,self.n['continue_command_status']()['state']=='expired')
        self.persist(self.command(state='accepted',startedAt=self.stamp(self.now-121)))
        self.write(self.root/'voice.json',{})
        self.assertEqual('expired',self.n['continue_command_status']()['state'])

    def test_r4_18_19_capcut_liveness_heartbeat_and_every_safe_stop_fingerprint(self):
        check=self.n['_capcut_recovery_command_is_stale'];command=self.command(state='recovering',lastHeartbeat=self.stamp(self.now-121))
        item={'pipelineStatus':'blocked_capcut','currentPhase':'stopped','capcut':{'running':0}}
        self.assertTrue(check(command,item))
        self.assertFalse(check(command,{**item,'capcut':{'running':1}}))
        self.assertFalse(check(command,{**item,'currentPhase':'capcut_running'}))
        self.assertFalse(check({**command,'lastHeartbeat':self.stamp(self.now-120)},item))
        for fingerprint in self.n['RECOVERABLE_DRAFT_REOPEN_ERRORS']:
            for state in ('waiting','waiting_capcut','waiting_client','stopped'):
                self.assertTrue(self.n['_is_recoverable_draft_waiting']({'state':state,'failureFingerprint':fingerprint}))
            self.assertFalse(self.n['_is_recoverable_draft_waiting']({'state':'running','failureFingerprint':fingerprint}))
        self.assertFalse(self.n['_is_recoverable_draft_waiting']({'state':'failed','error':'ordinary failed'}))

    def test_r4_20_21_22_terminal_history_and_public_fields(self):
        command=self.command(state='blocked',finishedAt=self.stamp(self.now-2),boundManifestId='m1',boundAttemptId='a1',
                             clientPid=123,operationGeneration='generation',boundOperationState='failed')
        self.persist(command)
        self.write(self.root/'workbench/handoff/download/project_status.json',{'items':{'current-task':{'pipelineStatus':'voice_pending'}}})
        result=self.n['continue_command_status']();self.assertEqual('expired',result['state'])
        for field in ('boundManifestId','boundAttemptId','clientPid','operationGeneration','boundOperationState'):
            self.assertEqual(command[field],result[field])

    def test_r4_24_25_26_inflight_blocked_and_bound_states(self):
        self.n['continue_command_status']=lambda:self.command(state='executing')
        self.n['process_status']=lambda:{'capcut':True}
        for state,expected in (('running',False),('failed',True),('stopped',True),('completed_with_errors',True),('expired',True),('recoverable_failed',True)):
            self.n['continue_command_status']=lambda state=state:self.command(state='executing',boundOperationState=state)
            result=self.n['reconciliation_payload']([self.box()])
            self.assertEqual('executing',result['state']);self.assertEqual(expected,result['continueCanRetry'])
        self.n['COLLECTOR'].receiver_control_ready=False
        self.assertFalse(self.n['reconciliation_payload']([self.box()])['allowed'])

    def test_r4_22_23_27_reconciliation_archives_other_target_and_uses_task_scoped_steps(self):
        self.n['continue_command_status']=lambda:self.command(state='completed',taskId='old-task')
        self.n['COLLECTOR'].pipeline={'voice':{'total':5,'completed':2}}
        result=self.n['reconciliation_payload']([self.box(currentStep='配音')])
        self.assertEqual('old-task',result['archivedCommandTarget']['taskId'])
        self.assertEqual('current-task',result['taskId'])
        self.assertEqual(2,result['steps'][1]['actual']);self.assertEqual(0,result['steps'][2]['actual'])
        self.assertEqual(0,result['steps'][4]['expected'])

    def test_r4_28_get_and_legacy_cancel_never_touch_another_mailbox(self):
        with self.assertRaises(app.HTTPException):self.n['get_control_command']('missing',request_for('/api/control-commands/missing',{}))
        self.persist(self.command(state='executing'))
        with self.assertRaises(app.HTTPException):self.n['cancel_control_command']('continue-fixture',request_for('/api/control-commands/x/cancel',{}))
        self.persist(self.command());other=self.command(commandId='other',state='requested');self.mailbox(other)
        self.n['cancel_control_command']('continue-fixture',request_for('/api/control-commands/x/cancel',{}))
        self.assertEqual(other,self.n['read_json_object'](self.n['continue_command_file']()))


if __name__=='__main__':unittest.main()
