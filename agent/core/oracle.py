"""Frozen legacy oracle. Never imports/starts the installed Dashboard.

Caller provides source text, a verified snapshot and a fresh scratch directory.
Top-level engine construction, mounts and __main__ are excluded by AST, while
the original function/class bodies and route decorators are retained.
"""
from __future__ import annotations
import ast,asyncio,copy,hashlib,inspect,json,re,sqlite3,types,urllib.error,urllib.parse
from contextlib import ExitStack
from functools import lru_cache
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException
from agent.core.snapshot import Snapshot,SnapshotError,canonical,digest_file,sqlite_rows
from agent.core.sandbox import SandboxIO

LEGACY_COMMIT='f78db5a4bfd32eb5ebeab2c63f6dea48cc26f061'
LEGACY_SOURCE_SHA256='f4d754cd86c524933d3f87da1006167c2fd698e288fcda09992115dc0e1c044e'

class Registry:
    def __init__(self):self.routes=[]
    def get(self,path,**kwargs):
        def register(function):self.routes.append((path,function));return function
        return register
    def post(self,*args,**kwargs):return lambda function:function
    middleware=post
    exception_handler=post

def response_value(value):
    if isinstance(value,Response):
        raw=value.body
        try:body=json.loads(raw) if raw else None
        except (ValueError,UnicodeError):body=raw.decode('utf-8')
        return {'status':value.status_code,'body':body,'headers':dict(value.headers)}
    return {'status':200,'body':value,'headers':{}}

@lru_cache(maxsize=128)
def root_prefixes(root):
    variants=set()
    for prefix in (root,str(Path(root).resolve())):
        for initial in (prefix,prefix.replace(chr(92),'/')):
            variants.add(initial)
            for _ in range(3):
                initial=json.dumps(initial,ensure_ascii=False)[1:-1];variants.add(initial)
    return tuple(sorted(variants,key=len,reverse=True))

def normalize_root(value,root):
    if isinstance(value,dict):return {normalize_root(k,root):normalize_root(v,root) for k,v in value.items()}
    if isinstance(value,list):return [normalize_root(v,root) for v in value]
    if isinstance(value,str):
        for prefix in root_prefixes(str(root)):value=value.replace(prefix,'$SNAPSHOT')
    return value


