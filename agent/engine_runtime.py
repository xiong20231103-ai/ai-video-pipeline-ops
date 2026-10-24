"""Explicit, fail-closed R6 activation. Absent settings keep the legacy path.

Only called after the agent owns its existing process lock. Nothing here stops
legacy programs, changes Windows tasks, copies production data or enables cleanup.
"""
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
import psutil
from fastapi import HTTPException
from contracts.state_files import atomic_json,read_json
from .core.authority_lease import AuthorityLease
from .core.composed import ComposedSession
from .core.engine_host import EngineHost,CompatibilityApp
from .core.ordinary_fence import OrdinaryFence,FenceRejected
from .core.projection_store import durable_store,require_plain_path
from .core.retirement_gate import switch_blockers,pre_retirement_blockers
from .core.runtime_ports import native_ports,normalize_config

STATE_FILES=frozenset({'control_actions.json','test_reset_state.json','capcut_draft_cleanup_status.json',
    'audio_cleanup_status.json','production_file_cleanup_status.json'})
STATE_DIRS=frozenset({'control-commands','task-box-completion-receipts','task-box-reconciliation',
    'capcut-draft-cleanup-backups','audio-cleanup-records','production-file-cleanup-records'})
SETTINGS=frozenset({'schema','enabled','stateRoot','legacyRoot','legacyScripts','legacyTasks','reviewFile',
    'shadowReport','stateManifest','fenceRoot','opsConfig','recoveryModule','recoveryModuleSha256',
    'recoveryControlDir','seedDatabase','seedSha256'})


