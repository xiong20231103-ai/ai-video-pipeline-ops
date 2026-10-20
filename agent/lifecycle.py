"""Local cooperative stop/status protocol. No credentials, HTTP or process control."""
from datetime import datetime,timezone
import json
import os
import re
from pathlib import Path
import time
import uuid
from contracts.state_files import atomic_json,read_json

STOP_FILE='stop-request.json'
MAINTENANCE_FILE='maintenance.json'
STATUS_FILE='agent-runtime.json'

def request_identity(path):
    try:data=read_json(path,max_bytes=2048,retry_missing=False)
    except FileNotFoundError:return None
    except (ValueError,UnicodeError):return 'manual'
    try:
        value=data.get('requestId','')
        if isinstance(value,str) and 1<=len(value)<=64 and all(char in '0123456789abcdef-' for char in value):return value
    except (AttributeError,TypeError):pass
    return 'manual'

def own_creation_filetime():
    if os.name!='nt': return None
    import ctypes
    from ctypes import wintypes as w
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.GetProcessTimes.argtypes=[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)]
    kernel.GetProcessTimes.restype=w.BOOL
    created,exited,kernel_time,user_time=(w.FILETIME() for _ in range(4))
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(),ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel_time),ctypes.byref(user_time)):
        raise OSError('Cannot identify own process creation time')
    return (created.dwHighDateTime<<32)|created.dwLowDateTime

class Lifecycle:
    def __init__(self,state_dir):
        self.state_dir=Path(state_dir);self.instance_id=uuid.uuid4().hex
        self.started=time.monotonic();self.creation_filetime=own_creation_filetime()
        self.worker_failure=None;self.failure_persisted=False
        self.version='unpackaged'
        path=Path(__file__).resolve().parents[1]/'deployment-manifest.json'
        if path.is_file():
            data=read_json(path);version=data.get('commit','')
            if isinstance(version,str) and len(version)==40 and all(char in '0123456789abcdef' for char in version): self.version=version
    def stop_request(self):
        return request_identity(self.state_dir/STOP_FILE) or request_identity(self.state_dir/MAINTENANCE_FILE)
    def record_worker_failure(self,worker,error):
        if worker not in {'heartbeat','collection','upload','demand','foreground','backup','commands','engine','engine-compatibility','engine-retention'}:raise ValueError('Unknown worker')
        def identifier(value):
            return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',value) else 'other'
        frames=[];trace=error.__traceback__
        while trace:
            code=trace.tb_frame.f_code
            frames.append({'file':identifier(Path(code.co_filename).name),'function':identifier(code.co_name),'line':trace.tb_lineno})
            trace=trace.tb_next
        # Never stringify an exception or capture messages, source lines or locals.
        self.worker_failure={'worker':worker,'exceptionType':identifier(type(error).__name__),'frames':frames[-8:]}
        code=getattr(error,'sqlite_errorcode',None)
        if type(code) is int:self.worker_failure['sqliteCode']=code
        event={'schema':1,'instanceId':self.instance_id,'pid':os.getpid(),'version':self.version,
               'observedAt':datetime.now(timezone.utc).isoformat(),'failure':self.worker_failure}
        atomic_json(self.state_dir/'last-worker-failure.json',event)
        self.failure_persisted=True
    def publish(self,phase,request_id=None,workers_remaining=0):
        if phase not in {'starting','running','stopped','failed'}: raise ValueError('Invalid lifecycle phase')
        value={'schema':1,'instanceId':self.instance_id,'pid':os.getpid(),'parentPid':os.getppid(),
            'processCreationFileTime':self.creation_filetime,'version':self.version,'phase':phase,
            'observedAt':datetime.now(timezone.utc).isoformat(),'uptimeSeconds':time.monotonic()-self.started,
            'stopRequestId':request_id,'workersRemainingAtExit':workers_remaining}
        if self.worker_failure is not None:
            value['workerFailure']=self.worker_failure;value['workerFailurePersisted']=self.failure_persisted
        atomic_json(self.state_dir/STATUS_FILE,value)
