"""Real PowerShell 5.1/Python/uvicorn fixtures, ephemeral loopback only.

Run separately from the isolated unit runner (which blocks process creation).
Never imports installed app.py, reads live settings or controls home processes.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

ROOT=Path(__file__).resolve().parents[1]
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)
POWERSHELL=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'

APP='''import json,os,sys,time,threading
from pathlib import Path
from fastapi import FastAPI
base=Path(__file__).parent
sys.stderr.write('FIXTURE_STDERR_BEFORE_SERVER\\n');sys.stderr.flush()
with (base/'events.jsonl').open('a') as stream:stream.write(json.dumps({'event':'app-import','pid':os.getpid()})+'\\n')
CONFIG=json.loads((base/'fixture.json').read_text())
app=FastAPI()
'''

RUNTIME='''import json,os,threading,time
from pathlib import Path
import psutil,uvicorn
def configure(dashboard,spec,mode,control):
    base=Path(dashboard.__file__).parent
    if spec['scenario']=='prepare-fail':raise ValueError('fixture preparation failure')
    def serve(app,**options):
        with (base/'events.jsonl').open('a') as stream:stream.write(json.dumps({'event':'serve-call','pid':os.getpid()})+'\\n')
        process=psutil.Process()
        (base/'owner.json').write_text(json.dumps({'pid':os.getpid(),'created':process.create_time(),'runId':spec['runId']}))
        server=uvicorn.Server(uvicorn.Config(app,**options))
        def finish():
            while not (base/'FINISH').exists():time.sleep(.02)
            server.should_exit=True
        threading.Thread(target=finish,daemon=True).start()
        server.run()
        if spec['scenario']=='after-start-exit':raise SystemExit(23)
    uvicorn.run=serve
'''


def write_json(path,value):
    path.write_text(json.dumps(value),encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PowerShell51ProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name!='nt':raise unittest.SkipTest('Windows PowerShell 5.1 fixture')
        version=subprocess.check_output([str(POWERSHELL),'-NoProfile','-NonInteractive','-Command',
            '$PSVersionTable.PSVersion.ToString()'],creationflags=FLAGS,text=True).strip()
        if not version.startswith('5.1.'):raise AssertionError('Expected explicit powershell.exe 5.1, got '+version)
        print('Real process fixture host: Windows PowerShell '+version,flush=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='shadow-ps51-')
        self.base=Path(self.temp.name);self.package=self.base/'package';self.project=self.base/'original'
        (self.package/'tools').mkdir(parents=True);self.project.mkdir()
        self.settings=self.base/'settings.json';self.legacy=self.base/'legacy.jsonl'
        self.run_id=self.base.name;self.wrapper=None;self.owner=None
        self.addCleanup(self.cleanup)

    def cleanup(self):
        # Gracefully release only this fixture even if a prior ownership
        # assertion failed; never bypass the force-kill identity checks.
        (self.project/'FINISH').write_text('cleanup this fixture only')
        if self.wrapper is not None:
            if self.wrapper.poll() is None:
                try:self.wrapper.communicate(timeout=5)
                except subprocess.TimeoutExpired:self.kill_owned_child()
            if self.wrapper.poll() is None:self.wrapper.kill()
            self.wrapper.communicate(timeout=15)
        self.temp.cleanup()

    def kill_owned_child(self):
        receipt=self.project/'owner.json'
        if not receipt.exists():return
        try:
            value=json.loads(receipt.read_text());process=psutil.Process(value['pid'])
            if value['runId']!=self.run_id or process.create_time()!=value['created']:raise AssertionError('fixture PID ownership mismatch')
            expected=(self.package/'tools/shadow_dashboard_bootstrap.py').resolve(strict=True)
            matched=False
            for argument in process.cmdline():
                try:
                    candidate=Path(argument)
                    if candidate.is_absolute() and candidate.resolve(strict=True)==expected:matched=True
                except (OSError,ValueError):pass
            if not matched:raise AssertionError('fixture command ownership mismatch')
            process.kill();return process.wait(10)
        except psutil.NoSuchProcess:pass

    def start(self,scenario,port):
        (self.project/'app.py').write_text(APP,encoding='utf-8')
        write_json(self.project/'fixture.json',dict(listen_host='127.0.0.1',listen_port=port))
        files={'tools/__init__.py':'','tools/shadow_live_runtime.py':RUNTIME,
               'tools/shadow_dashboard_host.py':'# inert fixture\n','tools/shadow_sqlite_snapshot.py':'# inert fixture\n'}
        hashes={}
        for name,text in files.items():
            path=self.package/name;path.write_text(text,encoding='utf-8');hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        name='tools/shadow_dashboard_bootstrap.py';path=self.package/name
        path.write_bytes((ROOT/name).read_bytes());hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        manifest=write_json(self.package/'shadow-package.json',dict(schema=1,sourceCommit='a'*40,files=hashes))
        plan=self.base/'plan.json';plan_hash=write_json(plan,dict(scenario=scenario,runId=self.run_id))
        write_json(self.settings,dict(schema=1,enabled=False,mode='preflight',sourceCommit='a'*40,
            # Deliberately exercise Windows case aliases; CI temp paths also
            # use 8.3 aliases (RUNNER~1), which resolve to the same exact file.
            packageRoot=str(self.package).upper(),packageManifestSha256=manifest,planPath=str(plan),planSha256=plan_hash))
        # Values are exact fixture paths passed as arguments, never string-built commands.
        wrapper=self.base/'wrapper.ps1'
        wrapper.write_text('''param($Helper,$Python,$Project,$Settings,$Legacy)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5){throw 'PowerShell 5.1 required'}
. $Helper
Set-Location -LiteralPath $Project
$script:legacyMarker=$Legacy
$old={param($PythonPath,$ProjectPath) 'legacy' | Add-Content -LiteralPath $script:legacyMarker; $global:LASTEXITCODE=0}
Invoke-ShadowOrLegacy -Python $Python -Project $Project -SettingsPath $Settings -LegacyAttempt $old
exit $LASTEXITCODE
''',encoding='utf-8-sig')
        self.wrapper=subprocess.Popen([str(POWERSHELL),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
            '-File',str(wrapper),str(ROOT/'deploy/shadow-launch.ps1'),sys.executable,str(self.project),str(self.settings),str(self.legacy)],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=FLAGS)

    def events(self):
        path=self.project/'events.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def await_ready(self,port):
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            if self.wrapper.poll() is not None:
                out,err=self.wrapper.communicate()
                log=self.base/'launch-status.log'
                self.fail('Fixture wrapper exited before readiness: '+str(self.wrapper.returncode)+' '+out.decode(errors='replace')[-1000:]+' '+err.decode(errors='replace')[-1000:]+' '+(log.read_text(encoding='utf-8-sig') if log.exists() else 'no-launch-log'))
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1):return
            except OSError:time.sleep(.05)
        self.fail('Fixture server readiness deadline')

    def finish(self):
        (self.project/'FINISH').write_text('fixture only')
        return self.wrapper.communicate(timeout=30)

    def assert_single_optional_process(self):
        events=self.events()
        self.assertEqual(['app-import','serve-call'],[row['event'] for row in events])
        self.assertEqual(1,len({row['pid'] for row in events}))
        self.assertFalse(self.legacy.exists())

    @staticmethod
    def free_port():
        with closing(socket.socket()) as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]

    def test_stderr_then_normal_server_no_fallback_or_second_process(self):
        port=self.free_port();self.start('normal',port);self.await_ready(port)
        out,err=self.finish();self.assertEqual(0,self.wrapper.returncode)
        self.assertIn(b'FIXTURE_STDERR_BEFORE_SERVER',err);self.assertIn(b'Started server process',err)
        self.assert_single_optional_process()

    def test_post_start_nonzero_propagates_without_legacy(self):
        port=self.free_port();self.start('after-start-exit',port);self.await_ready(port)
        self.finish();self.assertEqual(23,self.wrapper.returncode);self.assert_single_optional_process()

    def test_forced_child_termination_never_falls_back(self):
        port=self.free_port();self.start('normal',port);self.await_ready(port);child_code=self.kill_owned_child()
        self.wrapper.communicate(timeout=30)
        self.assertEqual(child_code,self.wrapper.returncode)
        self.assertNotIn(self.wrapper.returncode,(0,75));self.assert_single_optional_process()

    def test_occupied_port_never_falls_back(self):
        with closing(socket.socket()) as blocker:
            blocker.bind(('127.0.0.1',0));blocker.listen()
            self.start('normal',blocker.getsockname()[1]);self.wrapper.communicate(timeout=30)
        self.assertEqual(1,self.wrapper.returncode);self.assert_single_optional_process()

    def test_preparation_failure_allows_exactly_one_legacy(self):
        self.start('prepare-fail',self.free_port());self.wrapper.communicate(timeout=30)
        self.assertEqual(0,self.wrapper.returncode)
        self.assertEqual(['legacy'],self.legacy.read_text(encoding='utf-8-sig').splitlines())
        self.assertEqual(['app-import'],[row['event'] for row in self.events()])


if __name__=='__main__':unittest.main(verbosity=2)
