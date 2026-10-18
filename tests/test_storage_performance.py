import io
import json
import sqlite3
import threading
import time
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from agent.readonly import Ledger,ReadOnlyAgent
from cloud.store import Store
from contracts.cache import cache_key,semantic_hash
import test_cloud_readonly as cloud_tests

class StorageTests(unittest.TestCase):
    def test_old_archive_is_removed_and_pages_reclaimed_without_losing_unsent_payload(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'agent.db'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE sources(target TEXT PRIMARY KEY,body TEXT NOT NULL,etag TEXT NOT NULL,scanned TEXT NOT NULL)')
                db.execute('INSERT INTO sources VALUES(?,?,?,?)',('/api/dashboard',json.dumps({'large':'x'*6_000_000}),'fixture','scan'))
                db.execute('CREATE TABLE versions(target TEXT PRIMARY KEY,version INTEGER NOT NULL)')
                db.execute('CREATE TABLE outbox(target TEXT PRIMARY KEY,payload TEXT NOT NULL,wall REAL NOT NULL,monotonic REAL NOT NULL)')
                db.execute('INSERT INTO versions VALUES(?,?)',('/api/health',7))
                db.execute('INSERT INTO outbox VALUES(?,?,?,?)',('/api/health',json.dumps({'target':'/api/health','version':7,'status':200,'body':{'unsent':'preserve'}}),time.time(),time.monotonic()))
                db.commit()
            before=path.stat().st_size
            ledger=Ledger(path)
            self.assertEqual({'unsent':'preserve'},ledger.next()['body'])
            ledger.acknowledge('/api/health',7)
            with ledger.db() as db:
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='sources'").fetchone())
                self.assertNotIn('body',{row['name'] for row in db.execute('PRAGMA table_info(source_validators)')})
            self.assertLess(path.stat().st_size,before/10)
            self.assertEqual('fixture',ledger.source('/api/dashboard')['etag'])
            ledger.enqueue('/api/dashboard',200,{'data':'not-retained-after-ack'})
            item=ledger.next();ledger.acknowledge(item['target'],item['version'])
            self.assertIsNone(ledger.next())
            self.assertNotIn('not-retained-after-ack',json.dumps(ledger.source('/api/dashboard')))
            # Old code rollback recreates its own empty sources; it cannot use
            # the new validators as if an archived response body still existed.
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE sources(target TEXT PRIMARY KEY,body TEXT NOT NULL,etag TEXT NOT NULL,scanned TEXT NOT NULL)')
                db.commit()
            self.assertIsNotNone(Ledger(path).source('/api/dashboard'))

    def test_pending_200_survives_304_then_304_has_no_body_after_ack(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db'); body={'updatedAt':'scan','some':'value'}
            ledger.enqueue('/api/dashboard',200,body,'tag')
            ledger.enqueue('/api/dashboard',304,None,'tag')
            item=ledger.next();self.assertEqual(200,item['status']);self.assertEqual(body,item['body'])
            ledger.acknowledge(item['target'],item['version'])
            ledger.enqueue('/api/dashboard',304,None,'tag')
            item=ledger.next();self.assertEqual(304,item['status']);self.assertIsNone(item['body'])
            self.assertEqual(semantic_hash(body),item['semanticHash']);self.assertEqual('scan',item['sourceScannedAt'])

    def test_limit_evicts_oldest_and_records_persistent_counter(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db',max_outbox_bytes=1800)
            for index in range(6):
                ledger.enqueue('/api/dashboard?batchId='+str(index),200,{'data':'汉'*100})
            stats=ledger.storage();self.assertLessEqual(stats['outboxBytes'],1800);self.assertGreater(stats['outboxDropped'],0)
            self.assertNotEqual('/api/dashboard?batchId=0',ledger.next()['target'])
            with ledger.db() as db:self.assertIsNotNone(db.execute("SELECT 1 FROM outbox WHERE target='/api/dashboard?batchId=5'").fetchone())
            self.assertEqual(6-stats['pendingItems'],stats['outboxDropped'])
            self.assertEqual(stats['outboxDropped'],Ledger(ledger.path,max_outbox_bytes=1800).storage()['outboxDropped'])

    def test_wal_read_does_not_compete_for_reserved_writer_lock(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db');ledger.enqueue('/api/dashboard',200,{'n':1})
            external=sqlite3.connect(ledger.path);external.execute('BEGIN IMMEDIATE')
            try:
                started=time.monotonic();self.assertIsNotNone(ledger.next())
                self.assertLess(time.monotonic()-started,0.5)
                with self.assertRaisesRegex(OSError,'temporarily busy'):ledger.enqueue('/api/dashboard',200,{'n':2})
            finally:external.rollback();external.close()
            ledger.enqueue('/api/dashboard',200,{'n':3});self.assertEqual(2,ledger.next()['version'])
            # Do not hide SQL programming/schema errors behind a retry.
            with self.assertRaises(sqlite3.OperationalError):
                with ledger.db(True) as db:db.execute('SELECT * FROM nonexistent_fixture_table')

    def test_foreground_upload_outranks_old_history_backlog(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db')
            ledger.enqueue('/api/dashboard?date=10.1',200,{'n':1})
            ledger.enqueue('/api/dashboard?batchId=fixture',200,{'n':2},priority=10)
            self.assertEqual('/api/dashboard?batchId=fixture',ledger.next()['target'])

    def test_four_real_threads_share_one_writer_and_versions_stay_monotonic(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db')
            def worker(index):
                for n in range(20):
                    ledger.enqueue('/api/dashboard',200,{'i':index,'n':n})
                    item=ledger.next()
                    if item:ledger.acknowledge(item['target'],item['version'])
                    ledger.note_request('/api/dashboard',8765,'active','fixture',0.001,False)
            with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(worker,range(4)))
            with ledger.db() as db:
                self.assertEqual(80,db.execute('SELECT version FROM versions').fetchone()[0])
                self.assertEqual(80,db.execute('SELECT sum(count) FROM request_stats').fetchone()[0])

    def test_304_without_cloud_base_refetches_body_instead_of_inventing_it(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db');ledger.enqueue('/api/dashboard',200,{'n':1})
            item=ledger.next();ledger.acknowledge(item['target'],item['version'])
            ledger.enqueue('/api/dashboard',304,None)
            store=Store(Path(folder)/'cloud.db')
            with self.assertRaisesRegex(ValueError,'304_without_body'):store.push(ledger.next())

class PriorityTests(unittest.TestCase):
    def test_slow_periodic_safety_does_not_block_foreground_and_same_target_is_singleflight(self):
        with TemporaryDirectory() as folder:
            agent=ReadOnlyAgent('https://fixture.ts.net','fixture',folder)
            entered=threading.Event();release=threading.Event();calls=[]
            def home(target,**kw):
                calls.append(target)
                if target=='/api/safety':entered.set();release.wait(3)
                return 200,{},''
            with patch.object(agent,'home',side_effect=home):
                slow=threading.Thread(target=agent.collect,args=('/api/safety',));slow.start()
                try:
                    self.assertTrue(entered.wait(1));started=time.monotonic()
                    agent.collect('/api/dashboard?batchId=fixture',reason='on-demand')
                    self.assertLess(time.monotonic()-started,0.5)
                    agent.collect('/api/safety',reason='on-demand')
                    self.assertEqual(1,calls.count('/api/safety'))
                finally:release.set();slow.join(3)
            self.assertIsNotNone(agent.ledger.next())

    def test_safety_demand_routes_to_periodic_channel_and_box_priority_is_first(self):
        with TemporaryDirectory() as folder:
            agent=ReadOnlyAgent('https://fixture.ts.net','fixture',folder)
            agent.queue_demand('/api/safety')
            agent.queue_demand('/api/overview')
            agent.queue_demand('/api/dashboard?batchId=fixture')
            self.assertEqual(['/api/safety'],agent.slow_demands)
            self.assertEqual('/api/dashboard?batchId=fixture',agent.demands.get_nowait()[2])
            self.assertEqual('/api/overview',agent.demands.get_nowait()[2])

    def test_prefetch_stops_on_lease_expiry_or_waiting_foreground(self):
        with TemporaryDirectory() as folder:
            agent=ReadOnlyAgent('https://fixture.ts.net','fixture',folder)
            now=[0];agent.schedule.clock=lambda:now[0]
            agent.prefetch_targets=['/api/dashboard?batchId=fixture']
            self.assertIsNone(agent.prefetch())
            agent.schedule.update_viewer({'viewerActive':True,'viewerLeaseSeconds':120})
            agent.pending_demands.add('/api/safety');self.assertIsNone(agent.prefetch())
            agent.pending_demands.clear();self.assertIsNotNone(agent.prefetch())
            agent.prefetch_targets=['/api/dashboard?batchId=other'];now[0]=121
            self.assertIsNone(agent.prefetch())

    def test_partial_http_response_is_retryable_but_other_http_errors_are_diagnostic(self):
        import http.client
        with TemporaryDirectory() as folder:
            agent=ReadOnlyAgent('https://fixture.ts.net','fixture',folder)
            with patch.object(agent.transport,'open',side_effect=http.client.IncompleteRead(b'partial-sensitive')):
                with self.assertRaisesRegex(OSError,'Incomplete cloud'):agent.cloud('/agent/heartbeat',{})
                with self.assertRaisesRegex(OSError,'Incomplete home'):agent.home('/api/dashboard')
            with patch.object(agent.transport,'open',side_effect=http.client.CannotSendRequest('fixture programming error')):
                with self.assertRaises(http.client.CannotSendRequest):agent.cloud('/agent/heartbeat',{})

class CloudPerformanceTests(cloud_tests.CloudTests):
    # Re-use authentication helpers, while avoiding duplicated inherited tests
    # in discovery by assigning them below after class construction.
    def complete(self,batch='fixture'):
        box={'batchId':batch,'state':'completed','projectCount':1,'completedProjects':1,'totalVideos':2,'completedVideos':2,
             'completionReceipt':{'status':'completed_verified','uploadStatus':'uploaded_pending_verification','receiptHash':'a'*64}}
        return {'selectedBatchId':batch,'selectedDate':'10.16','pipeline':{'items':['archived']},'taskBoxes':{'selected':box},'controls':{'old':True}}
    def test_archive_hits_forever_and_overlays_current_controls_not_stale_ones(self):
        self.register();self.login()
        self.store.push(self.item(body={'controls':{'current':True},'taskBoxes':{'items':[]}}))
        self.store.push({**self.item(),'target':'/api/dashboard?batchId=fixture','body':self.complete()})
        self.now[0]+=86400*60
        self.login()
        for _ in range(5):
            response=self.client.get('/api/dashboard?date=10.16&batchId=fixture')
            self.assertEqual(200,response.status_code);self.assertEqual('completed-uploaded',response.headers['x-archived-box'])
            self.assertEqual({'current':True},response.json()['controls'])
            self.assertEqual(['archived'],response.json()['pipeline']['items'])
        self.assertEqual([],self.store.claim_reads())
        self.assertEqual(202,self.client.get('/api/dashboard?date=10.15&batchId=fixture').status_code)
    def test_incomplete_upload_or_missing_identity_cannot_become_permanent(self):
        for field,value in [('uploadStatus','upload_pending'),('receiptHash','')]:
            body=self.complete();body['taskBoxes']['selected']['completionReceipt'][field]=value
            self.assertIsNone(self.store.completed_box(body,'fixture'))
        body=self.complete();body['taskBoxes']['selected']['completedVideos']=1
        self.assertIsNone(self.store.completed_box(body,'fixture'))
        self.assertIsNone(self.store.completed_box(self.complete(),'other'))
    def test_prefetch_latest_ten_cloud_only_and_only_when_visible(self):
        boxes=[{'batchId':str(n)} for n in range(15)]
        self.store.push(self.item(body={'taskBoxes':{'items':boxes}}))
        self.assertEqual([],self.store.prefetch_targets());self.store.page_view()
        targets=self.store.prefetch_targets();self.assertEqual(10,len(targets));self.assertTrue(targets[-1].endswith('=9'))
        self.store.push({**self.item(),'target':targets[0],'body':self.complete('0')})
        self.assertNotIn(targets[0],self.store.prefetch_targets())
        self.now[0]+=121;self.assertEqual([],self.store.prefetch_targets())
    def test_long_poll_wakes_in_under_one_second_and_never_holds_db_writer(self):
        results=[]
        thread=threading.Thread(target=lambda:results.extend(self.store.wait_reads(2)))
        thread.start();time.sleep(0.05);started=time.monotonic()
        self.store.enqueue_read(cache_key('GET','/api/dashboard?batchId=fixture'))
        thread.join(1);self.assertFalse(thread.is_alive());self.assertLess(time.monotonic()-started,1)
        self.assertEqual(1,len(results))
    def test_only_bounded_numeric_storage_metrics_are_retained_in_cloud(self):
        auth={'Authorization':'Bearer '+self.token}
        result=self.client.post('/agent/heartbeat',headers=auth,json={'engineState':'healthy','storage':{'outboxDropped':3,'databaseBytes':32768}})
        self.assertEqual(200,result.status_code)
        self.assertEqual(3,self.store.health()['agentStorage']['outboxDropped'])
        for invalid in [{'body':'fixture-sensitive'},{'databaseBytes':-1},{'databaseBytes':True}]:
            self.assertEqual(400,self.client.post('/agent/heartbeat',headers=auth,json={'storage':invalid}).status_code)

    def test_cloud_304_hash_mismatch_requires_body_and_preserves_previous_cache(self):
        self.store.push(self.item())
        with self.assertRaisesRegex(ValueError,'304_validator_mismatch'):
            self.store.push(self.item(2,status=304,body=None,semanticHash='different'))
        self.assertEqual(1,self.store.response(cache_key('GET','/api/dashboard'))['version'])

for name in list(cloud_tests.CloudTests.__dict__):
    if name.startswith('test_'):setattr(CloudPerformanceTests,name,None)
