"""M5 daily report: two fixed Beijing slots, at most one send per slot.

Reads only the cached /api/dashboard response the agent already refreshes
(idle: every 10 minutes); never polls home. A slot waits up to 45 minutes for
fresh data, then sends a short stale notice instead of invented zeros.
"""
import http.client,json
from datetime import datetime,timedelta,timezone
from contracts.cache import cache_key
from cloud.notification_facts import public_text

BEIJING=timezone(timedelta(hours=8))
SLOTS=(('morning',8,30,'早报'),('evening',22,30,'晚报'))
WINDOW=45*60
FRESH=15*60
STEPS=(('download','下载'),('voice','配音'),('stitch','拼接'),('capcut','剪映'),('upload','上传'))
STATES={'completed':'已完成','running':'运行中','waiting':'等待中','blocked':'需处理','failed':'失败','cancelled':'已取消'}

def due_slot(now):
 local=datetime.fromtimestamp(now,BEIJING)
 for name,hour,minute,label in SLOTS:
  start=local.replace(hour=hour,minute=minute,second=0,microsecond=0)
  if start<=local<start+timedelta(seconds=WINDOW):
   return local.strftime('%Y-%m-%d')+':'+name,label,start.timestamp()
 return None

def count(value):return value if type(value) is int and value>=0 else None
def ratio(item):
 if not isinstance(item,dict):return '未知'
 done,total,failed=count(item.get('completed')),count(item.get('total')),count(item.get('failed'))
 if done is None or total is None:return '未知'
 return str(done)+'/'+str(total)+('（失败'+str(failed)+'）' if failed else '')

def render(body,label,now,data_at):
 overview=body.get('overview') if isinstance(body.get('overview'),dict) else {}
 day=public_text(body.get('selectedDate') or '未知',20)
 local=datetime.fromtimestamp(now,BEIJING);age=max(0,int((now-data_at)//60))
 lines=['[AI视频生产线·云端] '+label+' '+local.strftime('%m-%d %H:%M'),
        '数据截至 '+datetime.fromtimestamp(data_at,BEIJING).strftime('%H:%M')+'（约 '+str(age)+' 分钟前）','']
 counts=overview.get('counts') if isinstance(overview.get('counts'),dict) else {}
 parts=[(k,count(counts.get(k))) for k in ('total','completed','waiting','running','failed')]
 if all(v is not None for _,v in parts):
  v=dict(parts);lines.append('生产日期 '+day+'：共 '+str(v['total'])+' 条，完成 '+str(v['completed'])+'，等待 '+str(v['waiting'])+'，运行 '+str(v['running'])+'，失败 '+str(v['failed']))
 else:lines.append('生产日期 '+day+'：任务计数未知')
 pipeline=overview.get('pipeline') if isinstance(overview.get('pipeline'),dict) else {}
 lines.append('各步骤：'+' · '.join(name+' '+ratio(pipeline.get(key)) for key,name in STEPS))
 upload=overview.get('upload') if isinstance(overview.get('upload'),dict) else {}
 verified=count(upload.get('cloudVerified'))
 lines.append('上传：'+ratio(upload)+('，云端已核验 '+str(verified) if verified is not None else ''))
 boxes=body.get('taskBoxes',{}).get('items') if isinstance(body.get('taskBoxes'),dict) else None
 boxes=[b for b in boxes if isinstance(b,dict) and b.get('productionDate')==body.get('selectedDate')] if isinstance(boxes,list) else []
 if boxes:
  lines.append('任务箱：')
  for box in boxes[:6]:
   tail=public_text(box.get('batchId'),80)[-10:]
   lines.append('- …'+tail+'：项目 '+str(count(box.get('completedProjects')))+'/'+str(count(box.get('projectCount')))+'，视频 '+str(count(box.get('completedVideos')))+'/'+str(count(box.get('totalVideos')))+'，'+STATES.get(box.get('state'),public_text(box.get('state') or '未知',20)))
 status=body.get('currentProjectStatus') if isinstance(body.get('currentProjectStatus'),dict) else {}
 errors=status.get('errors') if isinstance(status.get('errors'),list) else []
 if status:
  ident=status.get('identity') if isinstance(status.get('identity'),dict) else {}
  name=public_text(ident.get('project') or '',40)
  lines.append('当前项目：'+(name+' ' if name else '')+STATES.get(status.get('state'),public_text(status.get('state') or '未知',20))+('，错误 '+str(len(errors))+' 条，请查看云端页面' if errors else ''))
 lines+=['','日报汇总的是家里看板此刻的数字，以云端页面为准；不代表上传之外的后续处理。','https://ops.tail830b6f.ts.net']
 return '\n'.join(lines)

def stale_text(label,now):
 local=datetime.fromtimestamp(now,BEIJING)
 return '\n'.join(['[AI视频生产线·云端] '+label+' '+local.strftime('%m-%d %H:%M'),
  '家里看板数据超过 '+str(FRESH//60)+' 分钟没有更新，本次日报不生成数字，避免误报。','请打开云端页面查看家里代理是否在线。','https://ops.tail830b6f.ts.net'])

class DailyReports:
 def __init__(self,store):
  self.store=store
  with store.db(True) as db:
   db.execute('CREATE TABLE IF NOT EXISTS daily_reports(key TEXT PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,receipt TEXT NOT NULL,error_code TEXT NOT NULL)')
   # A crashed send is never repeated: the report may already be on the phone.
   db.execute("UPDATE daily_reports SET state='unknown',updated=? WHERE state='sending'",(store.clock(),))
 def source(self,now):
  with self.store.db() as db:row=db.execute('SELECT * FROM responses WHERE key=?',(cache_key('GET','/api/dashboard'),)).fetchone()
  if not row or row['status']!=200:return None,None
  try:
   health=json.loads(row['source_health'] or '{}');scan=health.get('scanAgeSeconds') if isinstance(health,dict) else None
   body=json.loads(row['body'])
  except (ValueError,TypeError):return None,None
  if type(scan) not in (int,float) or scan<0 or not isinstance(body,dict):return None,None
  data_at=row['last_success']-scan
  return (body,data_at) if 0<=now-data_at<=FRESH else (None,None)
 def tick(self,send_report):
  now=self.store.clock();slot=due_slot(now)
  if not slot:return
  key,label,start=slot
  with self.store.db() as db:
   if db.execute('SELECT 1 FROM daily_reports WHERE key=?',(key,)).fetchone():return
  body,data_at=self.source(now)
  if body is None:
   if now<start+WINDOW-60:return
   text,kind=stale_text(label,now),'stale'
  else:text,kind=render(body,label,now,data_at),'report'
  with self.store.db(True) as db:
   if db.execute('SELECT 1 FROM daily_reports WHERE key=?',(key,)).fetchone():return
   db.execute("INSERT INTO daily_reports VALUES(?,?,'sending',?,?,'','')",(key,kind,now,now))
  try:answer=send_report(text)
  except (OSError,http.client.HTTPException,ValueError):answer={'state':'unknown','error_code':'transport_uncertain'}
  with self.store.db(True) as db:
   db.execute('UPDATE daily_reports SET state=?,updated=?,receipt=?,error_code=? WHERE key=?',
    (answer.get('state','unknown'),self.store.clock(),str(answer.get('receipt',''))[:80],str(answer.get('error_code',''))[:80],key))
 def status(self):
  with self.store.db() as db:
   last=db.execute('SELECT key,kind,state,updated FROM daily_reports ORDER BY updated DESC LIMIT 1').fetchone()
  return {'lastDailyReport':dict(last) if last else None}
