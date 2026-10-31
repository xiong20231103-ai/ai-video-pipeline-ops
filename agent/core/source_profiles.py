"""Closed source allowlist: no caller-supplied baseline or permissive fallback."""
import hashlib
from pathlib import Path
from .snapshot import SnapshotError

F78 = 'f4d754cd86c524933d3f87da1006167c2fd698e288fcda09992115dc0e1c044e'
PR49 = '9b3ebded024ffa5d9db1662b2fe9fd2e3348e0630efd2f24d1c6bdd61f16d84a'
PR49_HELPER = '69b8b086e0502c506e75f1644fe2a3d28c8bac94c99c2b54870c2205fb9199e0'
FRESH_HELPER = '57631ede4f2199db025163010e12dfe8ecc493784979194b87c4ead83b2aa818'
D6A7211_CRLF = 'a02d25a6787e0b33725695d616a595396aa4280ed4c9049f309ad1f3b9d6e8b7'
# PR49 plus one route fix: /api/subtitle-verification/current returns an empty
# inventory instead of a 500 when no task box is active (between batches).
SUBTITLE_IDLE = '232545fa6c1f72f7a7c98635348d94f49782973024dd087fae6b2b62653a9ee0'
SUBTITLE_IDLE_CRLF = 'f07466fdaf313ebf49419527769f355dbf1da6bdc0de8c52a18ba7813728638f'
# SUBTITLE_IDLE with a startup-only native console guard. The frozen replay
# excludes module-level startup branches; business AST equality is tested.
PIP_CONSOLE = '91549e1a9a61ec4fc31ce9c32df6e81b9674b118539c684582b00f14f90b808c'
PIP_CONSOLE_CRLF = '8c48b305936c0f90da80402a03180f307ca8710078e210901047a9f4a81f7eb2'
# Reviewed a93f446 / PR #81: exact CapCut image names, never executor argv.
CAPCUT_IMAGE = 'd03364c65a48b22ed3da6131d048e015e3a72421680d95641c7dd00bec1fbb9e'
CAPCUT_IMAGE_CRLF = 'b2ac1ba5bd1b08eeab08e3bd1025717c38d6f9892908f2594ae39fbf7ff224ed'
PR49_BEHAVIOR = frozenset({PR49, D6A7211_CRLF, SUBTITLE_IDLE, SUBTITLE_IDLE_CRLF, PIP_CONSOLE, PIP_CONSOLE_CRLF, CAPCUT_IMAGE, CAPCUT_IMAGE_CRLF})
PROFILES = {CAPCUT_IMAGE:'pr81-capcut-image', CAPCUT_IMAGE_CRLF:'pr81-capcut-image-crlf', F78:'f78db5a', PR49:'pr49-verified-final',
            D6A7211_CRLF:'d6a7211-crlf-pr49-behavior',
            SUBTITLE_IDLE:'pr49-subtitle-idle', SUBTITLE_IDLE_CRLF:'pr49-subtitle-idle-crlf',
            PIP_CONSOLE:'pr49-pip-console', PIP_CONSOLE_CRLF:'pr49-pip-console-crlf'}
SOURCE_HELPER_PROFILES = {
    (source, helper): name
    for source in PR49_BEHAVIOR
    for helper, name in ((PR49_HELPER, 'pr49-cached-helper'),
                         (FRESH_HELPER, 'pr49-fresh-identity-helper'))
}

def read_source(path):
    # Preserve the byte identity: universal newline translation would hide a
    # one-byte CR deletion and silently relabel a modified source as PR49.
    return Path(path).read_bytes().decode('utf-8')

def legacy_verified_final_source(helper_hash=PR49_HELPER):
    names={PR49_HELPER:'legacy-verified-final-pr49.txt',
           FRESH_HELPER:'legacy-verified-final-fresh.txt'}
    if helper_hash not in names:raise SnapshotError('source_dependency_hash_mismatch')
    helper=Path(__file__).resolve().parents[2]/'contracts'/names[helper_hash]
    source=helper.read_text(encoding='utf-8-sig')
    if hashlib.sha256(source.encode()).hexdigest()!=helper_hash:
        raise SnapshotError('source_dependency_hash_mismatch')
    return source


def reviewed_helper(source_hash, facts):
    helper=facts.get('captureProof',{}).get('helperHashes',{}).get('verified_final.py',PR49_HELPER)
    if (source_hash,helper) not in SOURCE_HELPER_PROFILES:
        raise SnapshotError('source_dependency_hash_mismatch')
    return helper


def validate_fresh_helper_identity(identity):
    from .verified_final_replay import validate_identity
    validate_identity(identity)
    source=legacy_verified_final_source(FRESH_HELPER)
    allowed={hashlib.sha256(body).hexdigest():len(body) for body in
             (source.encode(),source.replace('\n','\r\n').encode())}
    if identity.get('sha256') not in allowed or identity['size']!=allowed[identity['sha256']]:
        raise SnapshotError('source_dependency_byte_hash_mismatch')


def verify_source(source, snapshot):
    digest=hashlib.sha256(source.encode()).hexdigest()
    if digest not in PROFILES or snapshot.manifest['legacySha256'] != digest:
        raise SnapshotError('legacy_source_hash_mismatch')
    facts=snapshot.manifest.get('facts',{})
    helper_hash=reviewed_helper(digest,facts) if digest in PR49_BEHAVIOR else None
    if helper_hash:
        legacy_verified_final_source(helper_hash)
    if helper_hash==FRESH_HELPER:
        validate_fresh_helper_identity(facts.get('captureProof',{}).get('helperIdentities',{}).get('verified_final.py'))
    for name,expected in snapshot.manifest.get('facts',{}).get('captureProof',{}).get('helperHashes',{}).items():
        if name not in {'pending_delete.py','cleanup_tickets.py','verified_final.py'}:raise SnapshotError('undeclared_source_dependency')
        source=legacy_verified_final_source(helper_hash) if helper_hash and name=='verified_final.py' else (Path(__file__).resolve().parents[2]/name).read_text(encoding='utf-8-sig')
        if hashlib.sha256(source.encode()).hexdigest()!=expected:raise SnapshotError('source_dependency_hash_mismatch')
        if helper_hash==FRESH_HELPER and name!='verified_final.py':
            from .verified_final_replay import validate_identity
            identity=facts.get('captureProof',{}).get('helperIdentities',{}).get(name)
            validate_identity(identity)
            allowed={hashlib.sha256(raw).hexdigest():len(raw) for raw in
                     (source.encode(),source.replace('\n','\r\n').encode())}
            if identity.get('sha256') not in allowed or identity['size']!=allowed[identity['sha256']]:
                raise SnapshotError('source_dependency_byte_hash_mismatch')
    return digest
