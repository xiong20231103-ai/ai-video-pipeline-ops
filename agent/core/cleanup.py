"""R5 candidate session retaining original strict-source guards and H2 mover."""
from __future__ import annotations
import asyncio
import copy
from contextvars import ContextVar
import inspect
import threading
import types

from . import cleanup_logic


def bind_function(function,namespace,memo=None):
    memo={} if memo is None else memo
    if id(function) in memo:return memo[id(function)]
    cells=[]
    for cell in function.__closure__ or ():
        value=cell.cell_contents
        if inspect.isfunction(value) and value.__module__==cleanup_logic.__name__:
            value=bind_function(value,namespace,memo)
        cells.append(types.CellType(value))
    clone=types.FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,tuple(cells) or None)
    memo[id(function)]=clone
    clone.__kwdefaults__=function.__kwdefaults__;clone.__annotations__=function.__annotations__
    if hasattr(function,'__wrapped__'):
        clone.__wrapped__=bind_function(function.__wrapped__,namespace,memo)
    return clone


class CleanupSession:
    def __init__(self,ports,*,tickets,isolated=False):
        missing=set(cleanup_logic.REQUIRED_PORTS)-set(ports)
        if missing:raise ValueError('missing_cleanup_ports:'+','.join(sorted(missing)))
        namespace={'__builtins__':__builtins__,'__name__':'cleanup_candidate','wraps':cleanup_logic.wraps}
        namespace.update({key:copy.deepcopy(value) if isinstance(value,(dict,list,set)) else value
                          for key,value in ports.items() if key in cleanup_logic.REQUIRED_PORTS})
        namespace['_CLEANUP_SOURCE_STRICT']=ContextVar('r5_strict_source',default=False)
        for name in ('CAPCUT_DRAFT_LOCK','AUDIO_CLEANUP_LOCK','PRODUCTION_FILE_CLEANUP_LOCK'):
            namespace[name]=threading.RLock()
        namespace['CLOUD_CLEANUP_TICKETS']=tickets
        memo={}
        for name,value in vars(cleanup_logic).items():
            if inspect.isfunction(value) and value.__module__==cleanup_logic.__name__:
                namespace[name]=bind_function(value,namespace,memo)
        self.namespace=namespace;self.isolated=isolated

    def evaluate(self,name,*args,**kwargs):
        if not self.isolated:raise ValueError('cleanup_isolated_evaluation_only')
        function=self.namespace.get(name)
        if not inspect.isfunction(function) or function.__globals__ is not self.namespace:
            raise ValueError('unknown_cleanup_function')
        result=function(*args,**kwargs)
        return asyncio.run(result) if inspect.isawaitable(result) else result

    @staticmethod
    def capability():
        return {'enabled':False,'mode':'shadow','categories':['drafts','audio','production'],
                'retentionDays':3,'fiveDirectoryExtension':False,'switchAccepted':False}


def replay_cleanup(source,snapshot,scratch,targets):
    from cleanup_tickets import CleanupTickets
    from .oracle import Oracle
    with Oracle(source,snapshot,scratch) as environment:
        session=CleanupSession(environment.namespace,tickets=CleanupTickets(clock=environment.namespace['time'].time),isolated=True)
        environment.namespace.update(session.namespace)
        before=environment.effects()
        responses={target:environment.request(target) for target in targets}
        after=environment.effects()
        return {'schema':1,'mode':'isolated','sourceIdentity':snapshot.manifest['sourceIdentity'],
                'legacySha256':snapshot.manifest['legacySha256'],'responses':responses,
                'effects':{'before':before,'after':after},'httpReads':environment.requests,
                'realShadowPassed':False,'switchAccepted':False}
