"""Read-only evidence checks. Passing does not deploy, stop or delete anything.

Review flags are human attestations, not cryptographic proof of production facts.
The runtime additionally needs a live legacy-process/startup probe and owner fence.
"""
from datetime import datetime
import json
import math
from pathlib import Path
from .comparison import evidence_gate

RULES=tuple([f'R4-{i:02}' for i in range(1,31)]+[f'RC-{i:02}' for i in range(1,13)]+
    [f'R5-{i:02}' for i in range(1,7)]+[f'R5-D{i:02}' for i in range(1,9)]+
    [f'R5-A{i:02}' for i in range(1,9)]+[f'R5-P{i:02}' for i in range(1,14)])


def required_targets(module):
    matrix=json.loads((Path(__file__).parents[2]/'contracts/endpoints.json').read_text(encoding='utf-8'))
    targets=['GET '+row['path'] for row in matrix if row['method']=='GET']
    if module=='R2':targets+=['history:counts-primary-keys-hashes','history:timeline']
    if module=='R3':targets += ['POST '+path for path in (
        '/api/controls/tasks/create','/api/controls/tasks/{task_id}/replenish',
        '/api/controls/tasks/{task_id}/start','/api/controls/tasks/{task_id}/cancel',
        '/api/controls/upload/rescan','/api/controls/upload/verify-history')]
    if module=='R4':targets+=['POST /api/control-commands','protocol2:expiry-cancellation']
    if module=='R5':targets+=['POST /api/controls/cloud-cleanup/preview','POST /api/controls/cloud-cleanup/execute']
    return targets


def switch_blockers(review,report,*,build,ledger_id,now):
    blockers=[]
    if not isinstance(review,dict) or not isinstance(report,dict):return ['review_or_evidence_missing']
    if type(report.get('schema')) is not int or report['schema']!=1 or report.get('build')!=build:blockers.append('shadow_build_mismatch')
    if type(review.get('schema')) is not int or review['schema']!=1 or review.get('action')!='R6_SWITCH' or review.get('build')!=build or not build:
        blockers.append('review_build_mismatch')
    if not isinstance(review.get('approvedBy'),str) or not review['approvedBy'].strip():blockers.append('human_review_missing')
    expires=review.get('expiresAt')
    if type(expires) not in (int,float) or not math.isfinite(expires) or not now<expires<=now+3600:
        blockers.append('review_expired_or_unbounded')
    if not ledger_id or review.get('ledgerId')!=ledger_id:blockers.append('existing_execution_ledger_not_bound')
    expected={'commandsPaused':True,'drained':True,'leased':0,'sent':0,'unknown':0,
        'unreconciledRecovery':0,'legacyAutostartDisabled':True,'stateImportVerified':True,
        'autoRecoveryDisabled':True,'cleanupEnabled':False,'rollbackVerified':True}
    for key,value in expected.items():
        if type(review.get(key)) is not type(value) or review[key]!=value:blockers.append('review_missing:'+key)
    return blockers+shadow_blockers(report,('R0','R1','R2','R3','R4','R5'),RULES)


def shadow_blockers(report,required_modules,required_rules=()):
    blockers=[]
    if not isinstance(report,dict):return ['shadow_report_missing']
    modules=report.get('modules',{})
    if not isinstance(modules,dict):modules={}
    for module in required_modules:
        evidence=modules.get(module)
        if not isinstance(evidence,dict):blockers.append('real_shadow_missing:'+module);continue
        if not isinstance(evidence.get('batchId'),str) or not evidence['batchId'].strip():
            blockers.append('shadow_batch_identity_missing:'+module)
        # Absence is not evidence of no side effects. Reject booleans too:
        # Python otherwise treats False as the integer zero in comparisons.
        for field in ('effectsOutsideScratch','businessRequests'):
            if type(evidence.get(field)) is not int or evidence[field]!=0:
                blockers.append('shadow_effect_evidence_missing:'+module+':'+field)
        targets=required_targets(module)
        declared=evidence.get('requiredTargets')
        if not isinstance(declared,list) or any(not isinstance(x,str) for x in declared) or set(declared)!=set(targets):
            blockers.append('shadow_targets_missing:'+module);continue
        try:result=evidence_gate(evidence,targets)
        except (ValueError,TypeError,KeyError,AttributeError):result=['malformed_evidence']
        blockers.extend(module+':'+item for item in result)
    rules=report.get('rules',{})
    if not isinstance(rules,dict):rules={}
    for rule in required_rules:
        row=rules.get(rule,{})
        if (not isinstance(row,dict) or row.get('reviewed') is not True
            or type(row.get('positiveCases')) is not int or row['positiveCases']<1
            or type(row.get('negativeCases')) is not int or row['negativeCases']<1
            or type(row.get('mismatchCount')) is not int or row['mismatchCount']!=0):
            blockers.append('rule_not_accepted:'+rule)
    return blockers


def pre_retirement_blockers(review,*,now):
    """Final R6 activation is later than the preceding R5 observation.

    This does not authorize or implement the earlier per-module transition.
    The old process must have remained available through that observation.
    """
    if not isinstance(review,dict):return ['r5_observation_missing']
    blockers=[]
    try:
        stamp=datetime.fromisoformat(str(review.get('r5AcceptedAt')).replace('Z','+00:00'))
        if stamp.tzinfo is None or now-stamp.timestamp()<14*86400:blockers.append('r5_two_week_observation_missing')
    except (ValueError,TypeError,OverflowError):blockers.append('r5_two_week_observation_missing')
    for key in ('r5ContinuousCandidateUse','r5NoRollbackDuringObservation','legacyAvailableThroughObservation'):
        if review.get(key) is not True:blockers.append('r5_observation_missing:'+key)
    return blockers


def retirement_blockers(review,*,now):
    if not isinstance(review,dict):return ['retirement_review_missing']
    blockers=[]
    started=review.get('switchAcceptedAt')
    try:
        stamp=datetime.fromisoformat(str(started).replace('Z','+00:00'))
        if stamp.tzinfo is None or now-stamp.timestamp()<14*86400:blockers.append('two_week_observation_missing')
    except (ValueError,TypeError,OverflowError):blockers.append('two_week_observation_missing')
    for key in ('continuousCandidateUse','noRollbackDuringObservation','legacyFilesRetained','oneCommandRollbackVerified','userRetirementApproved'):
        if review.get(key) is not True:blockers.append('retirement_missing:'+key)
    return blockers
