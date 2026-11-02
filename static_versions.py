"""Version an index response by the actual JavaScript bytes; no file writes."""
import hashlib
import re


def versioned_index(static_root):
    page = (static_root / 'index.html').read_text(encoding='utf-8')
    version = hashlib.sha256((static_root / 'app.js').read_bytes()).hexdigest()[:20]
    return re.sub(r'(/static/app\.js)(?:\?v=[^"\s>]*)?', lambda match: match[1]+'?v='+version, page)
