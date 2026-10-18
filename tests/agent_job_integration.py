"""Real Windows processes/file locks; synthetic services only, no production HTTP."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PYTHON=Path(os.environ.get('OPS_AGENT_TEST_PYTHON',r'C:\Users\Administrator\AppData\Local\TikHubOPS\venv_cuda\Scripts\python.exe'))
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
kernel.CloseHandle.argtypes=[w.HANDLE]
kernel.GetExitCodeProcess.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
kernel.GetProcessTimes.argtypes=[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)]
kernel.TerminateProcess.argtypes=[w.HANDLE,w.UINT]

def alive(pid):
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return False
        raise OSError(ctypes.get_last_error(),'Cannot query own fixture process')
    try:
        code=w.DWORD();assert kernel.GetExitCodeProcess(handle,ctypes.byref(code))
        return code.value==259
    finally:kernel.CloseHandle(handle)

def crash_fixture(runtime):
    handle=kernel.OpenProcess(0x1001,False,runtime['pid']);assert handle
    try:
        created,exited,kt,ut=(w.FILETIME() for _ in range(4))
        assert kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kt),ctypes.byref(ut))
        assert (created.dwHighDateTime<<32)|created.dwLowDateTime==runtime['processCreationFileTime']
        assert kernel.TerminateProcess(handle,7)
    finally:kernel.CloseHandle(handle)

def read(path):
    from contracts.state_files import read_json
    try:return read_json(path)
    except FileNotFoundError:return None

def wait_for(predicate,timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(.05)
    raise AssertionError('Fixture deadline exceeded')

fixture_launcher='''import json,os,subprocess,sys,time
from pathlib import Path
from agent.readonly import ReadOnlyAgent
state=Path(os.environ['OPS_AGENT_JOB_FIXTURE_STATE'])
grandchild=subprocess.Popen([sys.executable,'-B','-c','import time;time.sleep(90)'],creationflags=subprocess.CREATE_NO_WINDOW)
(state/'grandchild.json').write_text(json.dumps({'pid':grandchild.pid}))
agent=ReadOnlyAgent('https://fixture.ts.net','inert-synthetic-credential',state)
def cloud(path,data=None):
    if path=='/agent/fetch-requests':return {'items':[],'viewerActive':False,'viewerLeaseSeconds':0}
    if path=='/agent/push':return {'result':'stored'}
    return {'viewerActive':False,'viewerLeaseSeconds':0}
agent.cloud=cloud
agent.collect=lambda *args,**kwargs:time.sleep(60)
def forbidden(*args,**kwargs):raise AssertionError('All fixture network forbidden')
agent.transport.open=forbidden
agent.run()
'''

def case(kind):
    with TemporaryDirectory(prefix='ops-agent-job-fixture-') as temporary:
        base=Path(temporary);fixture=base/'package';state=base/'state';state.mkdir()
        (fixture/'agent').mkdir(parents=True);(fixture/'deploy').mkdir()
        (fixture/'agent/__init__.py').write_text('__path__.append('+repr(str(ROOT/'agent'))+')\n')
        (fixture/'agent/launcher.py').write_text(fixture_launcher)
        shutil.copyfile(ROOT/'deploy/AgentJobRunner.cs',fixture/'deploy/AgentJobRunner.cs')
        shutil.copyfile(ROOT/'deploy/agent-json.ps1',fixture/'deploy/agent-json.ps1')
        environment=dict(os.environ,OPS_AGENT_JOB_FIXTURE_STATE=str(state),PYTHONPATH=str(ROOT))
        # This suite tests one Job's exit propagation; the separate supervisor
        # suite exercises the production wrapper's new restart loop.
        harness=base/'run-one-job.ps1'
        quote=lambda value: "'"+str(value).replace("'","''")+"'"
        harness.write_text('Add-Type -Path '+quote(fixture/'deploy/AgentJobRunner.cs')+'\nexit [OpsAgentJob]::Run('+','.join(map(quote,(PYTHON,fixture,state)))+')\n')
        command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(harness)]
        wrapper=subprocess.Popen(command,env=environment,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            runtime=wait_for(lambda: (row if row and row.get('phase')=='running' else None) if (row:=read(state/'agent-runtime.json')) else None)
            job=wait_for(lambda:read(state/'task-job.json'));grandchild=wait_for(lambda:read(state/'grandchild.json'))
            pids=sorted({runtime['pid'],job['launcherPid'],grandchild['pid']})
            assert all(alive(pid) for pid in pids)
            started=time.monotonic()
            if kind=='cooperative-stop':
                (state/'stop-request.json').write_text('{"requestId":"abc123"}')
            elif kind=='worker-crash':
                from deploy.agent_legacy_lock import holders,terminate_holder
                owners=holders(state/'agent.lock')
                assert any(item['pid']==runtime['pid'] and item['processCreationFileTime']==runtime['processCreationFileTime'] for item in owners)
                try:terminate_holder(state/'agent.lock',runtime['pid'],runtime['processCreationFileTime']+1)
                except ValueError:pass
                else:raise AssertionError('Mismatched process identity must not terminate')
                assert alive(runtime['pid'])
                terminate_holder(state/'agent.lock',runtime['pid'],runtime['processCreationFileTime'])
            else:wrapper.terminate()
            code=wrapper.wait(timeout=8)
            wait_for(lambda:all(not alive(pid) for pid in pids),timeout=5)
            from deploy.agent_source_update import exclusive_agent_lock
            process_exit_seconds=time.monotonic()-started
            def lock_released():
                try:
                    with exclusive_agent_lock(state):pass
                    return True
                except PermissionError:return False
            # Job teardown is asynchronous: an exit code can precede kernel
            # lock/handle cleanup. Wait boundedly, just like the real updater.
            wait_for(lock_released,timeout=5)
            if kind=='cooperative-stop':
                assert code==0;assert read(state/'agent-runtime.json')['stopRequestId']=='abc123'
                assert time.monotonic()-started<5
            elif kind=='worker-crash':assert code!=0
            print(json.dumps({'case':kind,'kind':'real-windows-processes-with-synthetic-services',
                'wrapperPid':wrapper.pid,'managedPids':pids,'wrapperExitCode':code,
                'elapsedSeconds':time.monotonic()-started,'processExitSeconds':process_exit_seconds,'lockFree':True,'allDescendantsExited':True,
                'homeHTTPRequests':0,'actualScheduledTaskTest':False}),flush=True)
        finally:
            if wrapper.poll() is None:wrapper.terminate();wrapper.wait(timeout=5)

if __name__=='__main__':
    assert os.name=='nt' and PYTHON.is_file()
    for kind in ('cooperative-stop','worker-crash','wrapper-terminated'):case(kind)
