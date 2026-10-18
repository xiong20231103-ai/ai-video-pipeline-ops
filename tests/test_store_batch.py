import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class StoreBatchTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "ops.db"
        with patch("app.DATA_DIR", Path(folder.name)):
            self.store = app.Store(self.path)
        with self.store.connection() as db:
            db.execute("CREATE TABLE probe(k TEXT PRIMARY KEY, v TEXT)")

    def rows(self):
        db = sqlite3.connect(self.path)
        try:
            return dict(db.execute("SELECT k, v FROM probe").fetchall())
        finally:
            db.close()

    def put(self, key, value="x"):
        with self.store.connection() as db:
            db.execute("INSERT OR REPLACE INTO probe VALUES(?,?)", (key, value))

    def test_outside_batch_each_block_commits(self):
        self.put("a")
        self.assertEqual({"a": "x"}, self.rows())

    def test_batch_commits_on_exit(self):
        with self.store.batch():
            self.put("a")
            self.put("b")
        self.assertEqual({"a": "x", "b": "x"}, self.rows())

    def test_failing_block_is_rolled_back_alone(self):
        with self.store.batch():
            self.put("a")
            with self.assertRaises(ValueError):
                with self.store.connection() as db:
                    db.execute("INSERT INTO probe VALUES('bad','x')")
                    raise ValueError("row failed")
            self.put("c")
        self.assertEqual({"a": "x", "c": "x"}, self.rows())

    def test_exception_leaving_batch_still_keeps_finished_rows(self):
        with self.assertRaises(RuntimeError):
            with self.store.batch():
                self.put("a")
                raise RuntimeError("scan aborted")
        self.assertEqual({"a": "x"}, self.rows())

    def test_nested_blocks_share_one_savepoint_stack(self):
        with self.store.batch():
            with self.store.connection() as outer:
                outer.execute("INSERT INTO probe VALUES('outer','x')")
                self.put("inner")
        self.assertEqual({"outer": "x", "inner": "x"}, self.rows())

    def test_commits_in_chunks_so_other_connections_see_progress(self):
        with patch.object(app.Store, "BATCH_COMMIT_ROWS", 3), patch.object(app.Store, "BATCH_COMMIT_SECONDS", 3600):
            with self.store.batch():
                for index in range(3):
                    self.put(f"k{index}")
                self.assertEqual(3, len(self.rows()))  # visible before the batch ends
                self.put("k3")
                self.assertEqual(3, len(self.rows()))  # still pending
        self.assertEqual(4, len(self.rows()))

    def test_nested_batch_is_a_no_op(self):
        with self.store.batch():
            with self.store.batch():
                self.put("a")
        self.assertEqual({"a": "x"}, self.rows())

    def test_batch_is_per_thread(self):
        import threading
        seen = []
        with self.store.batch():
            thread = threading.Thread(target=lambda: seen.append(getattr(self.store._local, "batch", None)))
            thread.start()
            thread.join()
        self.assertEqual([None], seen)


if __name__ == "__main__":
    unittest.main()
