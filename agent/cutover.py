"""Reviewed R6 staging / rollback kit. Import does nothing.

Stage writes ONLY a new independent candidate directory. Rollback is an explicit
CLI operation for Claude after cloud pause and human review; it never resumes the
cloud queue, kills a process, changes task actions or touches media/pending-delete.
"""
from contextlib import closing
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import uuid
from contracts.state_files import atomic_json,read_json
from .engine_runtime import state_inventory,legacy_processes_stopped,legacy_tasks_disabled,ledger_identity
from .core.ordinary_fence import OrdinaryFence
from .core.projection_store import require_plain_path
from .core.transition import r5_record
from .core.retirement_gate import pre_retirement_blockers


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def disjoint(left,right):
    left=require_plain_path(left);right=require_plain_path(right)
    if left==right or left.is_relative_to(right) or right.is_relative_to(left):raise ValueError('cutover_roots_not_independent')
    return left,right


def sqlite_backup(source,destination):
    source=require_plain_path(source);destination=require_plain_path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(temporary)) as target:
            if src.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('projection_integrity_failed')
            src.backup(target)
        os.replace(temporary,destination)
    finally:temporary.unlink(missing_ok=True)


def atomic_copy(source,destination):
    source=require_plain_path(source);destination=require_plain_path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        shutil.copy2(source,temporary)
        if hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(temporary.read_bytes()).digest():raise ValueError('cutover_copy_digest_mismatch')
        os.replace(temporary,destination)
    finally:temporary.unlink(missing_ok=True)


def stage(settings,confirmation,*,quiet=legacy_processes_stopped,tasks_disabled=legacy_tasks_disabled):
    if confirmation!='R6_STAGE_REVIEWED':raise ValueError('cutover_confirmation_required')
    legacy,candidate=disjoint(settings['legacyRoot'],settings['stateRoot'])
    if not quiet(settings['legacyScripts']) or not tasks_disabled(settings['legacyTasks']):raise ValueError('legacy_must_be_stopped_before_staging')
    if candidate.exists() and any(candidate.iterdir()):raise ValueError('candidate_staging_not_empty')
    candidate.mkdir(parents=True,exist_ok=True)
    inventory=state_inventory(legacy/'data')
    for row in inventory:atomic_copy(legacy/'data'/row['path'],candidate/row['path'])
    seed=candidate/'projection-seed.db';sqlite_backup(legacy/'data/ops.db',seed)
    if inventory!=state_inventory(legacy/'data'):raise ValueError('legacy_state_changed_during_staging')
    manifest={'schema':1,'complete':True,'files':inventory}
    atomic_json(candidate/'state-import.json',manifest)
    result={'schema':1,'stateManifest':str(candidate/'state-import.json'),'stateManifestSha256':hashlib.sha256((candidate/'state-import.json').read_bytes()).hexdigest(),
        'seedDatabase':str(seed),'seedSha256':hashlib.sha256(seed.read_bytes()).hexdigest(),
        'legacyStateInventorySha256':digest(inventory),'legacyDatabaseSha256':hashlib.sha256((legacy/'data/ops.db').read_bytes()).hexdigest()}
    atomic_json(candidate/'staging.json',result)
    return result


