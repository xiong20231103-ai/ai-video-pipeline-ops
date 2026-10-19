"""Synthetic Linux ownership/rollback, durable dedup and provider encoding only."""
import json,os,stat,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cloud.notification_setup import save
from cloud.notification_settings import load,runtime_settings
from cloud.notification_runtime import NotificationWorker
from cloud.feishu_notifications import sign
from cloud.store import Store

with tempfile.TemporaryDirectory(prefix='ops-m2b-smoke-') as directory:
 root=Path(directory);path=root/'notifications.json'
 settings={'schema':1,'provider':'feishu','enabled':False,'legacy_notifications_disabled':False,'webhook':'https://open.feishu.cn/open-apis/bot/v2/hook/00000000-0000-0000-0000-000000000000','signing_secret':'inert-smoke','keyword':'fixture','quiet_start':0,'quiet_end':8}
 answer=save(settings,path,root/'backups');assert path.exists() and (next((root/'backups').iterdir())/'rollback.sh').exists()
 assert stat.S_IMODE(path.stat().st_mode)==0o640
 assert load(path)==settings and runtime_settings(path)[1] is None
 assert sign(100,'inert-smoke')
 now=[1000];store=Store(root/'fixture.db',clock=lambda:now[0]);sent=[]
 def sender(batch):sent.append(batch);return {'state':'sent','receipt':'fixture'}
 worker=NotificationWorker(store,{'enabled':True,'quiet_start':0,'quiet_end':0},sender)
 store.heartbeat('healthy');worker.tick();now[0]+=301;worker.tick();worker.tick();assert len(sent)==1
 now[0]+=5;store.heartbeat('healthy');worker.tick();assert [b['kind'] for b in sent]==['home_offline','recovered']
print(json.dumps({'m2bNotificationSmoke':True,'privateFilePermissions':'0640','backupBeforeReplace':True,'syntheticOfflineRecovery':True,'externalMessages':0,'homeRequests':0}))
