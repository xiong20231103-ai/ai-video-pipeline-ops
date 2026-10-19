from concurrent.futures import ThreadPoolExecutor
import base64,json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from cloud.store import Store
from cloud.commands import CommandQueue,CommandError
from contracts.commands import command,MAX_PAYLOAD

LEDGER='a'*32
HTTP={'kind':'http','httpStatus':200,'bodyBase64':base64.b64encode(b'{"accepted":true,"commandId":"fixture-local"}').decode(),'contentType':'application/json'}

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=[1000.]
        self.store=Store(Path(self.temp.name)/'console.db',clock=lambda:self.now[0]);self.queue=CommandQueue(self.store,True,True)
        self.queue.advertise({'enabled':True,'protocol':1,'ledgerId':LEDGER});self.store.heartbeat('healthy')
    def enqueue(self,request='fixture-request-123456',target='/api/controls/upload/rescan',body=None):return self.queue.enqueue('user:fixture',request,target,body or {})
    def claim(self):
        item=self.queue.claim(LEDGER);self.assertIsNotNone(item);return item
    def start(self,job):return self.queue.permit(job['id'],job['lease'],LEDGER)
    def finish(self,job,result=HTTP):return self.queue.finish(job['id'],job['lease'],LEDGER,result)
    def test_idempotency_cross_reload_and_concurrent_accounts_queue_is_bounded(self):
        with ThreadPoolExecutor(4) as pool:rows=list(pool.map(lambda _:self.enqueue(),range(8)))
        self.assertEqual(1,len({r['cloudCommandId'] for r in rows}))
        with self.assertRaisesRegex(CommandError,'content_conflict'):self.enqueue(target='/api/controls/upload/verify-history')
        self.assertEqual(rows[0]['cloudCommandId'],self.queue.by_request('user:fixture','fixture-request-123456')['cloudCommandId'])
        self.assertNotIn('lease',rows[0]);self.assertNotIn('body',rows[0])
    def test_only_one_active_write_and_sent_is_not_reclaimed_after_timeout(self):
        first=self.enqueue();self.enqueue('second-request-123456');job=self.claim()
        self.assertIsNone(self.queue.claim(LEDGER));self.start(job);self.now[0]+=1000;self.store.heartbeat('healthy')
        self.assertIsNone(self.queue.claim(LEDGER));self.assertEqual('unknown',self.queue.get(first['cloudCommandId'])['state'])
        self.finish(job);self.assertEqual('completed',self.queue.get(first['cloudCommandId'])['state'])
    def test_leases_can_retry_only_before_send_permit_and_old_token_is_rejected(self):
        self.enqueue();old=self.claim();self.now[0]+=61;self.store.heartbeat('healthy');new=self.claim()
        self.assertEqual(old['id'],new['id']);self.assertNotEqual(old['lease'],new['lease'])
        with self.assertRaises(CommandError):self.start(old)
        self.start(new);self.assertIsNone(self.queue.claim(LEDGER))
    def test_cancel_expire_and_late_request_tombstone_never_authorize_home(self):
        row=self.enqueue();job=self.claim();self.queue.cancel(row['cloudCommandId'],'user:other')
        with self.assertRaises(CommandError):self.start(job)
        self.queue.cancel_request('user:fixture','late-request-123456')
        with self.assertRaisesRegex(CommandError,'cancelled_before_receipt'):self.enqueue('late-request-123456')
        row=self.enqueue('expiring-request-123456');self.now[0]+=301
        self.assertEqual('expired',self.queue.get(row['cloudCommandId'])['state'])
    def test_unknown_blocks_all_writes_until_explicit_human_reconciliation_no_retry(self):
        row=self.enqueue();job=self.claim();self.start(job);self.finish(job,{'kind':'unknown','reason':'transport_uncertain'})
        self.enqueue('next-request-123456');self.assertIsNone(self.queue.claim(LEDGER))
        with self.assertRaises(CommandError):self.queue.cancel(row['cloudCommandId'],'user:other')
        with self.assertRaises(CommandError):self.queue.resolve(row['cloudCommandId'],'user:other','too short','wrong')
        self.queue.resolve(row['cloudCommandId'],'user:other','fixture: verified original request has stopped','CONFIRMED_HOME_REQUEST_STOPPED')
        self.assertNotEqual(row['cloudCommandId'],self.claim()['id'])
    def test_result_ack_is_idempotent_preserves_raw_body_and_triggers_read_refresh(self):
        row=self.enqueue();job=self.claim();self.start(job);self.finish(job);self.finish(job)
        self.assertEqual(HTTP,self.queue.get(row['cloudCommandId'])['result']);self.assertGreater(len(self.store.claim_reads()),0)
        with self.assertRaises(CommandError):self.finish(job,{**HTTP,'httpStatus':500})
    def test_executor_database_loss_is_fail_closed_and_pause_survives_heartbeats(self):
        with self.assertRaisesRegex(CommandError,'manual_reconciliation'):self.queue.advertise({'enabled':True,'protocol':1,'ledgerId':'b'*32})
        self.queue.set_paused(True);self.queue.advertise({'enabled':True,'protocol':1,'ledgerId':LEDGER});self.enqueue();self.assertIsNone(self.queue.claim(LEDGER))
        self.queue.set_paused(False);self.assertIsNotNone(self.queue.claim(LEDGER))
        self.queue.advertise(None);self.assertFalse(self.queue.capability())
    def test_continue_requires_complete_fresh_matching_target_and_h3(self):
        body={'clientRequestId':'continue-request-123456','expectedTarget':{'batchId':'fixture-b','taskId':'fixture-t','attemptId':'fixture-a'}}
        with self.assertRaises(CommandError):self.enqueue(target='/api/control-commands',body=body)
        self.store.push({'target':'/api/dashboard/summary','version':1,'status':200,'body':{'autoRecovery':{'enabled':False,'state':'paused'},'currentTaskBox':{'batchId':'fixture-b','current':{'taskId':'fixture-t','attemptId':'fixture-a'}}},'sourceHealth':{'scanAgeSeconds':5}})
        row=self.enqueue(target='/api/control-commands',body=body);job=self.claim();self.now[0]+=56;self.store.heartbeat('healthy')
        with self.assertRaises(CommandError):self.start(job)
        self.assertEqual('leased',self.queue.get(row['cloudCommandId'])['state'])

    def test_continue_refuses_local_automatic_recovery_at_enqueue_and_send(self):
        body={'clientRequestId':'continue-request-123456','expectedTarget':{'batchId':'fixture-b','taskId':'fixture-t','attemptId':'fixture-a'}}
        snapshot={'currentTaskBox':{'batchId':'fixture-b','current':{'taskId':'fixture-t','attemptId':'fixture-a'}}}
        version=0
        def push(auto):
            nonlocal version
            version+=1
            value={**snapshot}
            if auto is not None:value['autoRecovery']=auto
            self.store.push({'target':'/api/dashboard/summary','version':version,'status':200,'body':value,'sourceHealth':{'scanAgeSeconds':0}})
        for auto in (None,{'enabled':True,'state':'idle'},{'enabled':False,'state':'recovering'}):
            push(auto)
            self.assertFalse(self.queue.health()['canContinue'])
            with self.assertRaisesRegex(CommandError,'home_auto_recovery'):
                self.enqueue(target='/api/control-commands',body=body)
        push({'enabled':False,'state':'paused'})
        row=self.enqueue(target='/api/control-commands',body=body);job=self.claim()
        push({'enabled':True,'state':'running'})
        with self.assertRaisesRegex(CommandError,'home_auto_recovery'):self.start(job)
        self.assertEqual('leased',self.queue.get(row['cloudCommandId'])['state'])
        with self.store.db() as db:self.assertEqual(0,db.execute("SELECT count(*) FROM commands WHERE state='sent'").fetchone()[0])

    def test_closed_command_contract_blocks_reset_cleanup_legacy_continue_and_ssrf(self):
        for path in ['/api/controls/testing/reset','/api/controls/pending-delete/empty','/api/controls/continue-current','http://evil.invalid/x','/api/controls/upload/rescan?x=1','/api/controls/tasks/%2e%2e/start']:
            with self.subTest(path=path),self.assertRaises(ValueError):command(path,{})
        with self.assertRaises(ValueError):command('/api/control-commands',{'clientRequestId':'fixture-request-123456','expectedTarget':{'taskId':'only-one'}})
        with self.assertRaises(ValueError):command('/api/controls/tasks/create',{'urls':'x'*(MAX_PAYLOAD+1)})

    def test_listing_omits_large_payloads_and_http_bodies(self):
        self.enqueue();job=self.claim();self.start(job);self.finish(job)
        row=self.queue.listing()['items'][0];self.assertIsNone(row['result']);self.assertNotIn('body',row)
        self.assertEqual(HTTP,self.queue.get(job['id'])['result'])
    def test_admin_pause_cancel_queued_and_drain_does_not_cancel_sent(self):
        from cloud.command_admin import pause,status
        first=self.enqueue();job=self.claim();self.start(job);second=self.enqueue('fixture-second-123456')
        answer=pause(self.queue,cancel_queued=True);self.assertFalse(answer['drained']);self.assertTrue(answer['commandsPaused'])
        self.assertEqual('cancelled',self.queue.get(second['cloudCommandId'])['state']);self.assertEqual('sent',self.queue.get(first['cloudCommandId'])['state'])
        self.finish(job);self.assertTrue(status(self.queue)['drained']);self.assertIsNone(self.queue.claim(LEDGER))

    def test_late_not_sent_receipt_can_close_unreclaimed_lease_but_not_a_new_token(self):
        self.enqueue();old=self.claim();self.now[0]+=61;self.store.heartbeat('healthy')
        self.queue.get(old['id']) # expiry returns the lease to queued, preserving its last token
        self.finish(old,{'kind':'not_sent','reason':'invalid_or_expired'});self.assertEqual('not_sent',self.queue.get(old['id'])['state'])
        self.enqueue('fixture-another-123456');old=self.claim();self.now[0]+=61;self.store.heartbeat('healthy');new=self.claim()
        with self.assertRaises(CommandError):self.finish(old,{'kind':'not_sent','reason':'invalid_or_expired'})
        self.assertNotEqual(old['lease'],new['lease'])
    def test_agent_rejection_reasons_close_the_lease_as_not_sent(self):
        # PR #24: the agent reports a rejected (never sent) job with these reasons.
        for index,reason in enumerate(('agent_rejected_identity','agent_rejected_contract')):
            self.enqueue('fixture-rejected-'+str(index)+'-123456');job=self.claim()
            self.finish(job,{'kind':'not_sent','reason':reason});self.assertEqual('not_sent',self.queue.get(job['id'])['state'])
        self.enqueue('fixture-rejected-x-123456');job=self.claim()
        with self.assertRaises(CommandError):self.finish(job,{'kind':'not_sent','reason':'agent_rejected_other'})
    def test_cloud_timeout_never_reissues_and_can_accept_late_definitive_reply(self):
        self.enqueue();job=self.claim();self.start(job);self.now[0]+=91
        self.assertEqual('unknown',self.queue.get(job['id'])['state'])
        self.queue.resolve(job['id'],'fixture-operator','fixture verified home request is stopped','CONFIRMED_HOME_REQUEST_STOPPED')
        self.finish(job);self.assertEqual('completed',self.queue.get(job['id'])['state'])

    def test_clock_rollback_does_not_extend_a_queued_command(self):
        row=self.enqueue();self.now[0]-=10;self.store.heartbeat('healthy')
        self.assertEqual('expired',self.queue.get(row['cloudCommandId'])['state']);self.assertIsNone(self.queue.claim(LEDGER))

    def test_activation_can_atomically_require_no_queued_business(self):
        self.queue.set_paused(True);row=self.enqueue()
        with self.assertRaisesRegex(CommandError,'empty_queue'):self.queue.resume(empty_only=True)
        self.assertTrue(self.queue.health()['commandsPaused']);self.queue.cancel(row['cloudCommandId'],'fixture-operator')
        self.queue.resume(empty_only=True);self.assertFalse(self.queue.health()['commandsPaused'])
