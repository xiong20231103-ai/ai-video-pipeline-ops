"""Only synthetic temp paths; forbidden probes never reach their target."""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from agent.core.sandbox import SandboxIO


class MetadataGuardTests(unittest.TestCase):
    def test_metadata_and_mutations_outside_snapshot_are_rejected(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/'scratch';root.mkdir()
            outside=Path(directory)/'outside';outside.mkdir()
            file=outside/'file';file.write_text('unchanged')
            operations=[lambda:os.listdir(outside),lambda:list(os.scandir(outside)),
                lambda:list(os.walk(outside)),lambda:os.path.exists(file),
                lambda:os.path.isfile(file),lambda:os.path.isdir(outside),
                lambda:os.path.lexists(file),lambda:os.utime(file,None),
                lambda:os.chmod(file,0o600)]
            with ExitStack() as stack:
                guard=SandboxIO(root,stack).install()
                for operation in operations:
                    with self.subTest(operation=operation),self.assertRaisesRegex(PermissionError,'outside_snapshot'):
                        operation()
                self.assertEqual(len(operations),len(guard.denied))
            self.assertEqual('unchanged',file.read_text())

    def test_scratch_and_explicit_alias_support_enumeration_and_metadata(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'mapped';folder.mkdir()
            file=folder/'file';file.write_text('fixture')
            with ExitStack() as stack:
                SandboxIO(root,stack,aliases={'Z:/synthetic': 'mapped'}).install()
                self.assertEqual(['file'],os.listdir('Z:/synthetic'))
                self.assertEqual(['file'],[item.name for item in os.scandir('Z:/synthetic')])
                self.assertTrue(os.path.isfile('Z:/synthetic/file'))
                self.assertTrue(os.path.exists('Z:/synthetic/file'))
                self.assertEqual(1,len(list(os.walk('Z:/synthetic'))))
                os.utime(file,None);os.chmod(file,0o600)