def build_digest(root):
    from deploy.agent_source_update import R6_RELOCATED_FILES
    root=Path(root);files=[root/name for name in R6_RELOCATED_FILES]
    digest=hashlib.sha256()
    for path in sorted(files,key=lambda p:p.relative_to(root).as_posix()):
        require_plain_path(path)
        digest.update(path.relative_to(root).as_posix().encode()+b'\0'+hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def verify_state_import(root,manifest):
    if not isinstance(manifest,dict) or manifest.get('schema')!=1 or manifest.get('complete') is not True:
        raise ValueError('state_import_manifest_missing')
    entries=manifest.get('files')
    if not isinstance(entries,list) or len(entries)>50000:raise ValueError('state_import_manifest_invalid')
    seen=set()
    for row in entries:
        if not isinstance(row,dict) or set(row)!={'path','sha256'}:raise ValueError('state_import_manifest_invalid')
        relative=row['path']
        if not isinstance(relative,str) or '\\' in relative or ':' in relative:raise ValueError('state_import_path_refused')
        parts=relative.split('/')
        if any(p in {'','.','..'} for p in parts) or not(relative in STATE_FILES or len(parts)>1 and parts[0] in STATE_DIRS and parts[-1].endswith('.json')):
            raise ValueError('state_import_path_refused')
        if relative in seen:raise ValueError('state_import_duplicate')
        seen.add(relative)
        path=require_plain_path(Path(root)/relative)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('state_import_digest_mismatch')
    present={p.relative_to(root).as_posix() for p in Path(root).rglob('*.json')
        if p.relative_to(root).as_posix() in STATE_FILES or p.relative_to(root).parts[0] in STATE_DIRS}
    if present!=seen:raise ValueError('state_import_unlisted_file')


def state_inventory(root):
    root=require_plain_path(root);files=[]
    for name in sorted(STATE_FILES):
        path=root/name
        if path.is_file():files.append(path)
    for name in sorted(STATE_DIRS):
        directory=require_plain_path(root/name)
        if not directory.exists():continue
        for folder,dirs,names in os.walk(directory,followlinks=False):
            for child in dirs:require_plain_path(Path(folder)/child)
            for child in names:
                if child.endswith('.json'):files.append(require_plain_path(Path(folder)/child))
            if len(files)>50000:raise ValueError('state_import_file_limit')
    result=[];total=0
    for path in sorted(files):
        require_plain_path(path);size=path.stat().st_size;total+=size
        if size>32*1024*1024 or total>256*1024*1024:raise ValueError('state_import_byte_limit')
        result.append({'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return result


def legacy_processes_stopped(scripts):
    if not isinstance(scripts,list) or not scripts:return False
    paths=[str(require_plain_path(p)).casefold() for p in scripts]
    for process in psutil.process_iter(['pid','name']):
        name=str(process.info.get('name') or '').lower()
        if not any(x in name for x in ('python','powershell','pwsh','cmd.exe')):continue
        try:
            args=process.cmdline()
            if 'agent.legacy_host' in args:return False
            if any(path in ' '.join(args).casefold() for path in paths):return False
            for arg in args[1:]:
                if str(arg).lower().endswith(('.py','.pyw','.ps1','.cmd')):
                    candidate=Path(arg)
                    if not candidate.is_absolute():candidate=Path(process.cwd())/candidate
                    if str(candidate.absolute()).casefold() in paths:return False
        except psutil.NoSuchProcess:continue
        except (psutil.AccessDenied,OSError,ValueError):return False
    return True


def legacy_tasks_disabled(tasks):
    if os.name!='nt' or not isinstance(tasks,list) or not tasks:return False
    if any(not isinstance(x,dict) or set(x)!={'name','path'} or any(not isinstance(v,str) or not v or len(v)>256 for v in x.values()) for x in tasks):return False
    # Fixed code; task names arrive over stdin as JSON, never shell interpolation.
    script="""$ErrorActionPreference='Stop';$tasks=ConvertFrom-Json ([Console]::In.ReadToEnd());foreach($item in $tasks){$task=Get-ScheduledTask -TaskName $item.name -TaskPath $item.path;if(@($task).Count -ne 1 -or $task.State -ne 'Disabled'){exit 3}};exit 0"""
    try:
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            input=json.dumps(tasks),text=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:return False
    return result.returncode==0


def ledger_identity(path,*,require_empty):
    path=require_plain_path(path)
    if not path.is_file():raise ValueError('existing_execution_ledger_missing')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        row=db.execute('SELECT ledger_id FROM execution_meta WHERE id=1').fetchone()
        if not row or not isinstance(row[0],str) or not row[0]:raise ValueError('execution_ledger_identity_missing')
        if require_empty and db.execute("SELECT count(*) FROM executions WHERE state<>'acknowledged'").fetchone()[0]:
            raise ValueError('execution_ledger_not_drained')
        return row[0]


class DeferredEngine:
    """Settings existence selects this fail-closed adapter, never an old fallback."""
    def __init__(self,state_dir,origin):
        self.state_dir=Path(state_dir);self.origin=origin;self.host=None;self.session=None;self.compatibility_enabled=False
        self.ready=threading.Event()
    supports=staticmethod(EngineHost.supports)
    def activate(self):
        try:self._activate()
        except (OSError,ValueError,TypeError,KeyError,AttributeError,ImportError,SyntaxError,RuntimeError,sqlite3.Error,HTTPException) as error:
            if self.session is not None:self.session.close();self.session=None
            self.host=None
            reason=str(error)
            if not re.fullmatch('[a-z][a-z0-9_]{1,80}',reason):reason='candidate_activation_failed'
            atomic_json(self.state_dir/'engine-runtime.json',{'schema':1,'phase':'unavailable','reason':reason,'legacyFallback':False,'observedAt':time.time()})
    def _activate(self):
        settings=read_json(self.state_dir/'engine-settings.json')
        if not isinstance(settings,dict) or settings.get('schema')!=1 or settings.get('enabled') is not True:raise ValueError('candidate_not_enabled')
        if set(settings)!=SETTINGS:raise ValueError('candidate_settings_fields_invalid')
        root=require_plain_path(settings['stateRoot']);source_root=Path(__file__).resolve().parents[1]
        legacy_root=require_plain_path(settings['legacyRoot'])
        if root==legacy_root or root.is_relative_to(legacy_root) or legacy_root.is_relative_to(root):raise ValueError('candidate_state_not_independent')
        if root==source_root or source_root.is_relative_to(root) or root.is_relative_to(source_root):raise ValueError('candidate_state_contains_source')
        review=read_json(require_plain_path(settings['reviewFile']))
        report_path=require_plain_path(settings['shadowReport']);report_bytes=report_path.read_bytes();report=json.loads(report_bytes)
        review_bytes=json.dumps(review,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        build=build_digest(source_root)
        activation_path=root/'activation.json'
        activation=read_json(activation_path) if activation_path.exists() else None
        evidence_digest=hashlib.sha256(report_bytes).hexdigest();review_digest=hashlib.sha256(review_bytes).hexdigest()
        settings_digest=hashlib.sha256(json.dumps(settings,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        config_path=require_plain_path(settings['opsConfig']);config_bytes=config_path.read_bytes()
        config_digest=hashlib.sha256(config_bytes).hexdigest()
        if review.get('settingsSha256')!=settings_digest or review.get('opsConfigSha256')!=config_digest or review.get('shadowSha256')!=evidence_digest:
            raise ValueError('candidate_review_inputs_changed')
        expected_activation={'schema':1,'build':build,'ledgerId':None,'evidenceSha256':evidence_digest,
            'reviewSha256':review_digest,'settingsSha256':settings_digest,'opsConfigSha256':config_digest}
        identity=ledger_identity(self.state_dir/'execution.db',require_empty=activation is None)
        expected_activation['ledgerId']=identity
        from .core.transition import r5_record,digest as transition_digest
        transition=r5_record(self.state_dir,review,build=build,ledger_id=identity)
        expected_activation['migrationSha256']=transition_digest(transition)
        if (self.state_dir/'migration-settings.json').exists():raise ValueError('transition_pointer_not_parked')
        if activation is None:
            blockers=switch_blockers(review,report,build=build,ledger_id=identity,now=time.time())
            blockers+=pre_retirement_blockers(review,now=time.time())
            if blockers:raise ValueError('candidate_switch_evidence_incomplete')
            manifest_path=require_plain_path(settings['stateManifest']);manifest_bytes=manifest_path.read_bytes()
            if hashlib.sha256(manifest_bytes).hexdigest()!=review.get('stateManifestSha256'):raise ValueError('state_import_not_reviewed')
            manifest=json.loads(manifest_bytes)
            verify_state_import(root,manifest)
            if manifest['files']!=state_inventory(legacy_root/'data'):raise ValueError('state_import_not_complete')
            if (root/'projection.db').exists():raise ValueError('uncommitted_projection_requires_review')
            if not settings.get('seedDatabase'):raise ValueError('projection_seed_required')
        elif activation!=expected_activation:
            raise ValueError('candidate_resume_identity_changed')
        if not legacy_tasks_disabled(settings['legacyTasks']) or not legacy_processes_stopped(settings['legacyScripts']):raise ValueError('legacy_still_active')
        fence=OrdinaryFence(require_plain_path(settings['fenceRoot']))
        state=fence.status()
        if state['owner']!='candidate' or state['fenceId']!=review.get('fenceId'):raise ValueError('candidate_owner_not_selected')
        proof={**state,'protocol':1,'legacyWritesBlocked':True}
        def probe():
            if not legacy_processes_stopped(settings['legacyScripts']):raise FenceRejected('legacy_restarted')
            return proof
        raw_config=json.loads(config_bytes)
        if not isinstance(raw_config,dict):raise ValueError('engine_config_invalid')
        config=normalize_config(legacy_root,raw_config)
        required_config={'machine_name','scan_interval_seconds','heartbeat_interval_seconds','simulation_enabled','workbench_dir'}
        if not required_config.issubset(config) or config['simulation_enabled'] is not False:raise ValueError('engine_config_not_normalized')
        module_path=require_plain_path(settings['recoveryModule'])
        module_digest=hashlib.sha256(module_path.read_bytes()).hexdigest()
        if module_digest!=settings['recoveryModuleSha256'] or module_digest!=review.get('recoveryModuleSha256'):
            raise ValueError('recovery_build_not_reviewed')
        spec=importlib.util.spec_from_file_location('ops_engine_recovery_control',module_path)
        if spec is None or spec.loader is None:raise ValueError('recovery_module_unavailable')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        control=require_plain_path(settings['recoveryControlDir'])
        workbench=require_plain_path(config['workbench_dir'])
        if (workbench/'workbench').is_dir():workbench=workbench/'workbench'
        if module_path!=workbench/'recovery_control.py' or control!=workbench/'handoff/control':raise ValueError('recovery_authority_path_mismatch')
        scripts=settings['legacyScripts']
        if not isinstance(scripts,list) or str(legacy_root/'app.py').casefold() not in {str(require_plain_path(p)).casefold() for p in scripts}:
            raise ValueError('legacy_script_inventory_incomplete')
        controller=module.RecoveryControl(control/'automatic_recovery.json',control/'automatic_recovery.lock',control/'continue_current_project.json')
        from .core.recovery_transport import require_protocol
        try:require_protocol(controller)
        except HTTPException:raise ValueError('recovery_protocol2_not_deployed') from None
        ports=native_ports(legacy_root,root,config)
        # The control plane can call back through CompatibilityApp on another
        # thread. It is never called while holding a global request mutex.
        # control_plane_json is an explicit external port with original loopback
        # URL validation; do not import the installed app for this function.
        from .core.control_plane import control_plane_json
        ports['control_plane_json']=lambda path,timeout=8:control_plane_json(config,path,timeout,sanitize=self.session.namespace['sanitize_public_value'])
        seed_path=settings.get('seedDatabase')
        if seed_path and not (root/'projection.db').exists():
            seed_path=require_plain_path(seed_path)
            if hashlib.sha256(seed_path.read_bytes()).hexdigest()!=settings.get('seedSha256') or review.get('seedSha256')!=settings.get('seedSha256'):
                raise ValueError('projection_seed_not_reviewed')
            with closing(sqlite3.connect(seed_path.as_uri()+'?mode=ro',uri=True)) as seed:
                self.session=ComposedSession(ports,tickets=ports['CLOUD_CLEANUP_TICKETS'],seed=seed,store_factory=durable_store(root/'projection.db'))
        else:self.session=ComposedSession(ports,tickets=ports['CLOUD_CLEANUP_TICKETS'],store_factory=durable_store(root/'projection.db'))
        self.session.bind_controller(controller)
        self.session.valid=False # no business write until first successful scan
        self.host=EngineHost(self.session,AuthorityLease(fence,probe))
        self.compatibility_enabled=True
        atomic_json(activation_path,expected_activation)
        atomic_json(self.state_dir/'engine-runtime.json',{'schema':1,'phase':'waiting-first-scan','legacyFallback':False,'observedAt':time.time()})
    def get(self,*args,**kwargs):
        if self.host is None or not self.ready.is_set():raise OSError('candidate_unavailable')
        return self.host.get(*args,**kwargs)
    def send(self,job):
        return self.host.send(job) if self.host is not None and self.ready.is_set() else {'kind':'not_sent','reason':'send_permit_denied'}
    def collection_loop(self,stop):
        if self.host is None:stop.wait();return
        while not self.ready.wait(.1):
            if stop.is_set():return
        def observed(valid):
            atomic_json(self.state_dir/'engine-runtime.json',{'schema':1,'phase':'active' if valid else 'scan-unavailable','legacyFallback':False,'observedAt':time.time()})
        self.host.collection_loop(stop,on_scan=observed)
    def retention_loop(self,stop):
        if self.host is None:stop.wait();return
        while not self.ready.wait(.1):
            if stop.is_set():return
        self.host.retention_loop(stop)
    def compatibility_loop(self,stop):
        if not self.compatibility_enabled or self.host is None:stop.wait();return
        import uvicorn
        server=uvicorn.Server(uvicorn.Config(CompatibilityApp(self.host,self.origin),host='127.0.0.1',port=8765,
            log_config=None,access_log=False,log_level='critical',lifespan='off'))
        # Single process, no reloader/child process and no console window.
        def shutdown():
            while not stop.wait(.05):
                if server.started:self.ready.set();break
            stop.wait();server.should_exit=True
        thread=threading.Thread(target=shutdown,daemon=True);thread.start()
        try:server.run()
        except SystemExit:raise OSError('candidate_compatibility_bind_failed') from None
        finally:
            self.ready.clear()
            server.should_exit=True
            if not stop.is_set():raise OSError('candidate_compatibility_listener_stopped')


def configured_engine(state,origin):
    staged=Path(state)/'migration-settings.json'
    path=Path(state)/'engine-settings.json'
    if staged.exists():
        from .staged_runtime import StagedBackend
        return StagedBackend(state,conflict=path.exists())
    if not path.exists():return None
    return DeferredEngine(state,origin)
