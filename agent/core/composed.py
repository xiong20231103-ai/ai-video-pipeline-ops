"""Offline composition boundary. No installed app, listener or live executor.

All extracted algorithms share one projection, lock set and global namespace.
Construction requires explicit ports; production activation is deliberately absent.
"""
from __future__ import annotations
import copy
import inspect
import threading
from contextvars import ContextVar
from .collection import CollectionSession
from .cleanup import bind_function
from . import collection_logic,ordinary_logic,recovery_logic,cleanup_logic,compatibility_logic


def _unwired_recovery(*args,**kwargs):
    raise ValueError('recovery_protocol2_transport_not_bound')


class ComposedSession(CollectionSession):
    def __init__(self,ports,*,tickets,seed=None,store_factory=None):
        prepared=dict(ports)
        for module in (collection_logic,ordinary_logic,recovery_logic,cleanup_logic,compatibility_logic):
            memo={}
            for name,value in vars(module).items():
                if inspect.isfunction(value) and value.__module__==module.__name__:
                    prepared[name]=bind_function(value,prepared,memo)
        super().__init__(prepared,seed=seed,store_factory=store_factory)
        try:
            namespace=self.namespace
            for name,value in ports.items():
                if name not in namespace:
                    namespace[name]=copy.deepcopy(value) if isinstance(value,(dict,list,set)) else value
            namespace['_CLEANUP_SOURCE_STRICT']=ContextVar('r6_strict_source',default=False)
            namespace['CONTROL_COMMAND_LOCK']=threading.Lock()
            namespace['SAFETY_CACHE_LOCK']=threading.Lock()
            namespace['SAFETY_CACHE']={'payload':None,'expiresAt':0.0}
            namespace['_HEALTH_CACHE']={'at':0.0,'payload':None}
            for name in ('CAPCUT_DRAFT_LOCK','AUDIO_CLEANUP_LOCK','PRODUCTION_FILE_CLEANUP_LOCK'):
                namespace[name]=threading.RLock()
            namespace['CLOUD_CLEANUP_TICKETS']=tickets
            for module in (ordinary_logic,recovery_logic,cleanup_logic,compatibility_logic):
                memo={}
                for name,value in vars(module).items():
                    if inspect.isfunction(value) and value.__module__==module.__name__:
                        namespace[name]=bind_function(value,namespace,memo)
            # No dynamic import of the installed Workbench controller.
            namespace['request_workbench_continue']=_unwired_recovery
        except BaseException:
            self.close()
            raise

    @staticmethod
    def capability():
        return {'enabled':False,'mode':'isolated-composition',
                'realShadowPassed':False,'switchAccepted':False,
                'legacyRetired':False}

    def bind_controller(self,controller):
        from .recovery_transport import RecoveryTransport
        transport=RecoveryTransport(controller,self.namespace)
        self.namespace['request_workbench_continue']=transport.submit
        self.namespace['cancel_control_command']=transport.cancel
        self.recovery_transport=transport


def replay_composed(source,snapshot,scratch,targets):
    import sqlite3,types
    from contextlib import closing
    from datetime import datetime
    from cleanup_tickets import CleanupTickets
    from .oracle import Oracle,normalize_root
    with Oracle(source,snapshot,scratch,collect=False) as environment:
        with closing(sqlite3.connect(environment.namespace['DB_PATH'])) as seed:
            session=ComposedSession(environment.namespace,seed=seed,
                tickets=CleanupTickets(clock=environment.namespace['time'].time))
        with session:
            # R0 declares these three external observations as frozen ports.
            # Preserve the exact same fixture inputs on both sides rather than
            # re-measuring this machine's CPU/NICs in the extracted implementation.
            for name in ('system_metrics','process_status','pending_delete_roots'):
                session.namespace[name]=environment.namespace[name]
            environment.namespace.update(session.namespace)
            # Route objects must use candidate handlers, not legacy handlers
            # merely seeing candidate helpers through updated globals.
            environment.registry.routes=[(path,session.namespace[fn.__name__])
                for path,fn in environment.registry.routes]
            if snapshot.manifest['facts'].get('scan',True):session.scan()
            session.collector.last_scan_at=snapshot.manifest['frozenAt']
            session.collector.last_scan_epoch=datetime.fromisoformat(snapshot.manifest['frozenAt'].replace('Z','+00:00')).timestamp()
            session.collector.thread=types.SimpleNamespace(is_alive=lambda:snapshot.manifest['facts'].get('collectorAlive',False))
            def effects():
                result=environment.effects()
                result['database']=normalize_root(session.rows(),environment.root)
                return result
            before=effects();responses={target:environment.request(target) for target in targets};after=effects()
            return {'schema':1,'mode':'isolated','sourceIdentity':snapshot.manifest['sourceIdentity'],
                'legacySha256':snapshot.manifest['legacySha256'],'responses':responses,
                'effects':{'before':before,'after':after},'httpReads':environment.requests,
                'realShadowPassed':False,'switchAccepted':False}
