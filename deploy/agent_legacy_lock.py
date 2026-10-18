"""One-time legacy migration only: identify an exact lock holder, pin its creation time."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import sys
try:from agent_state_io import read_json
except ModuleNotFoundError:from contracts.state_files import read_json

class UniqueProcess(ctypes.Structure):
    _fields_=[('pid',w.DWORD),('created',w.FILETIME)]
class ProcessInfo(ctypes.Structure):
    _fields_=[('process',UniqueProcess),('name',w.WCHAR*256),('service',w.WCHAR*64),
        ('kind',ctypes.c_int),('status',w.ULONG),('session',w.DWORD),('restartable',w.BOOL)]

def holders(path):
    manager=ctypes.WinDLL('Rstrtmgr',use_last_error=True)
    manager.RmStartSession.argtypes=[ctypes.POINTER(w.DWORD),w.DWORD,w.LPWSTR]
    manager.RmRegisterResources.argtypes=[w.DWORD,w.UINT,ctypes.POINTER(w.LPCWSTR),w.UINT,ctypes.POINTER(UniqueProcess),w.UINT,ctypes.POINTER(w.LPCWSTR)]
    manager.RmGetList.argtypes=[w.DWORD,ctypes.POINTER(w.UINT),ctypes.POINTER(w.UINT),ctypes.POINTER(ProcessInfo),ctypes.POINTER(w.DWORD)]
    manager.RmEndSession.argtypes=[w.DWORD]
    session=w.DWORD();key=ctypes.create_unicode_buffer(33)
    code=manager.RmStartSession(ctypes.byref(session),0,key)
    if code:raise OSError(code,'Cannot open read-only resource query')
    try:
        names=(w.LPCWSTR*1)(str(Path(path).absolute()))
        code=manager.RmRegisterResources(session,1,names,0,None,0,None)
        if code:raise OSError(code,'Cannot register agent-lock resource')
        needed=w.UINT();count=w.UINT();reasons=w.DWORD()
        code=manager.RmGetList(session,ctypes.byref(needed),ctypes.byref(count),None,ctypes.byref(reasons))
        if code==0:return []
        if code!=234:raise OSError(code,'Cannot query agent-lock resource')
        for _ in range(3):
            count=w.UINT(needed.value);items=(ProcessInfo*count.value)()
            code=manager.RmGetList(session,ctypes.byref(needed),ctypes.byref(count),items,ctypes.byref(reasons))
            if code==0:
                return [{'pid':item.process.pid,'processCreationFileTime':(item.process.created.dwHighDateTime<<32)|item.process.created.dwLowDateTime} for item in items[:count.value]]
            if code!=234:raise OSError(code,'Cannot refresh agent-lock resource')
        raise RuntimeError('Agent lock owners changed repeatedly; no termination allowed')
    finally:manager.RmEndSession(session)

def terminate_holder(path,pid,created):
    # Caller must additionally validate the exact user's launcher command line.
    # This second live resource check and a pinned kernel handle prevent PID reuse.
    if not any(item['pid']==pid and item['processCreationFileTime']==created for item in holders(path)):
        raise ValueError('Process is no longer the identified agent-lock holder')
    terminate_pinned_process(pid,created)

def terminate_pinned_process(pid,created):
    # Never called before an exact file-holder or task-job identity check.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.GetProcessTimes.argtypes=[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)]
    kernel.TerminateProcess.argtypes=[w.HANDLE,w.UINT]
    kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
    kernel.CloseHandle.argtypes=[w.HANDLE]
    handle=kernel.OpenProcess(0x101001,False,pid)
    if not handle:raise OSError(ctypes.get_last_error(),'Cannot access identified legacy agent')
    try:
        born,exited,kt,ut=(w.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle,ctypes.byref(born),ctypes.byref(exited),ctypes.byref(kt),ctypes.byref(ut)):raise OSError('Cannot identify held process')
        if (born.dwHighDateTime<<32)|born.dwLowDateTime!=created:raise ValueError('Process identity changed')
        if not kernel.TerminateProcess(handle,7):raise OSError(ctypes.get_last_error(),'Exact legacy termination failed')
        if kernel.WaitForSingleObject(handle,5000)!=0:raise OSError('Exact legacy exit not confirmed')
    finally:kernel.CloseHandle(handle)

def terminate_supervisor(state,pid,created):
    metadata=read_json(Path(state)/'task-job.json')
    if metadata.get('wrapperPid')!=pid or metadata.get('wrapperCreationFileTime')!=created:
        raise ValueError('Supervisor identity changed')
    terminate_pinned_process(pid,created)

if __name__=='__main__':
    lock=Path(os.environ['LOCALAPPDATA'])/'OpsAgent/agent.lock'
    try:
        if len(sys.argv)==1:print(json.dumps(holders(lock)))
        elif len(sys.argv)==4 and sys.argv[1]=='--supervisor':
            terminate_supervisor(lock.parent,int(sys.argv[2]),int(sys.argv[3]));print('{"identifiedSupervisorExited":true}')
        elif len(sys.argv)==3:
            terminate_holder(lock,int(sys.argv[1]),int(sys.argv[2]));print('{"identifiedLegacyAgentExited":true}')
        else:raise ValueError('Invalid diagnostic arguments')
    except Exception as error:
        print(json.dumps({'result':'refused','reason':type(error).__name__}));raise SystemExit(1) from None
