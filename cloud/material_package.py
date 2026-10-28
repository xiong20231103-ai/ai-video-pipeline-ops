"""Bounded ZIP/manifest validation, without extracting or executing its contents."""
import hashlib
import json
from pathlib import PurePosixPath
import stat
import zipfile
import zlib

from cloud.material_handoff import HandoffError, SHA

MAX_FILES = 30000
MAX_EXPANDED = 4*1024**3
MAX_MANIFEST = 4*1024**2
ROOTS = {'attachments','review','mf-judge','exemplars','baseline'}
FORBIDDEN = {'site.json','device.json','mf_device.json','credentials','cookies','login',
             'browser-profile','node_modules','.git','__pycache__'}


def safe_path(name):
    if not isinstance(name,str) or not name or len(name)>400 or '\\' in name or ':' in name:
        raise HandoffError('unsafe_package_path',400)
    path=PurePosixPath(name)
    if path.is_absolute() or any(part in ('','.','..') for part in name.split('/')):
        raise HandoffError('unsafe_package_path',400)
    reserved={'con','prn','aux','nul',*[f'com{i}' for i in range(1,10)],*[f'lpt{i}' for i in range(1,10)]}
    if any(part.rstrip('. ')!=part or part.split('.')[0].lower() in reserved or
           any(ord(c)<32 or c in '<>"|?*' for c in part) for part in path.parts):
        raise HandoffError('unsafe_windows_package_path',400)
    if name!='material.db' and (len(path.parts)<2 or path.parts[0] not in ROOTS):
        raise HandoffError('unsupported_package_root',400)
    if any(part.lower() in FORBIDDEN or part.lower().startswith('.env') or part.lower().endswith(('.db-wal','.db-shm','.pid','.key','.pem')) for part in path.parts):
        raise HandoffError('machine_private_file_forbidden',400)
    return name


def strict_json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError('duplicate_key')
            result[key]=value
        return result
    try:
        return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError,UnicodeError):
        raise HandoffError('invalid_package_manifest',400) from None


def validate_package(path, row):
    """Verify immutable outer bytes and every manifest-referenced payload file.

    Cloud checks DB header/hash, not SQL/app schema or business completeness.
    PR5 must run SQLite integrity/foreign-key checks and attachment closure on
    its isolated copy before release and again on restore.
    """
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2),b''):
            digest.update(chunk)
    if path.stat().st_size!=row['bytes'] or digest.hexdigest()!=row['sha256']:
        raise HandoffError('package_storage_hash_mismatch',409)
    try:
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist()
            if not 2<=len(entries)<=MAX_FILES+1 or sum(x.file_size for x in entries)>MAX_EXPANDED:
                raise HandoffError('package_expansion_limit',413)
            names=set()
            for entry in entries:
                file_type=stat.S_IFMT(entry.external_attr>>16)
                if entry.filename.casefold() in names or entry.is_dir() or file_type not in (0,stat.S_IFREG) or entry.flag_bits&1:
                    raise HandoffError('duplicate_or_special_package_entry',400)
                names.add(entry.filename.casefold())
                if entry.filename!='manifest.json':
                    safe_path(entry.filename)
                if entry.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED):
                    raise HandoffError('unsupported_package_compression',400)
            info=archive.getinfo('manifest.json')
            if info.file_size>MAX_MANIFEST:
                raise HandoffError('manifest_size_limit',413)
            m=strict_json(archive.read(info))
            required={'format','package_id','parent_package_id','source_device','generation','epoch','schema_version','code_version','created_at','files','unresolved'}
            if not isinstance(m,dict) or set(m)!=required or m['format']!=1 or type(m['format']) is not int:
                raise HandoffError('manifest_fields',400)
            expected={'package_id':row['id'],'parent_package_id':row['parent_id'],
                      'source_device':row['device'],'generation':row['generation'],'epoch':row['epoch']}
            if any(m[k]!=v for k,v in expected.items()) or type(m['epoch']) is not int:
                raise HandoffError('manifest_holder_or_parent_mismatch',409)
            for key in ('schema_version','code_version','created_at'):
                if not isinstance(m[key],str) or not 1<=len(m[key])<=100:
                    raise HandoffError('manifest_version_or_date',400)
            # Counts only, never import envelopes, credentials or error/log text.
            if (not isinstance(m['unresolved'],dict) or set(m['unresolved'])-{'imports','collector_ops','attachments','reconcile'} or
                    any(type(v) is not int or not 0<=v<=10000000 for v in m['unresolved'].values())):
                raise HandoffError('invalid_unresolved_summary',400)
            if m['unresolved'].get('attachments',0) or m['unresolved'].get('collector_ops',0):
                raise HandoffError('normal_handoff_has_unresolved_attachments_or_collector',409)
            files=m['files']
            if not isinstance(files,list) or not 1<=len(files)<=MAX_FILES:
                raise HandoffError('manifest_file_list',400)
            listed=set()
            expanded=0
            for item in files:
                if not isinstance(item,dict) or set(item)!={'path','bytes','sha256'}:
                    raise HandoffError('manifest_file_fields',400)
                name=safe_path(item['path'])
                if name in listed or type(item['bytes']) is not int or not 0<=item['bytes']<=MAX_EXPANDED:
                    raise HandoffError('manifest_duplicate_or_size',400)
                if not isinstance(item['sha256'],str) or not SHA.fullmatch(item['sha256']):
                    raise HandoffError('manifest_file_hash',400)
                listed.add(name)
                entry=archive.getinfo(name)
                if entry.file_size!=item['bytes']:
                    raise HandoffError('manifest_file_size_mismatch',400)
                count=0
                sha=hashlib.sha256()
                first=b''
                with archive.open(entry) as stream:
                    while True:
                        chunk=stream.read(min(1024**2,item['bytes']-count+1))
                        if not chunk:
                            break
                        if not first:
                            first=chunk[:16]
                        count+=len(chunk)
                        if count>item['bytes']:
                            raise HandoffError('expanded_file_size_limit',413)
                        sha.update(chunk)
                if count!=item['bytes'] or sha.hexdigest()!=item['sha256']:
                    raise HandoffError('manifest_file_hash_mismatch',400)
                if name=='material.db' and first!=b'SQLite format 3\x00':
                    raise HandoffError('invalid_sqlite_header',400)
                expanded+=count
            if 'material.db' not in listed or listed|{'manifest.json'}!={x.filename for x in entries}:
                raise HandoffError('missing_or_unlisted_package_file',400)
            return {'schema_version':m['schema_version'],'code_version':m['code_version'],
                    'created_at':m['created_at'],'files':len(files),'expanded_bytes':expanded,'unresolved':m['unresolved']}
    except (zipfile.BadZipFile,KeyError,RuntimeError,ValueError,EOFError,NotImplementedError,zlib.error) as error:
        if isinstance(error,HandoffError):
            raise
        raise HandoffError('invalid_package_archive',400) from None
