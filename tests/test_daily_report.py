import json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from cloud.store import Store
from cloud.daily_report import DailyReports,due_slot,render
from cloud.feishu_notifications import FeishuSender,sign
from cloud.notification_runtime import NotificationWorker
from contracts.cache import cache_key
from test_feishu_notifications import Response,Transport,settings

BEIJING=timezone(timedelta(hours=8))
def at(hour,minute,day=19):return datetime(2026,10,day,hour,minute,tzinfo=BEIJING).timestamp()
def dashboard():
 return {'selectedDate':'10.15','overview':{'counts':{'total':48,'waiting':2,'running':0,'completed':46,'failed':0},
  'pipeline':{'download':{'completed':114,'total':114,'failed':0},'voice':{'completed':40,'total':48,'failed':1},'stitch':{},'capcut':{'completed':46,'total':48},'upload':{'completed':46,'total':46}},
  'upload':{'completed':46,'total':46,'failed':0,'cloudVerified':46}},
  'taskBoxes':{'items':[{'batchId':'formal-batch-1792032628470-924e109b0a','productionDate':'10.15','projectCount':9,'completedProjects':5,'totalVideos':79,'completedVideos':46,'state':'blocked'},
   {'batchId':'older-batch','productionDate':'10.14','projectCount':1,'completedProjects':1,'totalVideos':4,'completedVideos':4,'state':'completed'}]},
  'currentProjectStatus':{'state':'blocked','identity':{'project':'SPC地板'},'errors':[{'message':r'E:\private\x.mp4'}]}}

class DailyReportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.now=at(22,31)
  self.store=Store(Path(self.temp.name)/'console.db',clock=lambda:self.now);self.sent=[]
  self.reports=DailyReports(self.store)
 def send(self,text):self.sent.append(text);return {'state':'sent','receipt':'fixture-accepted'}
 def put(self,body,cache_age=0,scan_age=0):
  with self.store.db(True) as db:
   db.execute('INSERT OR REPLACE INTO responses VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cache_key('GET','/api/dashboard'),1,200,json.dumps(body),'fixture',self.now-cache_age,self.now,'',json.dumps({'scanAgeSeconds':scan_age}),'',self.now))
 def state(self):
  with self.store.db() as db:return [tuple(r) for r in db.execute('SELECT key,kind,state FROM daily_reports ORDER BY key')]

 def test_slots_are_beijing_0830_and_2230_for_45_minutes(self):
  self.assertEqual('2026-10-19:morning',due_slot(at(8,30))[0]);self.assertEqual('2026-10-19:evening',due_slot(at(23,14))[0])
  for hour,minute in ((8,29),(9,15),(22,29),(23,15),(12,0)):self.assertIsNone(due_slot(at(hour,minute)))
 def test_evening_report_sends_once_with_current_numbers(self):
  self.put(dashboard(),cache_age=120,scan_age=30);self.reports.tick(self.send);self.now+=5;self.reports.tick(self.send)
  self.assertEqual(1,len(self.sent));text=self.sent[0]
  for part in ('晚报','约 2 分钟前','生产日期 10.15：共 48 条，完成 46，等待 2，运行 0，失败 0','下载 114/114','配音 40/48（失败1）','拼接 未知','云端已核验 46','项目 5/9，视频 46/79，需处理','SPC地板 需处理，错误 1 条'):
   self.assertIn(part,text)
  self.assertNotIn('older-batch',text);self.assertNotIn('private',text)
  self.assertEqual([('2026-10-19:evening','report','sent')],self.state())
 def test_outside_slot_sends_nothing(self):
  self.now=at(12,0);self.put(dashboard());self.reports.tick(self.send);self.assertEqual([],self.sent);self.assertEqual([],self.state())
 def test_stale_data_waits_then_sends_notice_without_numbers(self):
  self.put(dashboard(),cache_age=900,scan_age=60);self.reports.tick(self.send);self.assertEqual([],self.sent)
  self.now=at(23,14);self.reports.tick(self.send)
  self.assertEqual(1,len(self.sent));self.assertIn('超过 15 分钟没有更新',self.sent[0]);self.assertNotIn('48',self.sent[0])
  self.assertEqual([('2026-10-19:evening','stale','sent')],self.state())
 def test_fresh_data_arriving_late_in_window_still_reports(self):
  self.put(dashboard(),cache_age=1200);self.reports.tick(self.send);self.now+=600;self.put(dashboard());self.reports.tick(self.send)
  self.assertEqual(1,len(self.sent));self.assertIn('共 48 条',self.sent[0])
 def test_morning_and_evening_are_separate_and_dated(self):
  self.now=at(8,35);self.put(dashboard());self.reports.tick(self.send)
  self.now=at(22,35);self.put(dashboard());self.reports.tick(self.send)
  self.now=at(8,31,20);self.put(dashboard());self.reports.tick(self.send)
  self.assertEqual(['2026-10-19:evening','2026-10-19:morning','2026-10-20:morning'],[k for k,_,_ in self.state()]);self.assertIn('早报',self.sent[0])
 def test_uncertain_send_and_crash_are_never_repeated(self):
  self.put(dashboard())
  def boom(_):raise OSError('fixture')
  self.reports.tick(boom);self.reports.tick(self.send);self.assertEqual([],self.sent)
  self.assertEqual([('2026-10-19:evening','report','unknown')],self.state())
  with self.store.db(True) as db:db.execute("INSERT INTO daily_reports VALUES('2026-10-20:morning','report','sending',0,0,'','')")
  DailyReports(self.store);self.now=at(8,40,20);self.put(dashboard());self.reports.tick(self.send)
  self.assertEqual([],self.sent);self.assertIn(('2026-10-20:morning','report','unknown'),self.state())
 def test_malformed_snapshot_is_treated_as_missing(self):
  self.put([]);self.reports.tick(self.send);self.assertEqual([],self.sent)
  self.put({'overview':'bad'});self.reports.tick(self.send);self.assertIn('任务计数未知',self.sent[0])
 def test_worker_uses_send_report_only_when_provider_supports_it(self):
  class Sender:
   def __init__(self):self.reports=[]
   def __call__(self,batch):return {'state':'sent'}
   def send_report(self,text):self.reports.append(text);return {'state':'sent'}
  sender=Sender();worker=NotificationWorker(self.store,{'enabled':True,'quiet_start':0,'quiet_end':0},sender)
  self.put(dashboard());worker.tick();self.assertEqual(1,len(sender.reports))
  self.assertEqual('2026-10-19:evening',worker.status()['lastDailyReport']['key'])
  plain=NotificationWorker(self.store,{'enabled':True,'quiet_start':0,'quiet_end':0},lambda batch:{'state':'sent'})
  self.now=at(8,35,20);self.put(dashboard());plain.tick();self.assertEqual(1,len(self.state()))
 def test_feishu_report_is_signed_with_keyword_and_size_bound(self):
  transport=Transport(Response());sender=FeishuSender(settings(),transport,clock=lambda:100)
  self.assertEqual('sent',sender.send_report('日报正文')['state'])
  payload=json.loads(transport.calls[0][0].data);self.assertEqual(sign(100,'fixture-secret'),payload['sign'])
  self.assertTrue(payload['content']['text'].startswith('fixture-keyword\n日报正文'))
  with self.assertRaises(ValueError):sender.send_report('长'*6000)

if __name__=='__main__':unittest.main()
