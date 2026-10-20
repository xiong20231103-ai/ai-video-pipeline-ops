"""Reviewed legacy fallback with the protocol-2 deadline/cancellation binding.

Importing this module starts nothing. The explicit CLI is for a reviewed rollback
startup task after candidate ownership has been removed, not for parallel use.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import re
from pathlib import Path
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from contracts.state_files import read_json
from .core.authority_lease import AuthorityLease
from .core.ordinary_fence import OrdinaryFence,FenceRejected
from .core.projection_store import require_plain_path
from .core.recovery_transport import RecoveryTransport


class LegacyBackgroundGuard:
    """Fence old background writes using the SAME lease as legacy HTTP.

    Install before the retained app's lifespan starts. Ownership rejection is
    normal standby: do not scan, purge, or write an error event in that state.
    This is a prerequisite for transition, not an activation/switch operation.
    """
    def __init__(self,namespace,lease):
        self.namespace=namespace;self.lease=lease
        self.collector=namespace['COLLECTOR']
    def install(self):
        collector=self.collector
        if collector.thread and collector.thread.is_alive():raise ValueError('legacy_background_already_started')
        if getattr(collector,'_ops_background_guard',None) is not None:raise ValueError('legacy_background_guard_already_installed')
        self.original_run=collector.run
        self.original_purge=self.namespace['_pending_delete_purge_loop']
        collector.run=self.collection_loop
        self.namespace['_pending_delete_purge_loop']=self.retention_loop
        collector._ops_background_guard=self
    def collection_loop(self):
        collector=self.collector;started=False
        while not collector.stop_event.is_set():
            try:
                with self.lease.guard():
                    if not started:
                        collector.store.event('OpsStarted','INFO','OPS Dashboard 已启动');started=True
                    try:collector.scan()
                    except Exception as error:
                        # Preserve the legacy loop's scan-error behavior while
                        # keeping its error event inside the owner lease too.
                        collector.store.event('CollectorError','ERROR','状态采集发生异常',
                            {'error':str(error)},f'collector:{type(error).__name__}:{error}')
            except FenceRejected:pass
            collector.stop_event.wait(max(1,float(collector.config['scan_interval_seconds'])))
    def retention_loop(self,stop):
        n=self.namespace
        while not stop.is_set():
            try:
                with self.lease.guard():n['pending_delete'].purge(n['pending_delete_roots']())
            except FenceRejected:pass
            except Exception:
                # Same tolerance as the old retention thread; never a fallback
                # deletion and never an everything=True purge.
                pass
            stop.wait(n['PENDING_DELETE_PURGE_INTERVAL_SECONDS'])


class LegacyRecoveryApp:
    def __init__(self,application,namespace,controller,lease):
        self.application=application;self.namespace=namespace;self.lease=lease
        self.transport=RecoveryTransport(controller,namespace)
        namespace['request_workbench_continue']=self.transport.submit
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.application(scope,receive,send)
        guard=self.lease.guard()
        try:await run_in_threadpool(guard.__enter__)
        except (OSError,ValueError):return await JSONResponse({'detail':'legacy_authority_unavailable'},status_code=503)(scope,receive,send)
        try:
            path=scope['path']
            match=re.fullmatch('/api/control-commands/([^/]+)/cancel',path)
            if scope['method']=='POST' and match:
                try:response=JSONResponse(await run_in_threadpool(self.transport.cancel,match[1],Request(scope,receive)))
                except HTTPException as error:response=JSONResponse({'detail':error.detail},status_code=error.status_code)
                return await response(scope,receive,send)
            if scope['method']=='POST' and path=='/api/controls/continue-current':
                return await JSONResponse({'detail':'use_control_commands_with_expected_target'},status_code=405)(scope,receive,send)
            return await self.application(scope,receive,send)
        finally:await run_in_threadpool(guard.__exit__,None,None,None)


def load_verified(path,digest,name):
    path=require_plain_path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('legacy_source_not_reviewed')
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None:raise ValueError('legacy_source_unavailable')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def make_app(plan):
    if not isinstance(plan,dict) or plan.get('schema')!=1 or plan.get('action')!='R6_LEGACY_START':raise ValueError('legacy_start_review_missing')
    if (require_plain_path(plan['agentState'])/'engine-settings.json').exists():raise ValueError('candidate_configuration_still_present')
    root=require_plain_path(plan['legacyRoot']);fence=OrdinaryFence(require_plain_path(plan['fenceRoot']))
    state=fence.status()
    if state['owner']!='legacy' or state['fenceId']!=plan['fenceId']:raise ValueError('legacy_owner_not_selected')
    lease=AuthorityLease(fence,lambda:{**state,'protocol':1,'candidateWritesBlocked':True},owner='legacy')
    # Importing app.py initializes its Store before lifespan starts. Ownership
    # must therefore span import AND wrapper installation, not only HTTP/scan.
    with lease.guard():return _load_legacy_app(plan,root,lease)


def _load_legacy_app(plan,root,lease):
    module=load_verified(root/'app.py',plan['legacyAppSha256'],'retained_legacy_dashboard')
    workbench=module.resolve_path(str(module.CONFIG['workbench_dir']))
    if (workbench/'workbench').is_dir():workbench=workbench/'workbench'
    if require_plain_path(plan['recoveryModule'])!=workbench/'recovery_control.py' or require_plain_path(plan['recoveryControlDir'])!=workbench/'handoff/control':
        raise ValueError('legacy_recovery_authority_path_mismatch')
    recovery=load_verified(plan['recoveryModule'],plan['recoveryModuleSha256'],'retained_legacy_recovery')
    control=require_plain_path(plan['recoveryControlDir'])
    controller=recovery.RecoveryControl(control/'automatic_recovery.json',control/'automatic_recovery.lock',control/'continue_current_project.json')
    LegacyBackgroundGuard(vars(module),lease).install()
    return LegacyRecoveryApp(module.app,vars(module),controller,lease),module.CONFIG


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True)
    parser.add_argument('--confirm',required=True,choices=['R6_LEGACY_RESTORE_REVIEWED']);args=parser.parse_args()
    application,config=make_app(read_json(require_plain_path(args.plan)))
    if int(config['listen_port'])!=8765:raise ValueError('legacy_port_changed')
    import uvicorn
    uvicorn.run(application,host=str(config['listen_host']),port=8765,reload=False,access_log=False,log_config=None,log_level='critical')

if __name__=='__main__':main()
