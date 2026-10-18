import ctypes
from ctypes import wintypes as w
import errno
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import patch
from contracts import state_files as io
from deploy.agent_source_update import read_json as update_read_json
from agent.lifecycle import Lifecycle

class StateFilesTests(unittest.TestCase):
    def test_bounded_reader_retries_without_fake_success(self):
        with patch.object(io,'open_shared_read',side_effect=PermissionError(errno.EACCES,'fixture sharing')),patch.object(io.time,'sleep') as sleep:
            with self.assertRaises(PermissionError):io.read_json('inert-fixture')
            self.assertEqual(9,sleep.call_count)

    def test_missing_snapshot_retries_but_absent_marker_returns_immediately(self):
        with patch.object(io,'open_shared_read',side_effect=[FileNotFoundError(),FileNotFoundError(),__import__('io').BytesIO(b'{"phase":"running"}')]),patch.object(io.time,'sleep') as sleep:
            self.assertEqual('running',io.read_json('inert-fixture')['phase'])
            self.assertEqual(2,sleep.call_count)
        with patch.object(io,'open_shared_read',side_effect=FileNotFoundError()),patch.object(io.time,'sleep') as sleep:
            with self.assertRaises(FileNotFoundError):io.read_json('absent-marker',retry_missing=False)
            sleep.assert_not_called()

    def test_partial_json_is_retried_until_repaired(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';path.write_text('{')
            worker=threading.Thread(target=lambda:(time.sleep(.15),path.write_text('{"phase":"repaired"}')))
            worker.start()
            try:self.assertEqual('repaired',update_read_json(path)['phase'])
            finally:worker.join()

    def test_failed_atomic_replace_preserves_last_complete_value(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';io.atomic_json(path,{'version':'old'})
            with patch.object(io,'replace_file',side_effect=PermissionError(errno.EACCES,'fixture sharing')),patch.object(io.time,'sleep') as sleep:
                with self.assertRaises(PermissionError):io.atomic_json(path,{'version':'new'})
                self.assertEqual(9,sleep.call_count)
            self.assertEqual({'version':'old'},io.read_json(path));self.assertEqual([],list(Path(folder).glob('*.tmp')))

    @unittest.skipUnless(os.name=='nt','Windows file sharing')
    def test_actual_exclusive_handle_then_read_recovery(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'agent-runtime.json';io.atomic_json(path,{'phase':'running'})
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE];kernel.CreateFileW.restype=w.HANDLE
            kernel.CloseHandle.argtypes=[w.HANDLE]
            handle=kernel.CreateFileW(str(path),0x80000000,0,None,3,0x80,None)
            self.assertNotEqual(w.HANDLE(-1).value,handle)
            worker=threading.Thread(target=lambda:(time.sleep(.35),kernel.CloseHandle(handle)));worker.start()
            started=time.monotonic()
            try:self.assertEqual('running',io.read_json(path)['phase'])
            finally:worker.join()
            self.assertGreaterEqual(time.monotonic()-started,.2)

    def test_shared_reader_allows_atomic_replace_and_keeps_complete_snapshot(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';io.atomic_json(path,{'version':'old'})
            with io.open_shared_read(path) as reader:
                io.atomic_json(path,{'version':'new'})
                self.assertEqual({'version':'old'},json.loads(reader.read()))
            self.assertEqual({'version':'new'},io.read_json(path))

    def test_runtime_publish_with_concurrent_readers_has_no_torn_json(self):
        with TemporaryDirectory() as folder:
            lifecycle=Lifecycle(folder);lifecycle.publish('running')
            path=Path(folder)/'agent-runtime.json';errors=[];stop=threading.Event()
            def reader():
                try:
                    while not stop.is_set():
                        value=io.read_json(path)
                        if value['phase']!='running' or value['instanceId']!=lifecycle.instance_id:raise AssertionError('Corrupt complete snapshot')
                except BaseException as error:errors.append(type(error).__name__)
            workers=[threading.Thread(target=reader) for _ in range(3)]
            for worker in workers:worker.start()
            try:
                for _ in range(40):lifecycle.publish('running')
            finally:
                stop.set()
                for worker in workers:worker.join(5)
            self.assertFalse(any(worker.is_alive() for worker in workers));self.assertEqual([],errors)
