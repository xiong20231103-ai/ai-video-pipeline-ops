"""Explicit R4 session; no scheduler, listener, installed app import or startup.

The default session is a shadow candidate. It cannot be attached as a live
command backend. R4 still requires the RC expiry/cancellation acceptance gate.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import threading
import types

from . import recovery_logic
from .ordinary import request_for
from fastapi import HTTPException
from starlette.responses import JSONResponse


class RecoverySession:
    def __init__(self, ports, *, isolated=False):
        missing=set(recovery_logic.REQUIRED_PORTS)-set(ports)
        if missing:raise ValueError('missing_recovery_ports:'+','.join(sorted(missing)))
        namespace={'__builtins__':__builtins__,'__name__':'recovery_candidate'}
        for name in recovery_logic.REQUIRED_PORTS:
            value=ports[name]
            namespace[name]=copy.deepcopy(value) if isinstance(value,(dict,list,set)) else value
        # Each isolated/shadow session owns its algorithm lock and cache. It is
        # never a second production authority or a lock for the running app.
        namespace['CONTROL_COMMAND_LOCK']=threading.Lock()
        namespace['_HEALTH_CACHE']={'at':0.0,'payload':None}
        for name,value in vars(recovery_logic).items():
            if inspect.isfunction(value) and value.__module__==recovery_logic.__name__:
                cloned=types.FunctionType(value.__code__,namespace,value.__name__,value.__defaults__,value.__closure__)
                cloned.__kwdefaults__=value.__kwdefaults__
                cloned.__annotations__=value.__annotations__
                namespace[name]=cloned
        self.namespace=namespace
        self.isolated=isolated

    def evaluate(self,name,*args,**kwargs):
        if not self.isolated:raise ValueError('recovery_isolated_evaluation_only')
        function=self.namespace.get(name)
        bound_cancel=getattr(getattr(self,'transport',None),'cancel',None)
        if function!=bound_cancel and (not inspect.isfunction(function) or function.__globals__ is not self.namespace):
            raise ValueError('unknown_recovery_function')
        result=function(*args,**kwargs)
        return asyncio.run(result) if inspect.isawaitable(result) else result

    def create(self,body,*,client='127.0.0.1'):
        return self.evaluate('create_control_command',request_for('/api/control-commands',body,client))

    def bind_transport(self,controller):
        if not self.isolated:raise ValueError('recovery_isolated_evaluation_only')
        from .recovery_transport import RecoveryTransport
        transport=RecoveryTransport(controller,self.namespace)
        self.namespace['request_workbench_continue']=transport.submit
        self.namespace['cancel_control_command']=transport.cancel
        # A bound external method is invoked only via explicit wrapper; the
        # normal evaluate allowlist still requires candidate-owned functions.
        self.transport=transport
        return transport

    @staticmethod
    def capability():
        # Deliberately not protocol 1/send-enabled: pending RC delivery rules
        # must not be bypassed by copying an old implementation into the agent.
        return {'enabled':False,'mode':'shadow','switchAccepted':False,
                'blockers':['full_batch_shadow_missing','rc_expiry_cancel_contract_unverified']}


def replay_recovery(source,snapshot,scratch,targets):
    """Use only R0 verified snapshots/IO; GET writes stay under scratch."""
    from .oracle import Oracle
    with Oracle(source,snapshot,scratch) as environment:
        session=RecoverySession(environment.namespace,isolated=True)
        environment.namespace.update(session.namespace)
        before=environment.effects()
        responses={target:environment.request(target) for target in targets}
        after=environment.effects()
        return {'schema':1,'mode':'isolated','sourceIdentity':snapshot.manifest['sourceIdentity'],
                'legacySha256':snapshot.manifest['legacySha256'],'responses':responses,
                'effects':{'before':before,'after':after},'httpReads':environment.requests,
                'realShadowPassed':False,'switchAccepted':False}
