"""Private Feishu settings, loaded in-process; never exposed by HTTP."""
import json,os,stat
from pathlib import Path
from cloud.feishu_notifications import validate_settings,FeishuSender
DEFAULT=Path('/etc/ops-console/notifications.json')
def load(path=DEFAULT):
 path=Path(path)
 if not path.exists():return None
 if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:raise ValueError('unsafe_notification_settings')
 if os.name!='nt' and stat.S_IMODE(path.stat().st_mode)&0o007:raise ValueError('notification_settings_publicly_readable')
 return validate_settings(json.loads(path.read_text('utf-8')))
def runtime_settings(path=DEFAULT):
 try:value=load(path)
 except (OSError,ValueError):return {'enabled':False,'configurationError':True},None
 if value is None:return {'enabled':False},None
 public={k:value[k] for k in ('enabled','legacy_notifications_disabled','quiet_start','quiet_end')}
 public['provider']='feishu';public['signingEnabled']=bool(value.get('signing_secret'))
 if not value['enabled'] or not value['legacy_notifications_disabled']:public['enabled']=False;return public,None
 return public,FeishuSender(value)
