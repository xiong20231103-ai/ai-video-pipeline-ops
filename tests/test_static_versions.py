import tempfile
import unittest
from pathlib import Path
from static_versions import versioned_index


class StaticVersionTests(unittest.TestCase):
 def test_changes_when_script_bytes_change_and_never_writes_index(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   original='<script src="/static/app.js?v=old"></script>'
   (root/'index.html').write_text(original,encoding='utf-8')
   (root/'app.js').write_text('first',encoding='utf-8')
   first=versioned_index(root)
   self.assertEqual(first,versioned_index(root))
   (root/'app.js').write_text('second',encoding='utf-8')
   self.assertNotEqual(first,versioned_index(root))
   self.assertNotIn('?v=old',first)
   self.assertEqual(original,(root/'index.html').read_text(encoding='utf-8'))
