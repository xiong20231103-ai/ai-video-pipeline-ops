import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from deploy.agent_source_update import LEGACY_FILES,PREVIOUS_FILES,FILES,PREVIOUS_R6_FILES,R6_FILES,prepare,apply,restore,validate

def package(path,commit,names=FILES):
    path.mkdir()
    hashes={}
    for name in names:
        file=path/name;file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(commit+':'+name,encoding='utf-8')
        hashes[name]=hashlib.sha256(file.read_bytes()).hexdigest()
    (path/'deployment-manifest.json').write_text(json.dumps({'commit':commit,'sha256':hashes}),encoding='utf-8')

class AgentSourceUpdateTests(unittest.TestCase):
    def test_pre_pip_relocated_manifest_and_exact_rollback_remain_supported(self):
        from deploy.agent_source_update import PRE_PIP_R6_RELOCATED_FILES,R6_RELOCATED_FILES
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40,PRE_PIP_R6_RELOCATED_FILES);package(new,'b'*40,R6_RELOCATED_FILES)
            prepare(new,old,backup,'b'*40);apply(new,old,backup,'b'*40)
            self.assertEqual(set(R6_RELOCATED_FILES),set(validate(old)['sha256']))
            restore(backup,old)
            self.assertEqual(set(PRE_PIP_R6_RELOCATED_FILES),set(validate(old)['sha256']))
            for name in set(R6_RELOCATED_FILES)-set(PRE_PIP_R6_RELOCATED_FILES):
                self.assertFalse((old/name).exists())

    def test_previous_r6_manifest_remains_accepted_and_can_be_restored(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40,PREVIOUS_R6_FILES);package(new,'b'*40,R6_FILES)
            prepare(new,old,backup,'b'*40);apply(new,old,backup,'b'*40)
            self.assertEqual(set(R6_FILES),set(validate(old)['sha256']))
            restore(backup,old)
            self.assertEqual(set(PREVIOUS_R6_FILES),set(validate(old)['sha256']))
            for name in set(R6_FILES)-set(PREVIOUS_R6_FILES):self.assertFalse((old/name).exists())
    def test_code_update_and_one_backup_restore_preserve_unlisted_private_file(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40);package(new,'b'*40)
            sentinel=old/'private-not-in-whitelist.json';sentinel.write_text('inert-private-fixture')
            prepare(new,old,backup,'b'*40)
            self.assertEqual('a'*40,validate(old)['commit'])
            self.assertTrue((backup/'operation.json').exists())
            apply(new,old,backup,'b'*40)
            self.assertEqual('b'*40,validate(old)['commit'])
            restore(backup,old)
            self.assertEqual('a'*40,validate(old)['commit'])
            self.assertEqual('inert-private-fixture',sentinel.read_text())
            self.assertFalse((backup/sentinel.name).exists())

    def test_tampered_input_or_target_identity_refused_before_replacement(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40);package(new,'b'*40)
            with self.assertRaises(ValueError): prepare(new,old,backup,'c'*40)
            self.assertFalse(backup.exists())
            prepare(new,old,backup,'b'*40)
            (new/FILES[0]).write_text('unexpected')
            with self.assertRaises(ValueError): apply(new,old,backup,'b'*40)
            self.assertEqual('a'*40,validate(old)['commit'])
            with self.assertRaises(ValueError): restore(backup,new)

    def test_rollback_recovers_a_partially_replaced_code_whitelist(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40);package(new,'b'*40)
            prepare(new,old,backup,'b'*40)
            (old/FILES[0]).write_bytes((new/FILES[0]).read_bytes())
            (old/FILES[1]).unlink()
            restore(backup,old)
            self.assertEqual('a'*40,validate(old)['commit'])

    def test_legacy_eleven_file_migration_and_exact_rollback(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40);package(new,'b'*40)
            manifest=json.loads((old/'deployment-manifest.json').read_text())
            for name in set(FILES)-set(LEGACY_FILES):
                (old/name).unlink();del manifest['sha256'][name]
            (old/'deployment-manifest.json').write_text(json.dumps(manifest))
            prepare(new,old,backup,'b'*40);apply(new,old,backup,'b'*40)
            self.assertEqual(set(FILES),set(validate(old)['sha256']))
            restore(backup,old)
            self.assertEqual(set(LEGACY_FILES),set(validate(old)['sha256']))
            for name in set(FILES)-set(LEGACY_FILES):self.assertFalse((old/name).exists())

    def test_previous_thirteen_file_migration_and_self_contained_backup(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40);package(new,'b'*40)
            manifest=json.loads((old/'deployment-manifest.json').read_text())
            for name in set(FILES)-set(PREVIOUS_FILES):
                (old/name).unlink();del manifest['sha256'][name]
            (old/'deployment-manifest.json').write_text(json.dumps(manifest))
            prepare(new,old,backup,'b'*40)
            self.assertTrue((backup/'agent_state_io.py').is_file())
            apply(new,old,backup,'b'*40);restore(backup,old)
            self.assertEqual(set(PREVIOUS_FILES),set(validate(old)['sha256']))
            for name in set(FILES)-set(PREVIOUS_FILES):self.assertFalse((old/name).exists())

    def test_m1b_twenty_three_file_upgrade_and_rollback_keep_execution_receipts(self):
        from deploy.agent_source_update import BACKUP_FILES
        with TemporaryDirectory() as folder:
            root=Path(folder);old=root/'old';new=root/'new';backup=root/'backup'
            package(old,'a'*40);package(new,'b'*40)
            manifest=json.loads((old/'deployment-manifest.json').read_text())
            for name in set(FILES)-set(BACKUP_FILES):(old/name).unlink();del manifest['sha256'][name]
            (old/'deployment-manifest.json').write_text(json.dumps(manifest))
            receipt=old/'execution.db';receipt.write_text('inert receipt fixture, not runtime source')
            prepare(new,old,backup,'b'*40);apply(new,old,backup,'b'*40);restore(backup,old)
            self.assertEqual(set(BACKUP_FILES),set(validate(old)['sha256']));self.assertEqual('inert receipt fixture, not runtime source',receipt.read_text())
    def test_update_refuses_inflight_before_creating_maintenance(self):
        from deploy.agent_source_update import begin_stop,UpdateError
        with TemporaryDirectory() as folder:
            state=Path(folder)
            for phase in ('sending','awaiting_ack','unknown'):
                (state/'execution-runtime.json').write_text(json.dumps({'schema':1,'phase':phase}))
                with self.assertRaisesRegex(UpdateError,'pause_cloud_and_drain'):begin_stop(state,'abc123')
                self.assertFalse((state/'maintenance.json').exists());self.assertFalse((state/'stop-request.json').exists())
