"""Strict leaf-only exceptions; no generic timestamp or array-order erasure."""
from contracts.golden import differences

VOLATILE={'/observation/observedAt','/observation/collectedAt','/observation/metrics/sampleTime'}

def compare(expected,actual,*,mode='isolated',ignored=()):
    if mode not in {'isolated','real-shadow'}:raise ValueError('invalid_comparison_mode')
    if mode=='isolated' and ignored:raise ValueError('offline_golden_has_no_ignored_fields')
    if any(path not in VOLATILE for path in ignored):raise ValueError('business_field_exception_forbidden')
    def leaf(value,path):
        try:
            for part in path.lstrip('/').split('/'):
                key=part.replace('~1','/').replace('~0','~');value=value[int(key)] if isinstance(value,list) else value[key]
        except (KeyError,TypeError,ValueError,IndexError):raise ValueError('ignored_field_must_exist') from None
        if isinstance(value,(dict,list)):raise ValueError('only_leaf_exceptions_allowed')
    for path in ignored:leaf(expected,path);leaf(actual,path)
    return differences(expected,actual,ignored)

def evidence_gate(report,required_targets):
    blockers=[]
    if not required_targets:blockers.append('required_targets_missing')
    if report.get('mode')!='real-shadow' or report.get('batchStarted') is not True or report.get('batchCompleted') is not True or not report.get('batchId'):blockers.append('complete_real_batch_not_observed')
    windows=report.get('windows',[])
    for target in required_targets:
        rows=[r for r in windows if r.get('target')==target]
        if not rows or any(not r.get('sourceIdentity') or r.get('sourceIdentity')!=r.get('candidateSourceIdentity') or r.get('comparable') is not True or type(r.get('caseCount')) is not int or r['caseCount']<1 or type(r.get('mismatchCount')) is not int or r['mismatchCount']!=0 for r in rows):blockers.append('missing_or_unaligned_or_different:'+target)
    if not windows:blockers.append('no_comparison_windows')
    if report.get('effectsOutsideScratch',0)!=0 or report.get('businessRequests',0)!=0:blockers.append('shadow_side_effect_detected')
    return blockers
