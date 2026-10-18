import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pending_delete


class PendingDeleteTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.area = self.root / ".pending"
        patcher = patch("pending_delete.area_root", return_value=self.area)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_file(self, name="clip.mp4", data=b"video"):
        path = self.root / "source" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def make_dir(self, name="draft"):
        path = self.root / "drafts" / name
        (path / "Resources").mkdir(parents=True)
        (path / "draft_content.json").write_text("{}", encoding="utf-8")
        (path / "Resources" / "a.png").write_bytes(b"png")
        return path

    def record(self, moved):
        return json.loads((Path(moved["target"]).parent / pending_delete.RECORD_NAME).read_text(encoding="utf-8"))

    def test_file_move_is_recorded_and_verified(self):
        source = self.make_file()
        moved = pending_delete.move(source, cleanup_id="c1", source_kind="production_file")
        self.assertFalse(source.exists())
        self.assertEqual(b"video", Path(moved["target"]).read_bytes())
        record = self.record(moved)
        self.assertEqual("moved", record["state"])
        self.assertEqual(str(source), record["source"])
        self.assertEqual(5, record["sizeBytes"])

    def test_directory_move_verifies_every_file(self):
        source = self.make_dir()
        moved = pending_delete.move(source, cleanup_id="c1", source_kind="capcut_draft")
        self.assertEqual(2, len(moved["files"]))
        self.assertTrue((Path(moved["target"]) / "Resources" / "a.png").is_file())

    def test_missing_source_is_refused(self):
        with self.assertRaises(OSError):
            pending_delete.move(self.root / "nope.mp4", cleanup_id="c1", source_kind="audio")

    def test_relative_path_is_refused(self):
        with self.assertRaises(OSError):
            pending_delete.move(Path("relative.mp4"), cleanup_id="c1", source_kind="audio")

    def test_fake_success_is_detected(self):
        source = self.make_file()
        with self.assertRaises(OSError) as error:
            pending_delete.move(source, cleanup_id="c1", source_kind="audio", rename=lambda a, b: None)
        self.assertIn("核验失败", str(error.exception))
        self.assertTrue(source.exists())
        records = list(self.area.glob(f"*/*/{pending_delete.RECORD_NAME}"))
        self.assertEqual("verify_failed", json.loads(records[0].read_text(encoding="utf-8"))["state"])

    def test_identity_mismatch_is_detected(self):
        source = self.make_file()

        def copy_then_delete(a, b):
            shutil.copyfile(a, b)
            os.remove(a)

        with patch("pending_delete._inventory", return_value=[{"relative": "", "size": 5, "fileId": -1}]):
            with self.assertRaises(OSError) as error:
                pending_delete.move(source, cleanup_id="c1", source_kind="audio", rename=copy_then_delete)
        self.assertIn("身份不符", str(error.exception))

    def test_partial_directory_move_is_detected(self):
        source = self.make_dir()

        def lose_a_file(a, b):
            os.rename(a, b)
            os.remove(Path(b) / "Resources" / "a.png")

        with self.assertRaises(OSError) as error:
            pending_delete.move(source, cleanup_id="c1", source_kind="capcut_draft", rename=lose_a_file)
        self.assertIn("缺少文件", str(error.exception))

    def test_rename_error_never_deletes(self):
        source = self.make_file()

        def locked(a, b):
            raise PermissionError(32, "in use")

        with self.assertRaises(OSError):
            pending_delete.move(source, cleanup_id="c1", source_kind="audio", rename=locked)
        self.assertTrue(source.exists())

    def test_cross_volume_is_refused(self):
        source = self.make_file()
        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            result = real_stat(path, *args, **kwargs)
            if Path(path) == source:
                return os.stat_result((result.st_mode, result.st_ino, result.st_dev + 1) + tuple(result)[3:])
            return result

        with patch("pending_delete.os.stat", side_effect=fake_stat):
            with self.assertRaises(OSError) as error:
                pending_delete.move(source, cleanup_id="c1", source_kind="audio")
        self.assertIn("跨盘", str(error.exception))
        self.assertTrue(source.exists())

    def test_same_name_items_get_separate_slots(self):
        first = self.make_file("same.mp4", b"one")
        a = pending_delete.move(first, cleanup_id="c1", source_kind="audio")
        second = self.make_file("same.mp4", b"two")
        b = pending_delete.move(second, cleanup_id="c1", source_kind="audio")
        self.assertNotEqual(a["target"], b["target"])
        self.assertEqual(b"one", Path(a["target"]).read_bytes())

    def test_source_inside_area_is_refused(self):
        inside = self.area / "x.mp4"
        inside.parent.mkdir(parents=True)
        inside.write_bytes(b"x")
        with self.assertRaises(OSError):
            pending_delete.move(inside, cleanup_id="c1", source_kind="audio")

    def test_symlink_is_refused(self):
        target = self.make_file()
        link = self.root / "link.mp4"
        try:
            os.symlink(target, link)
        except OSError:
            self.skipTest("symlink creation not permitted here")
        # Remove the link before TemporaryDirectory removes its target. On
        # Windows runners a dangling reparse path cannot be resolved reliably
        # by the production-I/O guard during recursive fixture cleanup.
        self.addCleanup(link.unlink)
        with self.assertRaises(OSError):
            pending_delete.move(link, cleanup_id="c1", source_kind="audio")

    def test_purge_respects_retention(self):
        moved = pending_delete.move(self.make_file(), cleanup_id="c1", source_kind="audio", retention_days=3)
        early = pending_delete.purge([self.area], now=datetime.now(timezone.utc) + timedelta(days=2))
        self.assertEqual(0, early["removedCount"])
        self.assertTrue(Path(moved["target"]).exists())
        late = pending_delete.purge([self.area], now=datetime.now(timezone.utc) + timedelta(days=4))
        self.assertEqual(1, late["removedCount"])
        self.assertEqual(5, late["freedBytes"])
        self.assertFalse(Path(moved["target"]).exists())

    def test_empty_now_removes_everything_verified_but_keeps_failures(self):
        pending_delete.move(self.make_file("a.mp4"), cleanup_id="c1", source_kind="audio")
        with self.assertRaises(OSError):
            pending_delete.move(self.make_file("b.mp4"), cleanup_id="c2", source_kind="audio", rename=lambda a, b: None)
        self.assertEqual(1, pending_delete.summary([self.area])["count"])
        self.assertEqual(1, pending_delete.summary([self.area])["needsReview"])
        result = pending_delete.purge([self.area], everything=True)
        self.assertEqual(1, result["removedCount"])
        self.assertEqual(1, pending_delete.summary([self.area])["needsReview"])

    def test_restore_returns_item(self):
        source = self.make_dir()
        moved = pending_delete.move(source, cleanup_id="c1", source_kind="capcut_draft")
        record_path = Path(moved["target"]).parent / pending_delete.RECORD_NAME
        pending_delete.restore(record_path)
        self.assertTrue((source / "Resources" / "a.png").is_file())
        self.assertEqual("restored", json.loads(record_path.read_text(encoding="utf-8"))["state"])

    def test_restore_refuses_to_overwrite(self):
        source = self.make_file()
        moved = pending_delete.move(source, cleanup_id="c1", source_kind="audio")
        source.write_bytes(b"new")
        with self.assertRaises(OSError) as error:
            pending_delete.restore(Path(moved["target"]).parent / pending_delete.RECORD_NAME)
        self.assertIn("拒绝覆盖", str(error.exception))
        self.assertEqual(b"new", source.read_bytes())
        self.assertTrue(Path(moved["target"]).exists())


if __name__ == "__main__":
    unittest.main()