def park_transition(plan,confirmation,*,quiet=legacy_processes_stopped,tasks_disabled=legacy_tasks_disabled,
                    clock=time.time,maintenance=None):
    """Explicit Claude-only R6 preparation; leaves the agent in maintenance.

    It neither stops the retained host nor selects candidate ownership. Those
    are separately reviewed actions. No native engine can start with both mode
    pointers present. Every failure after stopping leaves maintenance intact.
    """
    if (confirmation!='R6_PARK_REVIEWED' or not isinstance(plan,dict)
        or type(plan.get('schema')) is not int or plan['schema']!=1 or plan.get('action')!='R6_PARK'):
        raise ValueError('park_review_required')
    if not isinstance(plan.get('approvedBy'),str) or not plan['approvedBy'].strip():raise ValueError('park_review_required')
    expires=plan.get('expiresAt')
    if type(expires) not in (int,float) or not clock()<expires<=clock()+3600:raise ValueError('park_review_expired')
    required={'commandsPaused':True,'pipelineIdle':True,'drained':True,'leased':0,'sent':0,'unknown':0,
        'unreconciledRecovery':0,'autoRecoveryDisabled':True,'cleanupEnabled':False}
    if any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in required.items()):raise ValueError('park_queue_not_reviewed_empty')
    if pre_retirement_blockers(plan,now=clock()):raise ValueError('r5_observation_incomplete')
    state=require_plain_path(plan['agentState']);backup=require_plain_path(plan['backupRoot'])/('r6-transition-'+uuid.uuid4().hex)
    disjoint(state,backup)
    if (state/'engine-settings.json').exists():raise ValueError('native_pointer_already_present')
    identity=ledger_identity(state/'execution.db',require_empty=True)
    if identity!=plan.get('ledgerId'):raise ValueError('park_ledger_identity_changed')
    record=r5_record(state,plan,build=plan['build'],ledger_id=identity)
    pointer=read_json(require_plain_path(state/'migration-settings.json'))
    if not isinstance(pointer,dict) or set(pointer)!={'schema','plan','sha256'} or type(pointer['schema']) is not int or pointer['schema']!=1:
        raise ValueError('transition_pointer_invalid')
    raw=require_plain_path(pointer['plan']).read_bytes()
    if len(raw)>2*1024*1024 or hashlib.sha256(raw).hexdigest()!=pointer['sha256'] or digest(json.loads(raw))!=record['planSha256']:
        raise ValueError('transition_plan_changed')
    if not quiet(plan['legacyScripts']) or not tasks_disabled(plan['legacyTasks']):raise ValueError('legacy_must_be_stopped_before_parking')
    if maintenance is None:
        from deploy import agent_source_update as maintenance
    request_id=uuid.uuid4().hex;maintenance.begin_stop(state,request_id)
    result=maintenance.wait_stopped(state,request_id,timeout=930)
    if not result.get('lockFree') or not result.get('cooperativeAck'):raise ValueError('park_agent_not_cooperatively_stopped')
    with maintenance.exclusive_agent_lock(state):
        maintenance.verify_maintenance(state,request_id)
        if ledger_identity(state/'execution.db',require_empty=True)!=identity or r5_record(state,plan,build=plan['build'],ledger_id=identity)!=record:
            raise ValueError('park_state_changed')
        if read_json(state/'migration-settings.json')!=pointer:raise ValueError('transition_pointer_changed')
        if not quiet(plan['legacyScripts']) or not tasks_disabled(plan['legacyTasks']):raise ValueError('legacy_restarted_during_parking')
        backup.mkdir(parents=True,exist_ok=False)
        atomic_copy(state/'migration-settings.json',backup/'migration-settings.json')
        atomic_copy(state/'migration/active.json',backup/'active.json')
        atomic_json(backup/'journal.json',{'schema':1,'phase':'parked','migrationSha256':digest(record),'commandsRemainPaused':True,'requestId':request_id})
        (state/'migration-settings.json').unlink()
    return {'schema':1,'completed':True,'backup':str(backup),'maintenanceRetained':True,'commandsRemainPaused':True,
        'nativeEnabled':False,'ledgerIdentityPreserved':True}


