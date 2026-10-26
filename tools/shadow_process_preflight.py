"""Dynamic listener/PID birth probe. Call inside the actual Dashboard host.

No process launch or control. Private command lines are rejected before they
can enter a report. Missing image/argv fields never become empty valid facts.
"""
import os
import math
from tools.shadow_capture import _safe, CaptureError


def probe_processes(psutil,*,agent_pid=None,extra_pids=(),include_children=True,transient_children=False):
    """``transient_children`` skips a descendant (e.g. a per-video CapCut or
    ffmpeg worker) that exits or hides its fields mid-probe instead of
    reporting the whole probe incomplete. Role processes stay strict."""
    roles={'dashboard':os.getpid()}
    wanted={8765:'dashboard',8766:'receiver',18790:'control'}
    missing=[]
    try:
        connections=psutil.net_connections(kind='tcp')
    except Exception:
        connections=[];missing.append({'role':'listeners','code':'access_denied'})
    for port,role in wanted.items():
        owners={row.pid for row in connections if row.status=='LISTEN' and row.laddr.port==port and row.pid}
        if len(owners)==1 and (role!='dashboard' or os.getpid() in owners):roles[role]=owners.pop()
        else:missing.append({'role':role,'code':'listener_identity_missing_or_ambiguous'})
    if type(agent_pid) is int and agent_pid>0:roles['agent']=agent_pid
    else:missing.append({'role':'agent','code':'agent_status_missing'})
    pids=set(roles.values())|set(extra_pids);strict=set(pids)
    if include_children:
        for pid in list(pids):
            try:pids.update(row.pid for row in psutil.Process(pid).children(recursive=True))
            except Exception:missing.append({'role':'children','code':'process_tree_unavailable'})
    records=[]
    for pid in sorted(pids):
        role_names=sorted(role for role,value in roles.items() if value==pid)
        try:
            process=psutil.Process(pid)
            row=process.as_dict(attrs=['pid','ppid','name','exe','cmdline','create_time','username'])
            if (row['pid']!=pid or not row['exe'] or not row['cmdline'] or not row['username']
                    or type(row['create_time']) not in (int,float)
                    or not math.isfinite(row['create_time']) or row['create_time']<=0):
                raise CaptureError('process_identity_incomplete')
            _safe(row)
            # Check flag names even when a value is a separate argv item.
            from re import search,I
            if any(search(r'token|password|secret|webhook|authorization|cookie|api.?key',arg,I) for arg in row['cmdline']):
                raise CaptureError('private_process_argument')
            records.append(row)
        except Exception:
            if transient_children and pid not in strict:continue
            missing.append({'roles':role_names,'code':'process_fields_missing_or_private'})
    return {'processRecords':records,'processIds':[row['pid'] for row in records],'roles':dict(roles),
            'preflight':{'hostPid':os.getpid(),'missing':missing,'complete':not missing,
                         'businessRequests':0,'productionWrites':False}}
