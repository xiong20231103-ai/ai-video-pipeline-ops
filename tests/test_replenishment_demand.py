import copy
import unittest
from unittest.mock import patch
import app
from replenishment_demand import annotate_gaps


class ReplenishmentDemandTests(unittest.TestCase):
    def setUp(self):
        self.gap = dict(taskId="parent", date="11.20", project="fixture", material="board",
                        missingCount=1, status="blocked_missing_links", completed=3)
        self.child = dict(taskId="child", replenishForTaskId="parent", canonicalTaskId="parent",
                          date="11.20", project="fixture", material="board",
                          status="pending_confirmation", urls=["https://example.test/a"])

    def result(self, children):
        return annotate_gaps([self.gap], {"items": children})[0]

    def test_received_retains_real_gap_and_omits_sensitive_urls(self):
        before = copy.deepcopy(self.gap)
        result = self.result([self.child])
        self.assertEqual(result["missingCount"], 1)
        self.assertEqual(result["completed"], 3)
        self.assertEqual(result["replenishmentQueuedCount"], 1)
        self.assertEqual(result["replenishmentAdditionalNeeded"], 0)
        self.assertNotIn("urls", result)
        self.assertEqual(self.gap, before)

    def test_partial_and_duplicate_links(self):
        self.gap["missingCount"] = 3
        duplicate = dict(self.child, taskId="other-child")
        result = self.result([self.child, self.child, duplicate])
        self.assertEqual(result["replenishmentQueuedCount"], 1)
        self.assertEqual(result["replenishmentAdditionalNeeded"], 2)

    def test_failed_cancelled_and_wrong_identity_do_not_cover_gap(self):
        for extra in ({"status":"failed"}, {"status":"cancelled"},
                      {"status":"merged_into_parent"},
                      {"canonicalTaskId":"other"}, {"replenishForTaskId":"other"},
                      {"date":"11.19"}, {"project":"other"}, {"material":"other"}, {"urls":[]}):
            with self.subTest(extra=extra):
                self.assertEqual(self.result([dict(self.child, **extra)])["replenishmentAdditionalNeeded"], 1)

    def test_queue_unavailable_is_unknown_not_zero_receipts(self):
        for payload in (None, {}, {"items":[] ,"error":"unavailable"}):
            result = annotate_gaps([self.gap], payload)[0]
            self.assertEqual(result["replenishmentDemandState"], "unknown")
            self.assertNotIn("replenishmentAdditionalNeeded", result)

    def test_api_reads_same_queue_and_filters_without_mutating_collector(self):
        with patch.object(app.COLLECTOR, "project_download_statuses", [self.gap]), patch.object(
                app, "receiver_json", return_value={"items":[self.child]}) as read:
            result = app.project_gaps("11.20")
            read.assert_called_once_with("/api/tasks")
            self.assertEqual(result["items"][0]["replenishmentAdditionalNeeded"], 0)
            self.assertNotIn("replenishmentQueuedCount", self.gap)

    def test_api_receiver_failure_does_not_expose_error_details(self):
        with patch.object(app.COLLECTOR, "project_download_statuses", [self.gap]), patch.object(
                app, "receiver_json", side_effect=app.HTTPException(503, "private address")):
            result = app.project_gaps()
            self.assertEqual(result["items"][0]["replenishmentDemandState"], "unknown")
            self.assertNotIn("private address", str(result))

    def test_imported_unsettled_child_suspends_until_progress_is_known(self):
        for status in ('imported_waiting_start', 'downloading', 'running'):
            with self.subTest(status=status):
                result = self.result([dict(self.child, status=status)])
                self.assertEqual(result['replenishmentDemandState'], 'unknown')
                self.assertNotIn('replenishmentAdditionalNeeded', result)
