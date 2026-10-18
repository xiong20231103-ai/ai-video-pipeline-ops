from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid
from unittest.mock import patch
from cloud.backups import BackupVault,BackupError,FORMAT,encrypted_cms_header
from cloud.backup_runtime import CloudBackupWorker

# Shape-only fixtures exercise the vault, never claim real cryptographic validity.
CMS=b'\x30\x80'+bytes.fromhex('060b2a864886f70d0109100117')+b'vault-shape-fixture'
def manifest(at,kind='home',content=CMS):
    return {'schema':1,'packageId':'20261018T000000Z-'+uuid.uuid4().hex,'format':FORMAT,'privateKeyIncluded':False,
            'sourceBytes':20,'startedAt':at,'completedAt':at,
            'artifacts':[{'name':n,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),'files':1}
                         for n in (['ledger.cms','configuration.cms'] if kind=='home' else ['cloud.cms'])]}
def store(vault,data,kind='home',content=CMS):
    vault.reserve(data,kind)
    for part in data['artifacts']:
        upload=vault.begin_part(data['packageId'],part['name'],len(content))
        if not upload['stored']:upload['handle'].write(content)
        vault.finish_part(data['packageId'],part['name'],upload,len(content),part['sha256'])
    return vault.publish(data['packageId'])

class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=[datetime(2026,10,18,tzinfo=timezone.utc).timestamp()]
        self.vault=BackupVault(Path(self.temp.name)/'vault',clock=lambda:self.now[0])
    def item(self,days=0,kind='home'):
        return manifest(datetime.fromtimestamp(self.now[0]-days*86400,timezone.utc).isoformat(),kind)
    def test_reserve_upload_publish_resume_and_integrity(self):
        data=self.item();first=self.vault.reserve(data)
        self.assertFalse(first['idempotent']);self.assertEqual([],self.vault.catalog()['items'])
        with self.assertRaisesRegex(BackupError,'incomplete'):self.vault.publish(data['packageId'])
        self.now[0]+=4000
        self.assertTrue(self.vault.reserve(data)['idempotent'])
        store(self.vault,data);self.assertTrue(self.vault.verify(data['packageId'])['verified'])
        self.assertTrue(self.vault.reserve(data)['idempotent']);store(self.vault,data)
        changed={**data,'sourceBytes':21}
        with self.assertRaisesRegex(BackupError,'conflict'):self.vault.reserve(changed)
        descriptor,part=self.vault.open_download(data['packageId'],'ledger.cms')
        with descriptor:self.assertEqual(CMS,descriptor.read())
        (self.vault.directory(data['packageId'])/'ledger.cms').write_bytes(CMS[:-1]+b'x')
        self.assertFalse(self.vault.verify(data['packageId'])['verified'])
        with self.assertRaisesRegex(BackupError,'integrity'):self.vault.publish(data['packageId'])
    def test_concurrent_reservation_and_part_lease_are_singleflight(self):
        data=self.item()
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.vault.reserve(data),range(4)))
        self.assertEqual(1,sum(not r['idempotent'] for r in results))
        upload=self.vault.begin_part(data['packageId'],'ledger.cms',len(CMS))
        try:
            with self.assertRaisesRegex(BackupError,'busy'):self.vault.begin_part(data['packageId'],'ledger.cms',len(CMS))
        finally:self.vault.abort_part(data['packageId'],'ledger.cms',upload)
        second=self.vault.begin_part(data['packageId'],'ledger.cms',len(CMS));self.vault.abort_part(data['packageId'],'ledger.cms',second)
    def test_plaintext_and_bad_digest_do_not_become_downloadable(self):
        data=self.item();self.vault.reserve(data)
        upload=self.vault.begin_part(data['packageId'],'ledger.cms',len(CMS));upload['handle'].write(CMS)
        with self.assertRaisesRegex(BackupError,'digest'):self.vault.finish_part(data['packageId'],'ledger.cms',upload,len(CMS),'0'*64)
        plain=b'plaintext-not-an-encrypted-backup';data=self.item();data['artifacts']=[{**p,'bytes':len(plain),'sha256':hashlib.sha256(plain).hexdigest()} for p in data['artifacts']]
        self.vault.reserve(data);upload=self.vault.begin_part(data['packageId'],'ledger.cms',len(plain));upload['handle'].write(plain)
        with self.assertRaisesRegex(BackupError,'encrypted_cms'):self.vault.finish_part(data['packageId'],'ledger.cms',upload,len(plain),hashlib.sha256(plain).hexdigest())
        self.assertEqual([],self.vault.catalog()['items'])
    def test_expired_partial_is_removed_and_renamed_uncommitted_part_is_adopted(self):
        data=self.item();self.vault.reserve(data)
        upload=self.vault.begin_part(data['packageId'],'ledger.cms',len(CMS));upload['handle'].write(CMS);upload['handle'].close()
        self.now[0]+=601
        second=self.vault.begin_part(data['packageId'],'ledger.cms',len(CMS));self.assertFalse(upload['path'].exists())
        second['handle'].write(CMS);second['handle'].close()
        final=self.vault.directory(data['packageId'])/'ledger.cms';second['path'].rename(final)
        self.now[0]+=601
        adopted=self.vault.begin_part(data['packageId'],'ledger.cms',len(CMS));self.assertTrue(adopted['stored'])
    def test_fixed_names_timestamps_and_size_bounds(self):
        for changes in [{'packageId':'../outside'},{'privateKeyIncluded':True},{'sourceBytes':True},{'completedAt':'tomorrow'},{'startedAt':'2099-01-01T00:00:00Z'},{'artifacts':[{'name':'../a'}]}]:
            with self.subTest(changes=changes),self.assertRaises(BackupError):self.vault.reserve({**self.item(),**changes})
        with self.assertRaises(BackupError):self.vault.open_download('../bad','ledger.cms')
    def test_daily_monthly_cloud_retention_uses_capture_date_not_upload_date(self):
        dates=[datetime(2026,10,18,tzinfo=timezone.utc)-timedelta(days=n) for n in range(35)]
        dates += [datetime(2026,m,1,tzinfo=timezone.utc) for m in (6,7,8)]
        for day in dates:store(self.vault,manifest(day.isoformat()))
        home=self.vault.catalog()['items'];self.assertEqual(32,len(home))
        kept={p['date'] for p in home};self.assertIn('2026-08-01',kept);self.assertIn('2026-07-01',kept);self.assertNotIn('2026-06-01',kept)
        for n in range(16):store(self.vault,self.item(n,'cloud'),'cloud')
        self.assertEqual(14,len([p for p in self.vault.catalog()['items'] if p['kind']=='cloud']))
        newest=manifest('2026-10-18T02:00:00Z');self.now[0]+=86400;store(self.vault,newest)
        self.assertEqual(1,sum(p['kind']=='home' and p['date']=='2026-10-18' for p in self.vault.catalog()['items']))
    def test_quota_reservations_count_and_gc_rollback_never_loses_old_backup(self):
        first=self.item(4);store(self.vault,first);second=self.item(3);store(self.vault,second)
        used=self.vault.catalog()['usedReservedBytes'];self.vault.quota=used+10
        newest=self.item()
        with patch.object(self.vault,'event',side_effect=RuntimeError('injected before SQL commit')):
            with self.assertRaises(RuntimeError):self.vault.reserve(newest)
        self.assertTrue(self.vault.verify(first['packageId'])['verified'])
        self.assertTrue(self.vault.verify(second['packageId'])['verified'])
        store(self.vault,newest)
        self.assertLessEqual(self.vault.catalog()['usedReservedBytes'],self.vault.quota)
        self.assertFalse(self.vault.directory(first['packageId']).exists())
        self.assertIn('quota_removed_old_backup',[e['code'] for e in self.vault.catalog()['events']])
    def test_gc_crash_recovery_restores_uncommitted_rename_and_finishes_committed(self):
        data=self.item();store(self.vault,data)
        original=self.vault.directory(data['packageId']);trash=self.vault.root/('.deleting-'+data['packageId'])
        original.rename(trash)
        reopened=BackupVault(self.vault.root,clock=lambda:self.now[0]);self.assertTrue(reopened.verify(data['packageId'])['verified'])
        original.rename(trash)
        with reopened.db(True) as db:db.execute('DELETE FROM packages WHERE id=?',(data['packageId'],))
        BackupVault(self.vault.root,clock=lambda:self.now[0]);self.assertFalse(trash.exists())
    def test_delete_failure_is_counted_and_blocks_new_upload_until_gc_succeeds(self):
        first=self.item(4);store(self.vault,first);store(self.vault,self.item(3))
        self.vault.quota=self.vault.catalog()['usedReservedBytes']+10
        data=self.item()
        with patch.object(self.vault,'_erase_directory',side_effect=PermissionError('synthetic sharing conflict')):
            with self.assertRaisesRegex(BackupError,'gc_blocks'):self.vault.reserve(data)
        self.vault.reap_trash();store(self.vault,data)
        self.assertLessEqual(self.vault.catalog()['usedReservedBytes'],self.vault.quota)
    def test_request_generation_and_recipient_pinning(self):
        request=self.vault.request();self.assertEqual(request,self.vault.request())
        self.vault.complete_request('not-the-request');self.assertEqual(request,self.vault.pending_request())
        self.vault.complete_request(request);self.assertIsNone(self.vault.pending_request())
        cert='-----BEGIN CERTIFICATE-----\n'+'A'*100+'\n-----END CERTIFICATE-----\n'
        self.vault.set_recipient(cert);self.vault.set_recipient(cert)
        with self.assertRaisesRegex(BackupError,'local_admin'):self.vault.set_recipient(cert.replace('A'*100,'B'*100))
        with self.assertRaises(BackupError):self.vault.set_recipient('-----BEGIN PRIVATE KEY-----')
    def test_cloud_scratch_from_interrupted_process_is_removed_only_by_fixed_names(self):
        worker=CloudBackupWorker(self.vault,Path(self.temp.name)/'synthetic.db',{})
        work=self.vault.root/'cloud-work';old=work/'cloud-snapshot-interrupted';old.mkdir(parents=True)
        (old/'cloud.zip').write_bytes(b'synthetic-inert-state')
        (old/'console.db').write_bytes(b'synthetic-partial-snapshot')
        worker.clean_work(work);self.assertEqual([],list(work.iterdir()))
        unexpected=work/'do-not-delete';unexpected.mkdir();(unexpected/'important').write_bytes(b'inert')
        with self.assertRaises(BackupError):worker.clean_work(work)
        self.assertTrue((unexpected/'important').is_file())

