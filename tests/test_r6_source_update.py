"""Source package rollback uses only temporary synthetic packages."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
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
            self.package(new,update.R6_FILES,'b'*40)
            private=old/'private-state.bin';private.write_bytes(b'inert preserved local state')
            update.prepare(new,old,backup,'b'*40)
            update.apply(new,old,backup,'b'*40)
            self.assertTrue((old/'agent/engine_runtime.py').is_file())
            update.restore(backup,old)
            self.assertEqual('a'*40,update.validate(old)['commit'])
            for name in set(update.R6_FILES)-set(update.FILES):self.assertFalse((old/name).exists(),name)
            self.assertEqual(b'inert preserved local state',private.read_bytes())
            for name in update.FILES:
                self.assertEqual((backup/name).read_bytes(),(old/name).read_bytes(),name)
