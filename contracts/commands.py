"""Closed M2a write contract shared by cloud and the one home executor."""
import hashlib,json,re
from urllib.parse import quote,unquote,urlsplit

MAX_PAYLOAD=2*1024*1024
MAX_REPLY=2*1024*1024
REQUIRED_TARGET=('batchId','taskId','attemptId')
TARGET_FIELDS=(*REQUIRED_TARGET,'manifestId','runGroupId')
RULES=(
 (r'/api/controls/tasks/create','dashboard',{'date','templateId','material','audioBatch','voicePlan','expectedCount','urls','startNow'}),
 (r'/api/controls/tasks/[^/]+/replenish','dashboard',{'urls','startNow'}),
 (r'/api/controls/tasks/[^/]+/(start|cancel)','dashboard',set()),
 (r'/api/control-commands','dashboard',{'clientRequestId','expectedTarget'}),
 (r'/api/controls/upload/(rescan|verify-history)','dashboard',set()),
 (r'/api/task-boxes/[^/]+/reconcile','dashboard',set()),
 (r'/api/subtitle-verification/retry/preview','dashboard',{'ids'}),
 (r'/api/batches(?:/validate)?','receiver',None),
)

def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def identity(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9_-]{16,128}',value):raise ValueError('invalid_client_request_id')
    return value
def command(target,body):
    parts=urlsplit(target)
    if parts.scheme or parts.netloc or parts.query or parts.fragment or len(target)>512:raise ValueError('invalid_command_path')
    path=unquote(parts.path,errors='strict')
    if '\\' in path or '%' in path or any(p in {'','.','..'} or any(ord(c)<32 for c in p) for p in path.split('/')[1:]):raise ValueError('invalid_command_path')
    for pattern,source,keys in RULES:
        if re.fullmatch(pattern,path):break
    else:raise ValueError('command_not_in_m2a_allowlist')
    if not isinstance(body,dict) or keys is not None and set(body)-keys:raise ValueError('invalid_command_body')
    encoded=canonical(body)
    if len(encoded.encode())>MAX_PAYLOAD:raise ValueError('command_body_too_large')
    if path=='/api/control-commands':
        identity(body.get('clientRequestId'))
        expected=body.get('expectedTarget')
        if not isinstance(expected,dict) or set(expected)-set(TARGET_FIELDS):raise ValueError('expected_target_required')
        if any(not isinstance(expected.get(k),str) or not expected[k].strip() or len(expected[k])>256 for k in REQUIRED_TARGET):raise ValueError('complete_target_identity_required')
        if any(not isinstance(v,str) or len(v)>256 for v in expected.values()):raise ValueError('invalid_expected_target')
    if source=='receiver':
        if not isinstance(body.get('tasks'),list) or not 1<=len(body['tasks'])<=100:raise ValueError('invalid_submission_tasks')
        if not isinstance(body.get('batchId'),str) or not 1<=len(body['batchId'])<=200:raise ValueError('submission_batch_id_required')
    normalized=quote(path,safe='/-_')
    digest=hashlib.sha256(canonical({'method':'POST','target':normalized,'body':body}).encode()).hexdigest()
    return {'target':normalized,'body':body,'source':source,'digest':digest,'timeoutSeconds':45}

def target_from_summary(body):
    box=body.get('currentTaskBox') if isinstance(body,dict) else None
    if not isinstance(box,dict) or not isinstance(box.get('current'),dict):return None
    target={'batchId':box.get('batchId'),'taskId':box['current'].get('taskId'),'attemptId':box['current'].get('attemptId')}
    return target if all(isinstance(v,str) and v for v in target.values()) else None
