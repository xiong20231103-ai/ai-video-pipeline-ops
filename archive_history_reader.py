"""Read explicit archived dates only; never materialize archives as live tasks."""
import hashlib
import json
import re
from pathlib import Path


def indexes(root):
    for index in root.glob('files/*/index.json'):
        if (index.parent/'rolled-back.json').exists():continue
        try:
            if index.stat().st_size>16*1024*1024:continue
            from json_read_cache import JSON_READ_CACHE
            value=JSON_READ_CACHE.read(index)
            if (not isinstance(value,dict) or value.get('schemaVersion')!=1 or not isinstance(value.get('files'),list)
                    or Path(value.get('archiveData','')).resolve()!=(index.parent/'data').resolve()):continue
            yield index,value
        except (OSError,ValueError,TypeError):continue


def archived_dates(root):
    result=set()
    for _,index in indexes(root):
        for entry in index['files']:
            if not isinstance(entry,dict) or entry.get('kind')!='handoff':continue
            for date in entry.get('dates') or []:
                if isinstance(date,str) and re.fullmatch(r'\d{1,2}\.\d{1,2}',date):result.add(date)
    return result


def archived_handoffs(root,date):
    if not isinstance(date,str) or not re.fullmatch(r'\d{1,2}\.\d{1,2}',date):return []
    result=[]
    for index_path,index in indexes(root):
        data_root=(index_path.parent/'data').resolve()
        for entry in index['files']:
            if not isinstance(entry,dict) or entry.get('kind')!='handoff' or date not in (entry.get('dates') or []):continue
            try:
                path=data_root/entry['path']
                if not path.resolve().is_relative_to(data_root) or path.is_symlink():continue
                if path.stat().st_size>16*1024*1024:continue
                raw=path.read_bytes()
                if len(raw)!=entry.get('size') or hashlib.sha256(raw).hexdigest()!=entry.get('sha256'):continue
                payload=json.loads(raw.decode('utf-8-sig'))
                if not isinstance(payload,dict) or not isinstance(payload.get('tasks'),list):continue
                result.append((path,float(entry['mtimeNs'])/1_000_000_000,payload))
            except (OSError,ValueError,TypeError,KeyError):continue
    return result
