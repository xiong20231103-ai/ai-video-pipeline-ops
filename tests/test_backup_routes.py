from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi.testclient import TestClient
from cloud.app import create_app,HASHER
from cloud.store import Store
from test_backup_vault import manifest,CMS

class BackupRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=datetime(2026,10,18,tzinfo=timezone.utc).timestamp()
        self.store=Store(Path(self.temp.name)/'console.db',clock=lambda:self.now)
        self.config={'origin':'https://fixture.ts.net','agent_token_sha256':hashlib.sha256(b'fixture-token').hexdigest(),'invite_hash':HASHER.hash('fixture-invitation')}
        self.app=create_app(self.config,store=self.store);self.client=TestClient(self.app,base_url=self.config['origin'])
        self.auth={'Authorization':'Bearer fixture-token'};self.vault=self.app.state.backups
    def login(self):
        self.store.register('fixture',HASHER.hash('fixture-password'),2)
        result=self.client.post('/auth/login',headers={'Origin':self.config['origin']},json={'username':'fixture','password':'fixture-password'})
        self.assertEqual(200,result.status_code)
        return {'Origin':self.config['origin'],'X-CSRF-Token':self.client.get('/auth/session').json()['csrf']}
    def test_auth_csrf_and_no_home_write_or_plaintext_route(self):
        self.assertEqual(401,self.client.get('/console/backups').status_code)
        self.assertEqual(401,self.client.post('/agent/backups/reserve',json={}).status_code)
        headers=self.login();self.assertEqual(403,self.client.post('/console/backups/request').status_code)
        request=self.client.post('/console/backups/request',headers=headers).json()['requestId']
        heartbeat=self.client.post('/agent/heartbeat',headers=self.auth,json={'engineState':'healthy','backupState':{'phase':'waiting_configuration'}})
        self.assertEqual(request,heartbeat.json()['backupRequest'])
        self.assertEqual('waiting_configuration',self.client.get('/console/backups').json()['agentState']['phase'])
        self.assertEqual(403,self.client.post('/api/control-commands',headers=headers,json={}).status_code)
        self.assertEqual(404,self.client.get('/console/backups/key').status_code)
        for invalid in [{'phase':'completed','token':'private'}, {'phase':'completed','sourceBytes':True}]:
            self.assertEqual(400,self.client.post('/agent/heartbeat',headers=self.auth,json={'backupState':invalid}).status_code)
    def test_real_asgi_stream_upload_retry_publish_verify_and_download(self):
        headers=self.login();data=manifest(datetime.fromtimestamp(self.now,timezone.utc).isoformat())
        response=self.client.post('/agent/backups/reserve',headers=self.auth,json=data);self.assertEqual(200,response.status_code,response.text)
        for item in data['artifacts']:
            url='/agent/backups/'+data['packageId']+'/'+item['name']
            for _ in range(2):self.assertEqual(200,self.client.put(url,headers=self.auth,content=CMS).status_code)
        request=self.client.post('/console/backups/request',headers=headers).json()['requestId']
        response=self.client.post('/agent/backups/'+data['packageId']+'/publish',headers=self.auth,json={'requestId':request})
        self.assertEqual(200,response.status_code,response.text);self.assertIsNone(self.vault.pending_request())
        self.assertTrue(self.client.post('/console/backups/'+data['packageId']+'/verify',headers=headers).json()['verified'])
        for name in ['ledger.cms','configuration.cms','manifest.json']:
            response=self.client.get('/console/backups/'+data['packageId']+'/'+name)
            self.assertEqual(200,response.status_code);self.assertEqual(hashlib.sha256(response.content).hexdigest(),response.headers['x-content-sha256'])
        self.assertEqual(1,len(self.client.get('/console/backups').json()['items']))
    def test_failed_upload_not_listed_and_path_injection_refused(self):
        self.login();data=manifest(datetime.fromtimestamp(self.now,timezone.utc).isoformat())
        self.client.post('/agent/backups/reserve',headers=self.auth,json=data)
        response=self.client.put('/agent/backups/'+data['packageId']+'/ledger.cms',headers=self.auth,content=b'x'*len(CMS))
        self.assertEqual(400,response.status_code)
        self.assertEqual([],self.client.get('/console/backups').json()['items'])
        self.assertEqual(404,self.client.get('/console/backups/'+data['packageId']+'/config.json').status_code)

