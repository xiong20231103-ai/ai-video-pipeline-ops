"""Synthetic roots, media and WAL only; never imports the installed Dashboard."""
from contextlib import ExitStack, closing
import copy
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from agent.core.sandbox import SandboxIO
from tools.shadow_capture import validate_plan, _inventory, DigestCache, CaptureError
from tools.shadow_sqlite_snapshot import online_backup


class CaptureV3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.drive=self.root/'drive';self.drive.mkdir()
        (self.drive/'10.22').mkdir();(self.drive/'10.22'/'video.mp4').write_bytes(b'abcdefghi')
        (self.drive/'Backup').mkdir();(self.drive/'Backup'/'ops-shadow-v3').mkdir()
        self.plan={'schema':1,'roots':{'final':str(self.drive)},
                   'shallow':{'final':{'root':'final','path':'.'}},
                   'trees':{'final/10.22':{'root':'final','path':'10.22'}},
                   'exclude':{'final/Backup/ops-shadow-v3':{'root':'final','path':'Backup/ops-shadow-v3'}},
                   'hashMetadataFiles':True}

    def inventory(self,cache=None,budget=64*1024*1024):
        _,bindings=validate_plan(self.plan,self.drive/'Backup/ops-shadow-v3/new-snapshot')
        return _inventory(self.plan,bindings,100,budget,cache)

    def test_shallow_root_excludes_outputs_without_rejecting_entire_drive(self):
        nodes,_=self.inventory()
        self.assertIn('final/10.22/video.mp4',nodes)
        self.assertIn('final/Backup',nodes)
        self.assertFalse(nodes['final/Backup']['contentsCaptured'])
        self.assertNotIn('final/Backup/ops-shadow-v3',nodes)
        bad=copy.deepcopy(self.plan);bad.pop('exclude')
        with self.assertRaisesRegex(CaptureError,'overlap'):
            validate_plan(bad,self.drive/'Backup/ops-shadow-v3/new-snapshot')

    def test_new_date_is_discovered_but_never_treated_as_empty_directory(self):
        (self.drive/'10.23').mkdir();(self.drive/'10.23'/'not-read.txt').write_text('outside approved subtree')
        nodes,_=self.inventory()
        self.assertFalse(nodes['final/10.23']['contentsCaptured'])
        self.assertNotIn('final/10.23/not-read.txt',nodes)
        scratch=self.root/'scratch';(scratch/'final/10.23').mkdir(parents=True)
        with ExitStack() as stack:
            guard=SandboxIO(scratch,stack,nodes,strict_reads=True,closed_roots=['final/10.22']).install()
            self.assertTrue((scratch/'final/10.23').is_dir())
            with self.assertRaisesRegex(PermissionError,'uncaptured_directory_contents'):
                list((scratch/'final/10.23').iterdir())
            self.assertTrue(guard.denied)

    def test_excluded_tree_cannot_be_used_as_input_or_read_as_missing(self):
        bad=copy.deepcopy(self.plan);bad['trees']['final/Backup/ops-shadow-v3']={'root':'final','path':'Backup/ops-shadow-v3'}
        with self.assertRaisesRegex(CaptureError,'excluded_capture_input'):
            validate_plan(bad,self.root/'elsewhere')
        scratch=self.root/'scratch';scratch.mkdir()
        with ExitStack() as stack:
            SandboxIO(scratch,stack,strict_reads=True,excluded_paths=['final/Backup/ops-shadow-v3']).install()
            with self.assertRaisesRegex(PermissionError,'excluded_frozen_fact'):
                (scratch/'final/Backup/ops-shadow-v3').exists()

    def test_incremental_digest_honours_round_budget_and_reuses_completed_hash(self):
        cache=DigestCache()
        first,_=self.inventory(cache,4)
        self.assertTrue(first['final/10.22/video.mp4']['hashPending'])
        self.assertEqual(4,cache.partial[str(self.drive/'10.22/video.mp4')]['offset'])
        self.inventory(cache,4)
        third,_=self.inventory(cache,4)
        self.assertEqual(hashlib.sha256(b'abcdefghi').hexdigest(),third['final/10.22/video.mp4']['contentSha256'])
        with patch.object(Path,'open',side_effect=AssertionError('unchanged media must not be read again')):
            fourth,_=self.inventory(cache,0)
        self.assertEqual(third,fourth)

    def test_changed_media_invalidates_partial_and_complete_hash(self):
        cache=DigestCache();self.inventory(cache,4)
        media=self.drive/'10.22/video.mp4';media.write_bytes(b'changed')
        result,_=self.inventory(cache,4)
        self.assertTrue(result['final/10.22/video.mp4']['hashPending'])
        self.assertEqual(4,cache.partial[str(media)]['offset'])
        result,_=self.inventory(cache,4)
        self.assertEqual(hashlib.sha256(b'changed').hexdigest(),result['final/10.22/video.mp4']['contentSha256'])

    def test_readonly_online_backup_includes_wal_and_does_not_lock_out_writer(self):
        source=self.root/'source.db';out=self.root/'snapshot.db'
        with closing(sqlite3.connect(source)) as writer:
            writer.execute('PRAGMA journal_mode=WAL');writer.execute('CREATE TABLE pairs(id PRIMARY KEY,a,b)')
            writer.executemany('INSERT INTO pairs VALUES(?,?,?)',[(n,n,n) for n in range(600)])
            writer.commit()
            # Concurrent writer commits while the read-only online backup runs.
            stop=threading.Event();progress=threading.Event();errors=[]
            def update():
                try:
                    with closing(sqlite3.connect(source,timeout=1)) as conn:
                        while not stop.is_set():
                            conn.execute('UPDATE pairs SET a=a+1,b=b+1 WHERE id=1');conn.commit();progress.set()
                except Exception as error:errors.append(type(error).__name__)
            thread=threading.Thread(target=update);thread.start()
            try:
                self.assertTrue(progress.wait(2))
                proof=online_backup(source,out,max_bytes=2*1024*1024)
            finally:stop.set();thread.join(3)
            self.assertFalse(thread.is_alive());self.assertFalse(errors)
            self.assertEqual('sqlite-online-readonly',proof['method'])
            with closing(sqlite3.connect(out)) as reader:
                self.assertEqual(600,reader.execute('SELECT count(*) FROM pairs').fetchone()[0])
                self.assertEqual(0,reader.execute('SELECT count(*) FROM pairs WHERE a<>b').fetchone()[0])
            self.assertEqual('wal',writer.execute('PRAGMA journal_mode').fetchone()[0])

    def test_backup_budget_rejection_removes_only_new_scratch(self):
        source=self.root/'source.db'
        with closing(sqlite3.connect(source)) as conn:conn.execute('CREATE TABLE keep(id)')
        before=source.read_bytes()
        with self.assertRaisesRegex(CaptureError,'byte_limit'):
            online_backup(source,self.root/'too-big.db',max_bytes=1)
        self.assertFalse((self.root/'too-big.db').exists());self.assertEqual(before,source.read_bytes())


if __name__=='__main__':unittest.main()
