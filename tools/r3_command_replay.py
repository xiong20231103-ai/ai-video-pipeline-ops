"""Offline R3 response/effect comparison with synthetic inputs only.

No application import, network client, process launcher, credential discovery
or production path input. Every write is under a newly created scratch root.
This is isolated evidence, never a completed production-batch shadow report.
"""
from __future__ import annotations

import ast
import asyncio
import contextvars
import copy
import hashlib
import io
import ipaddress
import json
import os
import re
import types
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import JSONResponse, Response

from agent.core.ordinary import OrdinaryCommands, invoke
from agent.core.oracle import LEGACY_SOURCE_SHA256, normalize_root
from agent.core.sandbox import SandboxIO


ROOT = Path(__file__).resolve().parents[1]
ROUTES = (
    ('create', '/api/controls/tasks/create'),
    ('replenish', '/api/controls/tasks/fixture/replenish'),
    ('start', '/api/controls/tasks/fixture/start'),
    ('cancel', '/api/controls/tasks/fixture/cancel'),
    ('rescan', '/api/controls/upload/rescan'),
    ('verify', '/api/controls/upload/verify-history'),
)
SCENARIOS = {
    'ok', 'http400', 'http409', 'http500', 'timeout', 'incomplete',
    'malformed', 'wrong-shape', 'invalid-json', 'invalid-body', 'untrusted',
    'no-eligible', 'already-verifying', 'worker-missing', 'startup-failed',
    'startup-timeout', 'worker-running', 'backlog', 'unexpected',
}


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 20, 12, 0, tzinfo=timezone(timedelta(hours=8))).astimezone(tz or timezone(timedelta(hours=8)))

    def astimezone(self, tz=None):
        # Legacy now_iso calls .astimezone() again. Freeze local timezone too;
        # CI's UTC and a home machine's +08:00 must replay the same source time.
        return datetime.astimezone(self, tz or timezone(timedelta(hours=8)))


