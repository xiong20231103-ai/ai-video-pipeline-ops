"""Frozen ports for the fresh-digest helper; never reads media or host stat.

Static records describe one aligned capture instant. Explicit read sequences are
for ordered observations in a single snapshot, not inferred transitions.
"""
import re
import stat
import types
from pathlib import Path
from .snapshot import SnapshotError

IDENTITY = ('size', 'mtimeNs', 'ctimeNs', 'device', 'inode')
ALIGNMENT = 'single-open-fresh-sha256-v1'


def validate_identity(value):
    if (not isinstance(value, dict) or value.get('kind') != 'file'
            or any(type(value.get(k)) is not int or value[k] < 0 for k in IDENTITY)):
        raise SnapshotError('verified_final_identity_fact_required')
    return value


def validate_read(value):
    if not isinstance(value, dict):
        raise SnapshotError('verified_final_aligned_digest_required')
    before = validate_identity(value.get('before'))
    validate_identity(value.get('after'))
    opened = validate_identity(value.get('opened'))
    closed = validate_identity(value.get('closed'))
    if (any(before[k]!=opened[k] for k in IDENTITY if k!='ctimeNs')
            or any(opened[k]!=closed[k] for k in IDENTITY)):
        raise SnapshotError('verified_final_open_identity_mismatch')
    if (value.get('alignment') != ALIGNMENT
            or not isinstance(value.get('sha256'), str)
            or not re.fullmatch('[a-f0-9]{64}', value['sha256'])
            or type(value.get('readBytes')) is not int
            or value['readBytes'] != before['size']):
        raise SnapshotError('verified_final_aligned_digest_required')
    return value


class FreshHelperPorts:
    def __init__(self, io, facts, missing):
        self.io = io
        self.facts = facts
        self.missing = missing
        self.cursors = {}
        self.active = {}
        self.digest_calls = []

    def logical(self, path):
        mapped = self.io.check(path)
        # Do not call stat/resolve on host paths. Sandbox aliases translate first.
        import os
        try:
            return Path(os.path.realpath(os.path.abspath(mapped))).relative_to(self.io.root).as_posix()
        except ValueError:
            self.fail('verified_final_path_not_in_snapshot')

    def fail(self, code):
        self.missing.append(code)
        raise SnapshotError(code)

    def observation(self, logical):
        try:
            sequences = self.facts.get('verifiedFinalReadSequences', {})
            if logical in sequences:
                rows = sequences[logical]
                index = self.cursors.get(logical, 0)
                if not isinstance(rows, list) or not 1 <= len(rows) <= 10000 or index >= len(rows):
                    raise SnapshotError('verified_final_read_sequence_exhausted')
                record = rows[index]
            else:
                record = self.facts.get('verifiedFinalMedia', {}).get(logical)
            record = validate_read(record)
            node = validate_identity(self.facts.get('filesystem', {}).get(logical))
            if logical not in sequences:
                closing = validate_read(record.get('windowClose'))
                if (any(node[k] != row[k] for k in IDENTITY for row in
                        (record['before'],record['after'],closing['before'],closing['after']))
                        or node.get('contentSha256') != record['sha256']
                        or closing['sha256'] != record['sha256']):
                    raise SnapshotError('verified_final_media_fact_mismatch')
            return record
        except SnapshotError as error:
            self.fail(str(error))

    def path(self, value):
        ports = self

        class FrozenPath:
            def __init__(self):
                self.native = Path(value)
                self.record = None
                self.after_digest = False

            @property
            def name(self):
                return self.native.name

            def read_text(self, *args, **kwargs):
                # QC JSON is a declared snapshot file, guarded by SandboxIO.
                return self.native.read_text(*args, **kwargs)

            def resolve(self):
                return self.native.resolve()

            def is_file(self):
                self.stat()
                return True

            def stat(self):
                logical = ports.logical(self.native)
                if self.record is None:
                    self.record = ports.observation(logical)
                    ports.active[logical] = self
                node = self.record['after' if self.after_digest else 'before']
                return types.SimpleNamespace(
                    st_mode=stat.S_IFREG, st_size=node['size'],
                    st_mtime_ns=node['mtimeNs'], st_ctime_ns=node['ctimeNs'],
                    st_dev=node['device'], st_ino=node['inode'])

        return FrozenPath()

    def digest(self, path, size, modified, changed):
        logical = self.logical(path)
        active = self.active.get(logical)
        if active is None or active.after_digest:
            self.fail('verified_final_digest_without_before_stat')
        before = active.record['before']
        if (size, modified, changed) != tuple(before[k] for k in ('size', 'mtimeNs', 'ctimeNs')):
            self.fail('verified_final_digest_stat_mismatch')
        self.digest_calls.append(logical)
        active.after_digest = True
        self.cursors[logical] = self.cursors.get(logical, 0) + 1
        return active.record['sha256']
