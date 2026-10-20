import importlib.util,json,sqlite3,tempfile,unittest
from contextlib import closing
from pathlib import Path
spec=importlib.util.spec_from_file_location('passive_shadow',Path(__file__).resolve().parents[1]/'tools/passive_shadow.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PassiveTests(unittest.TestCase):
 def roots(self,base):
  roots={r.root:base/r.root for r in m.RULES}
  for root in roots.values():root.mkdir(exist_ok=True)
  return roots
 def test_sources_unchanged_and_private_data_not_persisted(self):
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);roots=self.roots(base);state=roots['WB']/'ops_pipeline_status.json'
   state.write_text('{"state":"paused"}');secret=roots['OPS']/'config.json';secret.write_text('{"password":"never-store"}')
   bad=roots['WB']/'saved_task_box.json';bad.write_text('{"leaseToken":"never-store"}')
   before={p:p.read_bytes() for p in (state,secret,bad)}
   result=m.record(base/'out',roots)
   self.assertFalse(result['realShadowPassed']);self.assertFalse(result['comparable']);self.assertEqual(result['businessRequests'],0)
   self.assertGreater(result['errorCounts']['private_content_rejected'],0)
   for path,body in before.items():self.assertEqual(path.read_bytes(),body)
   self.assertFalse(any(b'never-store' in p.read_bytes() for p in (base/'out'/'objects').iterdir()))
 def test_database_only_opened_on_copy(self):
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);roots=self.roots(base);path=roots['OPS']/'data/ops.db';path.parent.mkdir()
   with closing(sqlite3.connect(path)) as db:db.execute('create table tasks(task_id text)');db.execute("insert into tasks values('real-task')");db.commit()
   before=path.read_bytes();result=m.record(base/'out',roots)
   self.assertEqual(path.read_bytes(),before);self.assertFalse(Path(str(path)+'-shm').exists())
   self.assertTrue(any(b'real-task' in p.read_bytes() for p in (base/'out'/'objects').iterdir()))
   self.assertGreater(result['fileCount'],0)
 def test_overlap_and_quota_fail_closed(self):
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);roots=self.roots(base)
   with self.assertRaisesRegex(ValueError,'overlap'):m.record(roots['WB']/'out',roots)
   (roots['WB']/'ops_pipeline_status.json').write_text('{"state":"paused"}')
   result=m.record(base/'out',roots,quota=1)
   self.assertTrue(result['quotaExhausted']);self.assertFalse(list((base/'out'/'objects').iterdir()))
 def test_unchanged_json_is_not_reopened_and_budget_is_explicit(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);roots=self.roots(base);state=roots['WB']/'ops_pipeline_status.json';state.write_text('{"state":"paused"}')
   m.record(base/'out',roots)
   with patch.object(m,'stable_bytes',side_effect=AssertionError('unchanged source reopened')):
    result=m.record(base/'out',roots)
   self.assertGreater(result['fileCount'],0)
   result=m.record(base/'out',roots,budget_seconds=0)
   self.assertTrue(result['budgetHit']);self.assertFalse(result['comparable'])
if __name__=='__main__':unittest.main()
