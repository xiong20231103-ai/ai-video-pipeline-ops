"""Cloud-only observer. Reads existing cache/heartbeats; never polls home."""
import json,sqlite3,threading
from datetime import datetime,timedelta,timezone
from contracts.cache import cache_key
from cloud.notification_facts import current_facts,completion_facts,source_fresh,digest
from cloud.notification_ledger import NotificationLedger

class NotificationWorker:
 def __init__(self,store,config=None,sender=None):
  self.store=store;self.config=config or {};self.sender=sender
  self.ledger=NotificationLedger(store);self.stop=threading.Event()
  with store.db(True) as db:
   db.execute('CREATE TABLE IF NOT EXISTS notification_health(id INTEGER PRIMARY KEY CHECK(id=1),unavailable_since REAL)')
   db.execute('INSERT OR IGNORE INTO notification_health VALUES(1,NULL)')
  self.last_error=None
 def health_facts(self):
  now=self.store.clock();baseline=self.ledger.baseline()
  with self.store.db(True) as db:
   row=db.execute("SELECT received,engine_state FROM heartbeats WHERE agent_id='home'").fetchone()
   unavailable=db.execute('SELECT unavailable_since FROM notification_health WHERE id=1').fetchone()[0]
   age=now-row[0] if row else now-(baseline if baseline is not None else now)
   if row and 0<=age<=45 and row[1]=='unavailable':
    if unavailable is None:unavailable=now;db.execute('UPDATE notification_health SET unavailable_since=? WHERE id=1',(now,))
   elif row and 0<=age<=45 and row[1] in {'healthy','busy'}:
    unavailable=None;db.execute('UPDATE notification_health SET unavailable_since=NULL WHERE id=1')
  kind=None;message=''
  if age>300:kind='home_offline';message='家里代理心跳超过5分钟未到；不表示生产进程已停止，请人工查看。'
  elif row and 0<=age<=45 and row[1]=='unavailable' and unavailable is not None and now-unavailable>=60:
   kind='engine_unavailable';message='代理在线，但Dashboard或接收器健康检查持续未通过；与代理离线分开，暂不能确认具体组件。'
  if not kind:return []
  return [{'baseKey':digest(['health',kind]),'kind':kind,'identity':{},'phase':'connectivity','code':kind.upper(),'message':message,'severity':'critical','once':False}]
 def observations(self):
  now=self.store.clock();baseline=self.ledger.baseline()
  health=self.health_facts();observations=[('connectivity',int(now),health)]
  with self.store.db() as db:
   inflight=bool(db.execute("SELECT 1 FROM commands WHERE state IN ('leased','sent','unknown') LIMIT 1").fetchone()) if db.execute("SELECT 1 FROM sqlite_master WHERE name='commands'").fetchone() else False
   sources={path:db.execute('SELECT * FROM responses WHERE key=?',(cache_key('GET',path),)).fetchone() for path in ('/api/dashboard/summary','/api/dashboard')}
  row=sources['/api/dashboard/summary']
  if row:
   row=dict(row)
   try:
    if source_fresh(row,now,180):
     items=current_facts(json.loads(row['body']),cloud_inflight=inflight)
     if not source_fresh(row,now,60):items=[i for i in items if i['kind']!='manual_attention']
     observations.append(('current',row['version'],items))
   except (ValueError,TypeError):self.last_error='invalid_summary_snapshot'
  row=sources['/api/dashboard']
  if row and row['status']==200:
   try:
    # Receipts are immutable facts. Old receipt dates establish history, never
    # resurrect old completion notices when a historical view/cache is loaded.
    items=completion_facts(json.loads(row['body']),baseline_at=baseline if baseline is not None else now,now=now)
    observations.append(('production_completion',row['version'],items))
   except (ValueError,TypeError):self.last_error='invalid_completion_snapshot'
  return observations
 def quiet(self):
  hour=datetime.fromtimestamp(self.store.clock(),timezone(timedelta(hours=8))).hour
  start=self.config.get('quiet_start',0);end=self.config.get('quiet_end',8)
  if not (type(start) is int and type(end) is int and 0<=start<=23 and 0<=end<=23):raise ValueError('Invalid quiet hours')
  return start!=end and (start<=hour<end if start<end else hour>=start or hour<end)
 def tick(self):
  if self.config.get('enabled') is not True:return
  observations=self.observations()
  if not self.ledger.initialize(observations):
   for scope,version,items in observations:self.ledger.observe(scope,version,items)
  # A missing/unconfigured provider never consumes a pending event.
  if self.sender is None:return
  batch=self.ledger.prepare(quiet=self.quiet())
  if batch:
   try:answer=self.sender(batch)
   except (OSError,TimeoutError):
    self.ledger.finish(batch['id'],'unknown',error_code='transport_uncertain')
    return
   self.ledger.finish(batch['id'],answer['state'],answer.get('receipt',''),answer.get('error_code',''))
 def run(self):
  while not self.stop.is_set():
   try:self.tick()
   except (sqlite3.Error,ValueError,TypeError) as error:
    # Diagnostic class only; provider URLs/configuration/body never reach logs.
    self.last_error=type(error).__name__
   self.stop.wait(5)
 def status(self):
  return {'enabled':self.config.get('enabled') is True,'providerConfigured':self.sender is not None,'lastError':self.last_error,**self.ledger.status()}
