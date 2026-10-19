"""Interactive private configuration and isolated real-phone notification probe."""
import argparse,getpass,hashlib,json,os,shlex,shutil,stat,sys,tempfile,time,uuid
from pathlib import Path
from cloud.notification_settings import DEFAULT,load
from cloud.feishu_notifications import validate_settings,FeishuSender
def private_owner(path):
 if os.name!='nt':
  import grp
  os.chown(path,0,grp.getgrnam('ops-console').gr_gid)
def save(value,path=DEFAULT,backup_root=Path('/root/ops-console-notification-config-backups')):
 path=Path(path);validate_settings(value)
 if not path.parent.is_dir() or path.is_symlink():raise ValueError('unsafe_notification_settings_path')
 directory=Path(backup_root)/(time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]);directory.mkdir(parents=True,mode=0o700)
 exists=path.exists()
 if exists:shutil.copyfile(path,directory/'settings.before.json');os.chmod(directory/'settings.before.json',0o600)
 raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode();expected=hashlib.sha256(raw).hexdigest()
 quoted=shlex.quote(str(path));old=shlex.quote(str(directory/'settings.before.json'))
 rollback='#!/bin/bash\nset -euo pipefail\ntest "$(id -u)" = 0\n'
 rollback+='test "$(sha256sum '+quoted+' | cut -d" " -f1)" = '+shlex.quote(expected)+'\n'
 if exists:rollback+='install -o root -g ops-console -m 640 '+old+' '+quoted+'\n'
 else:rollback+='rm -- '+quoted+'\n'
 rollback+='echo "Notification settings restored. Delivery ledger retained; unknown sends are not replayed."\n'
 (directory/'rollback.sh').write_text(rollback,'utf-8');os.chmod(directory/'rollback.sh',0o700)
 temp=path.with_name('.notifications-'+uuid.uuid4().hex+'.tmp')
 try:
  fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
  private_owner(temp)
  os.chmod(temp,0o640);os.replace(temp,path)
 finally:temp.unlink(missing_ok=True)
 return {'savedPrivately':True,'enabled':value['enabled'],'signingEnabled':bool(value.get('signing_secret')),'rollback':'sudo '+str(directory/'rollback.sh')}
def phone_acceptance(settings):
 """Two real messages from a synthetic cache/clock; real home never goes offline."""
 from cloud.store import Store
 from cloud.notification_runtime import NotificationWorker
 sender=FeishuSender(settings,prefix='[隔离验收：模拟状态，不代表真实家里]\n')
 now=[time.time()]
 with tempfile.TemporaryDirectory(prefix='ops-notification-phone-fixture-') as directory:
  store=Store(Path(directory)/'fixture.db',clock=lambda:now[0])
  worker=NotificationWorker(store,{'enabled':True,'quiet_start':0,'quiet_end':0},sender)
  store.heartbeat('healthy');worker.tick()
  now[0]+=301;worker.tick();first=worker.status()
  if first['deliveries'].get('sent')!=1:raise ValueError('phone_probe_not_acknowledged_check_private_bot_settings')
  worker.tick();assert worker.status()['deliveries']==first['deliveries']
  now[0]+=5;store.heartbeat('healthy');worker.tick()
  status=worker.status()
  if status['deliveries'].get('sent')!=2:raise ValueError('phone_recovery_probe_not_acknowledged')
  return {'isolatedPhoneAcceptance':True,'realHomeContacted':False,'realHomeOffline':False,'messagesAccepted':2,'duplicateSuppressed':True,'messages':['模拟离线','模拟已恢复'],'providerReceiptMeans':'provider accepted; user phone receipt still required'}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=('configure','enable','disable','status','acceptance'));parser.add_argument('--legacy-disabled',action='store_true');args=parser.parse_args()
 if os.name!='nt' and os.geteuid()!=0:parser.error('Run with sudo in the server terminal')
 try:
  if args.action=='configure':
   if not sys.stdin.isatty():raise ValueError('interactive_private_terminal_required')
   value={'schema':1,'provider':'feishu','enabled':False,'legacy_notifications_disabled':False,'quiet_start':0,'quiet_end':8,
          'webhook':getpass.getpass('Feishu custom bot Webhook (hidden): ').strip(),
          'signing_secret':getpass.getpass('Signing secret (hidden; Enter if disabled): ').strip(),
          'keyword':getpass.getpass('Required bot keyword (hidden; Enter if none): ').strip()}
   answer=save(value)
  else:
   value=load()
   if value is None:raise ValueError('configure_notifications_first')
   if args.action=='status':
    answer={'provider':'feishu','enabled':value['enabled'],'legacyNotificationsDisabledAttested':value['legacy_notifications_disabled'],'signingEnabled':bool(value.get('signing_secret')),'credentialsPrinted':False}
   elif args.action=='acceptance':answer=phone_acceptance(value)
   else:
    if args.action=='enable' and not args.legacy_disabled:raise ValueError('disable_legacy_home_notifications_first_then_pass_legacy_disabled')
    value.update(enabled=args.action=='enable')
    if args.action=='enable':value['legacy_notifications_disabled']=True
    answer=save(value)
  print(json.dumps(answer,ensure_ascii=True))
 except (OSError,ValueError,AssertionError):
  # Do not print an exception with a private URL/key, response body or input.
  print(json.dumps({'ok':False,'reason':'notification_operation_refused_or_failed','credentialsPrinted':False}))
  raise SystemExit(2)
