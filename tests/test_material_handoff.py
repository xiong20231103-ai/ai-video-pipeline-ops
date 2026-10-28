"""Synthetic data only: no production files, devices, tokens or network."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
with patch('platform.machine', return_value='AMD64'):
    # Argon2's platform probe otherwise launches cmd.exe on this Windows test
    # host. Synthetic native architecture, no process or network allowance.
    from cloud.app import create_app, HASHER
from cloud.store import Store
from cloud.material_handoff import Handoff, HandoffError, CONFIRMATION
from cloud.material_package import validate_package


def rid(name):
    return 'fixture-'+name


def fence(holder, **extra):
    return {k:holder[k] for k in ('generation','epoch','session_id')} | extra


def package_bytes(holder,package_id='package-0001',parent=None,files=None,edit=None):
    files=files or {'material.db':b'SQLite format 3\x00'+b'fixture-not-a-business-db',
                    'review/current.json':b'{"fixture":true}'}
    manifest={'format':1,'package_id':package_id,'parent_package_id':parent,
              'source_device':holder['holder'],'generation':holder['generation'],'epoch':holder['epoch'],
              'schema_version':'material-v1','code_version':'fixture-code','created_at':'2026-10-27T14:00:00+08:00',
              'unresolved':{'imports':1,'collector_ops':0,'attachments':0,'reconcile':1},
              'files':[{'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in files.items()]}
    if edit:
        edit(manifest)
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest))
        for name,raw in files.items():
            archive.writestr(name,raw)
    return stream.getvalue()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        disk=patch('cloud.material_handoff.shutil.disk_usage',return_value=SimpleNamespace(free=40*1024**3))
        disk.start();self.addCleanup(disk.stop)
        temp=TemporaryDirectory(prefix='material-handoff-test-')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.now=1000.0
        self.h=Handoff(self.root,clock=lambda:self.now,lease_seconds=30)

    def acquire(self,device='office',name='acquire'):
        return self.h.acquire(device,{'request_id':rid(name)})

    def change(self,s,action,name=None,**extra):
        return self.h.transition(s['holder'],action,fence(s,request_id=rid(name or action),**extra))

    def stage(self,s,pid='package-0001',parent=None,edit=None):
        raw=package_bytes(s,pid,parent,edit=edit)
        path=self.root/(pid+'.zip')
        path.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest()
        self.h.reserve_upload(s['holder'],fence(s),pid,sha,len(raw),path)
        self.h.register_upload(s['holder'],fence(s),pid,sha,len(raw),path)
        return self.h.uploaded(s['holder'],fence(s),pid)

    def commit(self,s,pid='package-0001',parent=None):
        row=self.stage(s,pid,parent)
        summary=validate_package(self.root/row['path'],row)
        self.h.commit(s['holder'],fence(s),pid,summary)
        return row

    def ready(self):
        s=self.acquire()
        s=self.change(s,'activate',package_id=None)
        s=self.change(s,'drain')
        self.commit(s)
        return s

    def assert_code(self,code,fn):
        with self.assertRaises(HandoffError) as error:
            fn()
        self.assertEqual(code,error.exception.code)

    def test_office_home_office_preserves_pointer_and_fixed_restore_package(self):
        s=self.ready()
        self.assertFalse(s['execution_allowed'])
        released=self.change(s,'release',package_id='package-0001')
        self.assertIsNone(released['holder'])
        home=self.acquire('home','home-acquire')
        self.assertEqual('package-0001',home['base_package'])
        self.assertFalse(home['execution_allowed'])
        self.assert_code('restore_package_mismatch',lambda:self.change(home,'activate','bad',package_id=None))
        home=self.change(home,'activate','home-activate',package_id='package-0001')
        self.assertTrue(home['execution_allowed'])
        home=self.change(home,'drain','home-drain')
        self.commit(home,'package-0002','package-0001')
        self.change(home,'release','home-release',package_id='package-0002')
        office=self.acquire('office','office-again')
        self.assertEqual('package-0002',office['base_package'])
        self.assertGreater(office['epoch'],home['epoch'])
        self.assertEqual(self.h.download('package-0001')[1]['id'],'package-0001')

    def test_two_connections_racing_only_one_acquires(self):
        other=Handoff(self.root,clock=lambda:self.now,lease_seconds=30)
        def acquire(index):
            try:
                return (self.h if index==0 else other).acquire('office',{'request_id':rid('race-'+str(index))})
            except HandoffError as e:
                return e.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers=list(pool.map(acquire,[0,1]))
        self.assertEqual(1,sum(isinstance(x,dict) for x in answers))
        self.assertIn('holder_exists_manual_takeover_if_stopped',answers)

    def test_request_retries_preserve_original_session_and_reject_changed_body(self):
        s=self.acquire()
        self.assertEqual(s['session_id'],self.acquire()['session_id'])
        self.assert_code('request_id_conflict',lambda:self.h.acquire('office',{'request_id':rid('acquire'),'epoch':7}))
        active=self.change(s,'activate',package_id=None)
        self.change(active,'drain')
        replay=self.change(s,'activate',package_id=None)
        self.assertEqual('draining',replay['phase'])
        self.assertFalse(replay['execution_allowed'])

    def test_expiration_does_not_auto_transfer_or_revive_heartbeat(self):
        s=self.acquire()
        self.now+=31
        self.assertTrue(self.h.status()['lease_lost'])
        self.assert_code('lease_expired_manual_takeover_required',lambda:self.change(s,'heartbeat'))
        self.assert_code('holder_exists_manual_takeover_if_stopped',lambda:self.acquire('home','new-holder'))
        self.assert_code('lease_expired_manual_takeover_required',lambda:self.acquire())

    def test_restart_persists_ownership_audit_and_packages(self):
        s=self.ready()
        restored=Handoff(self.root,clock=lambda:self.now,lease_seconds=30)
        status=restored.status()
        self.assertEqual(s['epoch'],status['epoch'])
        self.assertEqual(s['generation'],status['generation'])
        self.assertEqual('office',status['holder'])
        self.assertTrue(status['candidates'])
        self.assertIsNone(status['current_package'])
        self.assertTrue(status['audit'])

    def test_release_requires_committed_current_holder_package_and_drain(self):
        s=self.acquire()
        self.assert_code('drain_required',lambda:self.change(s,'release',package_id='package-0001'))
        s=self.change(s,'drain')
        self.stage(s)
        self.assert_code('committed_holder_package_required',lambda:self.change(s,'release',package_id='package-0001'))
        self.assert_code('complete_package_not_found',lambda:self.h.download('package-0001'))

    def test_force_requires_confirmation_and_preserves_unknown_imports(self):
        old=self.ready()
        self.now+=31  # Lost power: cannot hold the weekend hostage.
        body={'request_id':rid('force'),'generation':old['generation'],'epoch':old['epoch'],
              'target_device':'home','package_id':'package-0001','reason':'fixture outage',
              'confirmation':CONFIRMATION,'other_device_stopped':True}
        self.assert_code('explicit_stopped_confirmation_required',lambda:self.h.force('user:1',body|{'other_device_stopped':False}))
        new=self.h.force('user:1',body)
        self.assertEqual('home',new['holder'])
        self.assertGreater(new['epoch'],old['epoch'])
        self.assertNotIn('session_id',new)
        self.assertFalse(new['execution_allowed'])
        self.assertEqual(new,self.h.force('user:1',body))
        self.assert_code('stale_holder',lambda:self.change(old,'heartbeat'))
        self.assert_code('stale_holder',lambda:self.h.commit('office',fence(old),'package-0001',{}))
        claim={'request_id':rid('claim'),'generation':new['generation'],'epoch':new['epoch']}
        held=self.h.acquire('home',claim)
        self.assertEqual(held['session_id'],self.h.acquire('home',claim)['session_id'])
        self.assertTrue(self.change(held,'activate','forced-activate',package_id='package-0001')['execution_allowed'])
        audit=self.h.status()['audit'][1] if self.h.status()['audit'][0]['action']=='activate' else self.h.status()['audit'][0]
        self.assertEqual('needs_reconcile',audit['detail']['unknown_operations'])
        self.assertFalse(audit['detail']['receiver_tasks_cancelled'])

    def test_stale_force_screen_cannot_override_new_epoch(self):
        s=self.ready()
        body={'request_id':rid('force'),'generation':s['generation'],'epoch':s['epoch']-1,
              'target_device':'home','package_id':'package-0001','reason':'fixture',
              'confirmation':CONFIRMATION,'other_device_stopped':True}
        self.assert_code('takeover_view_changed',lambda:self.h.force('user:1',body))

    def test_lost_release_ack_is_safe_after_other_device_acquires(self):
        s=self.ready()
        first=self.change(s,'release',package_id='package-0001')
        home=self.acquire('home','home-takes')
        self.assertEqual(first,self.change(s,'release',package_id='package-0001'))
        self.assertEqual(home['epoch'],self.h.status()['epoch'])
        self.assert_code('acquire_receipt_retired',lambda:self.acquire())

    def test_immutable_upload_conflicts_and_capacity_reservations(self):
        s=self.change(self.acquire(),'drain')
        row=self.stage(s)
        self.assert_code('immutable_package_conflict',lambda:self.h.register_upload('office',fence(s),row['id'],'f'*64,row['bytes'],self.root/row['path']))
        self.h.storage_cap_bytes=self.h.status()['storage']['reserved_bytes']
        self.assert_code('handoff_storage_capacity_requires_backup_and_maintenance',lambda:self.h.reserve_upload('office',fence(s),'package-0002','a'*64,1,self.root/'unfinished.zip'))

    def test_restored_control_database_counts_unknown_retained_objects(self):
        objects=self.root/'objects';objects.mkdir()
        (objects/'retained-after-restore.zip').write_bytes(b'fixture-retained')
        status=self.h.status()
        self.assertEqual(len(b'fixture-retained'),status['storage']['untracked_object_bytes'])
        self.assertEqual(len(b'fixture-retained'),status['storage']['reserved_bytes'])

    def test_missing_control_database_with_retained_objects_never_silently_bootstraps(self):
        isolated=TemporaryDirectory(prefix='handoff-missing-control-')
        self.addCleanup(isolated.cleanup)
        root=Path(isolated.name)
        objects=root/'objects';objects.mkdir()
        retained=objects/'retained.zip';retained.write_bytes(b'fixture-preserved')
        with self.assertRaisesRegex(RuntimeError,'control_database_missing'):
            Handoff(root)
        self.assertEqual(b'fixture-preserved',retained.read_bytes())
        self.assertFalse((root/'handoff.db').exists())

    def test_invalid_manifest_parent_and_missing_attachment_never_commit(self):
        s=self.change(self.acquire(),'drain')
        row=self.stage(s,edit=lambda m:m.update(parent_package_id='nonexistent-parent'))
        self.assert_code('manifest_holder_or_parent_mismatch',lambda:validate_package(self.root/row['path'],row))
        self.assert_code('committed_holder_package_required',lambda:self.change(s,'release',package_id=row['id']))

    def test_manifest_unresolved_normal_queues_fail_but_import_review_is_allowed(self):
        s=self.change(self.acquire(),'drain')
        row=self.stage(s,edit=lambda m:m['unresolved'].update(collector_ops=1))
        self.assert_code('normal_handoff_has_unresolved_attachments_or_collector',lambda:validate_package(self.root/row['path'],row))

    def test_unsafe_zip_paths_and_machine_files_rejected(self):
        s=self.change(self.acquire(),'drain')
        for index,name in enumerate(['../escape','/absolute','review/../escape','review/CON.txt',
                                      'review/file.','review/a:b','review/.env','review/device.json']):
            with self.subTest(name=name):
                pid='unsafe-'+str(index).zfill(8)
                raw=package_bytes(s,pid,files={'material.db':b'SQLite format 3\0','review/valid.jpg':b'fixture',name:b'fixture'})
                path=self.root/(pid+'.zip');path.write_bytes(raw)
                row={'id':pid,'parent_id':None,'device':'office','generation':s['generation'],'epoch':s['epoch'],
                     'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
                with self.assertRaises(HandoffError):validate_package(path,row)

    def test_recovery_rotates_generation_after_consistent_control_backup(self):
        from cloud.material_handoff_admin import recover
        s=self.ready()
        self.change(s,'release',package_id='package-0001')
        active=self.acquire('home','before-recovery')
        backups=TemporaryDirectory(prefix='handoff-backup-fixture-')
        self.addCleanup(backups.cleanup)
        result=recover(self.root,backups.name,'fixture-admin',True)
        backup=Path(result['backup_path'])
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(),result['backup_sha256'])
        c=sqlite3.connect(backup)
        try:
            before=json.loads(c.execute('SELECT body FROM state').fetchone()[0])
            self.assertEqual(active['generation'],before['generation'])
        finally:
            c.close()
        self.assertNotEqual(active['generation'],result['generation'])
        self.assertIsNone(result['holder'])
        self.assertEqual('package-0001',self.h.status()['current_package'])
        self.assert_code('stale_holder',lambda:self.change(active,'heartbeat','old-recovery-heartbeat'))

    def test_bad_hash_missing_file_and_expansion_limit(self):
        from unittest.mock import patch
        s=self.change(self.acquire(),'drain')
        def bad_hash(m):m['files'][0]['sha256']='f'*64
        row=self.stage(s,'hash-bad-0001',edit=bad_hash)
        self.assert_code('manifest_file_hash_mismatch',lambda:validate_package(self.root/row['path'],row))
        row=self.stage(s,'missing-0001',edit=lambda m:m['files'].append({'path':'review/absent.jpg','bytes':1,'sha256':'a'*64}))
        self.assert_code('invalid_package_archive',lambda:validate_package(self.root/row['path'],row))
        row=self.stage(s,'expanded-0001')
        with patch('cloud.material_package.MAX_EXPANDED',1):
            self.assert_code('package_expansion_limit',lambda:validate_package(self.root/row['path'],row))

    def test_stale_upload_and_expired_commit_cannot_publish(self):
        s=self.change(self.acquire(),'drain')
        row=self.stage(s)
        self.now+=31
        self.assert_code('lease_expired_manual_takeover_required',lambda:self.h.commit('office',fence(s),row['id'],{}))
        self.assertIsNone(self.h.status()['current_package'])
        self.assert_code('complete_package_not_found',lambda:self.h.download(row['id']))

    def test_foreign_and_old_generation_cannot_change_holder(self):
        s=self.acquire()
        self.assert_code('stale_holder',lambda:self.h.transition('home','heartbeat',fence(s,request_id=rid('foreign'))))
        self.assert_code('stale_holder',lambda:self.h.transition('office','drain',fence(s,generation='old-generation',request_id=rid('old-generation'))))
        self.assertFalse(self.h.status()['execution_allowed'])

    def test_package_bytes_changed_after_upload_rejected(self):
        s=self.change(self.acquire(),'drain')
        row=self.stage(s)
        (self.root/row['path']).write_bytes(b'fixture-corrupt')
        self.assert_code('package_storage_hash_mismatch',lambda:validate_package(self.root/row['path'],row))

    def test_force_and_normal_release_race_never_produces_two_holders(self):
        s=self.ready()
        body={'request_id':rid('race-force'),'generation':s['generation'],'epoch':s['epoch'],
              'target_device':'home','package_id':'package-0001','reason':'fixture stopped',
              'confirmation':CONFIRMATION,'other_device_stopped':True}
        def attempt(kind):
            try:
                return self.h.force('user:1',body) if kind=='force' else self.change(s,'release',package_id='package-0001')
            except HandoffError as e:
                return e.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers=list(pool.map(attempt,['force','release']))
        self.assertEqual(1,sum(isinstance(x,dict) for x in answers))
        self.assertIn(self.h.status()['holder'],(None,'home'))


class HandoffRoutesTests(unittest.TestCase):
    def setUp(self):
        disk=patch('cloud.material_handoff.shutil.disk_usage',return_value=SimpleNamespace(free=40*1024**3))
        disk.start();self.addCleanup(disk.stop)
        temp=TemporaryDirectory(prefix='handoff-routes-test-')
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.now=1000.0
        self.store=Store(self.root/'console.db',clock=lambda:self.now)
        self.tokens={'office':'fixture-office-not-real','home':'fixture-home-not-real'}
        self.config={'origin':'https://console.fixture.ts.net','agent_token_sha256':hashlib.sha256(b'fixture-agent').hexdigest(),
                     'invite_hash':HASHER.hash('fixture-invite'),'material_handoff_enabled':True,
                     'material_handoff_tokens_sha256':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in self.tokens.items()},
                     'material_handoff_dir':str(self.root/'packages')}
        self.app=create_app(self.config,self.store)
        self.client=TestClient(self.app,base_url=self.config['origin'])

    def headers(self,device='office'):
        return {'Authorization':'Bearer '+self.tokens[device]}

    def acquire(self):
        response=self.client.post('/api/material-handoff/v1/acquire',headers=self.headers(),json={'request_id':rid('acquire')})
        self.assertEqual(200,response.status_code,response.text)
        return response.json()

    def change(self,s,action,**extra):
        return self.client.post('/api/material-handoff/v1/'+action,headers=self.headers(s['holder']),
                                json=fence(s,request_id=rid(action),**extra))

    def upload(self,s,raw,pid='package-0001',**overrides):
        headers=self.headers(s['holder'])|{'X-Handoff-Generation':s['generation'], 'X-Handoff-Epoch':str(s['epoch']),
                'X-Handoff-Session':s['session_id'],'X-Package-SHA256':hashlib.sha256(raw).hexdigest(),'X-Package-Bytes':str(len(raw))}|overrides
        return self.client.put('/api/material-handoff/v1/packages/'+pid,headers=headers,content=raw)

    def test_device_token_identity_and_cookie_never_grant_device_writes(self):
        url='/api/material-handoff/v1/acquire'
        self.assertEqual(401,self.client.post(url,json={'request_id':rid('none')}).status_code)
        self.assertEqual(401,self.client.post(url,headers={'Authorization':'Bearer fixture-agent'},json={'request_id':rid('agent')}).status_code)
        self.assertEqual(409,self.client.post(url,headers=self.headers('home'),json={'request_id':rid('home')}).status_code)
        s=self.acquire()
        self.assertEqual(409,self.client.post('/api/material-handoff/v1/heartbeat',headers=self.headers('home'),json=fence(s,request_id=rid('spoof'))).status_code)
        self.assertEqual(400,self.client.post(url,headers=self.headers(),json={'request_id':rid('spoof'),'device':'home'}).status_code)
        self.assertEqual(200,self.change(s,'activate',package_id=None).status_code)
        office=self.client.get('/api/material-handoff/v1/status',headers=self.headers()).json()
        home=self.client.get('/api/material-handoff/v1/status',headers=self.headers('home')).json()
        self.assertTrue(office['execution_allowed'])
        self.assertFalse(home['execution_allowed'])
        self.assertTrue(home['holder_execution_allowed'])

    def test_stream_hash_commit_download_and_duplicate_upload(self):
        s=self.change(self.acquire(),'drain').json()
        raw=package_bytes(s)
        bad=self.upload(s,raw,**{'X-Package-SHA256':'f'*64})
        self.assertEqual(400,bad.status_code)
        self.assertEqual(404,self.client.get('/api/material-handoff/v1/packages/package-0001',headers=self.headers()).status_code)
        good=self.upload(s,raw)
        self.assertEqual(200,good.status_code,good.text)
        count=len(list((self.root/'packages/objects').glob('*.zip')))
        self.assertEqual(good.json(),self.upload(s,raw).json())
        self.assertEqual(count,len(list((self.root/'packages/objects').glob('*.zip'))))
        commit=self.client.post('/api/material-handoff/v1/packages/package-0001/commit',headers=self.headers(),json=fence(s))
        self.assertEqual(200,commit.status_code,commit.text)
        download=self.client.get('/api/material-handoff/v1/packages/package-0001',headers=self.headers('home'))
        self.assertEqual(raw,download.content)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),download.headers['x-package-sha256'])
        self.assertIsNone(self.app.state.material_handoff.status()['current_package'])
        self.assertEqual(200,self.change(s,'release',package_id='package-0001').status_code)

    def test_force_requires_logged_in_user_origin_csrf_and_unchecked_means_no(self):
        s=self.change(self.acquire(),'drain').json()
        raw=package_bytes(s);self.upload(s,raw)
        self.client.post('/api/material-handoff/v1/packages/package-0001/commit',headers=self.headers(),json=fence(s))
        body={'request_id':rid('force'),'generation':s['generation'],'epoch':s['epoch'],
              'target_device':'home','package_id':'package-0001','reason':'fixture outage',
              'confirmation':CONFIRMATION,'other_device_stopped':True}
        url='/api/material-handoff/v1/force-takeover'
        self.assertEqual(401,self.client.post(url,headers=self.headers(),json=body).status_code)
        self.assertEqual(200,self.client.post('/auth/register',headers={'Origin':self.config['origin']},
            json={'username':'fixture-user','password':'fixture-password-123','invite':'fixture-invite'}).status_code)
        self.assertEqual(200,self.client.post('/auth/login',headers={'Origin':self.config['origin']},
            json={'username':'fixture-user','password':'fixture-password-123'}).status_code)
        csrf=self.client.get('/auth/session').json()['csrf']
        self.assertEqual(403,self.client.post(url,json=body).status_code)
        self.assertEqual(403,self.client.post(url,headers={'Origin':'https://foreign.invalid','X-CSRF-Token':csrf},json=body).status_code)
        headers={'Origin':self.config['origin'],'X-CSRF-Token':csrf}
        self.assertEqual(400,self.client.post(url,headers=headers,json=body|{'other_device_stopped':False}).status_code)
        accepted=self.client.post(url,headers=headers,json=body)
        self.assertEqual(200,accepted.status_code,accepted.text)
        self.assertEqual('home',accepted.json()['holder'])
        self.assertNotIn('session_id',accepted.json())
        self.assertEqual(200,self.client.get('/material-handoff').status_code)
        self.assertIn('type="checkbox"',self.client.get('/material-handoff').text)
        self.assertNotIn('checked>',self.client.get('/material-handoff').text)

    def test_feature_disabled_creates_no_handoff_database(self):
        config=self.config|{'material_handoff_enabled':False,'material_handoff_dir':str(self.root/'disabled')}
        app=create_app(config,self.store)
        self.assertFalse(hasattr(app.state,'material_handoff'))
        self.assertFalse((self.root/'disabled').exists())

    def test_configuration_rejects_shared_tokens(self):
        config=self.config|{'material_handoff_tokens_sha256':{'office':'a'*64,'home':'a'*64}}
        with self.assertRaisesRegex(RuntimeError,'distinct_device'):
            create_app(config,self.store)

    def test_upload_size_limits_and_fence_rejected_before_payload_read(self):
        s=self.change(self.acquire(),'drain').json()
        raw=package_bytes(s)
        result=self.upload(s,raw,**{'X-Package-Bytes':str(3*1024**3)})
        self.assertEqual(413,result.status_code)
        self.assertEqual(409,self.upload(s,raw,**{'X-Handoff-Epoch':str(s['epoch']+1)}).status_code)
        self.assertEqual(401,self.client.get('/api/material-handoff/v1/packages/package-0001').status_code)
        self.assertFalse(list((self.root/'packages').glob('objects/*')))

    def test_manifest_validation_rechecks_fence_after_slow_validation(self):
        s=self.change(self.acquire(),'drain').json()
        raw=package_bytes(s);self.upload(s,raw)
        actual=validate_package
        def expired(*args):
            result=actual(*args)
            self.now+=121
            return result
        with patch('cloud.material_handoff_routes.validate_package',side_effect=expired):
            reply=self.client.post('/api/material-handoff/v1/packages/package-0001/commit',headers=self.headers(),json=fence(s))
        self.assertEqual(409,reply.status_code)
        self.assertEqual('lease_expired_manual_takeover_required',reply.json()['detail'])

    def test_partial_chunked_upload_is_not_downloadable_and_retry_recovers_original_id(self):
        s=self.change(self.acquire(),'drain').json()
        raw=package_bytes(s)
        headers=self.headers()|{'X-Handoff-Generation':s['generation'],'X-Handoff-Epoch':str(s['epoch']),
            'X-Handoff-Session':s['session_id'],'X-Package-SHA256':hashlib.sha256(raw).hexdigest(),
            'X-Package-Bytes':str(len(raw))}
        response=self.client.put('/api/material-handoff/v1/packages/package-0001',headers=headers,content=iter([raw[:8]]))
        self.assertEqual(400,response.status_code)
        self.assertEqual(404,self.client.get('/api/material-handoff/v1/packages/package-0001',headers=self.headers()).status_code)
        self.assertEqual(200,self.upload(s,raw).status_code)
        status=self.app.state.material_handoff.status()
        self.assertIsNone(status['current_package'])
        self.assertEqual(2*len(raw),status['storage']['reserved_bytes'])
