"""Additive collection/projection session. No background start or default hook.

Business code is checked in separately. Each session receives explicit frozen
ports and has a private in-memory projection store, never the engine ops.db.
"""
from __future__ import annotations
import copy,inspect,json,sqlite3,threading,types
from contextlib import contextmanager
from pathlib import Path
from . import collection_logic as logic

class CollectionError(ValueError):pass

def _function(function, namespace):
    clone=types.FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    clone.__kwdefaults__=function.__kwdefaults__;clone.__annotations__=function.__annotations__
    return clone

def _class(original,namespace):
    attributes={'__module__':__name__}
    for name,item in vars(original).items():
        if inspect.isfunction(item):attributes[name]=_function(item,namespace)
        elif isinstance(item,staticmethod):attributes[name]=staticmethod(_function(item.__func__,namespace))
        elif name not in {'__dict__','__weakref__','__module__'}:attributes[name]=item
    return type(original.__name__,(),attributes)

class CollectionSession:
    def __init__(self,ports,*,source_sha=None,seed=None,max_bytes=50*1024*1024,max_rows=200000,store_factory=None):
        provenance=json.loads((Path(__file__).parents[2]/'contracts/migration/r1-provenance.json').read_text(encoding='utf-8'))
        required=set(provenance['requiredPorts'])-{'STORE','COLLECTOR'}
        missing=required-set(ports)
        if missing:raise CollectionError('missing_collection_ports:'+','.join(sorted(missing)))
        if type(max_bytes) is not int or max_bytes<65536 or max_bytes>50*1024*1024 or type(max_rows) is not int or not 1<=max_rows<=200000:raise CollectionError('invalid_projection_bounds')
        namespace={'__builtins__':__builtins__,'__name__':'parallel_collection','Any':object}
        namespace.update({k:copy.deepcopy(v) if isinstance(v,(dict,list,set)) else v for k,v in ports.items() if k in required})
        for name,value in vars(logic).items():
            if inspect.isfunction(value) and value.__module__==logic.__name__:namespace[name]=_function(value,namespace)
        namespace['Store']=_class(logic.Store,namespace)
        namespace['Collector']=_class(logic.Collector,namespace)
        # PiP status is an additive projection adapter: preserve the pinned
        # legacy Collector body and its provenance checks byte-for-byte.
        from .pip_status import public_capcut_session
        original_scan = namespace['Collector'].scan_workbench_pipeline
        def scan_with_pip_status(collector):
            fresh = original_scan(collector)
            path = namespace['resolve_path'](str(collector.config.get('workbench_ops_status') or ''))
            data = collector._json(path) if path.is_file() else {}
            collector.pipeline['capcut']['capcutSession'] = public_capcut_session(
                (data or {}).get('capcutSession'), now=__import__('time').time(), workbench_fresh=fresh)
            return fresh
        namespace['Collector'].scan_workbench_pipeline = scan_with_pip_status

        if source_sha is not None:
            from .source_profiles import PROFILES,PR49_BEHAVIOR
            if source_sha not in PROFILES:raise CollectionError('unsupported_collection_source')
            if source_sha in PR49_BEHAVIOR:
                from .collection_verified_final import normalize_task
                namespace['Collector'].normalize_task=_function(normalize_task,namespace)

        self.valid=False
        class MemoryStore(namespace['Store']):
            def __init__(self):
                self.path=':memory:';self.lock=threading.RLock();self.db=sqlite3.connect(':memory:')
                self.db.row_factory=sqlite3.Row
                try:
                    if seed is not None:
                        if seed.execute('PRAGMA page_count').fetchone()[0]*seed.execute('PRAGMA page_size').fetchone()[0]>max_bytes:raise CollectionError('projection_byte_limit')
                        seed.backup(self.db)
                    page_size=self.db.execute('PRAGMA page_size').fetchone()[0]
                    self.db.execute('PRAGMA max_page_count='+str(max_bytes//page_size))
                    self._init_db()
                except BaseException:self.db.close();raise
            def connect(self):return self.db
            @contextmanager
            def connection(self):
                with self.lock:
                    try:yield self.db;self.db.commit()
                    except BaseException:self.db.rollback();raise
        self.namespace=namespace
        self.store=MemoryStore() if store_factory is None else store_factory(namespace['Store'],seed=seed,max_bytes=max_bytes)
        namespace['STORE']=self.store
        try:
            self.collector=namespace['Collector'](namespace['CONFIG'],self.store);namespace['COLLECTOR']=self.collector
            self.max_rows=max_rows;self._bounded();self.valid=True
        except BaseException:self.close();raise
    def _bounded(self):
        with self.store.connection() as db:
            count=sum(db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('tasks','task_history','events','heartbeats','source_health'))
        if count>self.max_rows:raise CollectionError('projection_row_limit')
    def scan(self):
        self.valid=False
        self.collector.scan();self._bounded();self.valid=True
    def project(self,name,*args,**kwargs):
        if not self.valid:raise CollectionError('projection_incomplete')
        allowed={'task_box_payloads','authoritative_active_task_box','pipeline_for_date','pipeline_dates','overview_payload','public_task_items','public_task_item','public_metrics_payload','source_status_payload','service_health_payload','current_project_status_payload','dashboard_payload','dashboard_summary_payload','subtitle_verification_inventory'}
        if name not in allowed:raise CollectionError('unknown_projection')
        value=self.namespace[name](*args,**kwargs);self._bounded();return value
    def rows(self):
        result={}
        with self.store.connection() as db:
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
                table=row[0];result[table]=[dict(v) for v in db.execute('SELECT * FROM '+table)]
        # Same relational ordering contract as the R0 snapshot reader.
        from .snapshot import canonical
        return {k:sorted(v,key=canonical) for k,v in result.items()}
    def close(self):
        if hasattr(self.store,'close'):self.store.close()
        else:self.store.db.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
