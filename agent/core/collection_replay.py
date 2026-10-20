"""Offline R1 comparison harness; R0 supplies only frozen I/O and deferred adapters."""
import sqlite3,types
from contextlib import closing
from datetime import datetime
from .collection import CollectionSession
from .oracle import Oracle,normalize_root

def replay_collection(source,snapshot,scratch,targets,*,mutate=None):
    with Oracle(source,snapshot,scratch,collect=False) as environment:
        # Original Store schema/fixture seeding is isolated; transfer its consistent
        # view into RAM. The new Collector/projections are separately checked-in code.
        with closing(sqlite3.connect(environment.namespace['DB_PATH'])) as seed:
            session=CollectionSession(environment.namespace,seed=seed)
        with session:
            environment.namespace.update(session.namespace)
            # Deferred R2/R4 adapters use this session's frozen globals. No POST.
            if snapshot.manifest['facts'].get('scan',True):session.scan()
            session.collector.last_scan_at=snapshot.manifest['frozenAt']
            session.collector.last_scan_epoch=datetime.fromisoformat(snapshot.manifest['frozenAt'].replace('Z','+00:00')).timestamp()
            session.collector.thread=types.SimpleNamespace(is_alive=lambda:snapshot.manifest['facts'].get('collectorAlive',False))
            if mutate:mutate(session)
            def effects():
                result=environment.effects();result['database']=normalize_root(session.rows(),environment.root);return result
            before=effects();responses={target:environment.request(target) for target in targets};after=effects()
            return {'schema':1,'mode':'isolated','sourceIdentity':snapshot.manifest['sourceIdentity'],'legacySha256':snapshot.manifest['legacySha256'],'responses':responses,'effects':{'before':before,'after':after},'httpReads':environment.requests,'realShadowPassed':False,'switchAccepted':False}
