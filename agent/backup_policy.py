"""Fixed-depth ledger/config backup inventory. No production writes or imports."""
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
import os
import stat

@dataclass(frozen=True)
class Rule:
    root: str
    pattern: str
    required: bool = False
    secret: bool = False
    sqlite: bool = False
    maximum: int = 16 * 1024 * 1024

RULES=(
    Rule('OPS','data/ops.db',True,sqlite=True,maximum=512*1024*1024),
    Rule('OPS','config.json',True,True),
    *[Rule('OPS','data/'+name,True) for name in (
        'control_actions.json','test_reset_state.json','audio_cleanup_status.json',
        'capcut_draft_cleanup_status.json','production_file_cleanup_status.json',
        'production_file_cleanup_index.json')],
    *[Rule('OPS','data/'+name+'/*.json') for name in (
        'task-box-completion-receipts','task-box-reconciliation','control-commands',
        'audio-cleanup-records','production-file-cleanup-records')],
    Rule('OPS','data/capcut-draft-cleanup-backups/*/root_meta_info.json'),
    Rule('OPS','data/capcut-draft-cleanup-backups/*/cleanup-manifest.json'),
    *[Rule('WB',name,True) for name in (
        'ops_pipeline_status.json','workbench_settings.json','pipeline_paths.json',
        'project_task_templates.json','current_download_request.json','saved_task_box.json',
        'handoff/current_pipeline_context.json','handoff/status/pipeline_snapshot.json',
        'handoff/control/automatic_recovery.json','handoff/control/continue_current_project.json',
        'handoff/download/download_batch_state.json','handoff/download/project_status.json',
        'handoff/upload/upload_status.json','handoff/upload/historical_cloud_verify_request.json',
        'handoff/upload/historical_cloud_verify_status.json')],
    Rule('WB','task_submitter_pending.json'),
    Rule('WB','task_submitter_last_receipt.json'),
    Rule('WB','task_receiver_config.json',True,True),
    Rule('WB','baidu_upload_config.json',True,True),
    *[Rule('WB','handoff/'+name+'/*.json') for name in (
        'status/outbox','task_inbox/pending','task_inbox/imported','task_inbox/cancelled',
        'submissions','control/recovery-requests','control/history','control/denor_start_intents',
        'download/checkpoints','capcut','cover_templates','denor_execution_profiles')],
    *[Rule('WB','handoff/denor_production/*/'+name) for name in (
        'execution-manifest.json','generation-record.json','source-replacements.json')],
    Rule('WB','交接记录/*/第四步到第五步.json'),
    *[Rule('VOICE','data/'+name,True) for name in (
        'last_batch_handoff.json','last_batch_handoff.json.last-valid','voice_launch_state.json',
        'workbench_handoff_state.json','copy_assignments.json','copy_usage.json',
        'tasks.csv','copy_library.csv','language_voice_rules.csv','languages.csv',
        'project_copy_rules.csv','project_output_dirs.csv','projects.csv')],
    Rule('VOICE','data/verified_voice_completions/*.json'),
    Rule('VOICE','data/remote_task_plans/*.csv'),
    Rule('VOICE','.env',True,True),
    Rule('CAP','data/capcut-tasks.json',True),
    Rule('CAP','capcut.config.json',True,True),
    Rule('CAP','data/draft-root-lease.json'),
    *[Rule('CAP','data/'+name+'/*.json') for name in (
        'capcut-transactions','placement-commands','draft-root-lease-history')],
    Rule('GEN','*/*/generation_records_*.json'),
    Rule('AGENT','execution.db',sqlite=True,maximum=512*1024*1024),
    Rule('AGENT','command-settings.json',secret=True),
    Rule('AGENT','config.json',True,True),
    Rule('AGENT','backup-settings.json',True,True),
    Rule('AGENT','backup-recipient.pem',True,True),
    Rule('PD_E','*/*/pending-delete.json'),
    Rule('PD_C','*/*/pending-delete.json'),
)

class PolicyError(RuntimeError): pass

