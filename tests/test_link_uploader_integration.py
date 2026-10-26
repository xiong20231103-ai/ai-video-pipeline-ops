"""Real private uploader -> public ASGI routes, entirely in memory/temp.

Set OPS_LINK_UPLOADER_SOURCE to the reviewed cloud_sync.py to include these
tests. No private code, credentials, business records or HTTP servers vendored.
"""
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from cloud.link_routes import mount_links


@unittest.skipUnless(os.environ.get('OPS_LINK_UPLOADER_SOURCE'), 'Private uploader source explicitly required')
class UploaderIntegrationTests(unittest.TestCase):
    def setUp(self):
        source=Path(os.environ['OPS_LINK_UPLOADER_SOURCE']).resolve()
        expected=os.environ.get('OPS_LINK_UPLOADER_SHA256')
        if expected:self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),expected)
        spec=importlib.util.spec_from_file_location('fixture_company_uploader',source)
        self.uploader=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.uploader)
        temporary=TemporaryDirectory(prefix='link-wire-fixture-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.now=datetime(2026,10,25,9,0,tzinfo=timezone.utc).timestamp() # 17:00 Shanghai
        self.box=self.uploader.Outbox(self.root/'outbox',clock=lambda:self.now)
        app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        mount_links(app,{'link_evidence_enabled':True,'link_evidence_dir':str(self.root/'cloud')},lambda r:None,lambda *a:None)
        self.store=app.state.link_evidence;self.store.clock=lambda:self.now
        self.client=self.enterContext(TestClient(app))
        self.enterContext(patch.dict(os.environ,{'LINK_EVIDENCE_TOKEN':'fixture-wire-token'}))
        self.enterContext(patch.object(self.uploader,'safe_open',self.transport))
        self.requests=[]

    def transport(self,request,timeout=20):
        self.requests.append((request.get_method(),request.full_url))
        self.assertEqual(request.full_url,'https://cloud.invalid/api/links/ingest')
        response=self.client.request(request.get_method(),'/api/links/ingest',content=request.data,headers=dict(request.header_items()))
        if response.status_code>=400:
            raise HTTPError('https://cloud.invalid',response.status_code,'fixture',{},BytesIO(response.content))
        return BytesIO(response.content)

    def event(self,**extra):
        return dict(source='fixture-company',platform='douyin',video_id='123',judge_round='v1:1',
                    url='https://www.douyin.com/video/123',review='pending',delivery='not_applicable',**extra)

    def image(self):
        out=BytesIO();Image.new('RGB',(1800,900),'blue').save(out,'PNG');return out.getvalue()

    def upload(self,token='fixture-wire-token'):
        return self.box.upload_once('https://cloud.invalid',token)

    def test_18_clock_startup_catchup_deleted_original_and_logged_outbox_only(self):
        source=self.root/'original.png';source.write_bytes(self.image())
        self.box.enqueue(self.event(),source.read_bytes());source.unlink()
        self.assertEqual(self.upload(),0);self.assertEqual(self.requests,[])
        self.now+=24*3600 # missed 18:00, next startup before today's 18:00
        self.assertEqual(self.upload(),1)
        row=self.store.listing()['items'][0]
        response=self.client.get('/api/links/shots/'+row['sha'])
        self.assertEqual(response.status_code,200)
        with Image.open(BytesIO(response.content)) as image:
            self.assertEqual(image.format,'JPEG');self.assertLessEqual(max(image.size),1600)
        self.assertLessEqual(len(response.content),600*1024)
        with self.box.db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)

    def test_auth_failure_retries_without_token_logs(self):
        self.box.enqueue(self.event(),due_at=1)
        with self.assertLogs(self.uploader.LOG,level='WARNING') as logs:
            self.assertEqual(self.upload('fixture-wrong-secret'),0)
        self.assertNotIn('fixture-wrong-secret','\n'.join(logs.output))
        self.assertEqual(self.store.listing()['total'],0)
        self.now+=120;self.assertEqual(self.upload(),1)
        self.assertEqual(self.store.listing()['total'],1)

    def test_capacity_retry_after_newer_decision_repairs_only_image(self):
        self.store.cap=1
        self.box.enqueue(self.event(),self.image(),due_at=1)
        self.assertEqual(self.upload(),0)
        self.assertEqual(self.store.listing()['total'],1)
        self.assertTrue(self.store.listing()['capacityReached'])
        decided=dict(self.event(),review='confirmed',delivery='waiting',decidedAt=self.now)
        self.box.enqueue(decided,due_at=1)
        self.assertEqual(self.upload(),1)
        row=self.store.listing()['items'][0];identifier=row['id']
        self.assertEqual((row['seq'],row['review'],row['delivery']),(2,'confirmed','waiting'))
        self.store.cap=1024*1024;self.now+=120
        self.assertEqual(self.upload(),1)
        row=self.store.listing()['items'][0]
        self.assertEqual((row['id'],row['seq'],row['review'],row['delivery']),(identifier,2,'confirmed','waiting'))
        self.assertIsNotNone(row['sha'])

    def test_lost_ack_retry_does_not_duplicate_link(self):
        self.box.enqueue(self.event(),self.image(),due_at=1)
        def lost_ack(request,timeout=20):
            self.transport(request,timeout).close()
            raise OSError('fixture-transport-failed-after-commit')
        with patch.object(self.uploader,'safe_open',lost_ack):self.assertEqual(self.upload(),0)
        self.assertEqual(self.store.listing()['total'],1)
        self.now+=120;self.assertEqual(self.upload(),1)
        self.assertEqual(self.store.listing()['total'],1)

    def test_real_capture_hook_preserves_confirmed_waiting_and_decision_time(self):
        source=Path(os.environ['OPS_LINK_UPLOADER_SOURCE']).with_name('cloud_events.py')
        spec=importlib.util.spec_from_file_location('fixture_company_events',source)
        hooks=importlib.util.module_from_spec(spec);spec.loader.exec_module(hooks)
        candidate={'video_id':'123','judge_version':'v1','round':1,'url':'https://www.douyin.com/video/123',
                   'category':'fixture','project':'fixture','material':'fixture',
                   'review_state':'accepted','status':'done','replace_id':'7','created_at':int(self.now*1000)}
        class Database:
            def one(self,sql,args):
                if 'FROM candidates' in sql:return dict(candidate)
                if 'FROM replacements' in sql:return {'home_task_id':'fixture-home-task','sent_urls':'[]','need':5}
                if 'FROM v13_sent' in sql:return None
                raise AssertionError('Unexpected hook query')
        with patch.dict('sys.modules',{'cloud_sync':self.uploader}), \
             patch.dict(os.environ,{'MJ_CLOUD_OUTBOX':str(self.box.root),'MJ_CLOUD_SOURCE':'fixture-company'}), \
             patch.object(self.uploader,'Outbox',return_value=self.box):
            hooks.capture(Database(),'123','v1',decided_at=self.now)
        self.now+=3600;self.assertEqual(self.upload(),1)
        row=self.store.listing()['items'][0]
        self.assertEqual((row['review'],row['delivery']),('confirmed','waiting'))
        self.assertEqual(row['decided'],self.now-3600)
        self.assertEqual(row['payload']['home_task_id'],'fixture-home-task')


if __name__=='__main__':unittest.main()
