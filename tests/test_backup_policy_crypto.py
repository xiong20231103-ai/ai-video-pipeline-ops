import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from agent.backup_crypto import CryptoError,create_recipient,encrypt,decrypt
from agent.backup_policy import PolicyError,Rule,inventory

class BackupPolicyTests(unittest.TestCase):
    def test_only_approved_metadata_and_explicit_secret_split(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); (root/'data').mkdir()
            (root/'data/state.json').write_text('{}')
            (root/'data/state.before-fix.json').write_text('{}')
            (root/'data/video.mp4').write_bytes(b'large-media-fixture')
            (root/'config.json').write_text('{"fixture":"inert"}')
            found=inventory({'OPS':root},[Rule('OPS','data/*.json'),Rule('OPS','config.json',True,True)])
            self.assertEqual({'data/state.json','config.json'},{row['relative'] for row in found['files']})
            self.assertEqual(['config.json'],[row['relative'] for row in found['files'] if row['secret']])

    def test_missing_required_and_oversize_fail_closed(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(PolicyError): inventory({'OPS':root},[Rule('OPS','required.json',True)])
            (root/'state.json').write_bytes(b'12345')
            with self.assertRaises(PolicyError): inventory({'OPS':root},[Rule('OPS','state.json',maximum=4)])
            found=inventory({'OPS':root},[Rule('OPS','optional.json')])
            self.assertEqual(1,len(found['optionalMissing']))
    def test_wildcard_directory_skips_sibling_markdown_and_keeps_real_handoff(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'handoff').mkdir();(root/'handoff/note.md').write_text('inert note')
            (root/'handoff/batch').mkdir();(root/'handoff/batch/state.json').write_text('{}')
            found=inventory({'WB':root},[Rule('WB','handoff/*/state.json')])
            self.assertEqual(['handoff/batch/state.json'],[r['relative'] for r in found['files']])

    def test_no_recursive_or_escape_pattern(self):
        with TemporaryDirectory() as folder:
            for pattern in ['**/*.json','../state.json','a//b.json','a\\b.json']:
                with self.assertRaises(PolicyError): inventory({'OPS':Path(folder)},[Rule('OPS',pattern)])

    def test_reparse_flag_rejected_before_traversing_matching_directory(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        with TemporaryDirectory() as folder:
            root=Path(folder); linked=root/'linked'; linked.mkdir()
            (linked/'state.json').write_text('{}')
            original=Path.lstat
            def flagged(path,*args,**kwargs):
                info=original(path,*args,**kwargs)
                if Path(path)==linked:
                    return SimpleNamespace(st_mode=info.st_mode,st_file_attributes=0x400)
                return info
            with patch.object(Path,'lstat',flagged):
                with self.assertRaises(PolicyError): inventory({'OPS':root},[Rule('OPS','linked/*.json')])