class CaseEnvironment:
    """Explicit native I/O ports which can only simulate external effects."""
    def __init__(self, root, case):
        self.root = Path(root).resolve()
        if self.root.exists():
            raise ValueError('scratch_must_be_new')
        if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in self.root.parents):
            raise ValueError('scratch_link_refused')
        self.root.mkdir(parents=True)
        self.case = case
        self.scenario = case['scenario']
        self.requests, self.launches, self.events = [], [], []
        self.epoch = 1000.0
        self.runtime = self.root / 'workbench'
        self.upload = self.runtime / 'handoff' / 'upload'
        self.upload.mkdir(parents=True)
        self.pid = self.upload / 'upload_service.pid'
        for path in (self.runtime / 'upload_service.py', self.runtime / '.venv/Scripts/pythonw.exe'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('inert-fixture', encoding='utf-8')
        if self.scenario == 'worker-missing':
            (self.runtime / 'upload_service.py').unlink()
        self.alive = self.scenario == 'worker-running'
        if self.alive:
            self.pid.write_text('7001', encoding='ascii')
        status = {'tasks': {'old-video': {'status': 'uploaded', 'cleanupPolicyVersion': 1}}}
        if self.scenario == 'no-eligible':
            status = {'tasks': {'old-video': {'status': 'uploaded', 'cleanupPolicyVersion': 2, 'cleanup': {'cloudVerifiedAt': '2026-10-19T12:00:00+08:00'}}}}
        (self.upload / 'upload_status.json').write_text(json.dumps(status), encoding='utf-8')
        if self.scenario == 'already-verifying':
            (self.upload / 'historical_cloud_verify_status.json').write_text(json.dumps({'state': 'running', 'commandId': 'existing-verification', 'total': 1}), encoding='utf-8')
        if self.scenario == 'backlog':
            records = self.runtime / 'records' / 'fixture'
            records.mkdir(parents=True)
            output = self.root / 'final.mp4'
            output.write_bytes(b'fixture-media-not-real')
            (records / '第四步到第五步.json').write_text(json.dumps({'tasks': [
                {'taskId': 'ready', 'status': 'completed', 'finalOutputPath': str(output)},
                {'taskId': 'gone', 'status': 'completed', 'finalOutputPath': str(self.root / 'missing.mp4')},
                {'taskId': 'uploaded', 'status': 'completed', 'finalOutputPath': str(output)},
                {'taskId': 'uploading', 'status': 'completed', 'finalOutputPath': str(output)},
                {'taskId': 'unfinished', 'status': 'waiting', 'finalOutputPath': str(output)},
            ]}), encoding='utf-8')
            status['tasks'].update(uploaded={'status': 'uploaded'}, uploading={'status': 'uploading'})
            (self.upload / 'upload_status.json').write_text(json.dumps(status), encoding='utf-8')
        self.ports = {
            'BASE_DIR': self.root, 'CONFIG': {
                'workbench_dir': str(self.runtime),
                'receiver_status_url': 'http://receiver.fixture.invalid/api/pipeline/snapshot',
                'upload_status_file': str(self.upload / 'upload_status.json'),
                'fourth_step_handoff_dir': str(self.runtime / 'records'),
            },
            'CONTROL_ACTIONS_PATH': self.root / 'data' / 'control_actions.json',
            'DATA_DIR': self.root / 'data', 'Path': Path,
            'HTTPException': HTTPException, 'JSONResponse': JSONResponse,
            'LOCAL_PATH_PATTERN': re.compile(r'(?!)'), 'SENSITIVE_KEY_PARTS': ('token', 'password', 'secret'),
            '_CLEANUP_SOURCE_STRICT': contextvars.ContextVar('fixture_strict', default=False),
            'STORE': types.SimpleNamespace(event=lambda *args: self.events.append(list(args))),
            'datetime': FrozenDateTime, 'ipaddress': ipaddress, 'json': json, 'os': os,
            'psutil': types.SimpleNamespace(pid_exists=lambda pid: self.alive and pid == 7001,
                                           Process=lambda pid: types.SimpleNamespace(cmdline=lambda: ['pythonw.exe', 'upload_service.py']), Error=OSError),
            'subprocess': types.SimpleNamespace(Popen=self.spawn, CREATE_NO_WINDOW=0x08000000),
            'time': types.SimpleNamespace(time=lambda: self.epoch, sleep=self.sleep),
            'urllib': types.SimpleNamespace(request=types.SimpleNamespace(Request=urllib.request.Request, urlopen=self.http),
                                           error=urllib.error, parse=urllib.parse),
            'uuid': types.SimpleNamespace(uuid4=lambda: uuid.UUID(int=1)),
        }

    def sleep(self, seconds):
        self.epoch += seconds

    def spawn(self, args, **kwargs):
        self.launches.append({'args': args, **kwargs})
        if self.scenario == 'unexpected':
            raise RuntimeError('fixture-unexpected-launch-failure')
        if self.scenario not in {'startup-failed', 'startup-timeout'}:
            self.alive = True
            self.pid.write_text('7001', encoding='ascii')
        return types.SimpleNamespace(poll=lambda: 7 if self.scenario == 'startup-failed' else None)

    def http(self, request, *, timeout):
        self.requests.append({'url': request.full_url, 'method': request.get_method(),
                              'body': json.loads(request.data) if request.data else None, 'timeout': timeout})
        if self.scenario.startswith('http'):
            code = int(self.scenario[4:])
            raise urllib.error.HTTPError(request.full_url, code, 'fixture', {}, io.BytesIO(b'{"detail":"fixture-rejected"}'))
        if self.scenario == 'timeout':
            raise TimeoutError('fixture-timeout')
        if self.scenario == 'incomplete':
            import http.client
            raise http.client.IncompleteRead(b'partial', 40)
        if self.scenario == 'unexpected':
            raise RuntimeError('fixture-unexpected-http-failure')
        raw = b'{' if self.scenario == 'malformed' else b'[]' if self.scenario == 'wrong-shape' else b'{"accepted":true,"taskId":"fixture"}'
        return io.BytesIO(raw)

    def effects(self):
        files = {}
        for path in sorted(self.root.rglob('*')):
            if path.is_file():
                raw = path.read_bytes()
                try:
                    value = json.loads(raw)
                except (ValueError, UnicodeError):
                    value = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                files[path.relative_to(self.root).as_posix()] = value
        return normalize_root({'files': files, 'requests': self.requests, 'launches': self.launches,
                               'events': self.events, 'clock': self.epoch}, self.root)


def legacy_namespace(source, ports):
    if hashlib.sha256(source.encode()).hexdigest() != LEGACY_SOURCE_SHA256:
        raise ValueError('legacy_source_hash_mismatch')
    provenance = json.loads((ROOT / 'docs/migration/r3-provenance.json').read_text(encoding='utf-8'))
    names = {row['name'] for row in provenance['functions']}
    nodes = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            node = copy.deepcopy(node)
            node.decorator_list = []
            nodes.append(node)
    if {node.name for node in nodes} != names:
        raise ValueError('legacy_function_set_changed')
    tree = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    ast.fix_missing_locations(tree)
    namespace = {'__builtins__': __builtins__, '__name__': 'r3_frozen_legacy', **ports}
    exec(compile(tree, '<r3-frozen-legacy>', 'exec'), namespace)
    return namespace


def replay_case(source, case, scratch, *, candidate=False):
    if hashlib.sha256(source.encode()).hexdigest() != LEGACY_SOURCE_SHA256:
        raise ValueError('legacy_source_hash_mismatch')
    if set(case) != {'id', 'target', 'body', 'scenario'} or case['target'] not in dict(ROUTES).values() or case['scenario'] not in SCENARIOS:
        raise ValueError('undeclared_synthetic_case')
    environment = CaseEnvironment(scratch, case)
    with ExitStack() as stack:
        sandbox = SandboxIO(environment.root, stack).install()
        before = environment.effects()
        namespace = OrdinaryCommands(environment.ports, isolated=True).namespace if candidate else legacy_namespace(source, environment.ports)
        body = [] if case['scenario'] == 'invalid-body' else case['body']
        raw = b'{' if case['scenario'] == 'invalid-json' else None
        client = '203.0.113.5' if case['scenario'] == 'untrusted' else '127.0.0.1'
        value = asyncio.run(invoke(namespace, case['target'], body, client=client, raw=raw))
        response = value if isinstance(value, Response) else JSONResponse(value)
        result = normalize_root({'status': response.status_code, 'headers': dict(response.headers),
                                 'body': json.loads(response.body)}, environment.root)
        after = environment.effects()
        if sandbox.denied:
            raise ValueError('replay_attempted_live_io')
    return {'mode': 'isolated', 'response': result, 'before': before, 'after': after,
            'realShadowPassed': False, 'switchAccepted': False}


def main():
    import argparse
    import tempfile
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=ROOT / 'tests/fixtures/r3/cases.json')
    args = parser.parse_args()
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    cases = json.loads(args.cases.read_text(encoding='utf-8'))
    differences = []
    with tempfile.TemporaryDirectory(prefix='r3-replay-') as directory:
        for i, case in enumerate(cases):
            old = replay_case(source, case, Path(directory) / str(i) / 'old')
            new = replay_case(source, case, Path(directory) / str(i) / 'new', candidate=True)
            if old != new:
                differences.append(case['id'])
    print(json.dumps({'mode': 'isolated', 'cases': len(cases), 'differences': differences,
                      'realShadowPassed': False, 'switchAccepted': False}))
    return bool(differences)


if __name__ == '__main__':
    raise SystemExit(main())
