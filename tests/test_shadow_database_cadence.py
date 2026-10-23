import unittest
from tools.shadow_database_cadence import DatabaseCadence


class CadenceTests(unittest.TestCase):
    def setUp(self):
        self.now=0;self.cadence=DatabaseCadence(clock=lambda:self.now)
    def test_initial_and_ten_minute_periodic_not_every_minute(self):
        ticket=self.cadence.due();self.assertEqual('initial',ticket['reason']);self.cadence.committed(ticket)
        for minute in range(1,10):self.now=minute*60;self.assertIsNone(self.cadence.due())
        self.now=600;self.assertEqual('periodic',self.cadence.due()['reason'])
    def test_change_requests_immediate_but_budget_cooldown_is_explicit(self):
        self.cadence.committed(self.cadence.due());self.now=1
        self.cadence.changed();self.assertEqual(1,self.cadence.status()['pendingChanges'])
        self.assertIsNone(self.cadence.due());self.assertFalse(self.cadence.status()['deferredPointsComparable'])
        self.now=120;self.assertEqual('change',self.cadence.due()['reason'])
    def test_change_during_backup_is_not_cleared_by_old_ticket(self):
        self.cadence.changed();ticket=self.cadence.due();self.cadence.changed();self.cadence.committed(ticket)
        self.assertEqual(1,self.cadence.status()['pendingChanges'])
    def test_failed_backup_never_consumes_pending_ticket(self):
        self.cadence.changed();ticket=self.cadence.due()
        self.assertEqual(ticket,self.cadence.due());self.assertEqual(1,self.cadence.status()['pendingChanges'])
    def test_budget_limits_cannot_be_disabled(self):
        with self.assertRaises(ValueError):DatabaseCadence(minimum_seconds=0)
        with self.assertRaises(ValueError):DatabaseCadence(periodic_seconds=60)


if __name__=='__main__':unittest.main()
