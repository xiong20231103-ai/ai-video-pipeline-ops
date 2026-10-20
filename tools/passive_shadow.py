"""Passive evidence only: no HTTP, production imports, SQLite opens or writes.

Captures allowlisted state by content hash for later *offline* comparisons.
Does not claim R1-R5 real-shadow acceptance or activate a migration pointer.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,sqlite3,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent.backup_policy import RULES,default_roots,match_paths,checked_stat,PolicyError
from agent.core.snapshot import safe_facts,SnapshotError,TABLES

MAX_FILE=32*1024*1024
MAX_TOTAL=2*1024*1024*1024

def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def atomic(path,body):
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as f:f.write(body)
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

def disjoint(destination,roots):
    destination=Path(destination).resolve()
    for root in roots.values():
        root=Path(root).resolve()
        if destination==root or destination.is_relative_to(root) or root.is_relative_to(destination):
            raise ValueError('output_source_overlap')
    checked_stat(destination)
    return destination

def approved_rules():
    # Never read files classified as private, configuration, CSV text, raw logs,
    # production media, or the agent execution database (may contain credentials).
    return [r for r in RULES if not r.secret and r.root!='AGENT'
            and not r.sqlite and r.pattern.endswith('.json')
            and Path(r.pattern).name not in {'workbench_settings.json','pipeline_paths.json'}]

def stable_bytes(path):
    first=checked_stat(path)
    if first is None:return None
    if first.st_size>MAX_FILE:raise ValueError('source_too_large')
    with path.open('rb') as stream:body=stream.read(MAX_FILE+1)
    after=checked_stat(path)
    if len(body)>MAX_FILE:raise ValueError('source_too_large')
    if after is None or (first.st_size,first.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError('source_changed_during_read')
    return body

def safe_json(body):
    text=body.decode('utf-8-sig');safe_facts(text)
    value=json.loads(text);safe_facts(value)
    return value

def ops_projection(path,output):
    # Copy the main DB/WAL while stable. SQLite may write shared-memory even in
    # mode=ro; therefore no SQLite connection ever touches the production path.
    parts={};before={}
    for suffix in ('','-wal'):
        source=Path(str(path)+suffix)
        info=checked_stat(source)
        before[suffix]=None if info is None else (info.st_size,info.st_mtime_ns)
        if info:
            if info.st_size>256*1024*1024:raise ValueError('database_too_large')
            parts[suffix]=source.read_bytes()
    if '' not in parts:return None
    for suffix in ('','-wal'):
        info=checked_stat(Path(str(path)+suffix))
        if (None if info is None else (info.st_size,info.st_mtime_ns))!=before[suffix]:
            raise ValueError('database_changed_during_copy')
    scratch=output/'scratch'/uuid.uuid4().hex;scratch.mkdir(parents=True)
    copy=scratch/'ops.db'
    try:
        for suffix,body in parts.items():Path(str(copy)+suffix).write_bytes(body)
        db=sqlite3.connect(copy)
        try:
            names=[row[0] for row in db.execute("select name from sqlite_master where type='table'")]
            if set(names)-TABLES:raise ValueError('unexpected_ops_table')
            result={}
            for name in sorted(names):
                cursor=db.execute('select * from "'+name+'"')
                columns=[c[0] for c in cursor.description]
                rows=[dict(zip(columns,row)) for row in cursor]
                safe_facts(rows);result[name]=sorted(rows,key=encoded)
            return encoded(result)
        finally:db.close()
    finally:
        # Only our unique scratch children, never recursive deletion of sources.
        for child in scratch.iterdir():child.unlink()
        scratch.rmdir()

def record(output,roots,*,quota=MAX_TOTAL):
    output=disjoint(output,roots)
    output.mkdir(parents=True,exist_ok=True)
    for name in ('objects','samples','scratch'):(output/name).mkdir(exist_ok=True)
    if any(checked_stat(output/name) is None for name in ('objects','samples','scratch')):
        raise ValueError('output_invalid')
    used=sum(p.stat().st_size for folder in ('objects','samples') for p in (output/folder).iterdir())
    rows=[];errors={};exhausted=False;started=time.monotonic()
    def store(root,relative,body):
        nonlocal used,exhausted
        digest=hashlib.sha256(body).hexdigest();target=output/'objects'/digest
        if not target.exists():
            if used+len(body)>quota:exhausted=True;return
            atomic(target,body);used+=len(body)
        rows.append(dict(root=root,relative=relative,sha256=digest,bytes=len(body)))
    def problem(kind):errors[kind]=errors.get(kind,0)+1
    for rule in approved_rules():
        root=Path(roots[rule.root])
        try:paths=match_paths(root,rule.pattern)
        except (OSError,PolicyError):problem('inventory_unavailable');continue
        for source in paths:
            if len(rows)>=10000:problem('file_limit');break
            try:
                body=stable_bytes(source)
                if body is not None:
                    safe_json(body);store(rule.root,source.relative_to(root).as_posix(),body)
            except SnapshotError:problem('private_content_rejected')
            except (OSError,ValueError,UnicodeError):problem('unreadable_or_unaligned')
    try:
        body=ops_projection(Path(roots['OPS'])/'data/ops.db',output)
        if body is not None:store('OPS','data/ops.logical.json',body)
    except SnapshotError:problem('private_database_content_rejected')
    except (OSError,ValueError,sqlite3.Error):problem('database_unaligned_or_unavailable')
    result=dict(schema=1,mode='passive-evidence',observedAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        files=rows,errorCounts=errors,quotaExhausted=exhausted,bytesStored=used,
        elapsedSeconds=round(time.monotonic()-started,3),productionWrites=False,businessRequests=0,
        comparable=False,realShadowPassed=False,switchAccepted=False,
        missingForComparison=['aligned filesystem/process/external-source facts','offline candidate replay','complete triggered batch coverage'])
    body=encoded(result)
    if used+len(body)<=quota:atomic(output/'samples'/(datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex+'.json'),body)
    summary={k:v for k,v in result.items() if k!='files'};summary['fileCount']=len(rows)
    atomic(output/'status.json',encoded(summary));return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--once',action='store_true');a=p.parse_args()
    roots=default_roots(Path(os.environ['LOCALAPPDATA'])/'OpsAgent')
    output=disjoint(a.output,roots);output.mkdir(parents=True,exist_ok=True)
    # One instance; only the independent output lock is writable.
    import msvcrt
    with (output/'observer.lock').open('a+b') as lock:
        if lock.tell()==0:lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return 2
        atomic(output/'process.json',encoded(dict(pid=os.getpid(),startedAt=datetime.datetime.now(datetime.timezone.utc).isoformat())))
        while not (output/'STOP').exists():
            try:
                status=record(output,roots)
                if a.once:print(json.dumps(status));return 0
            except (OSError,ValueError,sqlite3.Error):
                atomic(output/'status.json',encoded(dict(mode='passive-evidence',error='capture_failed',productionWrites=False,realShadowPassed=False)))
            for _ in range(120):
                if (output/'STOP').exists():break
                time.sleep(1)
    return 0
if __name__=='__main__':raise SystemExit(main())
