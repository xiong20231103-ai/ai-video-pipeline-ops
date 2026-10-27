"""Synthetic offline maintenance; no production disk or credentials touched."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cloud.material_handoff import Handoff, GIB, DISK_HEADROOM, DEFAULT_STORAGE_CAP
from cloud.material_handoff_prune import prune, PruneError, digest_file
from cloud.material_package import validate_package
from test_material_handoff import fence, package_bytes


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='material-prune-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.backup=TemporaryDirectory(prefix='material-archive-fixture-')
        self.addCleanup(self.backup.cleanup)
        self.root=Path(self.temp.name)
        self.now=1000.0
        # Declare a synthetic roomy disk, not assumptions about a hosted runner.
        disk=patch('cloud.material_handoff.shutil.disk_usage',return_value=SimpleNamespace(free=40*GIB))
        disk.start();self.addCleanup(disk.stop)
        self.h=Handoff(self.root,clock=lambda:self.now)
        (self.root/'objects').mkdir()
        self.rows=[]

    def package(self,*,release=True):
        n=len(self.rows)+1
        state=self.h.acquire('office',{'request_id':f'fixture-acquire-{n}'})
        state=self.h.transition('office','activate',fence(state,request_id=f'fixture-activate-{n}',package_id=state['base_package']))
        state=self.h.transition('office','drain',fence(state,request_id=f'fixture-drain-{n}'))
        pid=f'package-{n:08d}'
        raw=package_bytes(state,pid,state['base_package'])
        path=self.root/'objects'/(pid+'.zip')
        path.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest()
        self.h.reserve_upload('office',fence(state),pid,sha,len(raw),path)
        self.h.register_upload('office',fence(state),pid,sha,len(raw),path)
        row=self.h.uploaded('office',fence(state),pid)
        self.h.commit('office',fence(state),pid,validate_package(path,row))
        self.rows.append({'id':pid,'path':path,'raw':raw})
        if release:
            self.h.transition('office','release',fence(state,request_id=f'fixture-release-{n}',package_id=pid))
        self.now+=1
        return state

    def run_prune(self,keep_recent=3):
        # Actual temp bytes are copied/hashed/deleted. Only mount identity is
        # synthetic, avoiding a second physical drive as a unit-test dependency.
        with patch('cloud.material_handoff_prune._same_filesystem',return_value=False):
            return prune(self.root,self.backup.name,'fixture-admin',True,keep_recent=keep_recent)

    def test_startup_default_is_8gib_and_reserves_5gib(self):
        self.assertEqual(DEFAULT_STORAGE_CAP,8*GIB)
        self.assertEqual(self.h.storage_cap_bytes,8*GIB)
        with TemporaryDirectory(prefix='handoff-small-disk-') as directory:
            with patch('cloud.material_handoff.shutil.disk_usage',return_value=SimpleNamespace(free=13*GIB-1)):
                with self.assertRaisesRegex(RuntimeError,'cap_plus_5gib'):
                    Handoff(directory)
                self.assertFalse((Path(directory)/'handoff.db').exists())
            with patch('cloud.material_handoff.shutil.disk_usage',return_value=SimpleNamespace(free=13*GIB)):
                Handoff(directory)

    def test_warning_is_strictly_above_70_percent_and_counts_failed_reservations(self):
        self.h.storage_cap_bytes=100
        with self.h.tx() as db:
            db.execute('INSERT INTO uploads VALUES(?,?,?)',('objects/failed.zip',70,self.now))
        self.assertFalse(self.h.status()['storage']['warning'])
        with self.h.tx() as db:
            db.execute('UPDATE uploads SET reserved_bytes=71')
        storage=self.h.status()['storage']
        self.assertTrue(storage['warning'])
        self.assertEqual('handoff_storage_above_70_percent',storage['warning_code'])
        self.assertEqual(71,storage['used_bytes'])
        self.assertEqual(70,storage['warning_threshold_percent'])

    def test_keep_current_plus_three_other_committed_and_verified_restore_material(self):
        for _ in range(7):self.package()
        result=self.run_prune()
        self.assertEqual([r['id'] for r in self.rows[3:]],result['protected_packages'])
        self.assertEqual(3,result['removed_files'])
        self.assertEqual(sum(len(r['raw']) for r in self.rows[:3]),result['source_bytes_removed'])
        folder=Path(result['backup_path'])
        manifest=json.loads((folder/'prune-manifest.json').read_text(encoding='utf-8'))
        for entry in manifest['files']:
            saved=folder/entry['backup_path']
            self.assertEqual(entry['sha256'],digest_file(saved))
            self.assertFalse((self.root/entry['path']).exists())
        for row in self.rows[3:]:self.assertEqual(row['raw'],row['path'].read_bytes())
        c=sqlite3.connect(folder/'handoff.db')
        try:
            self.assertEqual(('ok',),c.execute('PRAGMA integrity_check').fetchone())
            self.assertEqual(7,c.execute("SELECT COUNT(*) FROM packages WHERE state='committed'").fetchone()[0])
        finally:c.close()
        with self.h.db() as db:
            self.assertEqual(3,db.execute("SELECT COUNT(*) FROM packages WHERE state='pruned'").fetchone()[0])
            actions=[r[0] for r in db.execute("SELECT action FROM audit WHERE action LIKE 'prune_%'")]
        self.assertIn('prune_begin',actions)
        self.assertIn('prune_backups_verified',actions)
        self.assertEqual(3,actions.count('prune_deleted'))
        self.assertIn('prune_complete',actions)
        # A second run is idempotent, with immutable old metadata preserved.
        self.assertEqual(0,self.run_prune()['removed_files'])

    def test_current_parent_survives_even_with_keep_zero(self):
        for _ in range(5):self.package()
        result=self.run_prune(0)
        self.assertEqual([r['id'] for r in self.rows[-2:]],result['protected_packages'])
        self.assertEqual(3,result['removed_files'])
        self.assertTrue(self.rows[-1]['path'].exists())
        self.assertTrue(self.rows[-2]['path'].exists())

    def test_all_current_epoch_packages_and_unknown_uploads_survive_active_handoff(self):
        for _ in range(5):self.package()
        held=self.package(release=False)
        # Another staged package of this same epoch must never be collected.
        pid='staged-current-epoch'
        raw=package_bytes(held,pid,held['base_package'])
        staged=self.root/'objects'/(pid+'.zip');staged.write_bytes(raw)
        sha=hashlib.sha256(raw).hexdigest()
        self.h.reserve_upload('office',fence(held),pid,sha,len(raw),staged)
        self.h.register_upload('office',fence(held),pid,sha,len(raw),staged)
        orphan=self.root/'objects/unfinished-live.zip';orphan.write_bytes(b'fixture-inflight')
        with self.h.tx() as db:
            db.execute('INSERT INTO uploads VALUES(?,?,?)',('objects/unfinished-live.zip',100,self.now))
        result=self.run_prune(0)
        self.assertIn(self.rows[-1]['id'],result['protected_packages'])
        self.assertIn(pid,result['protected_packages'])
        self.assertEqual(raw,staged.read_bytes())
        self.assertEqual(b'fixture-inflight',orphan.read_bytes())
        self.assertEqual('office',self.h.status()['holder'])

    def test_backup_corruption_aborts_before_any_delete_and_audits_failure(self):
        for _ in range(6):self.package()
        original=shutil.copyfileobj
        def corrupt(src,dst,**kwargs):
            original(src,dst,**kwargs)
            dst.write(b'fixture-corruption')
        with patch('cloud.material_handoff_prune.shutil.copyfileobj',side_effect=corrupt):
            with self.assertRaisesRegex(PruneError,'backup_verification_failed'):
                self.run_prune(0)
        for row in self.rows:self.assertEqual(row['raw'],row['path'].read_bytes())
        with self.h.db() as db:
            self.assertEqual(0,db.execute("SELECT COUNT(*) FROM packages WHERE state='pruned'").fetchone()[0])
            self.assertEqual('prune_failed',db.execute('SELECT action FROM audit ORDER BY seq DESC').fetchone()[0])

    def test_source_hash_mismatch_aborts_before_deleting_earlier_verified_copy(self):
        for _ in range(6):self.package()
        self.rows[1]['path'].write_bytes(b'fixture-corrupt-source')
        with self.assertRaisesRegex(PruneError,'source_package_hash_mismatch'):
            self.run_prune(0)
        self.assertEqual(self.rows[0]['raw'],self.rows[0]['path'].read_bytes())
        self.assertTrue(all(r['path'].exists() for r in self.rows))

    def test_state_change_after_backups_prevents_all_deletion(self):
        for _ in range(6):self.package()
        from cloud.material_handoff_prune import _copy_payload
        changed=False
        def changed_copy(*args):
            nonlocal changed
            _copy_payload(*args)
            if not changed:
                changed=True
                self.h.acquire('home',{'request_id':'fixture-unexpected-online'})
        with patch('cloud.material_handoff_prune._copy_payload',side_effect=changed_copy):
            with self.assertRaisesRegex(PruneError,'changed_before_deletion'):
                self.run_prune(0)
        self.assertTrue(all(r['path'].exists() for r in self.rows))

    def test_inactive_orphan_payload_and_empty_reservation_are_archived_and_reclaimed(self):
        self.package()
        orphan=self.root/'objects/old-unreferenced.zip';orphan.write_bytes(b'fixture-orphan')
        with self.h.tx() as db:
            db.execute('INSERT INTO uploads VALUES(?,?,?)',('objects/missing-aborted.zip',100,self.now))
        result=self.run_prune()
        self.assertEqual(1,result['removed_files'])
        self.assertFalse(orphan.exists())
        manifest=json.loads((Path(result['backup_path'])/'prune-manifest.json').read_text(encoding='utf-8'))
        self.assertTrue(any(x['missing_before_prune'] for x in manifest['files']))
        with self.h.db() as db:
            self.assertFalse(db.execute("SELECT * FROM uploads WHERE path='objects/missing-aborted.zip'").fetchall())

    def test_offline_command_works_when_startup_headroom_check_would_refuse(self):
        for _ in range(5):self.package()
        # More than enough bytes for tiny fixtures, below cap + 5 GiB.
        with patch('cloud.material_handoff.shutil.disk_usage',return_value=SimpleNamespace(free=GIB)):
            with self.assertRaisesRegex(RuntimeError,'cap_plus_5gib'):
                Handoff(self.root)
            self.assertEqual(1,self.run_prune()['removed_files'])

    def test_reject_same_filesystem_unconfirmed_and_bad_keep_without_deletion(self):
        for _ in range(5):self.package()
        with self.assertRaisesRegex(PruneError,'different_filesystem'):
            prune(self.root,self.backup.name,'fixture',True)
        with self.assertRaises(PruneError):prune(self.root,self.backup.name,'fixture',False)
        with self.assertRaises(PruneError):self.run_prune(-1)
        self.assertTrue(all(r['path'].exists() for r in self.rows))

    def test_unsafe_database_payload_path_never_touches_external_file(self):
        for _ in range(5):self.package()
        with self.h.tx() as db:
            db.execute('UPDATE packages SET path=? WHERE id=?',('../external.zip',self.rows[0]['id']))
        with self.assertRaisesRegex(PruneError,'unsafe_prune_payload'):
            self.run_prune(0)
        self.assertTrue(all(r['path'].exists() for r in self.rows))

    def test_delete_interruption_has_complete_backup_and_can_roll_back(self):
        from cloud.material_handoff_admin import recover
        for _ in range(6):self.package()
        original=Path.unlink
        calls=0
        def interrupted(path,*args,**kwargs):
            nonlocal calls
            if path.parent==self.root/'objects':
                calls+=1
                if calls==2:
                    raise OSError('fixture interrupted deletion')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',interrupted):
            with self.assertRaises(OSError):self.run_prune(0)
        folder=next(Path(self.backup.name).glob('material-handoff-before-prune-*'))
        manifest=json.loads((folder/'prune-manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(4,len(manifest['files']))
        self.assertFalse(self.rows[0]['path'].exists())
        self.assertTrue(self.rows[1]['path'].exists())
        # Recreate each payload from the verified archive, then restore the
        # control snapshot offline and rotate generation before re-enabling.
        for entry in manifest['files']:
            archive=folder/entry['backup_path']
            self.assertEqual(entry['sha256'],digest_file(archive))
            shutil.copyfile(archive,self.root/entry['path'])
        source=sqlite3.connect(folder/'handoff.db')
        target=sqlite3.connect(self.root/'handoff.db')
        try:source.backup(target)
        finally:source.close();target.close()
        old_generation=self.h.status()['generation']
        recover(self.root,self.backup.name,'fixture-rollback',True)
        self.assertNotEqual(old_generation,self.h.status()['generation'])
        self.assertEqual(self.rows[-1]['id'],self.h.status()['current_package'])
        self.assertTrue(all(r['path'].exists() for r in self.rows))
        with self.h.db() as db:
            self.assertEqual(0,db.execute("SELECT COUNT(*) FROM packages WHERE state='pruned'").fetchone()[0])

    def test_offline_prune_cli_selects_default_retention(self):
        from cloud.material_handoff_admin import main
        import sys
        with patch.object(sys,'argv',['admin','prune','--root',str(self.root),'--backup-dir',self.backup.name,
                                   '--actor','fixture-cli','--confirm-both-devices-stopped-and-cloud-offline']), \
             patch('cloud.material_handoff_prune.prune',return_value={'fixture':True}) as execute, \
             patch('builtins.print'):
            main()
        self.assertEqual(3,execute.call_args.kwargs['keep_recent'])
        self.assertTrue(execute.call_args.args[3])


if __name__=='__main__':
    unittest.main()
