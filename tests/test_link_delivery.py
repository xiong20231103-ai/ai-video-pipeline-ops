import base64
import hashlib
import json
from unittest.mock import Mock
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from cloud.link_evidence import Evidence
from cloud.link_delivery import LinkDelivery
from contracts.commands import canonical

REQUEST='daily-test-request-12345'


def setup_delivery(tmp_path,replacement=False):
    evidence=Evidence(tmp_path)
    event=dict(source='test',platform='douyin',video_id='123',judge_round='v1:1',seq=1,url='https://www.douyin.com/video/123',review='confirmed',delivery='waiting')
    if replacement:event.update(replace_id='24',home_task_id='home-parent')
    identifier=evidence.ingest(event)['id']
    commands=Mock();commands.enqueue.return_value={'cloudCommandId':'command-1','state':'queued'}
    commands.get.return_value={'state':'unknown','result':None}
    return evidence,commands,LinkDelivery(evidence,commands),identifier,event['url']


class LinkDeliveryTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory(prefix='link-delivery-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)

    def test_daily_frozen_payload_and_strict_receipt(self):
        tmp_path=self.root
        e,q,d,i,url=setup_delivery(tmp_path)
        payload={'batchId':'fixed-batch','clientSubmissionId':REQUEST,'tasks':[{'taskId':'fixed-task','urls':[url]}]}
        d.prepare('user:1',REQUEST,[i],payload,'daily',True)
        d.dispatch('user:1',REQUEST)
        d.dispatch('user:1',REQUEST)
        assert q.enqueue.call_count==1
        assert e.listing()['items'][0]['delivery']=='waiting'
        q.get.return_value={'state':'sent','result':None}
        assert d.status('user:1',REQUEST)['sent'] is False
        assert e.listing()['items'][0]['delivery']=='waiting'
        receipt={'ok':True,'batchId':'fixed-batch','clientSubmissionId':REQUEST,'payloadHash':hashlib.sha256(canonical(payload).encode()).hexdigest(),'taskIds':['fixed-task']}
        q.get.return_value={'state':'completed','result':{'kind':'http','httpStatus':200,'bodyBase64':base64.b64encode(json.dumps(receipt).encode()).decode()}}
        assert d.status('user:1',REQUEST)['sent']
        assert e.listing()['items'][0]['delivery']=='sent'


    def test_replacement_parent_and_empty_ack(self):
        tmp_path=self.root
        e,q,d,i,url=setup_delivery(tmp_path,True)
        d.prepare('user:1',REQUEST,[i],{'urls':[url],'startNow':False},'replacement',True)
        d.dispatch('user:1',REQUEST)
        assert q.enqueue.call_args.args[2]=='/api/controls/tasks/home-parent/replenish'
        q.get.return_value={'state':'completed','result':{'kind':'http','httpStatus':200,'bodyBase64':base64.b64encode(b'{"submitted":[],"waiting":[]}').decode()}}
        assert d.status('user:1',REQUEST)['state']=='unknown'
        assert e.listing()['items'][0]['delivery']=='waiting'
        with self.assertRaises(ValueError):d.prepare('user:1','another-request-12345',[i],{'urls':[url]},'replacement',True)


    def test_link_substitution_and_confirmation_rejected(self):
        tmp_path=self.root
        e,q,d,i,url=setup_delivery(tmp_path,True)
        with self.assertRaises(ValueError):d.prepare('user:1',REQUEST,[i],{'urls':[url]},'replacement',False)
        with self.assertRaises(ValueError):d.prepare('user:1',REQUEST,[i],{'urls':['https://example.invalid']},'replacement',True)
        q.enqueue.assert_not_called()


    def test_lost_command_id_recovers_original_request(self):
        tmp_path=self.root
        e,q,d,i,url=setup_delivery(tmp_path,True)
        d.prepare('user:1',REQUEST,[i],{'urls':[url]},'replacement',True)
        q.enqueue.side_effect=[RuntimeError('lost cloud response'),{'cloudCommandId':'command-1','state':'queued'}]
        with self.assertRaises(RuntimeError):d.dispatch('user:1',REQUEST)
        d.dispatch('user:1',REQUEST)
        assert q.enqueue.call_args_list[0]==q.enqueue.call_args_list[1]


    def test_real_queue_permit_is_not_delivery_ack(self):
        tmp_path=self.root
        from cloud.store import Store
        from cloud.commands import CommandQueue
        evidence=Evidence(tmp_path/'evidence')
        identifier=evidence.ingest(dict(source='test',platform='douyin',video_id='123',judge_round='v1:1',seq=1,
                                       url='https://www.douyin.com/video/123',review='confirmed',delivery='waiting',
                                       replace_id='7',home_task_id='parent-1'))['id']
        store=Store(tmp_path/'console.db')
        queue=CommandQueue(store,enabled=True)
        ledger='1'*32
        queue.advertise({'enabled':True,'ledgerId':ledger,'protocol':1})
        store.heartbeat('healthy')
        delivery=LinkDelivery(evidence,queue)
        delivery.prepare('user:1',REQUEST,[identifier],{'urls':['https://www.douyin.com/video/123'],'startNow':False},'replacement',True)
        delivery.dispatch('user:1',REQUEST)
        claim=queue.claim(ledger)
        queue.permit(claim['id'],claim['lease'],ledger)
        assert not delivery.status('user:1',REQUEST)['sent']
        ack=base64.b64encode(json.dumps({'ok':True,'taskId':'child-1','batchId':'child-batch'}).encode()).decode()
        queue.finish(claim['id'],claim['lease'],ledger,{'kind':'http','httpStatus':200,'contentType':'application/json','bodyBase64':ack})
        assert delivery.status('user:1',REQUEST)['sent']
