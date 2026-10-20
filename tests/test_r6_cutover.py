"""Temp-only state migration and rollback; Windows tasks/health are inert mocks."""
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import types
import unittest
from unittest.mock import patch
import app
from cleanup_tickets import CleanupTickets
from agent.cutover import stage,rollback,sqlite_backup,digest,park_transition
from agent.engine_runtime import state_inventory
from agent.execution import ExecutionLedger
from agent.core.composed import ComposedSession
from agent.core.projection_store import durable_store
from agent.core.ordinary_fence import OrdinaryFence
from deploy import agent_source_update


class CutoverTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r6-cutover-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.legacy=self.root/'legacy';(self.legacy/'data').mkdir(parents=True)
        self.candidate=self.root/'candidate';self.state=self.root/'agent';self.state.mkdir()
        self.settings={'legacyRoot':str(self.legacy),'stateRoot':str(self.candidate),
            'legacyScripts':[str(self.legacy/'app.py')],'legacyTasks':[{'name':'fixture-legacy','path':'\\'}]}
        self.calls=[]
        with ComposedSession(vars(app),tickets=CleanupTickets(),store_factory=durable_store(self.legacy/'data/ops.db')) as session:
            self.task(session,'existing')
        (self.legacy/'data/control_actions.json').write_text('{"state":"paused"}')
        self.before=state_inventory(self.legacy/'data')
        self.stage_result=stage(self.settings,'R6_STAGE_REVIEWED',quiet=lambda _:True,tasks_disabled=lambda _:True)
        sqlite_backup(self.candidate/'projection-seed.db',self.candidate/'projection.db')
        with ComposedSession(vars(app),tickets=CleanupTickets(),store_factory=durable_store(self.candidate/'projection.db')) as session:
            self.task(session,'new-task')
        (self.candidate/'control_actions.json').write_text('{"state":"paused","receipt":"new"}')
        (self.state/'engine-settings.json').write_text(json.dumps(self.settings))
        (self.state/'config.json').write_text('{"agent_token":"inert-private-value"}')
        (self.state/'agent-runtime.json').write_text('{"phase":"running","instanceId":"before"}')
        self.ledger=ExecutionLedger(self.state/'execution.db')
        self.fence=OrdinaryFence(self.root/'fence');owner=self.fence.prepare()
        self.fence.select('candidate',expected_id=owner['fenceId'],confirmation='R3_OWNER_CHANGE_REVIEWED',
            evidence=dict(commandsPaused=True,drained=True,leased=0,sent=0,unknown=0,legacyFenceInstalled=True,fullBatchShadowReviewed=True))
        self.plan=dict(schema=1,action='R6_ROLLBACK',approvedBy='isolated-test-reviewer',expiresAt=1300,
            legacyRoot=str(self.legacy),candidateState=str(self.candidate),agentState=str(self.state),backupRoot=str(self.root/'backups'),
            fenceRoot=str(self.root/'fence'),fenceId=owner['fenceId'],ledgerId=self.ledger.identity,
            legacyTasks=self.settings['legacyTasks'],legacyScripts=self.settings['legacyScripts'],
            agentTask={'name':'OpsConsoleReadonlyAgent','path':'\\'},commandsPaused=True,pipelineIdle=True,drained=True,
            leased=0,sent=0,unknown=0,unreconciledRecovery=0,
            legacyStateInventorySha256=self.stage_result['legacyStateInventorySha256'],legacyDatabaseSha256=self.stage_result['legacyDatabaseSha256'])
        self.maintenance=types.SimpleNamespace(begin_stop=agent_source_update.begin_stop,
            wait_stopped=lambda *args,**kwargs:{'lockFree':True,'cooperativeAck':True},
            exclusive_agent_lock=agent_source_update.exclusive_agent_lock,
            verify_maintenance=agent_source_update.verify_maintenance,finish=agent_source_update.finish)
    def task(self,session,identifier):
        row={key:'' for key in app.TASK_REQUIRED_COLUMNS}
        row.update(task_id=identifier,sequence=0,expected_task_count=1,source_timestamp=1000,state='Waiting',state_text='isolated pause')
        session.store.upsert_task(row)
    def tasks(self,rows,action):
        self.calls.append((action,[r['name'] for r in rows]))
        if action=='start' and rows[0]['name']=='OpsConsoleReadonlyAgent':
            (self.state/'agent-runtime.json').write_text('{"phase":"running","instanceId":"after"}')
        return [{**row,'state':'Disabled','sha256':'a'*64,'legacyWrapper':row['name']!='OpsConsoleReadonlyAgent'} for row in rows]
    def run_rollback(self,plan=None,**extra):
        return rollback(plan or self.plan,'R6_ROLLBACK_REVIEWED',task_control=self.tasks,quiet=lambda _:True,
            health=lambda:True,clock=lambda:1000,maintenance=self.maintenance,**extra)
    def test_stage_copies_only_whitelisted_state_and_read_only_sqlite_seed(self):
        self.assertEqual(self.before,[{'path':r['path'],'sha256':r['sha256']} for r in json.loads((self.candidate/'state-import.json').read_text())['files']])
        self.assertFalse((self.candidate/'config.json').exists())
        with self.assertRaisesRegex(ValueError,'not_empty'):stage(self.settings,'R6_STAGE_REVIEWED',quiet=lambda _:True,tasks_disabled=lambda _:True)
        wrong={**self.settings,'stateRoot':str(self.legacy/'data/new')}
        with self.assertRaisesRegex(ValueError,'not_independent'):stage(wrong,'R6_STAGE_REVIEWED',quiet=lambda _:True,tasks_disabled=lambda _:True)
        with self.assertRaisesRegex(ValueError,'must_be_stopped'):stage(self.settings,'R6_STAGE_REVIEWED',quiet=lambda _:False,tasks_disabled=lambda _:True)

    def test_park_and_rollback_restore_staged_pointer_and_reset_r5_observation(self):
        # Simulate only temp mode pointers. Tasks/process probes are inert;
        # this does not assert any Windows or production acceptance.
        (self.state/'engine-settings.json').unlink()
        source=self.root/'staged-plan.json';source.write_text('{"fixture":"no-service"}')
        pointer=dict(schema=1,plan=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        record=dict(schema=1,stage='R5',phase='active',build='fixture',ledgerId=self.ledger.identity,
            installedModules=['R0','R1','R2','R3','R4','R5'],sharedState=True,legacyRetired=False,
            planSha256=digest(json.loads(source.read_text())),acceptedAt='1969-01-01T00:00:00+00:00')
        from contracts.state_files import atomic_json
        atomic_json(self.state/'migration/active.json',record);atomic_json(self.state/'migration-settings.json',pointer)
        review=dict(self.plan,action='R6_PARK',build='fixture',autoRecoveryDisabled=True,cleanupEnabled=False,
            migrationSha256=digest(record),r5AcceptedAt=record['acceptedAt'],r5ContinuousCandidateUse=True,
            r5NoRollbackDuringObservation=True,legacyAvailableThroughObservation=True)
        with self.assertRaisesRegex(ValueError,'stopped_before_parking'):
            park_transition(review,'R6_PARK_REVIEWED',quiet=lambda _:False,tasks_disabled=lambda _:True,
                clock=lambda:1000,maintenance=self.maintenance)
        self.assertFalse((self.state/'maintenance.json').exists())
        parked=park_transition(review,'R6_PARK_REVIEWED',quiet=lambda _:True,tasks_disabled=lambda _:True,
            clock=lambda:1000,maintenance=self.maintenance)
        self.assertTrue(parked['maintenanceRetained']);self.assertFalse((self.state/'migration-settings.json').exists())
        self.assertTrue((self.state/'maintenance.json').exists())
        self.assertEqual(record,json.loads((self.state/'migration/active.json').read_text()))
        # The later reviewed native startup clears this exact preparation
        # request; rollback itself must not bypass another maintenance owner.
        journal=json.loads((Path(parked['backup'])/'journal.json').read_text())
        self.maintenance.finish(self.state,journal['requestId'])
        atomic_json(self.state/'engine-settings.json',self.settings)
        result=self.run_rollback(dict(self.plan,transitionBackup=parked['backup']))
        self.assertTrue(result['completed'])
        self.assertEqual(pointer,json.loads((self.state/'migration-settings.json').read_text()))
        reset=json.loads((self.state/'migration/active.json').read_text())
        self.assertEqual('prepared',reset['phase']);self.assertIsNone(reset['acceptedAt'])
        self.assertEqual(record['planSha256'],reset['planSha256'])
    def test_one_command_rollback_preserves_receipts_history_identity_and_private_config(self):
        secret=self.state/'config.json';original=Path.read_bytes
        def no_private_read(path):
            if path==secret:raise AssertionError('private agent credentials must not be read')
            return original(path)
        with patch.object(Path,'read_bytes',no_private_read):result=self.run_rollback()
        self.assertTrue(result['completed']);self.assertTrue(result['commandsRemainPaused'])
        self.assertTrue(result['agentRunningVerified']);self.assertTrue(result['legacyHealthVerified'])
        self.assertFalse((self.state/'engine-settings.json').exists());self.assertFalse((self.state/'maintenance.json').exists())
        self.assertEqual('legacy',self.fence.status()['owner'])
        self.assertEqual({'state':'paused','receipt':'new'},json.loads((self.legacy/'data/control_actions.json').read_text()))
        with closing(sqlite3.connect(self.legacy/'data/ops.db')) as db:
            self.assertEqual({'existing','new-task'},{r[0] for r in db.execute('SELECT task_id FROM tasks')})
            self.assertEqual(2,db.execute('SELECT count(*) FROM task_history').fetchone()[0])
        self.assertEqual(self.ledger.identity,ExecutionLedger(self.state/'execution.db').identity)
        self.assertEqual('{"agent_token":"inert-private-value"}',secret.read_text())
        backup=Path(result['backup']);self.assertTrue((backup/'legacy-ops.db').is_file())
        self.assertEqual('completed',json.loads((backup/'journal.json').read_text())['phase'])
        self.assertEqual(['fixture-legacy'],self.calls[-2][1]);self.assertEqual(['OpsConsoleReadonlyAgent'],self.calls[-1][1])
    def test_busy_cloud_or_changed_legacy_or_new_ledger_cannot_touch_data(self):
        for key,value in (('unknown',1),('sent',1),('pipelineIdle',False),('expiresAt',999),('ledgerId','wrong')):
            with self.assertRaises(ValueError):self.run_rollback({**self.plan,key:value})
            self.assertEqual(self.before,state_inventory(self.legacy/'data'))
            self.assertTrue((self.state/'engine-settings.json').exists())
        (self.legacy/'data/control_actions.json').write_text('{"unexpected":"manual-change"}')
        with self.assertRaisesRegex(ValueError,'manual_merge'):self.run_rollback()
        self.assertFalse(self.calls)
    def test_missing_historical_rows_refuses_before_legacy_state_replacement(self):
        with closing(sqlite3.connect(self.candidate/'projection.db')) as db:
            db.execute('DELETE FROM task_history');db.commit()
        with self.assertRaisesRegex(ValueError,'missing_history'):self.run_rollback()
        self.assertEqual(self.before,state_inventory(self.legacy/'data'))
        self.assertEqual('candidate',self.fence.status()['owner'])
        self.assertTrue((self.state/'maintenance.json').exists())
        self.assertFalse(any(action in {'enable','start'} for action,_ in self.calls))
    def test_unprepared_legacy_deadline_wrapper_refuses_before_stopping_agent(self):
        def tasks(rows,action):return [{**row,'state':'Disabled','sha256':'a'*64,'legacyWrapper':False} for row in rows]
        with self.assertRaisesRegex(ValueError,'startup_not_prepared'):
            rollback(self.plan,'R6_ROLLBACK_REVIEWED',task_control=tasks,quiet=lambda _:True,health=lambda:True,clock=lambda:1000,maintenance=self.maintenance)
        self.assertFalse((self.state/'maintenance.json').exists())
        self.assertEqual(self.before,state_inventory(self.legacy/'data'))

    def test_agent_start_failure_restores_maintenance_without_resending_commands(self):
        def tasks(rows,action):
            if action=='start' and rows[0]['name']=='OpsConsoleReadonlyAgent':
                raise OSError('isolated startup failure')
            return self.tasks(rows,action)
        with self.assertRaisesRegex(OSError,'agent_start_failed_maintenance_retained'):
            rollback(self.plan,'R6_ROLLBACK_REVIEWED',task_control=tasks,quiet=lambda _:True,
                health=lambda:True,clock=lambda:1000,maintenance=self.maintenance)
        self.assertTrue((self.state/'maintenance.json').exists())
        self.assertEqual(self.ledger.identity,ExecutionLedger(self.state/'execution.db').identity)
        self.assertEqual('legacy',self.fence.status()['owner'])
        self.assertNotEqual('completed',json.loads(next((self.root/'backups').glob('*/journal.json')).read_text())['phase'])
