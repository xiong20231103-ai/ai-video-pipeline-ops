"""Bounded state JSON I/O. No credential access, logging, network or process control."""
import errno
import json
import os
from pathlib import Path
import sys
import time
import uuid

ATTEMPTS=10
RETRY_SECONDS=.2

def transient(error):
    return getattr(error,'winerror',None) in {5,32,33} or getattr(error,'errno',None) in {errno.EACCES,errno.EBUSY,errno.EAGAIN}

def open_shared_read(path):
    if os.name!='nt':return Path(path).open('rb')
    import ctypes
    from ctypes import wintypes as w
    import msvcrt
    # Preserve the isolated runner's file-access audit before native open.
    sys.audit('open',str(path),'r',os.O_RDONLY)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE]
    kernel.CreateFileW.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.CreateFileW(str(path),0x80000000,7,None,3,0x80,None) # READ|WRITE|DELETE sharing
    if handle==w.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:descriptor=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY|os.O_NOINHERIT)
    except BaseException:kernel.CloseHandle(handle);raise
    return os.fdopen(descriptor,'rb')

def read_json(path,max_bytes=1024*1024,retry_missing=True):
    for attempt in range(ATTEMPTS):
        try:
            with open_shared_read(path) as stream:raw=stream.read(max_bytes+1)
            if len(raw)>max_bytes:raise ValueError('State JSON exceeds read limit')
            return json.loads(raw.decode('utf-8-sig'))
        except (OSError,UnicodeError,json.JSONDecodeError) as error:
            if isinstance(error,FileNotFoundError) and not retry_missing:raise
            if isinstance(error,OSError) and not isinstance(error,FileNotFoundError) and not transient(error):raise
            if attempt==ATTEMPTS-1:raise
            time.sleep(RETRY_SECONDS)

def replace_file(source,target):
    if os.name!='nt':os.replace(source,target);return
    import ctypes
    from ctypes import wintypes as w
    # ReplaceFile permits already-open delete-shared snapshots; MoveFileEx used
    # by os.replace does not provide the same replacement behavior on Windows.
    sys.audit('os.rename',str(source),str(target),-1,-1)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.ReplaceFileW.argtypes=[w.LPCWSTR,w.LPCWSTR,w.LPCWSTR,w.DWORD,w.LPVOID,w.LPVOID]
    kernel.ReplaceFileW.restype=w.BOOL
    if kernel.ReplaceFileW(str(target),str(source),None,0,None,None):return
    error=ctypes.get_last_error()
    if error==2:os.replace(source,target);return # Initial publication; no old snapshot.
    raise ctypes.WinError(error)

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        # Python's CRT open uses shared read/write; target is never truncated.
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
        for attempt in range(ATTEMPTS):
            try:replace_file(temporary,path);return
            except OSError as error:
                if not transient(error) or attempt==ATTEMPTS-1:raise
                time.sleep(RETRY_SECONDS)
    finally:temporary.unlink(missing_ok=True)