def windows_tasks(tasks,action):
    if os.name!='nt' or action not in {'snapshot','enable','start'}:raise ValueError('windows_task_action_invalid')
    if not isinstance(tasks,list) or not tasks:raise ValueError('windows_tasks_missing')
    for row in tasks:
        if not isinstance(row,dict) or not isinstance(row.get('name'),str) or not isinstance(row.get('path'),str):raise ValueError('windows_task_identity_invalid')
        if any(c in row['name']+row['path'] for c in '*?[]\r\n\0') or not row['path'].startswith('\\'):raise ValueError('windows_task_identity_invalid')
    # Values are JSON stdin. The only mutable task property is enabled state;
    # startup actions/triggers/principal are hashed with Settings.Enabled removed.
    code=r"""$ErrorActionPreference='Stop';$payload=ConvertFrom-Json ([Console]::In.ReadToEnd());$rows=@();foreach($item in $payload.tasks){$task=Get-ScheduledTask -TaskName $item.name -TaskPath $item.path;if(@($task).Count -ne 1 -or $task.TaskName -ne $item.name -or $task.TaskPath -ne $item.path){throw 'task identity'};$text=Export-ScheduledTask -TaskName $item.name -TaskPath $item.path;[xml]$xml=$text;$node=$xml.SelectSingleNode("/*[local-name()='Task']/*[local-name()='Settings']/*[local-name()='Enabled']");if($node){$node.InnerText='STATE'};$sha=[Security.Cryptography.SHA256]::Create();try{$hash=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($xml.OuterXml)))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()};if($payload.action -ne 'snapshot' -and $hash -ne $item.sha256){throw 'task definition changed'};if($payload.action -eq 'enable'){Enable-ScheduledTask -InputObject $task|Out-Null};if($payload.action -eq 'start'){Start-ScheduledTask -InputObject $task};$rows+=@{name=$item.name;path=$item.path;state=[string]$task.State;sha256=$hash;legacyWrapper=$text.Contains('agent.legacy_host')}};ConvertTo-Json -InputObject @($rows) -Depth 4 -Compress"""
    try:
        answer=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',code],input=json.dumps({'tasks':tasks,'action':action}),
            text=True,capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:raise OSError('windows_task_control_timeout') from None
    if answer.returncode:raise OSError('windows_task_control_failed')
    result=json.loads(answer.stdout)
    if not isinstance(result,list) or len(result)!=len(tasks):raise ValueError('windows_task_snapshot_invalid')
    return result


