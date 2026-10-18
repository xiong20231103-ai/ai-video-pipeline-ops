"""All values are inert fixture data; no real credentials or network calls."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi.testclient import TestClient
from cloud.app import create_app,HASHER,COOKIE,rate_identity
from starlette.requests import Request
from cloud.store import Store
from contracts.cache import cache_key

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='cloud-test-'); self.addCleanup(self.temp.cleanup)
        self.now=[1000.0]
        self.store=Store(Path(self.temp.name)/'console.db',clock=lambda:self.now[0])
        self.token='fixture-agent-value-not-a-real-credential'
        self.invite='fixture-invite-not-a-real-credential'
        self.password='fixture-password-not-a-real-credential'
        self.config={'origin':'https://console.fixture.ts.net','agent_token_sha256':hashlib.sha256(self.token.encode()).hexdigest(),'invite_hash':HASHER.hash(self.invite),'max_accounts':2}
        self.application=create_app(self.config,self.store,Path(__file__).parents[1]/'static')
        self.client=TestClient(self.application,base_url=self.config['origin'],headers={'Origin':self.config['origin']})
    def register(self,name='fixture-user'):
        return self.client.post('/auth/register',json={'username':name,'password':self.password,'invite':self.invite})
    def login(self,name='fixture-user'):
        return self.client.post('/auth/login',json={'username':name,'password':self.password})
    def item(self,version=1,body=None,**extra):
        return {'target':'/api/dashboard','version':version,'status':200,'body':body or {'updatedAt':'fixture-scan','state':'running'},'sourceScannedAt':'fixture-scan','sourceHealth':{'collectorRunning':True},**extra}
    def test_auth_static_and_origin_boundaries(self):
        self.assertEqual(303,self.client.get('/',follow_redirects=False).status_code)
        self.assertEqual(401,self.client.get('/static/app.js').status_code)
        self.assertEqual(401,self.client.get('/api/dashboard').status_code)
        self.assertEqual(403,self.client.post('/auth/register',json={},headers={'Origin':'https://foreign.invalid'}).status_code)
        self.assertEqual(200,self.register().status_code)
        login=self.login(); self.assertEqual(200,login.status_code)
        cookie=login.headers['set-cookie']
        for attribute in ['HttpOnly','Secure','SameSite=lax']: self.assertIn(attribute,cookie)
        self.assertIn('/cloud-readonly.js',self.client.get('/').text)
        self.assertEqual(200,self.client.get('/static/app.js').status_code)
    def test_registration_limit_is_atomic(self):
        encoded=HASHER.hash(self.password)
        def register(index):
            try: self.store.register('fixture-'+str(index),encoded,2); return True
            except ValueError: return False
        with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(register,range(4)))
        self.assertEqual(2,sum(results)); self.assertEqual(2,self.store.user_count())
        self.assertFalse(self.client.get('/auth/options').json()['registrationOpen'])
    def test_password_change_revokes_all_device_sessions(self):
        self.register(); self.login()
        token1=self.client.cookies.get(COOKIE)
        row=self.client.get('/auth/session').json()
        self.login(); token2=self.client.cookies.get(COOKIE)
        self.assertIsNotNone(self.store.session(token1)); self.assertIsNotNone(self.store.session(token2))
        result=self.client.post('/auth/password',headers={'X-CSRF-Token':row['csrf']},json={'oldPassword':self.password,'newPassword':'fixture-new-password-not-real'})
        self.assertEqual(403,result.status_code)  # CSRF belongs to the other device session.
        row=self.client.get('/auth/session').json()
        result=self.client.post('/auth/password',headers={'X-CSRF-Token':row['csrf']},json={'oldPassword':self.password,'newPassword':'fixture-new-password-not-real'})
        self.assertEqual(200,result.status_code)
        self.assertIsNone(self.store.session(token1)); self.assertIsNone(self.store.session(token2))
    def test_delete_account_revokes_session(self):
        self.register(); self.login(); token=self.client.cookies.get(COOKIE)
        self.store.delete_user('fixture-user'); self.assertIsNone(self.store.session(token))
    def test_login_failure_rate_limit_and_no_password_echo(self):
        for _ in range(10): response=self.client.post('/auth/login',json={'username':'missing','password':self.password})
        self.assertEqual(401,response.status_code); self.assertNotIn(self.password,response.text)
        self.assertEqual(429,self.client.post('/auth/login',json={'username':'missing','password':self.password}).status_code)
    def test_missing_cache_pending_is_single_flight_and_bounded(self):
        self.register(); self.login()
        first=self.client.get('/api/dashboard?date=10.16')
        second=self.client.get('/api/dashboard?date=10.16')
        self.assertEqual(202,first.status_code); self.assertEqual(first.json()['requestId'],second.json()['requestId'])
        key=cache_key('GET','/api/dashboard?date=10.16')
        self.assertEqual(first.json()['requestId'],self.store.enqueue_read(key))
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids=list(pool.map(lambda _:self.store.enqueue_read(key),range(16)))
        self.assertEqual(1,len(set(ids)))
        with self.assertRaises(ValueError): self.store.enqueue_read(cache_key('GET','/api/dashboard?date=10.15'),maximum=1)
    def test_reads_expire_and_do_not_lease_twice_before_timeout(self):
        key=cache_key('GET','/api/dashboard'); old=self.store.enqueue_read(key)
        self.assertEqual(1,len(self.store.claim_reads())); self.assertEqual([],self.store.claim_reads())
        self.now[0]+=181
        self.assertEqual([],self.store.claim_reads()); self.assertNotEqual(old,self.store.enqueue_read(key))
    def test_versions_survive_reopen_and_old_backfill_cannot_replace_new(self):
        self.store.push(self.item(3)); self.assertEqual('old_version_ignored',self.store.push(self.item(2,{'state':'old'})))
        reopened=Store(self.store.path,clock=lambda:self.now[0])
        self.assertEqual(3,reopened.response(cache_key('GET','/api/dashboard'))['version'])
    def test_304_refreshes_fetch_success_not_source_scan_or_content_change(self):
        key=cache_key('GET','/api/dashboard'); self.store.push(self.item())
        before=self.store.response(key); self.now[0]+=10
        self.store.push(self.item(2,status=304,sourceScannedAt='invented-later-scan'))
        after=self.store.response(key)
        self.assertEqual(before['body'],after['body']); self.assertEqual(before['last_changed'],after['last_changed'])
        self.assertEqual('fixture-scan',after['source_scanned_at']); self.assertEqual(1010,after['last_success'])
        with self.assertRaises(ValueError): self.store.push({**self.item(),'target':'/api/events','status':304})
    def test_delayed_backfill_does_not_look_fresh_and_heartbeat_is_independent(self):
        key=cache_key('GET','/api/dashboard'); self.store.push(self.item(captureAgeSeconds=3600))
        self.store.heartbeat('unavailable')
        self.assertEqual(3600,self.now[0]-self.store.response(key)['last_success'])
        health=self.store.health(); self.assertTrue(health['agentOnline']); self.assertEqual('unavailable',health['engineState'])
        self.now[0]+=46; self.assertFalse(self.store.health()['agentOnline'])
    def test_etag_304_has_freshness_headers_and_same_original_body(self):
        self.register(); self.login(); self.store.push(self.item())
        result=self.client.get('/api/dashboard'); self.assertEqual({'updatedAt':'fixture-scan','state':'running'},result.json())
        later=self.client.get('/api/dashboard',headers={'If-None-Match':result.headers['etag']})
        self.assertEqual(304,later.status_code); self.assertEqual('',later.text)
        self.assertIn('x-source-scanned-at',later.headers)
    def test_agent_auth_and_invalid_metadata_do_not_leak(self):
        self.assertEqual(401,self.client.post('/agent/push',json=self.item()).status_code)
        auth={'Authorization':'Bearer '+self.token}
        self.assertEqual(200,self.client.post('/agent/push',json=self.item(),headers=auth).status_code)
        bad=self.client.post('/agent/push',json=self.item(2,sourceScannedAt='scan\r\nInjected: value'),headers=auth)
        self.assertEqual(400,bad.status_code); self.assertNotIn(self.token,bad.text)
    def test_all_home_writes_fail_closed_even_with_valid_session_csrf(self):
        self.register(); self.login(); csrf=self.client.get('/auth/session').json()['csrf']
        for route in ['/api/control-commands','/api/controls/tasks/create','/api/controls/testing/reset','/api/controls/production-files/recycle']:
            response=self.client.post(route,json={},headers={'X-CSRF-Token':csrf})
            self.assertEqual(403,response.status_code)
        self.assertFalse(self.client.get('/console/status').json()['canContinue'])
        self.assertFalse(self.client.get('/console/status').json()['canCleanup'])
    def test_health_preserves_receiver_contract_and_fails_closed_if_missing(self):
        self.assertEqual(503,self.client.get('/api/health').status_code)
        self.store.push({**self.item(),'target':'/api/health','body':{'ok':True}})
        self.assertEqual(503,self.client.get('/api/health').status_code)
        body={'ok':True,'formalBatchTotal':120,'projectTotals':{'fixture-project':3},'contractVersion':'fixture-v1'}
        self.store.push({**self.item(2),'target':'/api/health','body':body})
        self.assertEqual(body,self.client.get('/api/health').json())
        self.now[0]+=61; self.assertEqual(503,self.client.get('/api/health').status_code)
    def test_unconfigured_factory_fails_closed(self):
        with self.assertRaises(RuntimeError): create_app({'origin':'https://fixture.ts.net'})

    def test_readiness_is_not_an_extra_anonymous_tailnet_api(self):
        self.assertEqual(403,self.client.get('/ready').status_code)
        internal=TestClient(self.application,base_url='http://127.0.0.1:8000',client=('127.0.0.1',12345))
        self.assertEqual(200,internal.get('/ready').status_code)

    def test_oversize_body_rejected_and_future_heartbeat_not_online(self):
        response=self.client.post('/agent/push',content=b'x'*(8*1024*1024+1),headers={'Authorization':'Bearer '+self.token})
        self.assertEqual(413,response.status_code)
        self.store.heartbeat('healthy'); self.now[0]-=1
        self.assertFalse(self.store.health()['agentOnline'])

    def test_test_guard_still_blocks_real_home_connections(self):
        import socket
        with socket.socket() as connection:
            with self.assertRaisesRegex(RuntimeError,'Production network/process execution blocked'):
                connection.connect(('127.0.0.1',8765))

    def test_only_authenticated_visible_page_reads_extend_viewer_lease(self):
        self.assertFalse(self.store.viewer_state()['viewerActive'])
        self.client.get('/login'); self.client.get('/api/health')
        self.assertFalse(self.store.viewer_state()['viewerActive'])
        self.register(); self.login(); self.client.get('/api/dashboard')
        self.assertEqual(120,self.store.viewer_state()['viewerLeaseSeconds'])
        self.now[0]+=119
        self.client.get('/console/status',headers={'X-Ops-Page-Visible':'false'})
        self.client.get('/api/dashboard/summary',headers={'X-Ops-Page-Visible':'false'})
        self.assertEqual(1,self.store.viewer_state()['viewerLeaseSeconds'])
        self.now[0]+=1; self.assertFalse(self.store.viewer_state()['viewerActive'])
        auth={'Authorization':'Bearer '+self.token}
        result=self.client.post('/agent/heartbeat',json={'engineState':'healthy'},headers=auth)
        self.assertFalse(result.json()['viewerActive'])
        self.assertFalse(self.client.get('/agent/fetch-requests',headers=auth).json()['viewerActive'])
        self.client.get('/console/status',headers={'X-Ops-Page-Visible':'true'})
        self.assertTrue(self.client.post('/agent/heartbeat',json={},headers=auth).json()['viewerActive'])
        self.now[0]-=1; self.assertFalse(self.store.viewer_state()['viewerActive'])

    def test_viewer_lease_survives_reopen_but_does_not_become_permanent(self):
        self.store.page_view(); self.now[0]+=100
        reopened=Store(self.store.path,clock=lambda:self.now[0])
        self.assertEqual(20,reopened.viewer_state()['viewerLeaseSeconds'])
        self.now[0]+=20; self.assertFalse(reopened.viewer_state()['viewerActive'])

    def test_serve_user_rate_limits_are_independent_and_same_user_shares_budget(self):
        proxy=TestClient(self.application,base_url=self.config['origin'],client=('127.0.0.1',12345),headers={'Origin':self.config['origin'],'X-Forwarded-Proto':'https','X-Forwarded-For':'100.64.1.10'})
        data={'username':'missing','password':self.password}
        for _ in range(10): self.assertEqual(401,proxy.post('/auth/login',json=data,headers={'Tailscale-User-Login':'fixture-a@example.invalid'}).status_code)
        self.assertEqual(429,proxy.post('/auth/login',json=data,headers={'Tailscale-User-Login':'fixture-a@example.invalid','X-Forwarded-For':'100.64.1.11'}).status_code)
        self.assertEqual(401,proxy.post('/auth/login',json=data,headers={'Tailscale-User-Login':'fixture-b@example.invalid'}).status_code)
        # Tagged nodes have no user header; distinct validated Serve IPs get distinct buckets.
        self.assertEqual(401,proxy.post('/auth/login',json=data,headers={'X-Forwarded-For':'100.64.2.1'}).status_code)
        self.assertEqual(401,proxy.post('/auth/login',json=data,headers={'X-Forwarded-For':'fd7a:115c:a1e0::1'}).status_code)

    def test_remote_or_malformed_proxy_headers_cannot_rotate_rate_bucket(self):
        def request(peer,headers):
            return Request({'type':'http','client':(peer,1234),'headers':[(key.lower().encode(),value.encode()) for key,value in headers.items()]})
        forged={'X-Forwarded-Proto':'https','X-Forwarded-For':'100.64.1.10','Tailscale-User-Login':'fixture@example.invalid'}
        self.assertEqual(rate_identity(request('100.64.2.10',forged)),rate_identity(request('100.64.2.10',{})))
        for bad in ['100.64.1.1, 100.64.1.2','foreign.invalid','8.8.8.8','127.0.0.1','']:
            self.assertEqual(rate_identity(request('127.0.0.1',{**forged,'X-Forwarded-For':bad})),rate_identity(request('127.0.0.1',{})))
