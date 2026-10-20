"""Page-only return destinations. No external, API or arbitrary static redirects."""
from urllib.parse import urlsplit, urlencode

PAGES={'/','/legacy','/static/index.html','/static/v2/index.html'}

def safe_destination(value):
    if not isinstance(value,str) or len(value)>2048 or not value.startswith('/') or value.startswith('//'):
        return '/'
    if chr(92) in value or any(ord(c)<33 or ord(c)==127 for c in value):
        return '/'
    parsed=urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path not in PAGES:
        return '/'
    return value

def login_location(value):
    return '/login?'+urlencode({'next':safe_destination(value)})
