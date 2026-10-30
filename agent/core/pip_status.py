"""Public PiP execution status; excludes filesystem paths and request secrets."""
import math

def public_capcut_session(value, *, now, workbench_fresh):
    if not isinstance(value,dict) or value.get('mode') not in ('main','pip'):
        return {'mode':'main','executorOnline':False}
    if value['mode']=='main':return {'mode':'main','executorOnline':False}
    epoch=value.get('heartbeatEpoch')
    fresh=(type(epoch) in (int,float) and math.isfinite(epoch) and 0<=now-epoch<=15)
    session=value.get('sessionId')
    online=(workbench_fresh and value.get('executorOnline') is True and fresh and
            type(session) is int and session>0 and value.get('state') in ('ready','busy'))
    result={'mode':'pip','executorOnline':bool(online),'state':value.get('state') if online else 'offline'}
    if online:result.update(sessionId=session,heartbeatEpoch=epoch)
    return result
