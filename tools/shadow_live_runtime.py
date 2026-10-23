"""Host-only disabled preflight. Observation activation is a later reviewed gate.

This module is invoked only by the explicit bootstrap, never by app.py import.
It makes no HTTP requests, does not start another app and does not replay here.
"""
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from agent.core.snapshot import canonical,no_links
from tools.shadow_capture import CaptureError, _safe, _stat, _read, _source, validate_plan
from tools.shadow_process_preflight import probe_processes
from tools.shadow_sqlite_snapshot import online_backup


def run_preflight(dashboard,spec,control_root):
    """Must run with the original host identity, after its normal startup.

    Only a new private scratch and an immutable result are written. This is not
    a comparable capture and does not attach a GET binding or activate engines.
    """
    started=time.monotonic();control=no_links(control_root)
    evidence=no_links(spec['evidenceRoot']);archive=no_links(spec['archivedRoot'])
    if evidence==archive or evidence.is_relative_to(archive) or archive.is_relative_to(evidence):raise CaptureError('preflight_archive_overlap')
    for other in (archive,evidence):
        if control==other or control.is_relative_to(other) or other.is_relative_to(control):raise CaptureError('preflight_control_overlap')
    plan=spec['capturePlan'];roots,bindings=validate_plan(plan,evidence/'_preflight_check')
    exclusions=[_source(roots,item) for item in plan.get('exclude',{}).values()]
    for root in roots.values():
        if root==archive or root.is_relative_to(archive):raise CaptureError('archive_not_capture_input')
        if archive.is_relative_to(root) and not any(archive==p or archive.is_relative_to(p) for p in exclusions):raise CaptureError('archive_not_excluded')
        if root==control or root.is_relative_to(control):raise CaptureError('control_not_capture_input')
        if control.is_relative_to(root) and not any(control==p or control.is_relative_to(p) for p in exclusions):raise CaptureError('control_not_excluded')
    if no_links(dashboard.__file__)!=no_links(spec['source']):raise CaptureError('preflight_not_original_host')
    if type(spec['approvedBytes']) is not int or spec['approvedBytes']!=2*1024*1024*1024:raise CaptureError('v3_fixed_capacity_required')
    if type(spec['maxCaptureBytes']) is not int or not 1<=spec['maxCaptureBytes']<=160*1024*1024:raise CaptureError('v3_preflight_cycle_limit')
    # Agent runtime JSON is a known public status file, never its config/token.
    state=Path(os.environ.get('LOCALAPPDATA',''))/'OpsAgent/agent-runtime.json'
    agent_pid=None
    if state.is_file() and state.stat().st_size<4096:
        agent_pid=json.loads(state.read_text(encoding='utf-8-sig')).get('pid')
    process=probe_processes(dashboard.psutil,agent_pid=agent_pid)
    missing=[];file_bytes=0
    for name in plan.get('files',{}):
        path=bindings[name];info=_stat(path)
        if not info or info['kind']!='file':missing.append({'path':name,'code':'required_file_missing'});continue
        if info['size']>spec['maxCaptureBytes']-file_bytes:raise CaptureError('preflight_state_byte_limit')
        # Read only explicit state, privacy-screen in memory, never copy its body
        # into the diagnostic report. Native config/profile paths are forbidden.
        raw,_=_read(path,spec['maxCaptureBytes']-file_bytes);_safe(raw.decode('utf-8-sig'))
        if path.suffix.lower()=='.json':
            try:_safe(json.loads(raw))
            except json.JSONDecodeError:missing.append({'path':name,'code':'state_json_invalid'})
        file_bytes+=len(raw)
    for name in plan.get('absent',{}):
        if bindings[name].exists():missing.append({'path':name,'code':'declared_absence_exists'})
    # Read-only preflight still reserves the same 0.5GiB transient budget.
    if 3*spec['maxCaptureBytes']+16*1024*1024>512*1024*1024:raise CaptureError('preflight_scratch_reserve_limit')
    control.mkdir(parents=True,exist_ok=True)
    results=[]
    with tempfile.TemporaryDirectory(prefix='.disabled-preflight-',dir=control) as folder:
        for name in plan.get('databases',{}):
            result=online_backup(bindings[name],Path(folder)/'backup.db',max_bytes=spec['maxCaptureBytes']-file_bytes)
            results.append({'path':name,**result})
    # No credentials, task content or original exception body in diagnostics.
    report={'schema':1,'mode':'preflight','enabled':False,'hostPid':os.getpid(),
            'hostCreateTime':dashboard.psutil.Process(os.getpid()).create_time(),
            'seconds':time.monotonic()-started,'stateFileBytes':file_bytes,'databases':results,
            'measuredSingleRoundReadBytes':file_bytes+sum(row['bytes'] for row in results),
            'measurementScope':'single-disabled-round-no-production-change-rate',
            'deduplicatedIncrementBytes':None,'forecast12hBytes':None,
            'processProbe':process,'missingPaths':missing,
            'planSha256':hashlib.sha256(canonical(plan)).hexdigest(),
            'technicalPreflight':'blocked' if missing or process['preflight']['missing'] else 'measured',
            'productionBudgetVerified':False,'installationPermitted':False,
            'startupShapeEquivalent':False,
            'startupShapeDifferences':['configuration-read-count','store-initialization-count','inactive-module-objects'],
            'businessRequests':0,'productionWrites':False,'realShadowPassed':False,'switchAccepted':False}
    _safe(report)
    target=control/('preflight-'+str(time.time_ns())+'.json')
    with target.open('xb') as stream:stream.write(canonical(report))
    return report


def configure(dashboard,spec,mode,control_root):
    if mode!='preflight':
        # Deliberately cannot activate from a preliminary, unreviewed report.
        raise CaptureError('observation_requires_reviewed_preflight')
    old=dashboard.app.router.lifespan_context
    stop=threading.Event();thread=None
    def worker():
        # Let the original server/collector start under its normal lifecycle.
        if stop.wait(1):return
        try:run_preflight(dashboard,spec,control_root)
        except Exception:
            # Failure reports contain a fixed code, no path/exception values.
            try:
                path=no_links(control_root)/('preflight-failed-'+str(time.time_ns())+'.json')
                with path.open('xb') as stream:stream.write(canonical({'schema':1,'enabled':False,'technicalPreflight':'blocked','code':'host_preflight_failed','installationPermitted':False}))
            except Exception:pass
    @asynccontextmanager
    async def lifespan(app):
        nonlocal thread
        async with old(app) as state:
            try:
                thread=threading.Thread(target=worker,name='shadow-disabled-preflight',daemon=True)
                thread.start()
            except Exception:pass # Optional preflight never prevents old startup.
            try:yield state
            finally:
                stop.set()
                if thread is not None and thread.is_alive():
                    import asyncio
                    try:await asyncio.to_thread(thread.join,2)
                    except Exception:pass
    dashboard.app.router.lifespan_context=lifespan
