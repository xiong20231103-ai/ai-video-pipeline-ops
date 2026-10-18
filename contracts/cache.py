"""Conservative keys and explicit-path semantic hashes for response caching."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit

MATRIX = json.loads((Path(__file__).with_name('endpoints.json')).read_text(encoding='utf-8'))

def endpoint(method, path):
    for row in MATRIX:
        pattern = re.sub(r'\{[^}]+\}', '[^/]+', row['path'])
        if row['method'] == method.upper() and re.fullmatch(pattern, path):
            return row
    raise ValueError('Endpoint is outside the explicit contract')

def cache_key(method, target):
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or parts.fragment or len(target) > 4096:
        raise ValueError('Only bounded relative API targets are accepted')
    path = unquote(parts.path, errors='strict')
    if any(x in {'.', '..', ''} for x in path.split('/')[1:]) or '\\' in path:
        raise ValueError('Non-canonical path')
    spec = endpoint(method, path)
    if method.upper() != 'GET':
        raise ValueError('Write operations are not response cache keys')
    pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=False)
    if len(pairs) > 16 or any(name not in spec['query'] for name, _ in pairs):
        raise ValueError('Unknown or excessive query parameters')
    # FastAPI scalar query parameters select the last supplied value.
    effective = dict(pairs)
    canonical = quote(path, safe='/{}-_')
    query = urlencode(sorted(effective.items()))
    return method.upper() + ' ' + canonical + ('?' + query if query else '')

def semantic_hash(body, ignored_pointers=('/updatedAt', '/metrics/time')):
    """Ignore exact transport-only paths, never all nested timestamps/identities."""
    ignored = set(ignored_pointers)
    def project(value, pointer=''):
        if isinstance(value, dict):
            return {key: project(child, pointer + '/' + key.replace('~','~0').replace('/','~1'))
                    for key, child in value.items()
                    if pointer + '/' + key.replace('~','~0').replace('/','~1') not in ignored}
        if isinstance(value, list):
            return [project(child, pointer + '/' + str(index)) for index, child in enumerate(value)]
        return value
    return hashlib.sha256(json.dumps(project(body),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
