"""Experimental write-side fixtures; kept off the read-only PR branch."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from cloud.link_evidence import Evidence
from test_link_evidence import event,image


class LinkActionsTests(unittest.TestCase):
    def test_cloud_decision_is_idempotent_and_source_isolated(self):
        with TemporaryDirectory(prefix='link-actions-fixture-') as root:
            store=Evidence(Path(root))
            identifier=store.ingest(event(image=image()))['id']
            result=store.decide(identifier,0,'confirmed','fixture-decision','user:1')
            self.assertEqual(store.decide(identifier,0,'confirmed','fixture-decision','user:1'),result)
            with self.assertRaises(ValueError):store.decide(identifier,0,'rejected','fixture-other','user:1')
            store.ingest(event(2))
            row=store.listing()['items'][0]
            self.assertEqual((row['review'],row['delivery']),('confirmed','waiting'))
            changes=store.changes('test-company')
            self.assertEqual(len(changes['items']),1)
            self.assertEqual(changes['items'][0]['data']['review'],'confirmed')
            self.assertEqual(store.changes('other-company')['items'],[])
            self.assertEqual(store.changes('test-company',changes['nextCursor'])['items'],[])
