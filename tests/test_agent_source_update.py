import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from deploy.agent_source_update import FILES,prepare,apply,restore,validate

def package(path,commit):
    path.mkdir()
    hashes={}
    for name in FILES:
        file=path/name;file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text(commit+':'+name,encoding='utf-8')
        hashes[name]=hashlib.sha256(file.read_bytes()).hexdigest()
    (path/'deployment-manifest.json').write_text(json.dumps({'commit':commit,'sha256':hashes}),encoding='utf-8')

class AgentSourceUpdateTests(unittest.TestCase):
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
