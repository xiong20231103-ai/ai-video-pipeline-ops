"""R5 branch evidence on private temporary fixtures, never live inventories."""
import copy
import json
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import app
import test_ops


class CleanupProtectionTests(unittest.TestCase):
    def draft_fixture(self, root):
        helper = test_ops.OpsTests()
        helper._make_capcut_draft(root, 'first', 'first', 'remote-inbox-fixture')
        helper._make_capcut_draft(root, 'second', 'second', 'remote-inbox-fixture')
        helper._write_capcut_index(root, [('first', 'first'), ('second', 'second')])

    def draft_context(self, root):
        stack = ExitStack()
        for target, value in [('CAPCUT_DRAFT_CLEANUP_BACKUP_DIR', root / '.backups'),
                              ('CAPCUT_DRAFT_CLEANUP_STATUS_PATH', root / '.status.json')]:
            stack.enter_context(patch.object(app, target, value))
        stack.enter_context(patch.object(app, 'save_control_action'))
        stack.enter_context(patch.object(app, '_capcut_draft_processes', return_value=[]))
        return stack

    def test_draft_missing_duplicate_and_recent_identity_are_protected(self):
        for case in ('missing', 'duplicate', 'recent'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.draft_fixture(root)
                meta = root / 'first' / 'draft_meta_info.json'
                value = json.loads(meta.read_text())
                if case == 'missing': value.pop('draft_id', None)
                if case == 'recent': value['tm_draft_modified'] = int(time.time() * 1000000)
                meta.write_text(json.dumps(value))
                if case == 'duplicate':
                    index = json.loads((root / 'root_meta_info.json').read_text())
                    index['all_draft_store'].append(index['all_draft_store'][0])
                    (root / 'root_meta_info.json').write_text(json.dumps(index))
                with patch.object(app, '_capcut_draft_processes', return_value=[]):
                    inventory = app._capcut_draft_inventory(root)
                item = next(item for item in inventory['items'] if item['folderName'] == 'first')
                self.assertTrue(item['protected'])

    def test_draft_unknown_requires_extra_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            helper = test_ops.OpsTests()
            helper._make_capcut_draft(root, 'manual', 'manual')
            helper._write_capcut_index(root, [('manual', 'manual')])
            with self.draft_context(root), patch('pending_delete.move') as move:
                preview = app.preview_capcut_draft_cleanup(['manual'], root=root)
                with self.assertRaises(app.HTTPException):
                    app.execute_capcut_draft_cleanup(['manual'], preview['snapshotToken'], root=root)
                move.assert_not_called()
                result = app.execute_capcut_draft_cleanup(['manual'], preview['snapshotToken'], root=root, include_unknown=True)
                self.assertEqual(1, result['removedCount'])

    def test_draft_backup_failure_never_moves_or_mutates_index(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.draft_fixture(root)
            before = (root / 'root_meta_info.json').read_bytes()
            with self.draft_context(root), patch.object(app, '_write_json_atomic', side_effect=OSError('fixture')), \
                    patch('pending_delete.move') as move:
                preview = app.preview_capcut_draft_cleanup(['first'], root=root)
                with self.assertRaises(OSError):
                    app.execute_capcut_draft_cleanup(['first'], preview['snapshotToken'], root=root)
                move.assert_not_called()
            self.assertEqual(before, (root / 'root_meta_info.json').read_bytes())

    def test_draft_partial_failure_retains_failed_index_and_rechecks_process(self):
        for case in ('move_failure', 'process_started'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                self.draft_fixture(root)
                with self.draft_context(root):
                    preview = app.preview_capcut_draft_cleanup(['first', 'second'], root=root)
                    processes = [[], [], [] if case == 'move_failure' else [{'pid': 7}]]
                    with patch.object(app, '_capcut_draft_processes', side_effect=processes), \
                            patch('pending_delete.move', side_effect=[{}, OSError('fixture')]) as move:
                        result = app.execute_capcut_draft_cleanup(['first', 'second'], preview['snapshotToken'], root=root)
                self.assertEqual('partial', result['state'])
                index = json.loads((root / 'root_meta_info.json').read_text())
                self.assertEqual(['second'], [item['draft_id'] for item in index['all_draft_store']])
                self.assertEqual(2 if case == 'move_failure' else 1, move.call_count)

    def test_audio_wait_failed_recovery_references_and_producer_recent_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.mp3'
            audio.write_bytes(b'voice')
            for state in ('Waiting', 'Failed', 'Recovering'):
                with self.subTest(state=state), patch.object(app.STORE, 'tasks', return_value=[{'audioPath': str(audio), 'taskId': 'task', 'state': state}]), \
                        patch.object(app.COLLECTOR, 'metadata', {}), patch.object(app, 'read_json_object', return_value={'tasks': {}, 'status': 'completed'}):
                    refs = app._audio_reference_inventory()
                    self.assertTrue(refs[app._path_key(audio)][0]['active'])
            with patch.object(app, '_audio_producer_processes', return_value=[{'pid': 1}]):
                inventory = app._audio_inventory(roots=[root], references={})
            self.assertTrue(inventory['items'][0]['protected'])

    def test_audio_missing_roots_and_manifest_failure_fail_closed(self):
        with patch.object(app, '_audio_reference_inventory', return_value={}), \
                patch.object(app, '_registered_audio_roots', return_value=[]), \
                patch.object(app, '_audio_producer_processes', return_value=[]):
            with self.assertRaises(app.HTTPException) as raised:
                app.preview_audio_cleanup(['id'])
            self.assertEqual(503, raised.exception.status_code)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.mp3'
            audio.write_bytes(b'voice')
            with patch.object(app, '_audio_producer_processes', return_value=[]):
                inventory = app._audio_inventory(roots=[root], references={})
            with patch.object(app, '_audio_inventory', return_value=inventory), \
                    patch.object(app, 'AUDIO_CLEANUP_BACKUP_DIR', root / 'backup'), \
                    patch.object(app, '_write_json_atomic', side_effect=OSError('fixture')), patch('pending_delete.move') as move:
                with self.assertRaises(OSError):
                    app.execute_audio_cleanup([inventory['items'][0]['audioId']], inventory['snapshotToken'])
                move.assert_not_called()

    def test_cloud_verification_every_required_field_negative(self):
        good = {'status': 'uploaded', 'fsId': 'id', 'cloudSize': 7,
                'cleanup': {'cloudVerifiedAt': 'now', 'cloudVerifiedSize': 7}}
        self.assertTrue(app._cloud_verification(good)[0])
        for field in ('status', 'fsId', 'cloudSize', 'cloudVerifiedAt', 'cloudVerifiedSize'):
            bad = copy.deepcopy(good)
            (bad['cleanup'] if field.startswith('cloudVerified') else bad).pop(field)
            with self.subTest(field=field): self.assertFalse(app._cloud_verification(bad)[0])
        bad = copy.deepcopy(good)
        bad['cloudSize'] = 8
        self.assertFalse(app._cloud_verification(bad)[0])

    def test_production_partial_protected_and_failed_index_preserves_old(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            items = []
            for name in ('safe', 'blocked', 'failed'):
                path = root / f'{name}.mp4'
                path.write_bytes(b'video')
                items.append(app._production_file_identity(path=path, root=root,
                    category='capcut_test', protected_reason='active' if name == 'blocked' else ''))
            index = root / 'index.json'
            index.write_text(json.dumps({'items': {'old-id': {'state': 'old'}}}))
            inventory = {'available': True, 'items': items, 'snapshotToken': 'snapshot'}
            with patch.object(app, '_production_file_inventory', return_value=inventory), \
                    patch.object(app, 'PRODUCTION_FILE_CLEANUP_INDEX_PATH', index), \
                    patch.object(app, 'PRODUCTION_FILE_CLEANUP_BACKUP_DIR', root / 'backups'), \
                    patch.object(app, 'PRODUCTION_FILE_CLEANUP_STATUS_PATH', root / 'status.json'), \
                    patch.object(app, 'save_control_action'), patch('pending_delete.move', side_effect=[{}, OSError('fixture')]):
                result = app.execute_production_file_cleanup([item['fileId'] for item in items], 'snapshot')
            self.assertEqual('partial', result['state'])
            self.assertEqual((1, 1, 1), (result['removedCount'], result['blockedCount'], result['failedCount']))
            records = json.loads(index.read_text())['items']
            self.assertIn('old-id', records)
            self.assertIn(items[0]['fileId'], records)
            self.assertNotIn(items[1]['fileId'], records)
            self.assertNotIn(items[2]['fileId'], records)

    def test_draft_timestamp_seconds_microseconds_and_fallback(self):
        self.assertEqual(1700000000, app._draft_timestamp(1700000000, 123))
        self.assertEqual(1700000000, app._draft_timestamp(1700000000000000, 123))
        for value in ('bad', None, -1, 0):
            self.assertEqual(123, app._draft_timestamp(value, 123))

    def test_canonical_identity_and_replenishment_aliases(self):
        aliases = {'child': 'parent'}
        self.assertEqual('parent', app._canonical_task_id({'taskId': 'child'}, aliases))
        self.assertEqual('explicit', app._canonical_task_id({'taskId': 'child', 'canonicalTaskId': 'explicit'}, aliases))
        self.assertEqual('', app._canonical_task_id({}, aliases))

    def test_audio_mixed_selection_is_all_or_reject_and_no_move(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('safe', 'active'): (root / f'{name}.mp3').write_bytes(b'audio')
            refs = {app._path_key(root / 'active.mp3'): [{'active': True, 'taskId': 'active'}]}
            with patch.object(app, '_audio_producer_processes', return_value=[]):
                inventory = app._audio_inventory(roots=[root], references=refs)
            with patch.object(app, '_audio_inventory', return_value=inventory), \
                    patch.object(app, 'AUDIO_CLEANUP_STATUS_PATH', root / 'status.json'), \
                    patch.object(app, 'save_control_action'), patch('pending_delete.move') as move:
                with self.assertRaises(app.HTTPException) as raised:
                    app.execute_audio_cleanup([item['audioId'] for item in inventory['items']], inventory['snapshotToken'])
                self.assertEqual(409, raised.exception.status_code)
                move.assert_not_called()
                self.assertTrue((root / 'safe.mp3').exists())

    def test_audio_reference_sources_deduplication_and_handoff_terminal_states(self):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'voice.mp3'
            audio.write_bytes(b'audio')
            row = {'taskId': 'id', 'audioPath': str(audio), 'state': 'Completed'}
            for state, active in [('running', True), ('completed', False),
                                  ('completed_with_errors', False), ('failed', False), ('cancelled', False)]:
                handoff = {'status': state, 'items': [row, row]}
                upload = {'tasks': {'id': row}}
                with self.subTest(state=state), patch.object(app.STORE, 'tasks', return_value=[row, row]), \
                        patch.object(app.COLLECTOR, 'metadata', {'id': row}), \
                        patch.object(app, 'read_json_object', side_effect=[handoff, upload]):
                    refs = app._audio_reference_inventory()[app._path_key(audio)]
                self.assertEqual(4, len(refs))
                self.assertEqual(active, next(item for item in refs if item['source'] == 'Fish配音交接')['active'])

    def test_audio_filters_extensions_and_snapshot_tracks_active_reference_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'voice.wav'
            audio.write_bytes(b'audio')
            (root / 'keep.txt').write_text('keep')
            with patch.object(app, '_audio_producer_processes', return_value=[]):
                before = app._audio_inventory(roots=[root], references={})
                after = app._audio_inventory(roots=[root], references={app._path_key(audio): [{'active': True}]})
            self.assertEqual(1, len(before['items']))
            self.assertNotEqual(before['snapshotToken'], after['snapshotToken'])

    def test_production_manifest_failure_prevents_every_move(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / 'video.mp4'
            target.write_bytes(b'video')
            item = app._production_file_identity(path=target, root=root, category='capcut_test')
            inventory = {'available': True, 'items': [item], 'snapshotToken': 'snapshot'}
            with patch.object(app, '_production_file_inventory', return_value=inventory), \
                    patch.object(app, 'PRODUCTION_FILE_CLEANUP_BACKUP_DIR', root / 'backup'), \
                    patch.object(app, '_write_json_atomic', side_effect=OSError('fixture')), patch('pending_delete.move') as move:
                with self.assertRaises(OSError): app.execute_production_file_cleanup([item['fileId']], 'snapshot')
                move.assert_not_called()
                self.assertTrue(target.exists())

    def test_production_registration_protections_and_path_deduplication(self):
        for case in ('normal', 'missing_project', 'not_completed', 'no_upload',
                     'shared_unverified', 'missing_prepared', 'active_test', 'duplicate_path', 'baidu'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                upload, paths = test_ops.OpsTests()._production_fixture(root)
                projects = {'parent-task': {'pipelineStatus': 'completed'}}
                uploads = [upload]
                if case == 'missing_project': projects = {}
                if case == 'not_completed': projects['parent-task']['pipelineStatus'] = 'failed'
                if case == 'no_upload': uploads = []
                if case == 'shared_unverified':
                    second = copy.deepcopy(upload)
                    second['cleanup'] = {}
                    uploads.append(second)
                if case == 'missing_prepared': upload.pop('preparedSamplePath')
                if case == 'duplicate_path': upload['localPath'] = upload['sourceVideoPath']
                config = {'download_root': str(paths['download'].parent),
                    'generation_output_root': str(paths['stitch'].parent),
                    'prepared_sample_roots': [str(paths['prepared'].parent)],
                    'capcut_test_roots': [str(paths['test'].parent)],
                    'baidu_sync_roots': [str(paths['final'].parent)] if case == 'baidu' else []}
                with patch.dict(app.CONFIG, config), patch.object(app, '_workbench_root', return_value=root / 'workbench'), \
                        patch.object(app, '_canonical_task_aliases', return_value={}), \
                        patch.object(app, '_project_status_records', return_value=projects), \
                        patch.object(app, '_upload_task_records', return_value=uploads), \
                        patch.object(app, '_production_active_projects', return_value=(set(), {})), \
                        patch.object(app, '_isolated_runtime_processes', return_value=[{'pid': 9}] if case == 'active_test' else []):
                    inventory = app._production_file_inventory()
                by_category = {item['category']: item for item in inventory['items']}
                if case in ('missing_project', 'not_completed', 'no_upload', 'shared_unverified'):
                    self.assertTrue(by_category['subtitle_output']['protected'])
                elif case == 'missing_prepared': self.assertTrue(by_category['prepared_sample']['protected'])
                elif case == 'active_test': self.assertTrue(by_category['capcut_test']['protected'])
                elif case == 'duplicate_path':
                    self.assertEqual(5, len(inventory['items']))
                    self.assertEqual(5, len({item['_path'] for item in inventory['items']}))
                elif case == 'baidu': self.assertTrue(by_category['local_final']['protected'])
                else:
                    self.assertFalse(by_category['subtitle_output']['protected'])
                    self.assertFalse(by_category['capcut_test']['defaultSelected'])

