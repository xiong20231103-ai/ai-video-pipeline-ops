"""Replay recorded R3 ports, never real POST/spawn/sleep. Unknown tapes block."""
from __future__ import annotations
import asyncio,copy,io,json,types,uuid,urllib.error,urllib.parse
from datetime import datetime,timezone
from pathlib import Path
from agent.core.oracle import Oracle,normalize_root,response_value
from agent.core.ordinary import OrdinaryCommands,invoke,route
from agent.core.snapshot import Snapshot,canonical,relative
from tools.shadow_capture import CaptureError,_safe
from tools.shadow_compare import _delta

class RecordedPorts:
 def __init__(self,environment,record):
  self.environment=environment;self.record=record;self.steps=list(record.get('ports',[]));self.position=0;self.failed=False;self.calls=[];self.epoch=datetime.fromisoformat(record['observedAt'].replace('Z','+00:00')).timestamp();self.processes={p['pid']:copy.deepcopy(p) for p in environment.snapshot.manifest['facts'].get('processRecords',[])};self.uuids=iter(record.get('uuidHexValues',[]));self.uuid_calls=0
 def normalized(self,value):
  return normalize_root(value,self.environment.root)
 def fail(self):self.failed=True;raise CaptureError('recorded_port_missing_or_mismatched')
 def take(self,expected):
  if self.position>=len(self.steps):return self.fail()
  item=self.steps[self.position]
  if any(item.get(k)!=v for k,v in expected.items()):return self.fail()
  self.position+=1;self.calls.append(expected)
  for name,value in item.get('writeFiles',{}).items():
   target=self.environment.root/relative(name);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value.encode() if isinstance(value,str) else canonical(value))
  for name in item.get('removeFiles',[]):(self.environment.root/relative(name)).unlink(missing_ok=True)
  for row in item.get('processRecords',[]):self.processes[row['pid']]=row
  for pid in item.get('exitedPids',[]):self.processes.pop(pid,None)
  return item
 def http(self,request,*args,**kwargs):
  url=urllib.parse.urlsplit(request.full_url if hasattr(request,'full_url') else request);method=request.get_method() if hasattr(request,'get_method') else 'GET';key=('control' if url.port==18790 else 'receiver')+':'+url.path+('?' + url.query if url.query else '')
  expected={'port':'http','method':method,'target':key,'body':json.loads(request.data) if getattr(request,'data',None) else None}
  item=self.take(expected)
  if item.get('error')=='timeout':raise TimeoutError('recorded_timeout')
  if item.get('error') not in (None,'timeout'):return self.fail()
  raw=item['rawText'].encode() if 'rawText' in item else canonical(item['response']);status=item.get('status',200)
  if not 200<=status<300:raise urllib.error.HTTPError(key,status,'recorded response',{},io.BytesIO(raw))
  return io.BytesIO(raw)
 def spawn(self,args,**kwargs):
  item=self.take({'port':'spawn','args':self.normalized(args),'kwargs':self.normalized(kwargs)})
  return types.SimpleNamespace(pid=item['pid'],poll=lambda:item.get('poll'))
 def sleep(self,seconds):
  item=self.take({'port':'sleep','seconds':seconds});elapsed=item.get('elapsed',seconds)
  if not isinstance(elapsed,(int,float)) or elapsed<0 or elapsed>60:return self.fail()
  self.epoch+=elapsed
 def uuid4(self):
  self.uuid_calls+=1
  try:return uuid.UUID(hex=next(self.uuids))
  except (StopIteration,ValueError):return self.fail()
 def bind(self):
  ports=self.environment.namespace;original_psutil=ports['psutil'];runtime=self
  class Process:
   def __init__(self,pid):
    if pid not in runtime.processes:raise original_psutil.NoSuchProcess(pid)
    self.pid=pid;self.info=copy.deepcopy(runtime.processes[pid])
   def cmdline(self):return self.info.get('cmdline',[])
   def name(self):return self.info.get('name','')
   def create_time(self):return self.info['create_time']
   def as_dict(self,*args,**kwargs):return dict(self.info)
   def is_running(self):return self.info.get('alive',True)
  class Clock(datetime):
   @classmethod
   def now(cls,tz=None):return cls.fromtimestamp(runtime.epoch,tz or datetime.fromisoformat(runtime.record['observedAt'].replace('Z','+00:00')).tzinfo)
   def astimezone(self,tz=None):return datetime.astimezone(self,tz or datetime.fromisoformat(runtime.record['observedAt'].replace('Z','+00:00')).tzinfo)
  original_urllib=ports['urllib']
  ports.update(urllib=types.SimpleNamespace(request=types.SimpleNamespace(Request=original_urllib.request.Request,urlopen=self.http),error=original_urllib.error,parse=original_urllib.parse),subprocess=types.SimpleNamespace(Popen=self.spawn,CREATE_NO_WINDOW=0x08000000,DEVNULL=-3),time=types.SimpleNamespace(time=lambda:self.epoch,monotonic=lambda:self.epoch,sleep=self.sleep),uuid=types.SimpleNamespace(uuid4=self.uuid4),datetime=Clock,psutil=types.SimpleNamespace(Process=Process,pid_exists=lambda pid:pid in self.processes,Error=original_psutil.Error,NoSuchProcess=original_psutil.NoSuchProcess,process_iter=lambda *a,**k:[Process(pid) for pid in self.processes]))
  return ports
 def verify(self):
  if self.failed or self.position!=len(self.steps):raise CaptureError('recorded_ports_not_fully_consumed')
  if self.uuid_calls!=len(self.record.get('uuidHexValues',[])):raise CaptureError('recorded_uuid_not_fully_consumed')

