"""Local cooperative stop/status protocol. No credentials, HTTP or process control."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
import uuid

STOP_FILE='stop-request.json'
MAINTENANCE_FILE='maintenance.json'
STATUS_FILE='agent-runtime.json'

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8') as handle:
            json.dump(value,handle,separators=(',',':'));handle.flush();os.fsync(handle.fileno())
        temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)

def request_identity(path):
    try:
        with Path(path).open('r',encoding='utf-8-sig') as handle: raw=handle.read(2049)
    except FileNotFoundError: return None
    try:
        data=json.loads(raw);value=data.get('requestId','')
        if len(raw)<=2048 and isinstance(value,str) and 1<=len(value)<=64 and all(char in '0123456789abcdef-' for char in value): return value
    except (ValueError,AttributeError,TypeError): pass
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
        self.version='unpackaged'
        path=Path(__file__).resolve().parents[1]/'deployment-manifest.json'
        if path.is_file():
            data=json.loads(path.read_text(encoding='utf-8-sig'));version=data.get('commit','')
            if isinstance(version,str) and len(version)==40 and all(char in '0123456789abcdef' for char in version): self.version=version
    def stop_request(self):
        return request_identity(self.state_dir/STOP_FILE) or request_identity(self.state_dir/MAINTENANCE_FILE)
    def publish(self,phase,request_id=None,workers_remaining=0):
        if phase not in {'starting','running','stopped','failed'}: raise ValueError('Invalid lifecycle phase')
        value={'schema':1,'instanceId':self.instance_id,'pid':os.getpid(),'parentPid':os.getppid(),
            'processCreationFileTime':self.creation_filetime,'version':self.version,'phase':phase,
            'observedAt':datetime.now(timezone.utc).isoformat(),'uptimeSeconds':time.monotonic()-self.started,
            'stopRequestId':request_id,'workersRemainingAtExit':workers_remaining}
        atomic_json(self.state_dir/STATUS_FILE,value)
