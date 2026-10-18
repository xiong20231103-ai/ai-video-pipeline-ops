"""Strict JSON-pointer diffs and fixture-only legacy adapter replay."""
import copy
import json
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

def differences(expected, actual, allowed_pointers=()):
    allowed = set(allowed_pointers)
    if any('*' in pointer for pointer in allowed):
        raise ValueError('Wildcard exclusions are forbidden')
    changes=[]
    def compare(left,right,path=''):
        if path in allowed:
            return
        if type(left) is not type(right):
            changes.append({'path':path,'kind':'type','expected':left,'actual':right})
        elif isinstance(left,dict):
            for key in sorted(left.keys() | right.keys()):
                child=path+'/'+key.replace('~','~0').replace('/','~1')
                if key not in left or key not in right:
                    changes.append({'path':child,'kind':'missing','expected':left.get(key),'actual':right.get(key)})
                else:
                    compare(left[key],right[key],child)
        elif isinstance(left,list):
            if len(left)!=len(right):
                changes.append({'path':path,'kind':'length','expected':len(left),'actual':len(right)})
            for i,(a,b) in enumerate(zip(left,right)):
                compare(a,b,path+'/'+str(i))
        elif left != right:
            changes.append({'path':path,'kind':'value','expected':left,'actual':right})
    compare(expected,actual)
    return changes

def replay_receiver(legacy, fixture):
    """Run the original receiver normalizer using only fixture file/HTTP/DB input."""
    with TemporaryDirectory(prefix='ops-golden-') as folder, ExitStack() as stack:
        root=Path(folder)
        local=root/'project_status.json'
        if fixture.get('localStatus') is not None:
            value=fixture['localStatus']
            local.write_text(value if isinstance(value,str) else json.dumps(value),encoding='utf-8')
        config=dict(legacy.CONFIG,workbench_dir=str(root),download_project_status_file=str(local),receiver_status_url='http://fixture.invalid/api/pipeline/snapshot')
        collector=legacy.Collector(config,legacy.Store(root/'ops.db'))
        class FixtureResponse:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self): return json.dumps(fixture['receiver']).encode()
        stack.enter_context(patch.object(legacy.urllib.request,'urlopen',return_value=FixtureResponse()))
        stack.enter_context(patch.object(legacy,'now_iso',return_value=fixture['clock']))
        stack.enter_context(patch.object(legacy.time,'time',return_value=fixture['epoch']))
        collector.scan_project_download_statuses()
        return {'projects':copy.deepcopy(collector.project_download_statuses),
                'archivedProjects':copy.deepcopy(collector.archived_project_statuses),
                'controlReady':collector.receiver_control_ready,'receiverError':collector.receiver_error}
