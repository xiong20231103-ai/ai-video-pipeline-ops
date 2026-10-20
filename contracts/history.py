"""Versioned bounded history transfer. No execution/restore instructions."""
import hashlib,json,re
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def safe_facts(value):
    forbidden={'password','newpassword','oldpassword','invite','authorization','cookie','csrf','secret','signingsecret','webhook','accesstoken','apikey','agenttoken','agenttokensha256','invitehash','passwordhash','refreshtoken','clientsecret','token','authkey','tailscaleauthkey','invitationcode','sessiontoken'}
    if isinstance(value,dict):
        for key,item in value.items():
            if str(key).lower().replace('-','').replace('_','') in forbidden:raise ValueError('credential_field_forbidden')
            safe_facts(item)
    elif isinstance(value,list):
        for item in value:safe_facts(item)
    elif isinstance(value,str) and ('tskey-' in value or 'PRIVATE KEY-----' in value or 'open.feishu.cn/open-apis/bot/v2/hook/' in value or value.lower().startswith('bearer ') or re.search(r"(?i)(?:^|[\s\"'])(?:password|secret|webhook|authorization|access_token|api_key|agent_token|invite_hash)[\"']*\s*[:=]",value)):raise ValueError('credential_text_forbidden')

KINDS={'ops.tasks','ops.task_history','ops.events','ops.heartbeats','ops.source_health','ops.sqlite_sequence','evidence','alias','reset','timeline'}
MAX_CHUNK=1024*1024
MAX_BYTES=256*1024*1024
MAX_ROWS=200000
class HistoryError(ValueError):
    def __init__(self,code,status=400):self.code=code;self.status=status;super().__init__(code)
def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',value):raise HistoryError('invalid_history_identity')
    return value
def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def record(value):
    if not isinstance(value,dict) or set(value)!={'kind','key','value'} or value['kind'] not in KINDS or not isinstance(value['key'],str) or not 1<=len(value['key'])<=512:raise HistoryError('invalid_history_record')
    try:safe_facts(value);body=canonical(value)
    except (ValueError,TypeError,UnicodeError):raise HistoryError('unsafe_history_record') from None
    if len(body)>MAX_CHUNK-1024:raise HistoryError('history_record_too_large')
    if value['kind']=='alias':
        row=value['value']
        if not isinstance(row,dict) or set(row)!={'alias','canonical','resetGeneration'} or row['alias']!=value['key']:raise HistoryError('invalid_history_alias')
        for key in row:identifier(row[key])
    if value['kind']=='reset':
        row=value['value']
        if not isinstance(row,dict) or set(row)!={'generation','resetAt'} or row['generation']!=value['key']:raise HistoryError('invalid_history_reset')
        identifier(row['generation'])
    return value
def summary(records):
    digest=hashlib.sha256();counts={};seen=set();size=0
    for item in records:
        record(item);key=(item['kind'],item['key'])
        if key in seen:raise HistoryError('duplicate_history_primary_key')
        seen.add(key);body=canonical(item);size+=len(body)
        if len(seen)>MAX_ROWS or size>MAX_BYTES:raise HistoryError('history_dataset_limit',413)
        digest.update(body+b'\n');counts[item['kind']]=counts.get(item['kind'],0)+1
    return {'rowsHash':digest.hexdigest(),'counts':counts,'rowCount':len(seen),'bytes':size}
def manifest(value):
    required={'schema','source','sequence','resetGeneration','sourceIdentity','mode','baseGeneration','chunks','summary','coverage'}
    if not isinstance(value,dict) or set(value)!=required or type(value['schema']) is not int or value['schema']!=1:raise HistoryError('invalid_history_manifest')
    identifier(value['source']);identifier(value['resetGeneration'])
    if type(value['sequence']) is not int or not 1<=value['sequence']<2**53:raise HistoryError('invalid_history_sequence')
    if not isinstance(value['sourceIdentity'],str) or not re.fullmatch('[0-9a-f]{64}',value['sourceIdentity']):raise HistoryError('invalid_history_source_hash')
    if value['mode'] not in {'full','delta'} or value['mode']=='delta' and value['baseGeneration'] is None:raise HistoryError('invalid_history_mode')
    if value['baseGeneration'] is not None and (not isinstance(value['baseGeneration'],str) or not re.fullmatch('[0-9a-f]{64}',value['baseGeneration'])):raise HistoryError('invalid_history_base')
    if not isinstance(value['chunks'],list) or len(value['chunks'])>4096 or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in value['chunks']):raise HistoryError('invalid_history_chunks')
    totals=value['summary']
    if not isinstance(totals,dict) or set(totals)!={'rowsHash','counts','rowCount','bytes'} or type(totals['rowCount']) is not int or not 0<=totals['rowCount']<=MAX_ROWS or type(totals['bytes']) is not int or not 0<=totals['bytes']<=MAX_BYTES or not isinstance(totals['counts'],dict) or any(k not in KINDS or type(n) is not int or n<1 for k,n in totals['counts'].items()) or sum(totals['counts'].values())!=totals['rowCount'] or not re.fullmatch('[0-9a-f]{64}',str(totals['rowsHash'])):raise HistoryError('invalid_history_totals')
    if not isinstance(value['coverage'],dict) or value['coverage'].get('dbPresent') is not True:raise HistoryError('history_ops_snapshot_required')
    try:safe_facts(value);canonical(value)
    except (ValueError,TypeError):raise HistoryError('unsafe_history_manifest') from None
    if len(canonical(value))>MAX_CHUNK:raise HistoryError('history_manifest_too_large',413)
    return value
