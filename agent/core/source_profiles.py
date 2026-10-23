"""Closed source allowlist: no caller-supplied baseline or permissive fallback."""
import hashlib
from pathlib import Path
from .snapshot import SnapshotError

F78 = 'f4d754cd86c524933d3f87da1006167c2fd698e288fcda09992115dc0e1c044e'
PR49 = '9b3ebded024ffa5d9db1662b2fe9fd2e3348e0630efd2f24d1c6bdd61f16d84a'
PR49_HELPER = '69b8b086e0502c506e75f1644fe2a3d28c8bac94c99c2b54870c2205fb9199e0'
D6A7211_CRLF = 'a02d25a6787e0b33725695d616a595396aa4280ed4c9049f309ad1f3b9d6e8b7'
PR49_BEHAVIOR = frozenset({PR49, D6A7211_CRLF})
PROFILES = {F78:'f78db5a', PR49:'pr49-verified-final',
            D6A7211_CRLF:'d6a7211-crlf-pr49-behavior'}

def read_source(path):
    # Preserve the byte identity: universal newline translation would hide a
    # one-byte CR deletion and silently relabel a modified source as PR49.
    return Path(path).read_bytes().decode('utf-8')

def legacy_verified_final_source():
    helper=Path(__file__).resolve().parents[2]/'contracts/legacy-verified-final-pr49.txt'
    source=helper.read_text(encoding='utf-8-sig')
    if hashlib.sha256(source.encode()).hexdigest()!=PR49_HELPER:
        raise SnapshotError('source_dependency_hash_mismatch')
    return source


def verify_source(source, snapshot):
    digest=hashlib.sha256(source.encode()).hexdigest()
    if digest not in PROFILES or snapshot.manifest['legacySha256'] != digest:
        raise SnapshotError('legacy_source_hash_mismatch')
    if digest in PR49_BEHAVIOR:
        legacy_verified_final_source()
    for name,expected in snapshot.manifest.get('facts',{}).get('captureProof',{}).get('helperHashes',{}).items():
        if name not in {'pending_delete.py','cleanup_tickets.py','verified_final.py'}:raise SnapshotError('undeclared_source_dependency')
        source=legacy_verified_final_source() if digest in PR49_BEHAVIOR and name=='verified_final.py' else (Path(__file__).resolve().parents[2]/name).read_text(encoding='utf-8-sig')
        if hashlib.sha256(source.encode()).hexdigest()!=expected:raise SnapshotError('source_dependency_hash_mismatch')
    return digest
