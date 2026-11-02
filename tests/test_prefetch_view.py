import json
import tempfile
import unittest
from pathlib import Path
from prefetch_view import public_views, original_hash


class PrefetchViewTests(unittest.TestCase):
    def test_states_progress_and_no_sensitive_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / "handoff/download/prefetch"
            directory.mkdir(parents=True)
            task = {"taskId":"task-6", "batchId":"batch", "expectedCount":26, "batchSequence":6,
                    "project":"真黄颢", "material":"碳岩板", "date":"11.2", "urls":["private-url"]}
            for state in ("running", "interrupted", "finished"):
                (directory / "task-6.json").write_text(json.dumps({"taskId":"task-6", "batchId":"batch",
                    "urlCount":26, "completedOutputs":23, "state":state, "failedLinks":[{"url":"private-url"}],
                    "downloadPath":"SECRET-PATH", "token":"SECRET-TOKEN"}), encoding="utf-8")
                view = public_views(root, [task])[0]
                self.assertEqual((23,26,1), (view["completed"],view["total"],view["missingCount"]))
                self.assertEqual(state == "finished", view["canReplenish"])
                self.assertNotIn("private-url", json.dumps(view))
                self.assertNotIn("SECRET", json.dumps(view))
            self.assertEqual([], public_views(root, [{**task, "pipelineStatus":"voice_running"}]))
            self.assertEqual([], public_views(root, [{**task, "batchId":"other"}]))
            contract = root / "handoff/task_inbox/pending/task-6.json"
            contract.parent.mkdir(parents=True)
            contract.write_text(json.dumps(task), encoding="utf-8")
            (directory / "task-6.replacements.json").write_text(json.dumps({"schemaVersion":1, "taskId":"task-6",
                "contractHash":original_hash(task), "replacements":{"private-url":"new-url"}}), encoding="utf-8")
            view = public_views(root, [task])[0]
            self.assertEqual((0,1,False), (view["missingCount"],view["acceptedPending"],view["canReplenish"]))
