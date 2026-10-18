"""Evidence gate for future module switches; never executes a switch."""
import json
from pathlib import Path

RULES=json.loads(Path(__file__).with_name('shadow_rules.json').read_text(encoding='utf-8'))

def switch_blockers(report, required_rules):
    blockers=[]
    if report.get('mode') != 'real-shadow' or not report.get('fullBatchId'):
        blockers.append('A real, complete shadow batch is required; simulation is not switch evidence')
    if not report.get('sourceIdentity') or report.get('sourceIdentity') != report.get('candidateSourceIdentity'):
        blockers.append('Source identities/versions are not aligned')
    rows={item.get('ruleId'):item for item in report.get('rules',[])}
    for key in required_rules:
        row=rows.get(key,{})
        if row.get('status') != 'passed' or row.get('caseCount',0)<1 or row.get('mismatchCount') != 0:
            blockers.append(key + ': missing, untested or mismatched evidence')
    return blockers

def pending_ledger():
    return {'mode':'simulation','fullBatchId':None,'sourceIdentity':None,'candidateSourceIdentity':None,
            'rules':[{'ruleId':row['id'],'status':'not-run','caseCount':0,'mismatchCount':None} for row in RULES]}
