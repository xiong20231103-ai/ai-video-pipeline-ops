"""Read cache behavior: mutable callers, atomic writers and failure visibility."""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from json_read_cache import JsonReadCache


class JsonReadCacheTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'state.json';self.path.write_text('{"rows":[{"v":1}]}',encoding='utf-8')
  self.cache=JsonReadCache()
 def test_unchanged_parses_once_and_callers_cannot_poison_cache(self):
  with patch('json_read_cache.json.loads',wraps=json.loads) as parse:
   first=self.cache.read(self.path);first['rows'][0]['v']=99
   self.assertEqual(1,self.cache.read(self.path)['rows'][0]['v'])
   self.assertEqual(1,parse.call_count)
 def test_same_size_atomic_replacement_with_restored_mtime_is_observed(self):
  self.cache.read(self.path);before=self.path.stat()
  staged=self.path.with_suffix('.tmp');staged.write_text('{"rows":[{"v":2}]}',encoding='utf-8')
  os.utime(staged,ns=(before.st_atime_ns,before.st_mtime_ns));os.replace(staged,self.path)
  self.assertEqual(2,self.cache.read(self.path)['rows'][0]['v'])
 def test_deleted_corrupt_and_unreadable_do_not_return_last_good(self):
  self.cache.read(self.path);self.path.unlink()
  with self.assertRaises(FileNotFoundError):self.cache.read(self.path)
  self.path.write_text('{broken',encoding='utf-8')
  for _ in range(2):
   with self.assertRaises(ValueError):self.cache.read(self.path)
  with patch.object(Path,'stat',side_effect=PermissionError('fixture')):
   with self.assertRaises(PermissionError):self.cache.read(self.path)
 def test_explicit_writer_invalidation_forces_reload(self):
  self.cache.read(self.path);self.cache.invalidate(self.path)
  with patch('json_read_cache.json.loads',wraps=json.loads) as parse:
   self.cache.read(self.path);self.assertEqual(1,parse.call_count)
 def test_lru_is_bounded(self):
  cache=JsonReadCache(max_entries=2)
  for n in range(8):
   path=self.path.with_name(str(n)+'.json');path.write_text('{}');cache.read(path)
  self.assertLessEqual(len(cache),2)
 def test_concurrent_readers_receive_separate_values(self):
  values=[]
  threads=[threading.Thread(target=lambda:values.append(self.cache.read(self.path))) for _ in range(8)]
  for thread in threads:thread.start()
  for thread in threads:thread.join()
  self.assertEqual(8,len(values));self.assertEqual(8,len({id(v) for v in values}))
