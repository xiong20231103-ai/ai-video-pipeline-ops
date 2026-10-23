import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.shadow_install_preflight import preflight, main, MAX_STORE
from tools.shadow_capture import CaptureError

ROOT = Path(__file__).resolve().parents[1]


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        live = self.root / 'live'
        live.mkdir()
        (live / 'state.json').write_text('{"ok":true}', encoding='utf-8')
        source = self.root / 'code' / 'app.py'
        source.parent.mkdir()
        source.write_text((ROOT / 'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8'), encoding='utf-8')
        self.plan = {'schema': 1, 'roots': {'workbench': str(live)},
                     'files': {'workbench/state.json': {'root': 'workbench', 'path': 'state.json'}},
                     'absent': {'workbench/missing.json': {'root': 'workbench', 'path': 'missing.json'}}}
        self.routes = [{'url': f'http://127.0.0.1:{port}' + ('/api/dashboard/summary' if port == 8765 else '/api/status'), 'port': port,
                        'path': '/api/dashboard/summary' if port == 8765 else '/api/status',
                        'key': ('receiver' if port == 8766 else 'control') + ':' + ('/api/dashboard/summary' if port == 8765 else '/api/status')}
                       for port in (8765, 8766, 18790)]
        self.args = [self.plan, source, self.root / 'new', self.root / 'old']
        self.kw = dict(approved_bytes=MAX_STORE, max_capture_bytes=192*1024*1024,
                       routes=self.routes, batch_started_before_capture=True)

    def call(self, **kw):
        return preflight(*self.args, **{**self.kw, **kw})

    def test_read_only_preflight_does_not_install_or_create_storage(self):
        before = (self.root/'live/state.json').read_bytes()
        result = self.call()
        self.assertEqual('ready-for-review', result['technicalPreflight'])
        self.assertFalse((self.root/'new').exists())
        self.assertFalse(result['installationPermitted'])
        self.assertFalse(result['dependencyClosureVerified'])
        self.assertEqual(before, (self.root/'live/state.json').read_bytes())

    def test_partial_batch_never_becomes_full_batch_or_zero_difference(self):
        result = self.call()
        self.assertEqual('resume-segment-only', result['batchCoverage'])
        self.assertFalse(result['completeBatchEligible'])
        self.assertFalse(result['realShadowPassed'])
        result = self.call(batch_started_before_capture=False)
        self.assertEqual('start-not-yet-observed', result['batchCoverage'])
        self.assertFalse(result['completeBatchEligible'])

    def test_current_size_must_fit_capture_and_quota_reserve(self):
        result = self.call(max_capture_bytes=1)
        self.assertIn('capture_input_exceeds_cycle_limit', result['blockers'])
        result = self.call(approved_bytes=100, max_capture_bytes=10)
        self.assertIn('capture_scratch_reserve_exceeds_store_limit', result['blockers'])

    def test_missing_state_and_false_absence_are_blockers(self):
        (self.root/'live/state.json').unlink()
        (self.root/'live/missing.json').write_text('{}')
        self.assertEqual(['declared_absence_now_exists', 'required_state_file_missing'], self.call()['blockers'])

    def test_three_ports_are_required(self):
        self.assertIn('three_port_coverage_missing', self.call(routes=self.routes[:2])['blockers'])

    def test_port_mismatch_private_url_and_remote_control_refused(self):
        for url in ['http://127.0.0.1:8766/api/status', 'http://example.invalid:18790/api/status',
                    'http://private-user:private-value@127.0.0.1:18790/api/status',
                    'http://127.0.0.1:18790/api/status?private=value']:
            routes = copy.deepcopy(self.routes)
            routes[-1]['url'] = url
            with self.assertRaises(CaptureError):
                self.call(routes=routes)

    def test_old_archive_not_counted_reused_or_deleted(self):
        old = self.root/'old'
        old.mkdir()
        (old/'keep').write_bytes(b'keep-original')
        result = self.call()
        self.assertFalse(result['oldStoreIncludedInNewQuota'])
        self.assertEqual(b'keep-original', (old/'keep').read_bytes())
        self.args[2] = old/'new'
        with self.assertRaises(CaptureError):
            self.call()

    def test_archive_cannot_be_capture_root_or_parent_of_capture_root(self):
        self.args[3] = self.root/'live'
        with self.assertRaises(CaptureError):
            self.call()

    def test_drive_wide_recursive_inventory_blocked(self):
        root = Path(self.root.anchor)
        self.plan['roots']['final'] = str(root)
        self.plan['trees'] = {'final': {'root': 'final', 'path': '.'}}
        # Output overlaps a drive root too, so validation must fail before walking.
        with self.assertRaises(CaptureError):
            self.call()

    def test_oversized_or_boolean_budget_refused(self):
        for n in [True, MAX_STORE+1, 0, -1]:
            with self.assertRaises(CaptureError):
                self.call(approved_bytes=n)

    def test_unreviewed_source_refused_before_any_live_import(self):
        self.args[1].write_text('raise RuntimeError("do not import me")')
        with self.assertRaisesRegex(CaptureError, 'unreviewed_capture_source'):
            self.call()

    def test_cli_errors_do_not_expose_exception_or_private_paths(self):
        with patch('tools.shadow_install_preflight.no_links', side_effect=RuntimeError('private-canary')), \
                patch('builtins.print') as output:
            self.assertEqual(1, main(['--spec', str(self.root/'private-path')]))
        report = json.loads(output.call_args.args[0])
        self.assertFalse(report['installationPermitted'])
        self.assertNotIn('private', output.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
