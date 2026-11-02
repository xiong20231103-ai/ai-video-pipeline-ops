import tempfile
import unittest
from pathlib import Path
from cloud.notification_facts import prefetch_facts
from cloud.notification_ledger import NotificationLedger
from cloud.store import Store


class PrefetchNotificationTests(unittest.TestCase):
 def test_once_per_gap_and_silent_close(self):
  with tempfile.TemporaryDirectory() as folder:
   store=Store(Path(folder)/'cloud.db')
   ledger=NotificationLedger(store)
   ledger.initialize([('prefetch',1,[])])
   view={'taskId':'task-6','batchId':'batch','project':'真黄颢','material':'碳岩板','productionDate':'11.2',
         'sequence':6,'state':'finished','canReplenish':True,'missingCount':3,'total':26,'gapFingerprint':'a'*64}
   facts=prefetch_facts({'prefetchViews':[view]})
   ledger.observe('prefetch',2,facts)
   ledger.observe('prefetch',3,facts)
   ledger.observe('prefetch',4,[])
   ledger.observe('prefetch',5,facts)
   with store.db() as db:
    self.assertEqual(1,db.execute('SELECT count(*) FROM notification_events').fetchone()[0])
    self.assertEqual(0,db.execute("SELECT count(*) FROM notification_events WHERE kind='recovered'").fetchone()[0])
    self.assertEqual(0,db.execute('SELECT active FROM notification_episodes').fetchone()[0])
    self.assertEqual('closed',db.execute('SELECT state FROM notification_events').fetchone()[0])
   changed=prefetch_facts({'prefetchViews':[{**view,'gapFingerprint':'b'*64}]})
   ledger.observe('prefetch',6,changed)
   with store.db() as db:self.assertEqual(2,db.execute('SELECT count(*) FROM notification_events').fetchone()[0])
 def test_running_project_and_unverified_snapshot_are_not_gap_alerts(self):
  self.assertEqual([],prefetch_facts({'prefetchViews':[{'state':'running'}]}))
  with self.assertRaises(ValueError):prefetch_facts({})
