"""Reviewed, prefix-only R0--R5 startup selection. No live configuration editing.

Candidate algorithms live in the retained process during observation. Its
single DB/Collector/locks remain authoritative until the separate R6 cutover.
"""
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import time
from contracts.state_files import read_json,atomic_json
from .projection_store import require_plain_path
from .retirement_gate import shadow_blockers,RULES
from .staged_modules import STAGES,selected,install


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def r5_record(state,review,*,build,ledger_id):
    """Bind final retirement to the actual persisted R5 health observation.

    Review attestations alone cannot supply an earlier start date. The retained
    host marker stays in place through native activation and cold restarts.
    """
    record=read_json(require_plain_path(Path(state)/'migration/active.json'))
    if (not isinstance(record,dict) or type(record.get('schema')) is not int or record['schema']!=1
        or record.get('stage')!='R5' or record.get('phase')!='active'
        or record.get('build')!=build or record.get('ledgerId')!=ledger_id
        or record.get('installedModules')!=list(STAGES) or record.get('sharedState') is not True
        or record.get('legacyRetired') is not False or not isinstance(record.get('acceptedAt'),str)
        or record.get('acceptedAt')!=review.get('r5AcceptedAt')
        or digest(record)!=review.get('migrationSha256')):
        raise ValueError('r5_persisted_observation_not_bound')
    return record


class Transition:
    def __init__(self,plan,*,build,ledger_id,clock=time.time):
        self.plan=plan;self.clock=clock
        details=plan.get('transition')
        if not isinstance(details,dict) or type(details.get('schema')) is not int or details['schema']!=1:
            raise ValueError('transition_review_missing')
        stage=details.get('stage');modules=selected(stage)
        if not isinstance(details.get('approvedBy'),str) or not details['approvedBy'].strip():raise ValueError('transition_review_missing')
        if details.get('build')!=build or details.get('ledgerId')!=ledger_id:raise ValueError('transition_build_or_ledger_changed')
        self.stage=stage;self.modules=modules;self.identity=ledger_id;self.build=build
        self.root=require_plain_path(plan['agentState'])/'migration'
        self.marker=self.root/'active.json'
        report_path=require_plain_path(details['shadowReport'])
        raw=report_path.read_bytes()
        if len(raw)>8*1024*1024 or hashlib.sha256(raw).hexdigest()!=details.get('shadowSha256'):
            raise ValueError('transition_shadow_digest_mismatch')
        report=json.loads(raw)
        if not isinstance(report,dict) or type(report.get('schema')) is not int or report['schema']!=1 or report.get('build')!=build:
            raise ValueError('transition_shadow_build_mismatch')
        rules=RULES if 'R5' in modules else RULES[:42] if 'R4' in modules else ()
        if shadow_blockers(report,modules,rules):raise ValueError('transition_real_shadow_incomplete')
        if 'R2' in modules and details.get('historyReadyVerified') is not True:
            raise ValueError('transition_history_not_ready')
        self.plan_hash=digest(plan);self.previous=read_json(self.marker) if self.marker.exists() else None
        if self.previous is not None and (not isinstance(self.previous,dict) or type(self.previous.get('schema')) is not int or self.previous['schema']!=1):
            raise ValueError('transition_marker_invalid')
        self.resuming=(self.previous is not None and self.previous.get('planSha256')==self.plan_hash)
        if self.resuming:
            if (self.previous.get('build')!=build or self.previous.get('ledgerId')!=ledger_id or self.previous.get('stage')!=stage
                or self.previous.get('installedModules')!=list(modules) or self.previous.get('sharedState') is not True
                or self.previous.get('legacyRetired') is not False or self.previous.get('phase') not in {'prepared','active'}):
                raise ValueError('transition_resume_identity_changed')
        else:
            expires=details.get('expiresAt')
            if type(expires) not in (int,float) or not math.isfinite(expires) or not clock()<expires<=clock()+3600:
                raise ValueError('transition_review_expired')
            expected={'commandsPaused':True,'drained':True,'leased':0,'sent':0,'unknown':0,
                'unreconciledRecovery':0,'autoRecoveryDisabled':True,'cleanupEnabled':False,'rollbackVerified':True,
                'controlPlaneWriterDisabled':True,'legacyFallbacksFenced':True}
            if any(type(details.get(k)) is not type(v) or details[k]!=v for k,v in expected.items()):
                raise ValueError('transition_queue_or_rollback_not_reviewed')
            previous_stage=self.previous.get('stage') if self.previous else None
            if previous_stage is not None and previous_stage not in STAGES:raise ValueError('transition_marker_invalid')
            expected_hash=digest(self.previous) if self.previous else None
            if details.get('previousSha256')!=expected_hash:raise ValueError('transition_previous_state_changed')
            old=STAGES.index(previous_stage) if previous_stage is not None else -1
            new=STAGES.index(stage)
            if new!=old+1 and not (details.get('rollbackApproved') is True and 0<=new<old) and not (details.get('reinstallApproved') is True and new==old):
                raise ValueError('transition_stage_skip_forbidden')
        self.installed=None
    def bind(self,namespace,application):
        self.installed=install(namespace,application,self.stage)
        return self.installed
    def commit(self):
        if self.installed is None:raise ValueError('transition_not_installed')
        if self.resuming:return self.previous
        # The timestamp starts again after any rollback/reinstallation. Never
        # accept a supplied historic timestamp to shorten the R5 observation.
        record={'schema':1,'stage':self.stage,'build':self.build,'ledgerId':self.identity,
            'planSha256':self.plan_hash,'previousSha256':digest(self.previous) if self.previous else None,
            'acceptedAt':None,'phase':'prepared',
            'installedModules':list(self.modules),'sharedState':True,'legacyRetired':False}
        self.root.mkdir(parents=True,exist_ok=True)
        atomic_json(self.marker,record)
        return record

    def ready(self):
        """The agent calls this only after real successful retained-host health."""
        record=read_json(self.marker)
        if not isinstance(record,dict) or record.get('planSha256')!=self.plan_hash or record.get('build')!=self.build or record.get('ledgerId')!=self.identity:
            raise ValueError('transition_active_identity_changed')
        if record.get('phase')=='active':return record
        if record.get('phase')!='prepared':raise ValueError('transition_not_prepared')
        record.update(phase='active',acceptedAt=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat())
        atomic_json(self.marker,record)
        return record
