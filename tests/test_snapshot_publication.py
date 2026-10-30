"""Own temporary directories only; exercise real Windows sharing contention."""
import ctypes
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.core.snapshot import SnapshotError, _publish_snapshot


class PublicationTests(unittest.TestCase):
    def test_existing_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)/'stage';stage.mkdir();(stage/'new').write_text('new')
            target=Path(folder)/'target';target.mkdir();(target/'old').write_text('old')
            with self.assertRaisesRegex(SnapshotError,'snapshot_destination_exists'):
                _publish_snapshot(stage,target)
            self.assertEqual((target/'old').read_text(),'old')
            self.assertTrue((stage/'new').exists())

    def test_unrelated_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)/'stage';stage.mkdir()
            with patch('agent.core.snapshot.os.rename',side_effect=OSError('synthetic_io_error')) as replace:
                with self.assertRaisesRegex(OSError,'synthetic_io_error'):
                    _publish_snapshot(stage,Path(folder)/'target')
            self.assertEqual(replace.call_count,1)

    @unittest.skipUnless(os.name=='nt','Windows rename retry classification')
    def test_destination_created_during_contention_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)/'stage';stage.mkdir();target=Path(folder)/'target'
            def contention(*args):
                target.mkdir();(target/'other-owner').write_text('preserved')
                error=PermissionError('synthetic_contention');error.winerror=5
                raise error
            with patch('agent.core.snapshot.os.rename',side_effect=contention) as rename:
                with self.assertRaisesRegex(SnapshotError,'snapshot_destination_exists'):
                    _publish_snapshot(stage,target)
                self.assertEqual(rename.call_count,1)
            self.assertTrue(stage.exists())
            self.assertEqual((target/'other-owner').read_text(),'preserved')

    @unittest.skipUnless(os.name=='nt','Windows rename retry classification')
    def test_replaced_stage_is_rejected_before_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)/'stage';stage.mkdir();target=Path(folder)/'target'
            original_rename=os.rename
            def substitute(*args):
                original_rename(stage,Path(folder)/'saved-stage')
                stage.mkdir();(stage/'unvalidated').write_text('different')
                error=PermissionError('synthetic_contention');error.winerror=5
                raise error
            with patch('agent.core.snapshot.os.rename',side_effect=substitute) as rename:
                with self.assertRaisesRegex(SnapshotError,'snapshot_stage_identity_changed'):
                    _publish_snapshot(stage,target)
                self.assertEqual(rename.call_count,1)
            self.assertFalse(target.exists())

    @unittest.skipUnless(os.name=='nt','Windows directory sharing handles')
    def test_real_directory_lock_can_release_during_bounded_retry(self):
        self._real_lock_case(release=True)

    @unittest.skipUnless(os.name=='nt','Windows directory sharing handles')
    def test_permanent_directory_lock_times_out_without_publication(self):
        self._real_lock_case(release=False)

    def _real_lock_case(self,*,release):
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        api.CreateFileW.restype=wintypes.HANDLE
        api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
        with tempfile.TemporaryDirectory() as folder:
            stage=Path(folder)/'stage';stage.mkdir();(stage/'snapshot.json').write_text('fixture')
            target=Path(folder)/'target'
            # Read/write sharing, deliberately no FILE_SHARE_DELETE.
            # Hold a child file for reading without delete sharing. Windows
            # must not rename its containing directory until it is released.
            handle=api.CreateFileW(str(stage/'snapshot.json'),0x80000000,3,None,3,0x80,None)
            self.assertNotEqual(handle,ctypes.c_void_p(-1).value)
            released=threading.Event()
            def close():
                api.CloseHandle(handle);released.set()
            timer=threading.Timer(0.08,close) if release else None
            if timer:timer.start()
            try:
                started=time.monotonic()
                if release:
                    _publish_snapshot(stage,target,timeout=1)
                    self.assertTrue(released.is_set())
                    self.assertEqual((target/'snapshot.json').read_text(),'fixture')
                    self.assertFalse(stage.exists())
                else:
                    with self.assertRaises(PermissionError):
                        _publish_snapshot(stage,target,timeout=0.08)
                    self.assertTrue((stage/'snapshot.json').exists())
                    self.assertFalse(target.exists())
                self.assertLess(time.monotonic()-started,2)
            finally:
                if timer:timer.join(timeout=2)
                if not released.is_set():close()
