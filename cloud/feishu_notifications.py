"""Feishu custom bot only. HTTPS verification, no proxies/redirects or secret logs."""
import base64,hashlib,hmac,http.client,json,re,time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request,ProxyHandler,HTTPRedirectHandler,build_opener
from cloud.notification_facts import public_text

class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
def validate_settings(value):
 if not isinstance(value,dict) or value.get('schema')!=1 or value.get('provider')!='feishu':raise ValueError('invalid_notification_schema')
 if set(value)-{'schema','provider','enabled','legacy_notifications_disabled','webhook','signing_secret','keyword','quiet_start','quiet_end'}:raise ValueError('unknown_notification_setting')
 if type(value.get('enabled')) is not bool or type(value.get('legacy_notifications_disabled')) is not bool:raise ValueError('invalid_notification_switch')
 if not isinstance(value.get('webhook'),str) or len(value['webhook'])>2048:raise ValueError('invalid_feishu_webhook')
 p=urlsplit(value['webhook'])
 if p.scheme!='https' or p.hostname!='open.feishu.cn' or p.port not in (None,443) or p.username or p.password or p.query or p.fragment or not re.fullmatch(r'/open-apis/bot/v2/hook/[A-Za-z0-9-]{16,128}',p.path):raise ValueError('invalid_feishu_webhook')
 for key,maximum in (('signing_secret',512),('keyword',64)):
  text=value.get(key,'')
  if not isinstance(text,str) or len(text)>maximum or any(ord(c)<32 for c in text):raise ValueError('invalid_private_notification_field')
 for key in ('quiet_start','quiet_end'):
  if type(value.get(key)) is not int or not 0<=value[key]<=23:raise ValueError('invalid_quiet_hour')
 return value
def sign(timestamp,secret):
 # Official Feishu algorithm: timestamp+"\\n"+secret is the HMAC key; message empty.
 return base64.b64encode(hmac.new((str(timestamp)+'\n'+secret).encode(),b'',hashlib.sha256).digest()).decode()
def message(batch,keyword=''):
 titles={'task_failed':'任务失败','download_gap':'下载需要补链','manual_attention':'需要人工核对','home_offline':'家里代理离线','engine_unavailable':'家里引擎不可用','batch_completed':'批次生产完成','recovered':'已恢复','test':'测试通知'}
 lines=['[AI视频生产线·云端] '+titles.get(batch['kind'],'状态通知'),public_text(keyword,64), '通知编号：'+str(batch['id'])]
 for event in batch['events']:
  identity=event.get('identity') or {}
  lines+=['事件：'+event['eventKey'],public_text(identity.get('project') or '家里设备',40)+' / '+public_text(event.get('phase'),80),
          public_text(event.get('message'),180)]
  if event.get('needsManualReview'):lines.append('需要人工核对；通知不会执行安全继续。')
 lines+=['快照通知可能漏掉两次采集间的短暂状态；以云端页面最新数据为准。','https://ops.tail830b6f.ts.net']
 text='\n'.join(line for line in lines if line)
 if len(text.encode())>16000:raise ValueError('notification_message_too_large')
 return text
class FeishuSender:
 def __init__(self,settings,transport=None,clock=time.time,prefix=''):
  self.prefix=prefix;self.settings=validate_settings(settings);self.transport=transport or build_opener(ProxyHandler({}),NoRedirect());self.clock=clock
 def __call__(self,batch):
  payload={'msg_type':'text','content':{'text':self.prefix+message(batch,self.settings.get('keyword',''))}}
  if self.settings.get('signing_secret'):
   stamp=str(int(self.clock()));payload.update(timestamp=stamp,sign=sign(stamp,self.settings['signing_secret']))
  raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
  if len(raw)>19000:raise ValueError('notification_payload_too_large')
  request=Request(self.settings['webhook'],data=raw,headers={'Content-Type':'application/json'},method='POST')
  try:
   try:response=self.transport.open(request,timeout=10)
   except HTTPError as error:response=error
   with response:
    # Provider error bodies/exceptions can echo the private webhook. Never persist them.
    raw=response.read(65537)
    declared=response.headers.get('Content-Length')
    if declared is not None and (not declared.isdigit() or int(declared)!=len(raw)):return {'state':'unknown','error_code':'incomplete_provider_response'}
    if len(raw)>65536:return {'state':'unknown','error_code':'oversized_provider_response'}
    if 300<=response.code<400:return {'state':'rejected','error_code':'redirect_refused'}
    if response.code>=500:return {'state':'unknown','error_code':'provider_http_5xx'}
    if response.code!=200:return {'state':'rejected','error_code':'provider_http_'+str(response.code)}
    try:value=json.loads(raw)
    except (ValueError,UnicodeError):return {'state':'unknown','error_code':'invalid_provider_json'}
    if not isinstance(value,dict):return {'state':'unknown','error_code':'invalid_provider_json'}
    code=value.get('code',value.get('StatusCode'))
    if type(code) is int and code==0:return {'state':'sent','receipt':'feishu_accepted_code_0'}
    if type(code) is int:return {'state':'rejected','error_code':'feishu_code_'+str(code)}
    return {'state':'unknown','error_code':'missing_provider_receipt'}
  except (OSError,http.client.HTTPException):return {'state':'unknown','error_code':'transport_uncertain'}