def checked_stat(path):
    """Reject links/reparse traversal, including ancestors outside the root."""
    path=Path(os.path.abspath(path))
    for ancestor in reversed((path,*path.parents)):
        try: info=ancestor.lstat()
        except FileNotFoundError: return None
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
            raise PolicyError('Reparse/link path rejected: '+str(ancestor))
    return path.lstat()

def excluded(name):
    name=name.casefold()
    return ('.before-' in name or '.bak.' in name or name.endswith('.bak')
            or name.startswith(('test_','test-','fixture-','isolated-'))
            or name in {'implementation-backups','quarantine','chrome-profile','task-draft-roots','draft-style-backups'})

def match_paths(root,pattern):
    if '**' in pattern or '\\' in pattern or any(part in {'','..','.'} for part in pattern.split('/')):
        raise PolicyError('Invalid whitelist pattern')
    parents=[Path(root)]
    parts=pattern.split('/')
    for index,part in enumerate(parts):
        matches=[]
        for parent in parents:
            info=checked_stat(parent)
            if info is None: continue
            if not stat.S_ISDIR(info.st_mode): raise PolicyError('Expected whitelist directory: '+str(parent))
            if any(character in part for character in '*?['):
                candidates=(Path(entry.path) for entry in os.scandir(parent) if fnmatchcase(entry.name,part))
            else: candidates=(parent/part,)
            for candidate in candidates:
                if excluded(candidate.name) and candidate.name!='test_reset_state.json': continue
                candidate_info=checked_stat(candidate)
                if candidate_info is not None:
                    # A wildcard directory level can also match a sibling .md
                    # file; it is not a directory and must not abort inventory.
                    if index<len(parts)-1 and not stat.S_ISDIR(candidate_info.st_mode):continue
                    matches.append(candidate)
        parents=matches
    return sorted(parents,key=lambda path:str(path).casefold())

def inventory(roots,rules=RULES,total_limit=512*1024*1024):
    """Only sizes/identities returned; never read a config body or private key."""
    result=[]; absent=[]; seen=set(); total=0
    for rule in rules:
        root=Path(roots[rule.root])
        if checked_stat(root) is None:
            if rule.required:raise PolicyError('Missing backup root: '+rule.root)
            absent.append({'root':rule.root,'pattern':rule.pattern,'required':False});continue
        paths=match_paths(root,rule.pattern)
        if not paths:
            absent.append({'root':rule.root,'pattern':rule.pattern,'required':rule.required})
            if rule.required: raise PolicyError('Required whitelist file missing: '+rule.root+'/'+rule.pattern)
        for path in paths:
            info=checked_stat(path)
            if not stat.S_ISREG(info.st_mode): raise PolicyError('Not a regular whitelist file: '+str(path))
            if info.st_size>rule.maximum: raise PolicyError('Oversized whitelist file: '+str(path))
            relative=path.relative_to(root).as_posix(); identity=(rule.root,relative)
            if identity in seen: continue
            seen.add(identity); total+=info.st_size
            if total>total_limit: raise PolicyError('Backup candidate bytes exceed hard budget')
            result.append({'root':rule.root,'relative':relative,'bytes':info.st_size,
                           'mtimeNs':info.st_mtime_ns,'device':info.st_dev,'inode':info.st_ino,
                           'secret':rule.secret,'sqlite':rule.sqlite,'maximum':rule.maximum})
    return {'files':result,'optionalMissing':absent,'totalBytes':total}

def default_roots(state):
    return {'OPS':r'E:\Backup\Documents\New project 3\ai-video-pipeline-ops',
            'WB':r'E:\Backup\Documents\ai-video-workbench-suite\workbench',
            'VOICE':r'E:\Backup\Documents\ai-video-workbench-suite\voice-client',
            'CAP':r'E:\Backup\Documents\New project 3\capcut-auto-caption-client\bin',
            'GEN':r'E:\生成视频','AGENT':str(Path(state).absolute()),'PD_E':r'E:\.ops-pending-delete','PD_C':r'C:\.ops-pending-delete'}
