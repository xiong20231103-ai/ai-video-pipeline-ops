import copy,hashlib,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from agent.core.replay import make_fixture
from tools.shadow_store import put_snapshot,materialize_snapshot,usage
from tools.shadow_capture import CaptureError
ROOT=Path(__file__).resolve().parents[1]
class ChunkStoreTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);source=(ROOT/'contracts/legacy-app-f78db5a.txt').read_text(encoding='utf-8');profile=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))['running'];self.profile=profile;self.source=source;self.snap=make_fixture(profile,source,self.root/'input');self.store=self.root/'store'
 def test_exact_roundtrip_dedup_and_hard_cap(self):
  first=put_snapshot(self.snap,self.store,approved_total_bytes=1024*1024);before=usage(self.store);second=put_snapshot(self.snap,self.store,approved_total_bytes=1024*1024)
  self.assertTrue(second['deduplicated']);self.assertEqual(0,second['newBytes']);self.assertEqual(before,usage(self.store));restored=materialize_snapshot(self.store,first['sourceIdentity'],self.root/'restored');self.assertEqual(self.snap.manifest,restored.manifest)
  for name in self.snap.manifest['files']:self.assertEqual(self.snap.read(name),restored.read(name))
 def test_insufficient_space_preserves_previous_evidence_and_publishes_no_index(self):
  identity=put_snapshot(self.snap,self.store,approved_total_bytes=1024*1024)['sourceIdentity'];before={p.relative_to(self.store).as_posix():p.read_bytes() for p in self.store.rglob('*') if p.is_file()};profile=copy.deepcopy(self.profile);profile['files']['workbench/new.json']={'fixture':'additional'};new=make_fixture(profile,self.source,self.root/'new')
  with self.assertRaisesRegex(CaptureError,'quota_exhausted'):put_snapshot(new,self.store,approved_total_bytes=usage(self.store)+1)
  self.assertEqual(before,{p.relative_to(self.store).as_posix():p.read_bytes() for p in self.store.rglob('*') if p.is_file()});materialize_snapshot(self.store,identity,self.root/'restored')
 def test_retained_old_roots_count_towards_explicit_budget(self):
  old=self.root/'old-evidence';old.mkdir();(old/'retained.bin').write_bytes(b'x'*2000)
  with self.assertRaisesRegex(CaptureError,'quota_exhausted'):put_snapshot(self.snap,self.store,approved_total_bytes=1000,retained_roots=[old])
  self.assertEqual(2000,(old/'retained.bin').stat().st_size)
 def test_corrupt_chunk_and_invalid_identity_refuse_no_partial_restore(self):
  identity=put_snapshot(self.snap,self.store,approved_total_bytes=1024*1024)['sourceIdentity'];key=next((self.store/'objects').iterdir());key.write_bytes(b'corrupt')
  with self.assertRaisesRegex(CaptureError,'corrupt'):materialize_snapshot(self.store,identity,self.root/'restore')
  self.assertFalse((self.root/'restore').exists())
  with self.assertRaisesRegex(CaptureError,'identity_invalid'):materialize_snapshot(self.store,'../escape',self.root/'restore')
 def test_busy_writer_does_not_delete_someone_elses_lock(self):
  self.store.mkdir();(self.store/'.writer.lock').write_text('fixture-owner')
  with self.assertRaisesRegex(CaptureError,'writer_busy'):put_snapshot(self.snap,self.store,approved_total_bytes=1024*1024)
  self.assertEqual('fixture-owner',(self.store/'.writer.lock').read_text())
