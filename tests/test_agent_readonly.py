import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from agent.readonly import Ledger,ReadOnlyAgent,SingleInstance,NoRedirect,HOME_HOST
from agent.polling import PollSchedule,periods
from datetime import date
import io
import urllib.error

class ReadOnlyAgentTests(unittest.TestCase):
    def test_ledger_versions_persist_and_canonicalize_effective_queries(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'agent.db'; ledger=Ledger(path)
            ledger.enqueue('/api/dashboard?date=10.16&batchId=b',200,{'state':'first'})
            Ledger(path).enqueue('/api/dashboard?batchId=b&date=10.16',200,{'state':'later'})
            payload=ledger.next(); self.assertEqual(2,payload['version']); self.assertEqual('later',payload['body']['state'])
            ledger.acknowledge(payload['target'],1); self.assertIsNotNone(ledger.next())
            ledger.acknowledge(payload['target'],2); self.assertIsNone(ledger.next())
    def test_304_compaction_never_drops_unacknowledged_base(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db'); body={'updatedAt':'frozen','state':'running'}
            ledger.enqueue('/api/dashboard/summary',200,body,'fixture-etag')
            ledger.enqueue('/api/dashboard/summary',304,body,'fixture-etag')
            self.assertEqual(200,ledger.next()['status']); self.assertEqual(body,ledger.next()['body'])
    def test_local_clock_delay_is_preserved_without_cloud_clock_comparison(self):
        with TemporaryDirectory() as folder:
            ledger=Ledger(Path(folder)/'agent.db')
            with patch('agent.readonly.time.time',return_value=100),patch('agent.readonly.time.monotonic',return_value=500):
                ledger.enqueue('/api/dashboard',200,{})
            with patch('agent.readonly.time.time',return_value=3700),patch('agent.readonly.time.monotonic',return_value=4100):
                self.assertEqual(3600,ledger.next()['captureAgeSeconds'])
    def test_single_instance_prevents_second_home_executor(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'agent.lock'
            with SingleInstance(path):
                with self.assertRaises(RuntimeError):
                    with SingleInstance(path): pass
    def test_agent_only_uses_fixed_loopback_home_routes(self):
        with TemporaryDirectory() as folder:
            instance=ReadOnlyAgent('https://fixture.ts.net','inert-fixture-value',folder)
            for target in ['https://foreign.invalid/api/dashboard','/api/controls/tasks/create','/api/controls/testing/reset']:
                with self.assertRaises(ValueError): instance.home(target)
            with self.assertRaises(ValueError): ReadOnlyAgent('http://fixture.ts.net','inert-fixture-value',folder)

    def test_active_and_idle_hourly_request_budgets_include_receiver_health(self):
        active=periods(True,date(2026,10,17)); idle=periods(False,date(2026,10,17))
        self.assertEqual(53,len(active)); self.assertEqual(11,len(idle))
        self.assertEqual(42,sum('?date=' in target for target in active))
        self.assertFalse(any('?date=' in target for target in idle))
        self.assertEqual(1752,sum(3600/period for period in active.values())+3600/active['/api/health'])
        self.assertEqual(666,sum(3600/period for period in idle.values())+3600/idle['/api/health'])

    def test_viewer_lease_uses_local_monotonic_time_and_expires_without_cloud(self):
        now=[1000.0]; schedule=PollSchedule(clock=lambda:now[0])
        self.assertFalse(schedule.active())
        schedule.update_viewer({'viewerActive':True,'viewerLeaseSeconds':120})
        now[0]+=119; self.assertTrue(schedule.active())
        now[0]+=1; self.assertFalse(schedule.active())
        for value in [float('nan'),float('inf'),121,-1,'120',True]:
            schedule.update_viewer({'viewerActive':True,'viewerLeaseSeconds':value})
            self.assertFalse(schedule.active())

    def test_idle_transition_stops_history_and_recomputes_full_summary_due_times(self):
        now=[0.0]; schedule=PollSchedule(clock=lambda:now[0]); day=date(2026,10,17)
        schedule.update_viewer({'viewerActive':True,'viewerLeaseSeconds':120})
        for target in periods(True,day): schedule.completed(target)
        now[0]=5; self.assertEqual('/api/dashboard/summary',schedule.next(day)); schedule.completed('/api/dashboard/summary')
        schedule.update_viewer({'viewerActive':False,'viewerLeaseSeconds':0})
        now[0]=30; self.assertIsNone(schedule.next(day))
        now[0]=60; self.assertNotEqual('/api/dashboard',schedule.next(day))
        for target in periods(False,day): schedule.completed(target)
        now[0]=600
        seen=[]
        while (target:=schedule.next(day)) is not None:
            seen.append(target); schedule.completed(target)
        self.assertFalse(any('?date=' in target for target in seen))
        self.assertNotIn('/api/dashboard',seen)
        now[0]=660; self.assertIn('/api/dashboard',periods(False,day))
        seen=[]
        while (target:=schedule.next(day)) is not None: seen.append(target); schedule.completed(target)
        self.assertIn('/api/dashboard',seen)

    def test_active_history_uses_actual_dates_across_year_boundary(self):
        active=periods(True,date(2027,1,2))
        self.assertIn('/api/dashboard?date=12.31',active)
        self.assertIn('/api/dashboard?date=1.2',active)
        self.assertNotIn('/api/dashboard?date=12.19',active)

    def test_cold_history_backlog_cannot_starve_current_summary(self):
        now=[0.0]; schedule=PollSchedule(clock=lambda:now[0]); day=date(2026,10,17)
        schedule.update_viewer({'viewerActive':True,'viewerLeaseSeconds':120})
        for target in periods(False,day): schedule.completed(target)
        self.assertIn('?date=',schedule.next(day))
        now[0]=5
        self.assertEqual('/api/dashboard/summary',schedule.next(day))

    def test_no_home_polling_before_first_authenticated_cloud_connection(self):
        with TemporaryDirectory() as folder:
            instance=ReadOnlyAgent('https://fixture.ts.net','inert-fixture-value',folder)
            def finish_wait(*args): instance.stop.set(); return True
            with patch.object(instance.stop,'wait',side_effect=finish_wait),patch.object(instance,'collect') as collect:
                instance.collection_loop()
                collect.assert_not_called()

    def test_home_get_is_explicit_fixed_address_no_body_and_metrics_capture_failures(self):
        with TemporaryDirectory() as folder:
            instance=ReadOnlyAgent('https://fixture.ts.net','inert-fixture-value',folder)
            response=io.BytesIO(b'{"ok":true}'); response.status=200; response.headers={}
            with patch.object(instance.transport,'open',return_value=response) as opener:
                self.assertEqual(200,instance.home('/api/dashboard')[0])
                request=opener.call_args.args[0]
                self.assertEqual('GET',request.get_method()); self.assertIsNone(request.data)
                self.assertEqual('http://'+HOME_HOST+':8765/api/dashboard',request.full_url)
                self.assertIsNone(request.get_header('Authorization'))
            with patch.object(instance.transport,'open',side_effect=OSError('fixture-read-failure')):
                with self.assertRaises(OSError): instance.home('/api/health',8766)
            with instance.ledger.db() as db:
                rows=db.execute('SELECT * FROM request_stats').fetchall()
            self.assertEqual(2,sum(row['count'] for row in rows)); self.assertEqual(1,sum(row['failures'] for row in rows))
            self.assertTrue(all(row['mode']=='idle' for row in rows))
            for port,target in [(80,'/api/dashboard'),(8766,'/api/dashboard')]:
                with self.assertRaises(ValueError): instance.home(target,port)
            self.assertIsNone(NoRedirect().redirect_request(None,None,302,'fixture',{},'https://foreign.invalid'))

    def test_idle_history_can_still_be_fetched_on_demand_and_deduplicated(self):
        with TemporaryDirectory() as folder:
            instance=ReadOnlyAgent('https://fixture.ts.net','inert-fixture-value',folder)
            with patch.object(instance,'home',return_value=(200,{'state':'fixture'},'')) as home:
                instance.collect('/api/dashboard?date=10.16',reason='on-demand')
                instance.collect('/api/dashboard?date=10.16',reason='on-demand')
                self.assertEqual(1,home.call_count); self.assertEqual('on-demand',home.call_args.kwargs['reason'])
                self.assertIsNotNone(instance.ledger.source('/api/dashboard?date=10.16'))
