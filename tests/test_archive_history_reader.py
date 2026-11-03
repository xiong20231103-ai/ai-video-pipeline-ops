import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from archive_history_reader import archived_dates, archived_handoffs


class ArchiveHistoryReaderTests(unittest.TestCase):
 def test_verified_history_is_queryable_without_becoming_live(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);operation=root/'files/fixture';data=operation/'data'
   source=data/'交接记录/9.1/第四步到第五步.json';source.parent.mkdir(parents=True)
   raw=json.dumps({'date':'9.1','tasks':[{'taskId':'archive-child','remotePipelineTaskId':'owner',
       'status':'completed','project':'项目','material':'材料'}]}).encode()
   source.write_bytes(raw)
   entry={'path':str(source.relative_to(data)),'kind':'handoff','dates':['9.1'],
          'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mtimeNs':1_700_000_000_000_000_000}
   (operation/'index.json').write_text(json.dumps({'schemaVersion':1,'archiveData':str(data),'files':[entry]}),encoding='utf-8')
   self.assertEqual({'9.1'},archived_dates(root));self.assertEqual(1,len(archived_handoffs(root,'9.1')))
   with patch.dict(app.CONFIG,history_archive_root=str(root)),patch.object(app.STORE,'tasks',return_value=[]),patch.object(app.COLLECTOR,'metadata',{}):
    self.assertEqual([],app.production_capcut_tasks())
    historical=app.production_capcut_tasks('9.1')
    self.assertEqual(['archive-child'],[row['task_id'] for row in historical])
    self.assertEqual({},app.COLLECTOR.metadata)
    self.assertEqual([],app.production_capcut_tasks())
   source.write_bytes(b'{}');self.assertEqual([],archived_handoffs(root,'9.1'))
   (operation/'rolled-back.json').write_text('{}');self.assertEqual(set(),archived_dates(root))
 def test_paths_outside_archive_and_invalid_indexes_are_rejected(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);operation=root/'files/fixture';operation.mkdir(parents=True)
   index=operation/'index.json'
   for value in ([],{'schemaVersion':1,'archiveData':str(root.parent),'files':[]}):
    index.write_text(json.dumps(value));self.assertEqual(set(),archived_dates(root))
   self.assertEqual([],archived_handoffs(root,'../../escape'))