def rollback(plan,confirmation,*,task_control=windows_tasks,quiet=legacy_processes_stopped,health=None,clock=time.time,maintenance=None):
    """The success path is one command; any partial failure leaves maintenance.

    Cloud pause / pipeline-idle fields are explicit human attestations, not a
    fabricated live API check. A reviewer must freshly capture those facts.
    """
    if confirmation!='R6_ROLLBACK_REVIEWED' or not isinstance(plan,dict) or plan.get('schema')!=1 or plan.get('action')!='R6_ROLLBACK':raise ValueError('rollback_review_required')
    if not isinstance(plan.get('approvedBy'),str) or not plan['approvedBy'].strip():raise ValueError('rollback_review_required')
    expires=plan.get('expiresAt')
    if type(expires) not in (int,float) or not clock()<expires<=clock()+3600:raise ValueError('rollback_review_expired')
    required={'commandsPaused':True,'pipelineIdle':True,'drained':True,'leased':0,'sent':0,'unknown':0,'unreconciledRecovery':0}
    if any(type(plan.get(k)) is not type(v) or plan[k]!=v for k,v in required.items()):raise ValueError('rollback_queue_not_reviewed_empty')
    legacy,candidate=disjoint(plan['legacyRoot'],plan['candidateState'])
    backup=require_plain_path(plan['backupRoot'])/('r6-rollback-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    disjoint(backup,legacy);disjoint(backup,candidate)
    state=require_plain_path(plan['agentState'])
    staged_backup=None
    if (state/'migration/active.json').exists():
        staged_backup=require_plain_path(plan['transitionBackup'])
        saved=read_json(staged_backup/'active.json');marker=read_json(state/'migration/active.json')
        pointer=read_json(staged_backup/'migration-settings.json')
        raw=require_plain_path(pointer['plan']).read_bytes()
        if (saved!=marker or pointer.get('sha256')!=hashlib.sha256(raw).hexdigest()
            or digest(json.loads(raw))!=marker.get('planSha256')):raise ValueError('rollback_transition_identity_changed')
    previous_runtime=read_json(state/'agent-runtime.json') if (state/'agent-runtime.json').exists() else {}
    if plan.get('agentTask',{}).get('name')!='OpsConsoleReadonlyAgent':raise ValueError('rollback_agent_task_identity_invalid')
    if not quiet(plan['legacyScripts']):raise ValueError('legacy_already_running')
    inventory=state_inventory(legacy/'data')
    if digest(inventory)!=plan['legacyStateInventorySha256'] or hashlib.sha256((legacy/'data/ops.db').read_bytes()).hexdigest()!=plan['legacyDatabaseSha256']:
        raise ValueError('legacy_changed_manual_merge_required')
    settings=read_json(state/'engine-settings.json')
    if require_plain_path(settings['stateRoot'])!=candidate or require_plain_path(settings['legacyRoot'])!=legacy:raise ValueError('rollback_configuration_identity_changed')
    if ledger_identity(state/'execution.db',require_empty=True)!=plan['ledgerId']:raise ValueError('rollback_ledger_identity_changed')
    legacy_tasks=task_control(plan['legacyTasks'],'snapshot');agent_task=task_control([plan['agentTask']],'snapshot')
    if any(row.get('state')!='Disabled' or row.get('legacyWrapper') is not True for row in legacy_tasks):raise ValueError('legacy_protocol2_startup_not_prepared')
    if not legacy_tasks:raise ValueError('legacy_tasks_missing')
    backup.mkdir(parents=True,exist_ok=False)
    atomic_json(backup/'task-states.json',{'legacy':legacy_tasks,'agent':agent_task})
    atomic_copy(state/'engine-settings.json',backup/'engine-settings.json')
    atomic_json(backup/'journal.json',{'schema':1,'phase':'backup-prepared','commandsRemainPaused':True})
    if maintenance is None:
        from deploy import agent_source_update as maintenance
    request_id=uuid.uuid4().hex
    maintenance.begin_stop(state,request_id)
    result=maintenance.wait_stopped(state,request_id,timeout=930)
    if not result.get('lockFree') or not result.get('cooperativeAck'):raise ValueError('rollback_agent_not_cooperatively_stopped')
    with maintenance.exclusive_agent_lock(state):
        maintenance.verify_maintenance(state,request_id)
        if not quiet(plan['legacyScripts']):raise ValueError('legacy_restarted_during_rollback')
        if ledger_identity(state/'execution.db',require_empty=True)!=plan['ledgerId']:raise ValueError('rollback_ledger_changed')
        current=state_inventory(candidate)
        if not {row['path'] for row in inventory}.issubset({row['path'] for row in current}):raise ValueError('candidate_state_missing_legacy_records')
        sqlite_backup(candidate/'projection.db',backup/'candidate-projection.db')
        sqlite_backup(legacy/'data/ops.db',backup/'legacy-ops.db')
        with closing(sqlite3.connect((backup/'legacy-ops.db').as_uri()+'?mode=ro',uri=True)) as db:
            db.execute('ATTACH DATABASE ? AS candidate',((backup/'candidate-projection.db').as_uri()+'?mode=ro',))
            if db.execute('SELECT count(*) FROM tasks old LEFT JOIN candidate.tasks new ON old.task_id=new.task_id WHERE new.task_id IS NULL').fetchone()[0]:raise ValueError('rollback_projection_missing_tasks')
            if db.execute('SELECT count(*) FROM (SELECT * FROM task_history EXCEPT SELECT * FROM candidate.task_history)').fetchone()[0]:raise ValueError('rollback_projection_missing_history')
        for row in inventory:atomic_copy(legacy/'data'/row['path'],backup/'legacy-data'/row['path'])
        atomic_json(backup/'journal.json',{'schema':1,'phase':'state-copying','commandsRemainPaused':True})
        # No live legacy connection is allowed to retain WAL while its DB swaps.
        with closing(sqlite3.connect(legacy/'data/ops.db',timeout=.1)) as db:
            if db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0]!=0:raise ValueError('legacy_database_still_busy')
        wal=legacy/'data/ops.db-wal'
        if wal.exists() and wal.stat().st_size:raise ValueError('legacy_wal_not_empty')
        for row in current:atomic_copy(candidate/row['path'],legacy/'data'/row['path'])
        atomic_copy(backup/'candidate-projection.db',legacy/'data/ops.db')
        fence=OrdinaryFence(require_plain_path(plan['fenceRoot']))
        fence.select('legacy',expected_id=plan['fenceId'],confirmation='R3_OWNER_CHANGE_REVIEWED',evidence={
            'commandsPaused':True,'drained':True,'leased':0,'sent':0,'unknown':0,'legacyFenceInstalled':True,'fullBatchShadowReviewed':True})
        # Removal is ONLY the owned mode pointer; agent secrets/config and its
        # durable execution.db stay exactly where they were, with the same ID.
        (state/'engine-settings.json').unlink()
        if staged_backup is not None:
            atomic_copy(staged_backup/'migration-settings.json',state/'migration-settings.json')
            # A native-to-retained rollback starts a NEW R5 observation. It must
            # not reuse the old two-week clock for another retirement attempt.
            marker.update(phase='prepared',acceptedAt=None)
            atomic_json(state/'migration/active.json',marker)
        atomic_json(backup/'journal.json',{'schema':1,'phase':'legacy-starting','commandsRemainPaused':True})
        task_control(legacy_tasks,'enable');task_control(legacy_tasks,'start')
        if health is None:
            import urllib.request
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline=time.monotonic()+30
            while True:
                try:
                    with opener.open('http://127.0.0.1:8765/api/health',timeout=2) as response:ready=response.status==200 and json.load(response).get('ok') is True
                    if ready:break
                except (OSError,ValueError):pass
                if time.monotonic()>=deadline:raise OSError('legacy_health_not_ready')
                time.sleep(.5)
        elif health() is not True:raise OSError('legacy_health_not_ready')
        maintenance.finish(state,request_id)
    try:task_control(agent_task,'start')
    except (OSError,ValueError):
        # finish() has cleared maintenance, but task startup can still fail.
        # Restore the stop marker before allowing the repeat trigger to run.
        maintenance.begin_stop(state,request_id)
        raise OSError('rollback_agent_start_failed_maintenance_retained') from None
    deadline=time.monotonic()+95
    while True:
        try:runtime=read_json(state/'agent-runtime.json')
        except (OSError,ValueError):runtime={}
        if runtime.get('phase')=='running' and runtime.get('instanceId') and runtime.get('instanceId')!=previous_runtime.get('instanceId'):break
        if time.monotonic()>=deadline:
            maintenance.begin_stop(state,request_id)
            raise OSError('rollback_agent_not_ready_maintenance_retained')
        time.sleep(.25)
    atomic_json(backup/'journal.json',{'schema':1,'phase':'completed','commandsRemainPaused':True})
    return {'schema':1,'completed':True,'backup':str(backup),'commandsRemainPaused':True,'ledgerIdentityPreserved':True,'legacyHealthVerified':True,'agentRunningVerified':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['stage','rollback','park-transition'])
    parser.add_argument('--plan',required=True);parser.add_argument('--confirm',required=True);args=parser.parse_args()
    plan=read_json(require_plain_path(args.plan))
    try:result={'stage':stage,'rollback':rollback,'park-transition':park_transition}[args.action](plan,args.confirm)
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        reason=str(error)
        if not reason.replace('_','').isalnum() or len(reason)>100:reason='cutover_failed_manual_review_required'
        print(json.dumps({'completed':False,'reason':reason,'commandsRemainPaused':True}));raise SystemExit(1)
    print(json.dumps(result))

if __name__=='__main__':main()
