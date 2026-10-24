"""Source package rollback uses only temporary synthetic packages."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from deploy import agent_source_update as update


class SourceRollbackTests(unittest.TestCase):
    def package(self,root,names,commit):
        hashes={}
        for name in names:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(('isolated package '+commit+' '+name).encode())
            hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        (root/'deployment-manifest.json').write_text(json.dumps({'commit':commit,'sha256':hashes}))
    def test_r6_to_previous_package_removes_only_owned_additive_files(self):
        with TemporaryDirectory(prefix='r6-source-') as temp:
            root=Path(temp);old=root/'installed';new=root/'new';backup=root/'backup'
            self.package(old,update.FILES,'a'*40)
            self.package(new,update.R6_RELOCATED_FILES,'b'*40)
            private=old/'private-state.bin';private.write_bytes(b'inert preserved local state')
            update.prepare(new,old,backup,'b'*40)
            update.apply(new,old,backup,'b'*40)
            self.assertTrue((old/'agent/engine_runtime.py').is_file())
            update.restore(backup,old)
            self.assertEqual('a'*40,update.validate(old)['commit'])
            for name in update.KNOWN_RUNTIME_FILES-set(update.FILES):self.assertFalse((old/name).exists(),name)
            self.assertEqual(b'inert preserved local state',private.read_bytes())
            for name in update.FILES:
                self.assertEqual((backup/name).read_bytes(),(old/name).read_bytes(),name)

    def installed_fixture(self):
        path=Path(__file__).parent/'fixtures/agent-source-update/installed-78949774.json'
        return json.loads(path.read_text(encoding='utf-8'))

    def test_historical_whitelists_keep_exact_installed_paths(self):
        installed=set(self.installed_fixture()['files'])
        self.assertEqual(set(update.INITIAL_R6_FILES),installed)
        previous=installed|{'agent/core/source_profiles.py','agent/core/collection_verified_final.py','verified_final.py'}
        self.assertEqual(set(update.PREVIOUS_R6_FILES),previous)
        self.assertEqual(set(update.R6_FILES),previous|{
            'agent/core/verified_final_replay.py','contracts/legacy-verified-final-pr49.txt',
            'contracts/legacy-verified-final-fresh.txt',
        })

    def test_installed_and_historical_r6_upgrade_to_relocated_and_restore(self):
        fixture=self.installed_fixture()
        layouts=(fixture['files'],update.PREVIOUS_R6_FILES,update.R6_FILES)
        for names in layouts:
            with self.subTest(files=len(names)),TemporaryDirectory(prefix='r6-relocated-') as temp:
                root=Path(temp);old=root/'installed';new=root/'new';backup=root/'backup'
                self.package(old,names,fixture['commit'])
                self.package(new,update.R6_RELOCATED_FILES,'b'*40)
                before={name:(old/name).read_bytes() for name in (*names,'deployment-manifest.json')}
                private={}
                for name in ('private-state.bin','docs/migration/local-state.json','contracts/migration/local-state.json'):
                    path=old/name;path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(b'unlisted private state');private[name]=path.read_bytes()

                update.prepare(new,old,backup,'b'*40)
                self.assertEqual(fixture['commit'],update.validate(old)['commit'])
                self.assertEqual(set(names),set(update.validate(backup)['sha256']))
                update.apply(new,old,backup,'b'*40)
                self.assertEqual(set(update.R6_RELOCATED_FILES),set(update.validate(old)['sha256']))
                for name in set(names)-set(update.R6_RELOCATED_FILES):
                    self.assertFalse((old/name).exists(),name)
                for name in update.R6_RELOCATED_FILES:
                    self.assertEqual((new/name).read_bytes(),(old/name).read_bytes(),name)

                update.restore(backup,old)
                self.assertEqual(set(names),set(update.validate(old)['sha256']))
                for name,content in before.items():self.assertEqual(content,(old/name).read_bytes(),name)
                for name in set(update.R6_RELOCATED_FILES)-set(names):
                    self.assertFalse((old/name).exists(),name)
                for name,content in private.items():self.assertEqual(content,(old/name).read_bytes(),name)

    def test_failed_relocated_apply_restores_installed_package(self):
        fixture=self.installed_fixture()
        with TemporaryDirectory(prefix='r6-relocated-failure-') as temp:
            root=Path(temp);old=root/'installed';new=root/'new';backup=root/'backup'
            self.package(old,fixture['files'],fixture['commit'])
            self.package(new,update.R6_RELOCATED_FILES,'b'*40)
            update.prepare(new,old,backup,'b'*40)
            copyfile=update.shutil.copyfile
            def fail_contract_copy(source,destination):
                if Path(source)==new/'contracts/migration/r6-provenance.json':
                    raise OSError('injected relocated contract copy failure')
                return copyfile(source,destination)
            with patch.object(update.shutil,'copyfile',side_effect=fail_contract_copy):
                with self.assertRaisesRegex(OSError,'injected relocated contract'):
                    update.apply(new,old,backup,'b'*40)
            self.assertEqual(fixture['commit'],update.validate(old)['commit'])
            for name in (*fixture['files'],'deployment-manifest.json'):
                self.assertEqual((backup/name).read_bytes(),(old/name).read_bytes(),name)
            for name in set(update.R6_RELOCATED_FILES)-set(fixture['files']):
                self.assertFalse((old/name).exists(),name)

    def test_mixed_provenance_layout_is_not_an_accepted_whitelist(self):
        with TemporaryDirectory(prefix='r6-relocated-mixed-') as temp:
            root=Path(temp);old=root/'installed';new=root/'new';backup=root/'backup'
            self.package(old,update.R6_FILES,'a'*40)
            mixed=tuple(name.replace('contracts/migration/r1-provenance.json',
                                     'docs/migration/r1-provenance.json') for name in update.R6_RELOCATED_FILES)
            self.package(new,mixed,'b'*40)
            with self.assertRaisesRegex(update.UpdateError,'unexpected_source_whitelist'):
                update.prepare(new,old,backup,'b'*40)
            self.assertFalse(backup.exists())
            self.assertEqual('a'*40,update.validate(old)['commit'])

    def test_restore_checks_relocated_manifest_identity_before_copying(self):
        with TemporaryDirectory(prefix='r6-relocated-identity-') as temp:
            root=Path(temp);old=root/'installed';new=root/'new';backup=root/'backup'
            self.package(old,update.R6_FILES,'a'*40)
            self.package(new,update.R6_RELOCATED_FILES,'b'*40)
            update.prepare(new,old,backup,'b'*40);update.apply(new,old,backup,'b'*40)
            manifest=json.loads((old/'deployment-manifest.json').read_text())
            manifest['sha256']['docs/migration/r1-provenance.json']=manifest['sha256'].pop('contracts/migration/r1-provenance.json')
            (old/'deployment-manifest.json').write_text(json.dumps(manifest))
            before=(old/'agent/engine_runtime.py').read_bytes()
            with self.assertRaisesRegex(update.UpdateError,'rollback_source_identity_changed'):
                update.restore(backup,old)
            self.assertEqual(before,(old/'agent/engine_runtime.py').read_bytes())