def _one(source,snapshot,scratch,record,candidate):
 with Oracle(source,snapshot,scratch,collect=False) as environment:
  runtime=RecordedPorts(environment,record);ports=runtime.bind();namespace=OrdinaryCommands(ports,isolated=True).namespace if candidate else ports
  before=environment.effects();response=asyncio.run(invoke(namespace,record['target'],record['body'],client=record.get('client','127.0.0.1')));runtime.verify();after=environment.effects()
  return normalize_root({'response':response_value(response),'before':before,'after':after,'ports':runtime.calls},environment.root)

def compare_recorded_command(source,snapshot,scratch,record_path):
 snapshot=Snapshot(snapshot.root);record=snapshot.json(record_path);_safe(record)
 if not isinstance(record,dict) or record.get('schema')!=1 or not record.get('commandId') or not record.get('batchId') or not record.get('taskId') or not record.get('observedAt') or 'body' not in record or not isinstance(record.get('ports'),list):raise CaptureError('recorded_command_identity_required')
 handler,args=route(record['target'])
 if args.get('task_id',record['taskId'])!=record['taskId']:raise CaptureError('command_task_identity_mismatch')
 base={'schema':1,'module':'R3','batchId':record['batchId'],'taskId':record['taskId'],'observedTriggerIds':[record['commandId']],'sourceIdentity':snapshot.manifest['sourceIdentity'],'candidateSourceIdentity':snapshot.manifest['sourceIdentity'],'caseCount':0,'mismatchCount':None,'comparable':False,'realShadowPassed':False,'switchAccepted':False}
 if snapshot.manifest['facts'].get('dependencyClosure') is not True:return {**base,'status':'incomplete','blockers':['dependency_closure_not_enforced']}
 if Path(scratch).exists():raise CaptureError('comparison_scratch_must_be_new')
 try:
  old=_one(source,snapshot,Path(scratch)/'old',record,False);new=_one(source,snapshot,Path(scratch)/'new',record,True);delta=_delta(old,new)
  observed=record.get('receipt')
  if not isinstance(observed,dict) or set(observed)!={'status','body'}:raise CaptureError('recorded_actual_receipt_required')
  actual_delta=_delta(observed,{k:old['response'][k] for k in ('status','body')});count=delta['mismatchCount']+actual_delta['mismatchCount']
  return {**base,'status':'different' if count else 'zero-difference','caseCount':1,'mismatchCount':count,'comparable':True,'dependencyClosureVerified':True,'realBatchEvidence':snapshot.manifest.get('realBatchEvidence') is True,'differingPaths':delta['differingPaths']+['actualReceipt'+p for p in actual_delta['differingPaths']],'blockers':[]}
 except Exception as error:return {**base,'status':'incomplete','blockers':['recorded_replay_failed:'+type(error).__name__]}
