"""Real synthetic SQLite/WAL, CMS encryption and isolated inert restore only."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
import zipfile
import threading
import io
from unittest.mock import patch
from agent.backup_crypto import create_recipient,CryptoError
from agent.backup_policy import Rule,PolicyError
from agent.backup_snapshot import create_package,sqlite_snapshot,stable_bytes
from agent.backup_restore import restore_package,extract_verified,member_allowed
from cloud.backups import encrypted_cms_header,BackupVault
from cloud.backup_runtime import CloudBackupWorker
from agent.backup_policy import RULES
from agent.backup_runtime import BackupWorker
from contracts.state_files import atomic_json

class RestoreIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.base=Path(cls.temp.name)
        cls.openssl=Path(os.environ.get('OPS_BACKUP_TEST_OPENSSL',r'C:\Program Files\Git\usr\bin\openssl.exe'))
        cls.password='synthetic-only-offline-recovery-passphrase'
        cls.certificate,cls.key=create_recipient(cls.openssl,cls.base/'keys',cls.password)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_real_snapshot_package_vault_and_inert_restore(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();(source/'data').mkdir()
            (source/'config.json').write_text('{"fixtureSecret":"synthetic-not-a-live-secret"}')
            db=sqlite3.connect(source/'data/ops.db');self.addCleanup(db.close)
            db.execute('PRAGMA journal_mode=WAL');db.execute('CREATE TABLE tasks(id TEXT,value TEXT)')
            db.execute('INSERT INTO tasks VALUES(?,?)',('paused-fixture','must-not-execute'));db.commit()
            rules=[Rule('OPS','data/ops.db',True,sqlite=True),Rule('OPS','config.json',True,True)]
            package,summary=create_package({'OPS':source},root/'out',root/'scratch',self.openssl,self.certificate,rules)
            self.assertEqual([],list((root/'scratch').iterdir()))
            self.assertTrue(all(encrypted_cms_header(package/p['name']) for p in summary['artifacts']))
            self.assertNotIn('fixtureSecret',(package/'manifest.json').read_text())
            for part in summary['artifacts']:self.assertNotIn(b'must-not-execute',(package/part['name']).read_bytes())
            target=root/'restore'
            result=restore_package(package,target,self.certificate,self.key,self.password,self.openssl,{'OPS':source}.values())
            self.assertTrue(result['verified']);self.assertFalse(result['automaticExecutionAllowed'])
            self.assertEqual(2,result['files']);self.assertEqual('synthetic-not-a-live-secret',json.loads((target/'evidence/OPS/config.json').read_text())['fixtureSecret'])
            with closing(sqlite3.connect(target/'evidence/OPS/data/ops.db')) as restored:self.assertEqual([('paused-fixture','must-not-execute')],restored.execute('SELECT * FROM tasks').fetchall())
            self.assertFalse((source/'RESTORE_EVIDENCE_ONLY.json').exists())
            with self.assertRaises(PolicyError):restore_package(package,source/'danger',self.certificate,self.key,self.password,self.openssl,[source])
            with self.assertRaises(CryptoError):restore_package(package,root/'wrong-password',self.certificate,self.key,'incorrect',self.openssl,[source])
            self.assertFalse(json.loads((root/'wrong-password/RESTORE_EVIDENCE_ONLY.json').read_text())['verified'])
            db.close()
    def test_actual_cloud_db_backup_contains_config_only_encrypted_and_restores_inertly(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);database=root/'console.db'
            with closing(sqlite3.connect(database)) as db:db.execute('CREATE TABLE accounts(id TEXT)');db.commit()
            vault=BackupVault(root/'vault');vault.set_recipient(self.certificate.read_text())
            worker=CloudBackupWorker(vault,database,{'fixture':'synthetic-cloud-config'},self.openssl)
            result=worker.run_once();self.assertTrue(result['published'])
            item=vault.catalog()['items'][0];self.assertEqual('cloud',item['kind'])
            self.assertTrue(vault.verify(item['packageId'])['verified'])
            target=root/'restored-cloud';output=restore_package(vault.directory(item['packageId']),target,self.certificate,self.key,self.password,self.openssl,[database.parent/'unrelated-production'])
            self.assertEqual(3,output['files']);self.assertFalse(output['automaticExecutionAllowed'])
            self.assertEqual([],list((vault.root/'cloud-work').iterdir()))
    def test_missing_required_or_unstable_json_fails_without_a_published_partial(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.mkdir();(source/'config.json').write_text('{truncated')
            with self.assertRaises(PolicyError):create_package({'OPS':source},root/'out',root/'scratch',self.openssl,self.certificate,[Rule('OPS','config.json',True)])
            self.assertEqual([],list((root/'out').iterdir()));self.assertEqual([],list((root/'scratch').iterdir()))
    def test_extractor_rejects_traversal_extra_members_and_invalid_metadata(self):
        for name in ['../escape','OPS/../escape','CLOUD/console.db:stream','OPS/CON.json','/OPS/config.json','OPS\\config.json']:
            self.assertFalse(member_allowed(name))
        with TemporaryDirectory() as folder:
            root=Path(folder)
            for index,name in enumerate(['../escape','OPS/config.json']):
                archive=root/(str(index)+'.zip');body=b'{}'
                with zipfile.ZipFile(archive,'w') as output:
                    output.writestr(name,body)
                    output.writestr('RESTORE_EVIDENCE_ONLY.json',json.dumps({'automaticExecutionAllowed':False,'restoreMode':'isolated-evidence-only','files':[{'path':name,'bytes':len(body),'sha256':'0'*64}]}))
                target=root/('target'+str(index));target.mkdir()
                with self.assertRaises(PolicyError):extract_verified(archive,target)
    def test_real_hidden_packer_streams_ciphertext_resumes_and_removes_local_copy(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);roots={name:str(root/'sources'/name) for name in {r.root for r in RULES}}
            for source in roots.values():Path(source).mkdir(parents=True)
            for rule in RULES:
                if not rule.required:continue
                path=Path(roots[rule.root])/rule.pattern;path.parent.mkdir(parents=True,exist_ok=True)
                if rule.sqlite:
                    with closing(sqlite3.connect(path)) as db:db.execute('CREATE TABLE fixture(id TEXT)');db.commit()
                else:path.write_text('{}' if path.name.endswith(('.json','.json.last-valid')) else 'inert-fixture\n')
            state=Path(roots['AGENT']);settings={'schema':1,'roots':roots,'openssl':str(self.openssl),'recipientCertificate':str(self.certificate)}
            atomic_json(state/'backup-settings.json',settings)
            (state/'backup-recipient.pem').write_text(self.certificate.read_text())
            vault=BackupVault(root/'cloud-vault');requests=[];fail=[True]
            self_test=self
            class Transport:
                def open(self,request,timeout):
                    requests.append((request.method,request.full_url))
                    self_test.assertEqual('PUT',request.method);self_test.assertTrue(hasattr(request.data,'read'))
                    if fail[0]:fail[0]=False;raise OSError('synthetic outage before first upload')
                    package_id,name=request.full_url.rsplit('/',2)[-2:]
                    upload=vault.begin_part(package_id,name,int(request.headers['Content-length']))
                    digest=hashlib.sha256();size=0
                    while block:=request.data.read(8192):
                        digest.update(block);size+=len(block)
                        if not upload['stored']:upload['handle'].write(block)
                    vault.finish_part(package_id,name,upload,size,digest.hexdigest())
                    return io.BytesIO(b'{"stored":true}')
            class Agent:
                state_dir=state;origin='https://synthetic.ts.net';token='inert-fixture';stop=threading.Event();transport=Transport()
                def cloud(self,path,data):
                    if path=='/agent/backups/recipient':return vault.set_recipient(data['certificate'])
                    if path=='/agent/backups/reserve':return vault.reserve(data)
                    if path.endswith('/publish'):
                        answer=vault.publish(path.split('/')[-2]);vault.complete_request(data.get('requestId'));return answer
                    raise AssertionError('Unexpected cloud endpoint')
            worker=BackupWorker(Agent());request=vault.request()
            with self.assertRaises(OSError):worker.execute(settings,request)
            pending=json.loads((state/'backup-pending.json').read_text());package=Path(pending['directory'])
            self.assertTrue(package.is_dir());self.assertEqual([],vault.catalog()['items'])
            answer=worker.execute(settings,request)
            self.assertEqual(package.name,answer['packageId']);self.assertFalse(package.exists())
            self.assertFalse((state/'backup-pending.json').exists());self.assertIsNone(vault.pending_request())
            self.assertTrue(vault.verify(answer['packageId'])['verified']);self.assertEqual(3,len(requests))
            self.assertEqual('completed',worker.public_state()['phase'])

