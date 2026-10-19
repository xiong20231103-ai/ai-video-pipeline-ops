import json,threading,urllib.error
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
from agent.execution import ExecutionLedger,ExecutionWorker
from contracts.commands import command
from test_command_queue import HTTP

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.ledger=ExecutionLedger(self.root/'execution.db')
        self.job={'id':'fixture-command','lease':'b'*32,'ledgerId':self.ledger.identity,'expiresAt':1300,**command('/api/controls/upload/rescan',{})}
    def test_restart_after_sent_becomes_unknown_and_cannot_post_again(self):
        self.ledger.receive(self.job);self.ledger.sent(self.job['id'])
        reopened=ExecutionLedger(self.ledger.path);self.assertEqual('unknown',reopened.receive(self.job))
        self.assertEqual('restart_after_send',json.loads(reopened.pending()['result'])['reason'])
        with self.assertRaises(ValueError):reopened.sent(self.job['id'])
    def test_unsent_crash_can_receive_new_lease_but_content_must_match(self):
        self.ledger.receive(self.job);reopened=ExecutionLedger(self.ledger.path)
        self.assertEqual('received',reopened.receive({**self.job,'lease':'c'*32}))
        with self.assertRaises(ValueError):reopened.receive({**self.job,**command('/api/controls/upload/verify-history',{})})
    def test_ack_drops_bodies_but_retains_receipt_and_never_resends_after_cloud_rollback(self):
        self.ledger.receive(self.job);self.ledger.sent(self.job['id']);self.ledger.result(self.job['id'],HTTP)
        self.ledger.acknowledge(self.job['id']);self.assertIsNone(self.ledger.pending())
        self.assertEqual('acknowledged',self.ledger.receive({**self.job,'lease':'c'*32}))
        with self.ledger.db() as db:
            row=db.execute('SELECT * FROM executions').fetchone();self.assertIsNone(row['result']);self.assertEqual(200,row['http_status']);self.assertTrue(row['result_digest'])
    def worker(self):
        agent=Mock();agent.state_dir=self.root;agent.stop=threading.Event();agent.lifecycle.stop_request.return_value=None
        worker=ExecutionWorker(agent);worker._ledger=self.ledger
        worker.clock=lambda:1000
        worker.enabled=lambda:True
        return worker,agent
    def test_real_worker_permits_before_one_home_post_and_only_retries_result_upload(self):
        worker,agent=self.worker();agent.cloud.return_value={'sendPermitted':True}
        with patch.object(worker,'home_post',return_value=HTTP) as home:
            worker.process(self.job);worker.process(self.job);self.assertEqual(1,home.call_count)
        agent.cloud.side_effect=OSError('synthetic offline');self.assertRaises(OSError,worker.flush)
        agent.cloud.side_effect=None;agent.cloud.return_value={'recorded':True};self.assertTrue(worker.flush());self.assertIsNone(self.ledger.pending())
    def test_timeout_and_lost_permit_never_repost_and_denied_permit_never_posts(self):
        for mode in ('lost-permit','home-timeout','denied'):
            with self.subTest(mode=mode):
                worker,agent=self.worker();job={**self.job,'id':mode}
                if mode=='lost-permit':agent.cloud.side_effect=OSError('synthetic timeout')
                elif mode=='denied':agent.cloud.side_effect=urllib.error.HTTPError('https://fixture',409,'denied',{},None)
                else:agent.cloud.return_value={'sendPermitted':True}
                with patch.object(worker,'home_post',side_effect=TimeoutError('synthetic home timeout')) as home:
                    worker.process(job);worker.process(job);self.assertEqual(1 if mode=='home-timeout' else 0,home.call_count)
                with self.ledger.db() as db:row=db.execute('SELECT state FROM executions WHERE id=?',(mode,)).fetchone()
                self.assertEqual('result' if mode=='denied' else 'unknown',row['state'])

    def test_disabled_default_does_not_create_execution_database_and_stop_never_posts(self):
        agent=Mock();agent.state_dir=self.root/'disabled';agent.stop=threading.Event();agent.lifecycle.stop_request.return_value=None
        worker=ExecutionWorker(agent)
        self.assertEqual({'enabled':False},worker.capability());self.assertFalse((agent.state_dir/'execution.db').exists())
        worker,agent=self.worker();agent.lifecycle.stop_request.return_value='fixture-maintenance'
        with patch.object(worker,'home_post') as home:worker.process(self.job);home.assert_not_called()
        self.assertFalse(worker.active.is_set())
    def test_cooperative_stop_during_home_post_drains_without_repeating(self):
        worker,agent=self.worker();agent.cloud.return_value={'sendPermitted':True};entered=threading.Event();released=threading.Event()
        def blocked(job):entered.set();released.wait(2);return HTTP
        with patch.object(worker,'home_post',side_effect=blocked) as home:
            thread=threading.Thread(target=worker.process,args=(self.job,));thread.start();self.assertTrue(entered.wait(2));self.assertTrue(worker.active.is_set())
            agent.stop.set();released.set();thread.join(2);self.assertFalse(thread.is_alive());home.assert_called_once()
        self.assertFalse(worker.active.is_set());self.assertEqual('http',json.loads(self.ledger.pending()['result'])['kind'])

    def test_local_execution_switch_never_initializes_or_rewrites_the_ledger(self):
        from agent.execution import configure_execution
        state=self.root/'switch';state.mkdir();(state/'config.json').write_text('not read by switch')
        self.assertFalse(configure_execution(state,True)['credentialsRead']);self.assertFalse((state/'execution.db').exists())
        (state/'execution-runtime.json').write_text('{"phase":"sending"}')
        with self.assertRaisesRegex(ValueError,'Pause cloud'):configure_execution(state,False)
        (state/'execution-runtime.json').write_text('{"phase":"idle"}');configure_execution(state,False)
        self.assertFalse(json.loads((state/'command-settings.json').read_text())['enabled'])

    def test_expiry_is_checked_again_after_send_permission_before_home_post(self):
        worker,agent=self.worker()
        def permit(*args):worker.clock=lambda:1400;return {'sendPermitted':True}
        agent.cloud.side_effect=permit
        with patch.object(worker,'home_post') as home:worker.process(self.job);home.assert_not_called()
        self.assertEqual('invalid_or_expired',json.loads(self.ledger.pending()['result'])['reason'])

    def test_identity_and_content_conflicts_are_rejected_without_home_post(self):
        worker,agent=self.worker();agent.cloud.return_value={'recorded':True}
        changed={**self.job,**command('/api/controls/upload/verify-history',{})}
        self.ledger.receive(self.job)
        with patch.object(worker,'home_post') as home:
            worker.process({**self.job,'ledgerId':'f'*32})
            worker.process(changed)
            home.assert_not_called()
        reasons=[json.loads(line)['reason'] for line in worker.rejection_path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(['agent_rejected_identity','agent_rejected_contract'],reasons)
        self.assertEqual(2,agent.cloud.call_count)

    def test_missing_result_ack_keeps_result_and_loop_survives(self):
        worker,agent=self.worker();self.ledger.receive(self.job);self.ledger.sent(self.job['id']);self.ledger.result(self.job['id'],HTTP)
        agent.cloud.side_effect=ValueError('Result acknowledgement missing')
        with self.assertRaisesRegex(ValueError,'acknowledgement'):
            worker.flush()
        self.assertIsNotNone(self.ledger.pending())
        worker.retry_after=worker.clock()+30
        class ImmediateStop:
            def __init__(self):self.flag=False
            def is_set(self):return self.flag
            def wait(self,_):self.flag=True
        agent.stop=ImmediateStop();worker.loop()
        self.assertTrue(agent.stop.is_set())

    def test_real_home_exchange_marks_heartbeat_busy_without_marking_agent_offline(self):
        from agent.readonly import ReadOnlyAgent
        instance=ReadOnlyAgent('https://fixture.ts.net','inert-fixture',self.root/'heartbeat');instance.engine_state='healthy';instance.execution.home_busy.set();captured=[]
        def cloud(path,data):captured.append(data);instance.stop.set();return {'viewerActive':False,'viewerLeaseSeconds':0}
        instance.cloud=cloud;instance.heartbeat_loop();self.assertEqual('busy',captured[0]['engineState']);self.assertEqual('healthy',instance.engine_state)
