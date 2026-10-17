"""Real Windows supervisor/locks/processes; temporary synthetic services, zero home HTTP."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
from agent_job_integration import ROOT,PYTHON,fixture_launcher,read,wait_for,alive
from deploy.agent_legacy_lock import terminate_holder,terminate_supervisor
from deploy.agent_source_update import exclusive_agent_lock

@contextmanager
def fixture(mode='production',marker=None):
    with TemporaryDirectory(prefix='ops-agent-supervisor-fixture-') as directory:
        base=Path(directory);package=base/'package';state=base/'state';state.mkdir()
        (package/'agent').mkdir(parents=True);(package/'deploy').mkdir()
        (package/'agent/__init__.py').write_text('__path__.append('+repr(str(ROOT/'agent'))+')\n')
        (package/'agent/launcher.py').write_text(fixture_launcher)
        shutil.copyfile(ROOT/'deploy/AgentJobRunner.cs',package/'deploy/AgentJobRunner.cs')
        if marker:(state/marker).write_text('{"requestId":"abc123"}')
        if mode=='production':
            command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'deploy/agent-run.ps1'),
                '-AgentRoot',str(package),'-PythonExecutable',str(PYTHON),'-StateDirectory',str(state)]
        else:
            # Only the temporary harness uses a short delay. Production is fixed at 60000ms.
            quote=lambda value:"'"+str(value).replace("'","''")+"'"
            harness=base/'fast-supervisor.ps1'
            harness.write_text('Add-Type -Path '+quote(package/'deploy/AgentJobRunner.cs')+'\nexit [OpsAgentJob]::Supervise('+','.join(map(quote,(PYTHON,package,state)))+',500)\n')
            command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(harness)]
        environment=dict(os.environ,OPS_AGENT_JOB_FIXTURE_STATE=str(state),PYTHONPATH=str(ROOT))
        process=subprocess.Popen(command,env=environment,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        try:yield process,state,command,environment
        finally:
            if process.poll() is None:process.terminate();process.wait(8)
            def lock_free():
                try:
                    with exclusive_agent_lock(state):pass
                    return True
                except PermissionError:return False
            wait_for(lock_free,5)

def running(state,old=None):
    value=read(state/'agent-runtime.json')
    return value if value and value['phase']=='running' and value['instanceId']!=old else None

def stop(process,state):
    (state/'stop-request.json').write_text('{"requestId":"abc123"}')
    assert process.wait(5)==0

def report(case,**values):print(json.dumps(dict(case=case,homeHTTPRequests=0,actualScheduledTaskTest=False,**values)),flush=True)

def restart_and_single_supervisor():
    with fixture('fast') as (process,state,command,environment):
        old=wait_for(lambda:running(state));job=read(state/'task-job.json')
        # An additional invocation must not create a competing supervisor or overwrite status.
        duplicate=subprocess.Popen(command,env=environment,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
        try:assert duplicate.wait(8)==0
        finally:
            if duplicate.poll() is None:duplicate.terminate();duplicate.wait(5)
        assert read(state/'task-job.json')['wrapperPid']==process.pid
        try:terminate_supervisor(state,process.pid,job['wrapperCreationFileTime']+1)
        except ValueError:pass
        else:raise AssertionError('Wrong supervisor creation time accepted')
        assert process.poll() is None
        started=time.monotonic()
        terminate_holder(state/'agent.lock',old['pid'],old['processCreationFileTime'])
        waiting=wait_for(lambda: (value if value and value['phase']=='restart-wait' else None) if (value:=read(state/'task-job.json')) else None)
        assert waiting['exitCode']==7
        new=wait_for(lambda:running(state,old['instanceId']))
        elapsed=time.monotonic()-started;assert elapsed>=.5
        assert read(state/'task-job.json')['wrapperPid']==process.pid
        assert not alive(old['pid'])
        stop(process,state)
        report('real-supervisor-restarts-python',fixtureBackoffMilliseconds=500,elapsedSeconds=elapsed,
            oldPid=old['pid'],newPid=new['pid'],sameSupervisor=True,duplicateRejected=True)

def interrupt_production_backoff():
    with fixture() as (process,state,command,environment):
        old=wait_for(lambda:running(state))
        terminate_holder(state/'agent.lock',old['pid'],old['processCreationFileTime'])
        waiting=wait_for(lambda: (value if value and value['phase']=='restart-wait' else None) if (value:=read(state/'task-job.json')) else None)
        assert waiting['retryAfterSeconds']==60 and waiting['exitCode']==7
        started=time.monotonic();stop(process,state);elapsed=time.monotonic()-started
        assert elapsed<3 and read(state/'agent-runtime.json')['instanceId']==old['instanceId']
        report('production-60-second-backoff-interrupted-by-stop',elapsedSeconds=elapsed,noNewInstance=True)

def maintained_start(marker):
    with fixture(marker=marker) as (process,state,command,environment):
        assert process.wait(5)==0
        job=read(state/'task-job.json')
        assert job['phase']=='maintenance-blocked' and job['launcherPid']==0
        assert not (state/'agent-runtime.json').exists() and not (state/'agent.db').exists()
        assert (state/marker).is_file()
        report('maintained-start-'+marker,pythonStarted=False,privateConfigurationRead=False)

def supervisor_death_kills_tree():
    with fixture() as (process,state,command,environment):
        runtime=wait_for(lambda:running(state));job=read(state/'task-job.json');grandchild=read(state/'grandchild.json')
        pids={runtime['pid'],job['launcherPid'],grandchild['pid']}
        terminate_supervisor(state,process.pid,job['wrapperCreationFileTime'])
        assert process.wait(5)!=0
        wait_for(lambda:all(not alive(pid) for pid in pids),5)
        report('supervisor-terminated-whole-job-exits',allDescendantsExited=True)

if __name__=='__main__':
    restart_and_single_supervisor()
    interrupt_production_backoff()
    for marker in ('maintenance.json','stop-request.json'):maintained_start(marker)
    supervisor_death_kills_tree()
