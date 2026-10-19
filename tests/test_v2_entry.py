"""Cloud-only entry and anonymous surface; synthetic values and isolated DB only."""
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from fastapi.testclient import TestClient
from cloud.app import create_app, HASHER
from cloud.store import Store
from cloud.entry import safe_destination, login_location

class EntryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='v2-entry-test-'); self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'console.db')
        self.config={'origin':'https://entry.fixture.invalid','agent_token_sha256':hashlib.sha256(b'synthetic-only').hexdigest(),'invite_hash':HASHER.hash('synthetic-invite-only')}
        self.static=Path(__file__).parents[1]/'static'
        self.app=create_app(self.config,self.store,self.static)
        self.client=self.make_client(self.app)
    def make_client(self,app):
        return TestClient(app,base_url=self.config['origin'],headers={'Origin':self.config['origin']})
    def login(self,client=None):
        client=client or self.client
        self.store.register('synthetic-user',HASHER.hash('synthetic-password-only'),2)
        self.assertEqual(200,client.post('/auth/login',json={'username':'synthetic-user','password':'synthetic-password-only'}).status_code)
    def test_default_unchanged_and_legacy_has_cloud_wrappers(self):
        self.login()
        for path in ['/', '/legacy', '/static/index.html']:
            with self.subTest(path=path):
                page=self.client.get(path)
                self.assertEqual(200,page.status_code)
                for script in ['cloud-readonly.js','cloud-commands.js','cloud-cleanup.js','cloud-backups.js']:
                    self.assertIn(script,page.text)
                self.assertNotIn('src="/login.js"',page.text)
    def test_explicit_true_only_switch_and_no_script_injection_in_v2(self):
        for flag in [False, 'true', 1, None, True]:
            client=self.make_client(create_app({**self.config,'v2_default_enabled':flag},self.store,self.static))
            if not self.store.user('synthetic-user'): self.login(client)
            else: client.post('/auth/login',json={'username':'synthetic-user','password':'synthetic-password-only'})
            result=client.get('/',follow_redirects=False)
            with self.subTest(flag=flag):
                self.assertEqual(303 if flag is True else 200,result.status_code)
                if flag is True:
                    self.assertEqual('/static/v2/index.html',result.headers['location'])
                    page=client.get(result.headers['location']);self.assertEqual(200,page.status_code)
                    self.assertNotIn('cloud-commands.js',page.text)
    def test_missing_build_rejects_opt_in(self):
        with self.assertRaisesRegex(RuntimeError,'V2 entry missing'):
            create_app({**self.config,'v2_default_enabled':True},self.store,Path(self.temp.name))
    def test_anonymous_surface_is_exact_login_assets_only(self):
        for path,mime in [('/login','text/html'),('/login.js','application/javascript'),('/login-helpers.js','application/javascript'),('/login.css','text/css')]:
            result=self.client.get(path)
            with self.subTest(path=path):
                self.assertEqual(200,result.status_code);self.assertIn(mime,result.headers['content-type'])
                self.assertIn("script-src 'self'",result.headers['content-security-policy'])
                self.assertIn("form-action 'self'",result.headers['content-security-policy'])
                self.assertEqual('no-store',result.headers['cache-control'])
        for path in ['/static/app.js','/static/index.html','/static/v2/assets/missing.js','/api/dashboard','/console/status','/console/notifications','/console/backups','/auth/session']:
            with self.subTest(path=path): self.assertEqual(401,self.client.get(path).status_code)
        for path in ['/login.css/child','/login-helpers.js/child']:
            self.assertEqual(404,self.client.get(path).status_code)
    def test_unauthenticated_entry_return_and_no_open_redirect(self):
        for path in ['/', '/legacy']:
            result=self.client.get(path,follow_redirects=False)
            self.assertEqual(303,result.status_code);self.assertEqual(login_location(path),result.headers['location'])
        invalid=['https://evil.invalid','//evil.invalid','/api/dashboard','/auth/logout','/static/app.js','/login','/static/v2/../index.html','/%2f%2fevil.invalid','/legacy'+chr(92)+'evil','/legacy'+chr(10),' /legacy','/legacy'+chr(127), 'x'*2049, None]
        for value in invalid:
            with self.subTest(value=value): self.assertEqual('/',safe_destination(value))
        for value in ['/', '/legacy', '/static/index.html', '/static/v2/index.html?date=10.19#uploads']:
            self.assertEqual(value,safe_destination(value))
    def test_direct_v2_navigation_redirects_without_exposing_bundle(self):
        path='/static/v2/index.html?date=10.19'
        result=self.client.get(path,follow_redirects=False)
        self.assertEqual(303,result.status_code)
        self.assertEqual(login_location(path),result.headers['location'])
        self.assertEqual('no-store',result.headers['cache-control'])
        self.assertNotIn('type="module"',result.text)
        self.assertEqual(401,self.client.get('/static/v2/assets/not-public.js').status_code)
    def test_login_layout_no_inline_scripts_or_external_assets(self):
        page=self.client.get('/login').text
        self.assertNotIn('<style',page);self.assertNotIn('https://',page)
        self.assertIn('type="module"',page);self.assertIn('maxlength="64"',page)
        self.assertIn('minlength="12"',page);self.assertIn('maxlength="256"',page)
        self.assertIn('id="registration" hidden',page)
    def test_auth_contract_keeps_origin_cookie_and_invitation(self):
        result=self.client.post('/auth/register',json={'username':'synthetic-user','password':'synthetic-password-only','invite':'invalid'})
        self.assertEqual(403,result.status_code)
        self.assertEqual(403,self.client.post('/auth/login',json={},headers={'Origin':'https://foreign.invalid'}).status_code)
        self.login();session=self.client.get('/auth/session').json()
        self.assertEqual('synthetic-user',session['username'])
        cookie=self.client.cookies.get('ops_console_session');self.assertTrue(cookie)
        self.assertEqual(403,self.client.post('/auth/logout').status_code)
