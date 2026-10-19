import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import pending_delete
from cleanup_tickets import CleanupTickets


class CloudCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tickets = CleanupTickets(clock=lambda: 1000)
        self.context = patch.object(app, 'CLOUD_CLEANUP_TICKETS', self.tickets)
        self.context.start()
        self.addCleanup(self.context.stop)
        self.config = patch.dict(app.CONFIG, {'pending_delete_retention_days': 3})
        self.config.start()
        self.addCleanup(self.config.stop)

    def preview(self, kind='audio'):
        with patch.object(app, 'preview_audio_cleanup', return_value={
                'snapshotToken': 'snapshot', 'deletableCount': 1, 'blockedCount': 0}):
            return app.cloud_cleanup_preview({'kind': kind, 'ids': ['server-id']})

    def test_ticket_exact_fields_single_use_and_restart(self):
        preview = self.preview()
        self.assertEqual(1120, preview['expiresAt'])
        for key, replacement in [('kind', 'drafts'), ('ids', ['another-id']),
                ('snapshotToken', 'other'), ('includeUnknown', True),
                ('confirm', 'anything'), ('expiresAt', 1121)]:
            with self.subTest(key=key), self.assertRaises(app.HTTPException):
                self.tickets.consume({**preview, key: replacement})
        with self.assertRaises(app.HTTPException):
            CleanupTickets(clock=lambda: 1000).consume(preview)
        self.tickets.consume(preview)
        with self.assertRaises(app.HTTPException):
            self.tickets.consume(preview)

    def test_expired_ticket_rejected_before_delegation(self):
        preview = self.preview()
        self.tickets.clock = lambda: 1120
        with patch.object(app, 'execute_audio_cleanup') as execute, self.assertRaises(app.HTTPException):
            app.cloud_cleanup_execute(preview)
        execute.assert_not_called()

    def test_ticket_capacity_is_bounded(self):
        for _ in range(256):
            self.tickets.issue({'kind': 'audio'})
        with self.assertRaises(app.HTTPException) as raised:
            self.tickets.issue({'kind': 'audio'})
        self.assertEqual(429, raised.exception.status_code)

    def test_ticket_clock_rollback_monotonic_expiry_and_mutable_input(self):
        ticks = [0]
        wall = [1000]
        tickets = CleanupTickets(clock=lambda: wall[0], monotonic=lambda: ticks[0])
        fields = {'ids': ['id']}
        preview = tickets.issue(fields)
        fields['ids'].append('injected')
        preview['ids'].append('injected')
        with self.assertRaises(app.HTTPException):
            tickets.consume(preview)
        preview['ids'] = ['id']
        wall[0] = 999
        with self.assertRaises(app.HTTPException):
            tickets.consume(preview)
        wall[0] = 1001
        ticks[0] = 120
        with self.assertRaises(app.HTTPException):
            tickets.consume(preview)

    def test_types_paths_limits_and_confirmation_cannot_bypass(self):
        invalid = [None, {}, {'kind': 'bogus', 'ids': []},
                   {'kind': 'audio', 'ids': ['E:\\secret.mp3']},
                   {'kind': 'audio', 'ids': ['../file']},
                   {'kind': 'audio', 'ids': [42]},
                   {'kind': 'audio', 'ids': ['id'], 'includeUnknown': 'false'},
                   {'kind': 'audio', 'ids': ['x' * 81]},
                   {'kind': 'audio', 'ids': [str(i) for i in range(2001)]},
                   {'kind': 'pending', 'ids': ['id']}]
        for value in invalid:
            with self.subTest(value=str(value)[:100]), self.assertRaises(app.HTTPException):
                app.cloud_cleanup_preview(value)

    def test_execute_delegates_existing_category_semantics(self):
        for kind, preview_fn, execute_fn in [
            ('drafts', 'preview_capcut_draft_cleanup', 'execute_capcut_draft_cleanup'),
            ('audio', 'preview_audio_cleanup', 'execute_audio_cleanup'),
            ('production', 'preview_production_file_cleanup', 'execute_production_file_cleanup')]:
            with self.subTest(kind=kind), patch.object(app, preview_fn, return_value={'snapshotToken': 'snap'}), \
                    patch.object(app, execute_fn, return_value={'state': 'partial', 'failedCount': 1}) as execute:
                preview = app.cloud_cleanup_preview({'kind': kind, 'ids': ['id']})
                result = app.cloud_cleanup_execute(preview)
                self.assertEqual('partial', result['state'])
                self.assertEqual(['id'], execute.call_args.args[0])
                self.assertEqual('snap', execute.call_args.args[1])

    def test_missing_store_source_fails_closed_audio_and_production(self):
        with patch.object(app.STORE, 'tasks', side_effect=sqlite3.OperationalError('fixture')):
            for callback in (app._audio_reference_inventory, app._production_active_projects):
                with self.subTest(function=callback.__name__), self.assertRaises(app.HTTPException) as raised:
                    callback()
                self.assertEqual(503, raised.exception.status_code)

    def test_forbidden_draft_root_is_never_eligible(self):
        for value in [r'E:\JianyingPro Drafts', r'e:\jianyingpro drafts\child',
                      'E:/JianyingPro Drafts/nested']:
            self.assertTrue(pending_delete.forbidden_source(Path(value)))
            with self.assertRaises(OSError):
                pending_delete.move(Path(value), cleanup_id='fixture', source_kind='fixture')
        self.assertFalse(pending_delete.forbidden_source(Path(r'E:\JianyingPro Drafts-other')))

    def test_pending_snapshot_change_blocks_empty_and_never_calls_purge(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'pending_delete_roots', return_value=[Path(folder)]):
            preview = app.cloud_cleanup_preview({'kind': 'pending', 'ids': []})
            (Path(folder) / 'new-record').write_text('changed')
            with patch.object(pending_delete, 'purge') as purge, self.assertRaises(app.HTTPException):
                app.cloud_cleanup_execute(preview)
            purge.assert_not_called()

    def test_pending_invalid_json_refuses_preview(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'pending_delete_roots', return_value=[Path(folder)]):
            slot = Path(folder) / 'cleanup' / 'slot'
            slot.mkdir(parents=True)
            (slot / pending_delete.RECORD_NAME).write_text('{')
            with self.assertRaises(app.HTTPException):
                app.cloud_cleanup_preview({'kind': 'pending', 'ids': []})

    def test_pending_permission_error_never_becomes_empty_inventory(self):
        def inaccessible(path, onerror=None):
            onerror(PermissionError('fixture permission denied'))
            return iter(())
        with tempfile.TemporaryDirectory() as folder, patch.object(pending_delete.os, 'walk', side_effect=inaccessible):
            with self.assertRaises(PermissionError): pending_delete._inventory(Path(folder))
            with self.assertRaises(PermissionError): pending_delete.snapshot([Path(folder)])

    def test_cleanup_handoff_missing_or_malformed_never_authorizes_orphans(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = root / 'handoff.json'
            upload = root / 'upload.json'
            upload.write_text(json.dumps({'tasks': {}}))
            for content in ('{', '[]', '{}'):
                handoff.write_text(content)
                with self.subTest(content=content), patch.dict(app.CONFIG, {
                    'voice_handoff_file': str(handoff), 'upload_status_file': str(upload)}), \
                        patch.object(app.STORE, 'tasks', return_value=[]), patch.object(app.COLLECTOR, 'metadata', {}):
                    with self.assertRaises(app.HTTPException) as raised:
                        app._audio_reference_inventory()
                    self.assertEqual(503, raised.exception.status_code)

    def test_pending_unregistered_replaced_payload_and_protected_receipt_never_purge(self):
        import json
        for change in ('extra', 'replace', 'protected_source', 'escape_target'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                area = root / '.pending'
                source = root / 'payload.mp4'
                source.write_bytes(b'video')
                with patch.object(pending_delete, 'area_root', return_value=area):
                    record = pending_delete.move(source, cleanup_id='fixture', source_kind='production')
                receipt = next(area.glob('*/*/pending-delete.json'))
                if change == 'extra': (receipt.parent / 'unregistered.txt').write_text('preserve')
                elif change == 'replace':
                    Path(record['target']).unlink()
                    Path(record['target']).write_bytes(b'different-size')
                elif change == 'protected_source':
                    record['source'] = r'E:\JianyingPro Drafts\private'
                    receipt.write_text(json.dumps(record))
                else:
                    record['target'] = str(root / 'outside')
                    receipt.write_text(json.dumps(record))
                with self.assertRaises(OSError): pending_delete.snapshot([area])
                result = pending_delete.purge([area], everything=True)
                self.assertEqual(0, result['removedCount'])
                self.assertTrue(receipt.exists())

    def test_cleanup_source_json_errors_are_strict_only_inside_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            for content in ('{', '[]'):
                path.write_text(content)
                self.assertEqual({}, app.read_json_object(path))
                with self.assertRaises(app.HTTPException) as raised:
                    app.cleanup_source_guard(app.read_json_object)(path)
                self.assertEqual(503, raised.exception.status_code)
            path.unlink()
            with self.assertRaises(app.HTTPException):
                app.cleanup_source_guard(app.read_json_object)(path)
            self.assertEqual({}, app.read_json_object(path))

    def test_draft_snapshot_detects_same_size_descendant_edit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'draft').mkdir()
            content = root / 'draft' / 'draft_content.json'
            content.write_text('AAA')
            index = root / 'root_meta_info.json'
            index.write_text('{}')
            before = app._capcut_draft_snapshot(root, index)
            content.write_text('BBB')
            self.assertNotEqual(before, app._capcut_draft_snapshot(root, index))

    def test_pending_unchanged_snapshot_delegates_under_shared_lock(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'pending_delete_roots', return_value=[Path(folder)]):
            preview = app.cloud_cleanup_preview({'kind': 'pending', 'ids': []})
            self.assertEqual('EMPTY_PENDING_DELETE_NOW', preview['confirm'])
            with patch.object(pending_delete, 'purge', return_value={'removedCount': 0}) as purge:
                app.cloud_cleanup_execute(preview)
            self.assertTrue(purge.call_args.kwargs['everything'])

    def test_capabilities_require_three_day_retention(self):
        self.assertEqual(1, app.cloud_cleanup_capabilities()['protocol'])
        with patch.dict(app.CONFIG, {'pending_delete_retention_days': 1}), self.assertRaises(app.HTTPException):
            app.cloud_cleanup_capabilities()

