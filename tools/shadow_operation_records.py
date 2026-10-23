"""Cold adapter for existing completed R3 HTTP receipts (forward-only routes).

This does not read an execution DB, poll, deliver or retry a command. Caller
supplies an existing receipt and copies it into an independent evidence sink.
"""
from __future__ import annotations
import base64,json,copy
from agent.core.ordinary import route
from tools.shadow_capture import CaptureError,_safe

FORWARDED={
 'control_create_task':lambda args:'/api/tasks/create',
 'control_replenish_task':lambda args:'/api/tasks/replenish/'+args['task_id'],
 'control_start_task':lambda args:'/api/tasks/'+args['task_id']+'/start',
 'control_cancel_task':lambda args:'/api/tasks/'+args['task_id']+'/cancel',
}

def command_from_completed_receipt(job,result,*,batch_id,task_id,observed_at):
 name,args=route(job['target'])
 if name not in FORWARDED:raise CaptureError('native_command_requires_recorded_runtime_ports')
 if args.get('task_id',task_id)!=task_id:raise CaptureError('command_task_identity_mismatch')
 if result.get('kind')!='http' or type(result.get('httpStatus')) is not int:raise CaptureError('completed_http_receipt_required')
 raw=base64.b64decode(result['bodyBase64'],validate=True)
 if len(raw)>2*1024*1024:raise CaptureError('operation_receipt_limit')
 value=json.loads(raw);_safe(value);body=copy.deepcopy(job['body']);_safe(body)
 if not isinstance(body,dict):raise CaptureError('recorded_command_object_required')
 status=result['httpStatus']
 # Preserve unknown/local failure boundaries instead of inventing a receiver reply.
 if status>=500 or status in {401,403} or not isinstance(value,dict) or value.get('detail') in {'任务不是有效 JSON','补链不是有效 JSON'}:raise CaptureError('receipt_cannot_prove_forwarded_exchange')
 if not job.get('id') or not batch_id or not task_id:raise CaptureError('operation_identity_required')
 forwarded_body=body if name in {'control_create_task','control_replenish_task'} else None
 record={'schema':1,'commandId':job['id'],'batchId':batch_id,'taskId':task_id,'target':job['target'],'body':body,'observedAt':observed_at,'client':'127.0.0.1','ports':[{'port':'http','method':'POST','target':'receiver:'+FORWARDED[name](args),'body':forwarded_body,'status':status,'response':value}],'receipt':{'status':status,'body':value},'derivation':'pinned-r3-forward-only-v1'}
 _safe(record);return record
