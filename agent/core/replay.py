"""Explicit snapshot/oracle replay. No worker, switch or network transport."""
import hashlib,json,os
from pathlib import Path
from tempfile import TemporaryDirectory
from agent.core.snapshot import capture,canonical
from agent.core.oracle import Oracle

def read_targets(contract):
    return [row['path'].replace('{batch_id}','fixture-batch-1').replace('{command_id}','fixture-command') for row in contract if row['method']=='GET']

def make_fixture(profile,source,destination):
    from datetime import datetime
    with TemporaryDirectory(prefix='r0-input-') as folder:
        inputs={}
        for i,(name,value) in enumerate(profile.get('files',{}).items()):
            path=Path(folder)/(str(i)+(Path(name).suffix or '.json'))
            path.write_bytes(value.encode() if isinstance(value,str) else canonical(value))
            epoch=datetime.fromisoformat(profile['frozenAt']).timestamp()
            os.utime(path,(epoch-3600,epoch-3600));inputs[name]=path
        return capture(destination,files=inputs,facts=profile['facts'],frozen_at=profile['frozenAt'],legacy_sha256=hashlib.sha256(source.encode()).hexdigest())

def replay(source,snapshot,scratch,targets):
    with Oracle(source,snapshot,scratch) as oracle:
        before=oracle.effects()
        responses={target:oracle.request(target) for target in targets}
        after=oracle.effects()
        return {'schema':1,'mode':'isolated','sourceIdentity':snapshot.manifest['sourceIdentity'],'legacySha256':snapshot.manifest['legacySha256'],'responses':responses,'effects':{'before':before,'after':after},'httpReads':oracle.requests,'realShadowPassed':False,'switchAccepted':False}
