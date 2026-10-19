"""Conservative snapshot notification facts. No I/O, execution or credentials."""
import hashlib,json,re
from datetime import datetime,timezone

INFLIGHT={'requested','accepted','running','recovering','persisted','receiver_acknowledged','workbench_acknowledged','executing'}
BLOCKED={'failed','blocked','stalled','login_required'}
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def public_text(value,limit=180):
 value=str(value or '')
 value=re.sub(r'https?://\S+','[地址已省略]',value,flags=re.I)
 value=re.sub(r'(?i)(Bearer\s+|tskey-)[A-Za-z0-9._~+/=-]+','[密钥已省略]',value)
 value=re.sub(r'(?i)((?:access[_-]?token|token|password|secret|api[_-]?key|webhook)\s*[=:]\s*)\S+',r'\1[已省略]',value)
 value=re.sub(r'(?i)[A-Z]:[\\/][^\s,，;；]+','[本机路径已省略]',value)
 value=' '.join(value.split())
 return value[:limit]
def fact(kind,identity,phase,code,message,*,severity='normal',once=False):
 fields={k:str(identity.get(k) or '') for k in ('batchId','canonicalTaskId','attemptId','project')}
 if not fields['batchId'] or not fields['canonicalTaskId']:return None
 code=public_text(code,100);phase=public_text(phase,80);message=public_text(message)
 base=digest([kind,fields,phase,code,message])
 return {'baseKey':base,'kind':kind,'identity':fields,'phase':phase,'code':code,'message':message,'severity':severity,'once':once}
def current_facts(body,*,cloud_inflight=False):
 """Only current task-scoped facts; aggregate/date failures are never events."""
 status=body.get('currentProjectStatus') or {};identity=status.get('identity') or {}
 if not isinstance(identity,dict):return []
 identity={**identity,'canonicalTaskId':identity.get('canonicalTaskId') or identity.get('taskId')}
 if not identity.get('canonicalTaskId') or not identity.get('batchId'):return []
 box=body.get('currentTaskBox') or {};current=box.get('current') or {}
 if box.get('batchId')!=identity['batchId'] or (current.get('canonicalTaskId') or current.get('taskId'))!=identity['canonicalTaskId']:return []
 result=[];gap=bool(current.get('gapActive')) and type(current.get('missingCount')) is int and current['missingCount']>0
 if gap:
  item=fact('download_gap',identity,'download','DOWNLOAD_LINKS_MISSING','下载需补链：'+str(current['missingCount'])+'条')
  if item:result.append(item)
 errors=status.get('errors')
 if not isinstance(errors,list):return result
 for error in errors:
  if not isinstance(error,dict):continue
  component=str(error.get('component') or '')
  code=str(error.get('errorCode') or '')
  phase=str(error.get('phase') or '')
  if not code or not component or not phase:continue
  if 'cleanup' in (component+' '+phase+' '+code).lower():continue
  if error.get('status') not in BLOCKED:continue
  if status.get('state')=='completed' and component!='upload':continue
  if gap and component in {'download','workbench'}:continue
  attempt=error.get('attemptId') or identity.get('attemptId')
  item=fact('task_failed',{**identity,'attemptId':attempt},component+'/'+phase,code,error.get('message') or code)
  if item:result.append(item)
 # allowed means "there is a legal target", not "press continue now".
 control=(body.get('controls') or {}).get('continue') or {}
 auto=body.get('autoRecovery') or {}
 stages=status.get('stages') or []
 running=any(isinstance(s,dict) and s.get('status')=='running' and s.get('taskScoped') is True for s in stages)
 auto_running=auto.get('state') in INFLIGHT
 login_needed=status.get('state')=='login_required' or any('LOGIN' in str(e.get('errorCode','')).upper() for e in errors if isinstance(e,dict))
 if (status.get('state') in BLOCKED and identity.get('attemptId') and control.get('allowed') is True
     and control.get('continueCanRetry') is True and control.get('stale') is not True
     and control.get('state') not in INFLIGHT and not cloud_inflight and not running and not auto_running and not login_needed):
  if result:
   # One task/error must not produce a failure alert and another "continue"
   # alert for the same observation. The failure/gap carries the review hint.
   for item in result:item['needsManualReview']=True
  else:
   item=fact('manual_attention',identity,'recovery','REVIEW_SAFE_CONTINUE','当前项目需要人工核对，可在新鲜页面检查安全继续；本通知不执行操作。')
   if item:result.append(item)
 return result
def completion_facts(body,*,baseline_at,now):
 boxes=(body.get('taskBoxes') or {}).get('items') or []
 result=[]
 for box in boxes:
  if not isinstance(box,dict):continue
  receipt=box.get('completionReceipt') or {}
  if receipt.get('status')!='completed_verified' or not re.fullmatch('[a-fA-F0-9]{64}',str(receipt.get('receiptHash') or '')):continue
  total=box.get('totalVideos');done=box.get('completedVideos');projects=box.get('projectCount')
  if type(total) is not int or total<=0 or done!=total or type(projects) is not int or projects<=0 or box.get('completedProjects')!=projects:continue
  try:stamp=datetime.fromisoformat(str(receipt.get('completedAt')).replace('Z','+00:00'));assert stamp.tzinfo is not None;at=stamp.timestamp()
  except (ValueError,TypeError,AssertionError):continue
  if at>now+60:continue
  item=fact('batch_completed',{'batchId':box.get('batchId'),'canonicalTaskId':receipt['receiptHash'],'project':'批次'},'production','COMPLETED_VERIFIED','批次生产完成，共'+str(total)+'条；此通知不代表上传完成。',once=True)
  if item:item['historical']=at<=baseline_at;result.append(item)
 return result
def source_fresh(row,now,maximum):
 """Include source scan age, not just a recently repeated cache receipt."""
 if not row or row.get('status')!=200:return False
 age=now-row['last_success']
 health=json.loads(row.get('source_health') or '{}')
 scan=health.get('scanAgeSeconds')
 return type(scan) in (int,float) and 0<=scan and 0<=age and age+scan<=maximum
