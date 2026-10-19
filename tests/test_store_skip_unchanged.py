import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


def task(**overrides):
    value = {
        "task_id": "t1", "batch_id": "b1", "date_label": "10.19", "project": "p", "material": "m",
        "language": "英语", "number": "1", "sequence": 1, "video_path": "v.mp4", "audio_path": "a.mp3",
        "output_path": "o.mp4", "state": "Running", "state_text": "运行中", "error": "",
        "source_file": "s.json", "source_timestamp": 100.0, "remote_pipeline_task_id": "r1",
        "expected_task_count": 4, "phase": "export", "heartbeat_at": "h1",
    }
    value.update(overrides)
    return value


class StoreSkipUnchangedTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "ops.db"
        with patch("app.DATA_DIR", Path(folder.name)):
            self.store = app.Store(self.path)

    def row(self, table, key, value):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            return db.execute(f"SELECT * FROM {table} WHERE {key}=?", (value,)).fetchone()
        finally:
            db.close()

    def history_count(self):
        db = sqlite3.connect(self.path)
        try:
            return db.execute("SELECT count(*) FROM task_history").fetchone()[0]
        finally:
            db.close()

    def test_identical_task_is_not_rewritten(self):
        with patch("app.now_iso", return_value="first"):
            self.store.upsert_task(task())
        with patch("app.now_iso", return_value="second"):
            self.store.upsert_task(task())
        self.assertEqual("first", self.row("tasks", "task_id", "t1")["updated_at"])
        self.assertEqual(1, self.history_count())

    def test_any_changed_column_is_written(self):
        with patch("app.now_iso", return_value="first"):
            self.store.upsert_task(task())
        current = {}
        for changed in ({"heartbeat_at": "h2"}, {"output_path": "o2.mp4"}, {"source_timestamp": 101.0},
                        {"manifest_id": "m2"}, {"draft_cleanup_status": "done"}):
            current.update(changed)
            with patch("app.now_iso", return_value=str(changed)):
                self.store.upsert_task(task(**current))
            self.assertEqual(str(changed), self.row("tasks", "task_id", "t1")["updated_at"], changed)

    def test_state_change_is_written_and_recorded(self):
        self.store.upsert_task(task())
        self.store.upsert_task(task(state="Completed", state_text="完成", source_timestamp=101.0))
        self.assertEqual("Completed", self.row("tasks", "task_id", "t1")["state"])
        self.assertEqual(2, self.history_count())

    def test_older_source_still_ignored(self):
        self.store.upsert_task(task(source_timestamp=200.0, state="Completed"))
        self.store.upsert_task(task(source_timestamp=100.0, state="Running"))
        self.assertEqual("Completed", self.row("tasks", "task_id", "t1")["state"])

    def test_identical_source_health_is_not_rewritten(self):
        with patch("app.now_iso", return_value="first"):
            self.store.source_result(Path("a.json"), True, "sig")
        with patch("app.now_iso", return_value="second"):
            self.store.source_result(Path("a.json"), True, "sig")
        self.assertEqual("first", self.row("source_health", "path", "a.json")["updated_at"])

    def test_changed_source_health_is_written(self):
        with patch("app.now_iso", return_value="first"):
            self.store.source_result(Path("a.json"), True, "sig")
        with patch("app.now_iso", return_value="second"), patch.object(self.store, "event"):
            self.store.source_result(Path("a.json"), False, "sig", "boom")
        row = self.row("source_health", "path", "a.json")
        self.assertEqual(("error", "boom", "second"), (row["status"], row["error"], row["updated_at"]))


if __name__ == "__main__":
    unittest.main()
