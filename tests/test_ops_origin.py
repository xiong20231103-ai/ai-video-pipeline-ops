"""Deployment-origin regression using inert credentials and temporary files only."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from agent import configure
from cloud import manage
from fastapi.testclient import TestClient
from cloud.app import create_app,HASHER
from cloud.store import Store

class OpsOriginTests(unittest.TestCase):
    def test_home_and_cloud_setup_defaults_use_ops(self):
        self.assertEqual('https://ops.tail830b6f.ts.net',configure.DEFAULT_ORIGIN)
        self.assertEqual(configure.DEFAULT_ORIGIN,manage.DEFAULT_ORIGIN)

    def test_user_configuration_saves_new_origin_without_echoing_token_or_starting(self):
        token='inert-fixture-agent-token-never-used-for-a-real-server'
        with TemporaryDirectory() as folder,patch.dict(os.environ,{'LOCALAPPDATA':folder}),patch.object(configure,'getpass',return_value=token),patch.object(os,'getlogin',return_value='fixture-user'),patch.object(configure.subprocess,'run') as process:
            captured=io.StringIO()
            with redirect_stdout(captured): configure.main()
            saved=json.loads((Path(folder)/'OpsAgent/config.json').read_text())
            self.assertEqual(configure.DEFAULT_ORIGIN,saved['cloud_origin'])
            self.assertEqual(token,saved['agent_token'])
            self.assertNotIn(token,captured.getvalue())
            for call in process.call_args_list:
                self.assertEqual('icacls',call.args[0][0])
                self.assertNotIn(token,str(call))
            with self.assertRaises(SystemExit),patch.object(configure,'getpass',side_effect=AssertionError('must not ask again')): configure.main()

    def test_existing_user_and_session_survive_origin_move_and_login_uses_new_origin(self):
        old='https://izbp187vys3zuj6vk9xw9lz.tail830b6f.ts.net'
        new=configure.DEFAULT_ORIGIN
        with TemporaryDirectory() as folder:
            store=Store(Path(folder)/'console.db')
            password='inert-fixture-password-no-real-account'
            user_id=store.register('fixture-user',HASHER.hash(password),2)
            previous_cookie,_=store.new_session(user_id)
            config={'origin':new,'agent_token_sha256':'0'*64,'invite_hash':HASHER.hash('inert-fixture-invite')}
            app=create_app(config,store,Path(__file__).parents[1]/'static')
            client=TestClient(app,base_url=new)
            self.assertEqual(200,client.get('/login').status_code)
            self.assertEqual(303,client.get('/',follow_redirects=False).status_code)
            login=client.post('/auth/login',headers={'Origin':new},json={'username':'fixture-user','password':password})
            self.assertEqual(200,login.status_code)
            self.assertEqual(200,client.get('/').status_code)
            self.assertEqual(1,store.user_count())
            self.assertIsNotNone(store.session(previous_cookie))
            self.assertEqual(403,client.post('/auth/login',headers={'Origin':old},json={'username':'fixture-user','password':password}).status_code)
