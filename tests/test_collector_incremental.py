import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import app


class CollectorIncrementalTests(unittest.TestCase):
 def test_unchanged_source_health_is_not_requeried_and_mutations_are_isolated(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'source.json';path.write_text('{"tasks":[{"v":1}]}')
   store=Mock();collector=app.Collector(dict(app.CONFIG),store)
   first=collector._json(path);first['tasks'][0]['v']=99
   self.assertEqual(1,collector._json(path)['tasks'][0]['v'])
   self.assertEqual(1,store.source_result.call_count)
   path.write_text('{"tasks":[{"v":2}]}')
   self.assertEqual(2,collector._json(path)['tasks'][0]['v'])
   self.assertEqual(2,store.source_result.call_count)
 def test_unchanged_completed_status_not_reprocessed_but_changed_file_is(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'sample.status.json'
   payload={'date':'11.3','tasks':[{'taskId':'one','state':'Completed'}]}
   path.write_text(json.dumps(payload));store=Mock()
   collector=app.Collector({**app.CONFIG,'capcut_handoff_dir':str(root),'simulation_enabled':False},store)
   collector.scan_statuses();first=store.upsert_task.call_count
   self.assertEqual(1,first)
   collector.scan_statuses();self.assertEqual(first,store.upsert_task.call_count)
   payload['tasks'][0]['state']='Running';path.write_text(json.dumps(payload))
   collector.scan_statuses();self.assertEqual(first+1,store.upsert_task.call_count)
 def test_failed_evidence_is_rechecked_without_stat_only_media_authorization(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'sample.status.json'
   path.write_text(json.dumps({'tasks':[{'taskId':'one','state':'Failed'}]}))
   collector=app.Collector({**app.CONFIG,'capcut_handoff_dir':str(root),'simulation_enabled':False},Mock())
   with patch.object(collector,'normalize_task',return_value={'state':'Failed'}) as normalize:
    collector.scan_statuses();collector.scan_statuses()
    self.assertEqual(2,normalize.call_count)
 def test_replacement_between_read_and_memo_cannot_pin_old_status(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);path=root/'sample.status.json'
   payload={'tasks':[{'taskId':'one','state':'Completed'}]};path.write_text(json.dumps(payload))
   store=Mock();collector=app.Collector({**app.CONFIG,'capcut_handoff_dir':str(root),'simulation_enabled':False},store)
   read=collector._json;changed=False
   def replace_after_read(source):
    nonlocal changed
    value=read(source)
    if source==path and not changed:
     changed=True;payload['tasks'][0]['state']='Running';path.write_text(json.dumps(payload))
    return value
   with patch.object(collector,'_json',side_effect=replace_after_read):
    collector.scan_statuses();collector.scan_statuses()
   self.assertEqual('Running',store.upsert_task.call_args.args[0]['state'])
