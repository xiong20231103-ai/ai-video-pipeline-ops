"""Explicit loopback-only GET port for the existing 18790 control plane."""
import json
import urllib.error
import urllib.parse
import urllib.request
from fastapi import HTTPException


def control_plane_json(config,path,timeout=8,*,sanitize):
    base=str(config.get('control_plane_url') or 'http://127.0.0.1:18790').rstrip('/')
    parts=urllib.parse.urlsplit(base)
    if parts.scheme not in {'http','https'} or parts.hostname not in {'127.0.0.1','localhost','::1'} or parts.username or parts.password:
        raise HTTPException(500,'生产安全控制面只允许本机回环地址')
    target=urllib.parse.urlsplit(path)
    if target.scheme or target.netloc or not target.path.startswith('/api/') or any(p in {'.','..'} for p in target.path.split('/')):
        raise HTTPException(500,'控制面读取路径无效')
    request=urllib.request.Request(base+path,headers={'Accept':'application/json'},method='GET')
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise HTTPException(502,'控制面数据超出限制')
        value=json.loads(raw.decode('utf-8-sig'))
    except urllib.error.HTTPError as error:raise HTTPException(error.code,'生产安全控制面返回错误') from None
    except (OSError,ValueError,UnicodeError):raise HTTPException(503,'生产安全控制面不可用') from None
    if not isinstance(value,dict):raise HTTPException(502,'生产安全控制面返回无效数据')
    return sanitize(value)
