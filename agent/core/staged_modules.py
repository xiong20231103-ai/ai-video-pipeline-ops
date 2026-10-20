"""Install reviewed candidate algorithms in the retained host before lifespan.

There is one existing Store, Collector and set of locks throughout R0--R5.
R2's cloud history is additive; it is not a second local projection writer.
No discovery, process launch, HTTP request or background thread is performed.
"""
import inspect
import types
from . import collection_logic,ordinary_logic,recovery_logic,cleanup_logic
from .collection import _class
from .cleanup import bind_function

STAGES=('R0','R1','R2','R3','R4','R5')
MODULES={'R1':collection_logic,'R3':ordinary_logic,'R4':recovery_logic,'R5':cleanup_logic}


def selected(stage):
    if stage not in STAGES:raise ValueError('invalid_transition_stage')
    return STAGES[:STAGES.index(stage)+1]


def install(namespace,application,stage):
    """Only a quiescent startup may bind candidates; never hot-swap a request."""
    modules=selected(stage)
    collector=namespace['COLLECTOR'];store=namespace['STORE']
    if collector.thread and collector.thread.is_alive():raise ValueError('transition_collector_already_running')
    if getattr(collector,'_ops_staged_modules',None) is not None:raise ValueError('transition_already_installed')
    # Preserve the original objects. In particular, do not allocate new cleanup
    # locks, a new recovery lock, a second ticket cache or a new ContextVar.
    locks={name:namespace[name] for name in ('CONTROL_COMMAND_LOCK','CAPCUT_DRAFT_LOCK',
        'AUDIO_CLEANUP_LOCK','PRODUCTION_FILE_CLEANUP_LOCK','_CLEANUP_SOURCE_STRICT','CLOUD_CLEANUP_TICKETS')}
    origins={}
    for module_name in modules:
        module=MODULES.get(module_name)
        if module is None:continue
        memo={}
        for name,value in vars(module).items():
            if inspect.isfunction(value) and value.__module__==module.__name__:
                namespace[name]=bind_function(value,namespace,memo);origins[name]=module_name
        if module_name=='R1':
            candidate=_class(collection_logic.Collector,namespace)
            for name,method in vars(candidate).items():
                if inspect.isfunction(method) and name not in {'__init__','start','stop','run'}:
                    setattr(collector,name,types.MethodType(method,collector))
    if namespace['STORE'] is not store or namespace['COLLECTOR'] is not collector:
        raise ValueError('transition_state_authority_changed')
    if any(namespace[name] is not value for name,value in locks.items()):
        raise ValueError('transition_lock_authority_changed')
    # FastAPI has already derived request parameters from the unchanged source
    # signature. Its request handler retains this Dependant object, so update
    # the actual call as well as the public endpoint reference.
    for route in application.routes:
        old=getattr(route,'endpoint',None);name=getattr(old,'__name__',None)
        candidate=namespace.get(name)
        if name in origins:
            if not hasattr(route,'dependant'):raise ValueError('transition_route_binding_unavailable')
            route.endpoint=candidate;route.dependant.call=candidate
    collector._ops_staged_modules=modules
    return {'stage':stage,'installedModules':list(modules),'functions':origins,
        'sharedStore':True,'sharedCollector':True,'sharedLocks':True,'backgroundStarted':False}
