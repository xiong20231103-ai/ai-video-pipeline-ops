import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from core.pip_status import public_capcut_session
class Tests(unittest.TestCase):
 def setUp(self):self.row={'mode':'pip','executorOnline':True,'heartbeatEpoch':1000,'sessionId':2,'state':'busy','nonce':'secret','path':'private'}
 def test_allowlist(self):
  r=public_capcut_session(self.row,now=1001,workbench_fresh=True);self.assertTrue(r['executorOnline']);self.assertNotIn('nonce',r);self.assertNotIn('path',r)
 def test_age(self):
  for now in (999,1016):self.assertFalse(public_capcut_session(self.row,now=now,workbench_fresh=True)['executorOnline'])
 def test_stale_workbench(self):self.assertFalse(public_capcut_session(self.row,now=1001,workbench_fresh=False)['executorOnline'])
 def test_main_default(self):self.assertEqual(public_capcut_session(None,now=1001,workbench_fresh=True)['mode'],'main')
 def test_malformed(self):
  for kw in ({'sessionId':True},{'sessionId':0},{'heartbeatEpoch':float('nan')},{'executorOnline':'true'},{'state':'offline'}):self.assertFalse(public_capcut_session(dict(self.row,**kw),now=1001,workbench_fresh=True)['executorOnline'])
if __name__=='__main__':unittest.main()