class Oracle:
    def __init__(self,source,snapshot:Snapshot,scratch,*,collect=True):
        if hashlib.sha256(source.encode('utf-8')).hexdigest()!=snapshot.manifest['legacySha256'] or snapshot.manifest['legacySha256']!=LEGACY_SOURCE_SHA256:raise SnapshotError('legacy_source_hash_mismatch')
        self.collect=collect;self.snapshot=snapshot;self.root=snapshot.materialize(scratch);self.registry=Registry();self.stack=ExitStack();self.requests=[]
        self.namespace={'__name__':'isolated_legacy_oracle','__file__':str(self.root/'repository/app.py'),'_frozen_config':{},'_frozen_app':self.registry}
        tree=ast.parse(source)
        for index,node in enumerate(tree.body):
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in {'CONFIG','STORE','COLLECTOR','app'} for t in node.targets):
                name=node.targets[0].id
                replacement={'CONFIG':'_frozen_config','app':'_frozen_app','STORE':'None','COLLECTOR':'None'}[name]
                tree.body[index]=ast.copy_location(ast.Assign(targets=node.targets,value=ast.parse(replacement,mode='eval').body),node)
            elif not isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                tree.body[index]=ast.copy_location(ast.Pass(),node)
        ast.fix_missing_locations(tree);exec(compile(tree,'<isolated-legacy-oracle>','exec'),self.namespace)
    def _enter(self):
        n=self.namespace;facts=self.snapshot.manifest['facts'];epoch=datetime.fromisoformat(self.snapshot.manifest['frozenAt'].replace('Z','+00:00')).timestamp()
        offset=datetime.fromisoformat(self.snapshot.manifest['frozenAt'].replace('Z','+00:00')).utcoffset()
        class FrozenDateTime(datetime):
            @classmethod
            def fromtimestamp(cls,value,tz=None):
                item=datetime.fromtimestamp(value,tz or timezone(offset))
                return cls(item.year,item.month,item.day,item.hour,item.minute,item.second,item.microsecond,tzinfo=item.tzinfo if tz is not None else None,fold=item.fold)
            @classmethod
            def now(cls,tz=None):return cls.fromtimestamp(epoch,tz)
            @classmethod
            def utcnow(cls):return cls.fromtimestamp(epoch,timezone.utc).replace(tzinfo=None)
            def timestamp(self):return datetime.timestamp(self if self.tzinfo else self.replace(tzinfo=timezone(offset)))
            def astimezone(self,tz=None):return datetime.astimezone(self if self.tzinfo else self.replace(tzinfo=timezone(offset)),tz or timezone(offset))
        n['datetime']=FrozenDateTime
        self.stack.enter_context(patch.object(n['time'],'time',return_value=epoch))
        self.stack.enter_context(patch.object(n['time'],'monotonic',return_value=1000.0))
        self.stack.enter_context(patch.dict(n['os'].environ,{'LOCALAPPDATA':str(self.root/'localappdata'),'APPDATA':str(self.root/'appdata'),'USERPROFILE':str(self.root/'home'),'HOME':str(self.root/'home')}))
        self.stack.enter_context(patch.object(Path,'home',return_value=self.root/'home'))
        records={row['pid']:copy.deepcopy(row) for row in facts.get('processRecords',[])}
        class FrozenProcess:
            def __init__(self,pid):
                if pid not in records:raise n['psutil'].NoSuchProcess(pid)
                self.pid=pid;self.info=copy.deepcopy(records[pid])
            def cmdline(self):return list(self.info.get('cmdline',[]))
            def name(self):return self.info.get('name','fixture-process')
            def create_time(self):return self.info.get('create_time',0)
            def is_running(self):return self.info.get('alive',True)
            def ppid(self):return self.info.get('ppid',0)
            def as_dict(self,*args,**kwargs):return copy.deepcopy(self.info)
            def terminate(self):raise RuntimeError('oracle_process_control_forbidden')
            kill=terminate
        self.stack.enter_context(patch.object(n['psutil'],'Process',FrozenProcess))
        self.stack.enter_context(patch.object(n['psutil'],'process_iter',side_effect=lambda *args,**kwargs:[FrozenProcess(pid) for pid in records]))
        self.stack.enter_context(patch.object(n['psutil'],'pid_exists',side_effect=lambda pid:pid in records or pid in facts.get('processIds',[])))
        self.stack.enter_context(patch.object(n['psutil'],'disk_partitions',return_value=[]))
        self.stack.enter_context(patch.object(n['psutil'],'disk_usage',return_value=types.SimpleNamespace(**facts.get('diskUsage',dict(total=10**12,used=10**11,free=9*10**11,percent=10)))))
        self.stack.enter_context(patch.object(n['subprocess'],'Popen',side_effect=RuntimeError('oracle_process_start_forbidden')))
        self.stack.enter_context(patch.object(n['threading'].Thread,'start',side_effect=RuntimeError('oracle_thread_start_forbidden')))
        self.stack.enter_context(patch.object(n['urllib'].request,'urlopen',side_effect=self._http))
        # UUIDs are part of the answer; freeze their generator rather than drop IDs.
        import uuid
        sequence=iter(range(1,100000))
        self.stack.enter_context(patch.object(n['uuid'],'uuid4',side_effect=lambda:uuid.UUID(int=next(sequence))))
        n['socket']=types.SimpleNamespace(gethostname=lambda:facts.get('machineName','fixture-machine'))
        cfg=n['load_config']()
        paths={'workbench_dir':'workbench','workbench_ops_status':'workbench/ops_pipeline_status.json','download_state_file':'workbench/handoff/download/download_batch_state.json','download_project_status_file':'workbench/handoff/download/project_status.json','download_root':'downloads','voice_handoff_file':'workbench/voice/last_batch_handoff.json','generation_output_root':'generation','capcut_handoff_dir':'workbench/handoff/capcut','fourth_step_handoff_dir':'workbench/handoff/step4','final_output_root':'final','capcut_draft_root':'drafts','upload_status_file':'workbench/handoff/upload/upload_status.json'}
        cfg.update({k:str(self.root/v) for k,v in paths.items()})
        cfg.update(machine_name=facts.get('machineName','fixture-machine'),simulation_enabled=False,audio_roots=[str(self.root/'audio')],prepared_sample_roots=[],capcut_test_roots=[],baidu_sync_roots=[],receiver_status_url='http://receiver.fixture.invalid/api/pipeline/snapshot',control_plane_url='http://127.0.0.1:18790')
        # Only non-path algorithm knobs can be overridden; never credentials or hosts.
        for key,value in facts.get('settings',{}).items():
            if key not in {'offline_after_seconds','pipeline_live_after_seconds','test_history_batch_ids','test_history_remote_task_ids','scan_interval_seconds','heartbeat_interval_seconds'}:raise SnapshotError('undeclared_oracle_setting')
            cfg[key]=value
        self.io=SandboxIO(self.root,self.stack,facts.get('filesystem'),self.snapshot.manifest['files'],facts.get('pathAliases')).install()
        n['CONFIG']=cfg;n['DATA_DIR'].mkdir(parents=True,exist_ok=True)
        n['STORE']=n['Store'](n['DB_PATH']);n['COLLECTOR']=n['Collector'](cfg,n['STORE'])
        old_process_status=n['process_status']
        n['process_status']=lambda:copy.deepcopy(facts['processes']) if 'processes' in facts else old_process_status()
        n['system_metrics']=lambda config:copy.deepcopy(facts.get('metrics',{}))
        n['pending_delete_roots']=lambda:[self.root/'pending-delete']
        for task in facts.get('tasks',[]):
            row={k:'' for k in n['TASK_REQUIRED_COLUMNS']};row.update(sequence=0,expected_task_count=0,source_timestamp=0,state='Waiting',state_text='等待',task_id='fixture-task');row.update(task)
            n['STORE'].upsert_task(row)
        if self.collect and facts.get('scan',True):n['COLLECTOR'].scan()
        n['COLLECTOR'].last_scan_at=self.snapshot.manifest['frozenAt'];n['COLLECTOR'].last_scan_epoch=epoch
        n['COLLECTOR'].thread=types.SimpleNamespace(is_alive=lambda:facts.get('collectorAlive',False))
        return self
    def __enter__(self):
        try:return self._enter()
        except BaseException:
            self.stack.close();raise
    def __exit__(self,*args):
        self.stack.close()
        if self.io.denied and args[0] is None:raise SnapshotError('replay_attempted_live_io')
    def _http(self,request,*args,**kwargs):
        method=request.get_method() if hasattr(request,'get_method') else 'GET'
        if method!='GET':raise RuntimeError('oracle_non_get_forbidden')
        url=urllib.parse.urlsplit(request.full_url if hasattr(request,'full_url') else request)
        key=('control' if url.port==18790 else 'receiver')+':'+url.path+('?' + url.query if url.query else '')
        self.requests.append(key)
        responses=self.snapshot.manifest['facts'].get('http',{})
        if key not in responses:raise urllib.error.URLError('unavailable_frozen_source:'+key)
        value=responses[key]
        if isinstance(value,dict) and '_httpStatus' in value:raise urllib.error.HTTPError(key,value['_httpStatus'],'frozen source unavailable',{},None)
        class FrozenResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return canonical(value)
        return FrozenResponse()
    def request(self,target,*,headers=None):
        url=urllib.parse.urlsplit(target)
        if url.scheme or url.netloc or not url.path.startswith('/api/'):raise ValueError('only_declared_api_gets')
        for pattern,function in self.registry.routes:
            match=re.fullmatch(re.sub(r'\{([^}]+)\}',r'(?P<\1>[^/]+)',pattern),url.path)
            if not match:continue
            query=dict(urllib.parse.parse_qsl(url.query));arguments={**match.groupdict()}
            for name,param in inspect.signature(function).parameters.items():
                if name=='request':
                    arguments[name]=Request({'type':'http','method':'GET','path':url.path,'headers':[(k.lower().encode(),str(v).encode()) for k,v in (headers or {}).items()],'client':('127.0.0.1',10000),'server':('fixture.invalid',80),'scheme':'http','query_string':url.query.encode()})
                elif name in arguments:continue
                else:
                    default=param.default
                    if hasattr(default,'default'):default=default.default
                    value=query.get(name,default)
                    if isinstance(default,bool):value=value in (True,'true','1')
                    elif isinstance(default,int):value=int(value)
                    arguments[name]=value
            try:
                value=function(**arguments)
                if inspect.isawaitable(value):value=asyncio.run(value)
                return normalize_root(response_value(value),self.root)
            except HTTPException as error:return {'status':error.status_code,'body':{'detail':error.detail},'headers':{}}
            except Exception as error:
                value=self.namespace['unhandled_error'](None,error)
                result=response_value(asyncio.run(value));result['raisedType']=type(error).__name__
                return normalize_root(result,self.root)
        raise ValueError('unknown_read_route')
    def effects(self):
        files={}
        metadata=self.snapshot.manifest['facts'].get('filesystem',{})
        for path in self.root.rglob('*'):
            if not path.is_file() or path.suffix=='.db' or path.name.endswith(('-wal','-shm')):continue
            name=path.relative_to(self.root).as_posix()
            files[name]={'metadataOnly':metadata[name]} if name in metadata and name not in self.snapshot.manifest['files'] else digest_file(path)
        return normalize_root({'files':files,'database':sqlite_rows(self.namespace['DB_PATH'])},self.root)
