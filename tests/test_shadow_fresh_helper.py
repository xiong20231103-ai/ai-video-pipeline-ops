"""Synthetic fresh-helper observations only; no production files or requests."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from agent.core.oracle import Oracle
from agent.core.replay import make_fixture
from agent.core.collection import CollectionSession
from agent.core.source_profiles import FRESH_HELPER, PR49_HELPER, D6A7211_CRLF, read_source
from agent.core.snapshot import SnapshotError
from agent.core.verified_final_replay import ALIGNMENT
from tools.shadow_capture import aligned_capture, CaptureError

ROOT = Path(__file__).resolve().parents[1]


class FreshHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = read_source(ROOT/'contracts/legacy-app-d6a7211-crlf.txt')
        self.profile = json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))['running']
        self.profile['facts']['scan'] = False
        raw = (ROOT/'contracts/legacy-verified-final-fresh.txt').read_text(encoding='utf-8').encode()
        self.identity = {'kind':'file', 'size':len(raw), 'mtimeNs':17, 'ctimeNs':18,
                         'device':7, 'inode':8, 'sha256':hashlib.sha256(raw).hexdigest()}
        self.node = {'kind':'file', 'size':100, 'mtimeNs':1700000000000000000,
                     'ctimeNs':1700000000000000001, 'device':2, 'inode':42}
        self.record = {'alignment':ALIGNMENT, 'before':dict(self.node), 'after':dict(self.node),
                       'opened':dict(self.node),'closed':dict(self.node),
                       'sha256':'a'*64, 'readBytes':100}
        self.record['windowClose']=copy.deepcopy(self.record)
        self.profile['facts'].update(
            filesystem={'final':{'kind':'directory','size':0,'mtimeNs':0},
                        'final/video.mp4':{**self.node, 'contentSha256':'a'*64}},
            verifiedFinalMedia={'final/video.mp4':copy.deepcopy(self.record)},
            captureProof={'helperHashes':{'verified_final.py':FRESH_HELPER},
                          'helperIdentities':{'verified_final.py':self.identity}})
        self.profile['files']['reports/qc.json'] = {'status':'passed','taskId':'child',
            'canonicalTaskId':'parent','fileName':'video.mp4','fileSize':100,'sha256':'a'*64}

    def snapshot(self, name='snapshot'):
        return make_fixture(self.profile,self.source,self.root/name)

    def metadata(self, env):
        return {'taskId':'child','remotePipelineTaskId':'parent','status':'failed',
            'productionStatus':'completed','draftReleaseStatus':'released','qualityStatus':'passed',
            'qualityReportPath':str(env.root/'reports/qc.json'),
            'finalOutputPath':str(env.root/'final/video.mp4')}

    def helper(self):
        return sys.modules['verified_final']

    def test_fresh_helper_oracle_and_candidate_use_same_aligned_facts(self):
        with Oracle(self.source,self.snapshot(),self.root/'old',collect=False) as env:
            self.assertEqual(FRESH_HELPER,env.helper_hash)
            env.namespace['COLLECTOR'].metadata={'child':self.metadata(env)}
            old=env.namespace['COLLECTOR'].normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
            with CollectionSession(env.namespace,source_sha=D6A7211_CRLF) as candidate:
                candidate.collector.metadata={'child':self.metadata(env)}
                new=candidate.collector.normalize_task({'taskId':'child','status':'failed'},env.root/'status.json',1)
            self.assertEqual('completed',old['state']);self.assertEqual(old,new)
            self.assertEqual(2,len(env.fresh_helper_ports.digest_calls))
            self.assertEqual([],env.io.denied)

    def test_no_lru_reuse_for_same_stat_but_changed_digest(self):
        second={**copy.deepcopy(self.record),'sha256':'b'*64}
        self.profile['facts']['verifiedFinalReadSequences']={'final/video.mp4':[self.record,second]}
        with Oracle(self.source,self.snapshot(),self.root/'old',collect=False) as env:
            helper=self.helper();metadata=self.metadata(env)
            self.assertTrue(helper.released_final_verified(metadata))
            self.assertFalse(helper.released_final_verified(metadata))
            self.assertEqual(2,len(env.fresh_helper_ports.digest_calls))

    def test_changed_device_or_inode_during_digest_returns_false(self):
        for key in ('device','inode'):
            with self.subTest(key=key):
                profile=copy.deepcopy(self.profile)
                changed=copy.deepcopy(self.record);changed['after'][key]+=1
                profile['facts']['verifiedFinalReadSequences']={'final/video.mp4':[changed]}
                snap=make_fixture(profile,self.source,self.root/(key+'-snapshot'))
                with Oracle(self.source,snap,self.root/key,collect=False) as env:
                    self.assertFalse(self.helper().released_final_verified(self.metadata(env)))

    def test_missing_media_identity_is_not_inferred_from_scratch(self):
        for side in ('before','after'):
            for key in ('device','inode'):
                with self.subTest(side=side,key=key):
                    profile=copy.deepcopy(self.profile)
                    del profile['facts']['verifiedFinalMedia']['final/video.mp4'][side][key]
                    name=side+key
                    snap=make_fixture(profile,self.source,self.root/(name+'-snapshot'))
                    with self.assertRaisesRegex(SnapshotError,'missing_frozen_content_hash'):
                        with Oracle(self.source,snap,self.root/name,collect=False) as env:
                            self.assertFalse(self.helper().released_final_verified(self.metadata(env)))

    def test_missing_dependency_identity_is_rejected_before_replay(self):
        for key in ('device','inode'):
            profile=copy.deepcopy(self.profile)
            del profile['facts']['captureProof']['helperIdentities']['verified_final.py'][key]
            snap=make_fixture(profile,self.source,self.root/(key+'-snapshot'))
            with self.assertRaisesRegex(SnapshotError,'verified_final_identity_fact_required'):
                Oracle(self.source,snap,self.root/key,collect=False)

    def test_helper_byte_hash_change_is_rejected_before_replay(self):
        self.profile['facts']['captureProof']['helperIdentities']['verified_final.py']['sha256']='0'*64
        with self.assertRaisesRegex(SnapshotError,'source_dependency_byte_hash_mismatch'):
            Oracle(self.source,self.snapshot(),self.root/'old',collect=False)

    def test_lf_pr49_source_also_selects_the_explicit_new_combination(self):
        self.source=self.source.replace('\r\n','\n')
        with Oracle(self.source,self.snapshot(),self.root/'old',collect=False) as env:
            self.assertEqual(FRESH_HELPER,env.helper_hash)
            self.assertTrue(self.helper().released_final_verified(self.metadata(env)))

    def test_missing_aligned_digest_and_exhausted_sequence_reject(self):
        self.profile['facts']['verifiedFinalMedia']={}
        with self.assertRaisesRegex(SnapshotError,'missing_frozen_content_hash'):
            with Oracle(self.source,self.snapshot(),self.root/'old',collect=False) as env:
                self.helper().released_final_verified(self.metadata(env))
        self.profile['facts']['verifiedFinalReadSequences']={'final/video.mp4':[self.record]}
        with self.assertRaisesRegex(SnapshotError,'missing_frozen_content_hash'):
            with Oracle(self.source,self.snapshot('sequence'),self.root/'sequence-old',collect=False) as env:
                self.assertTrue(self.helper().released_final_verified(self.metadata(env)))
                self.helper().released_final_verified(self.metadata(env))

    def capture_fixture(self):
        source=self.root/'app.py';source.write_bytes(self.source.encode())
        source.with_name('verified_final.py').write_bytes((ROOT/'contracts/legacy-verified-final-fresh.txt').read_text(encoding='utf-8').encode())
        live=self.root/'live';(live/'final').mkdir(parents=True)
        media=live/'final/video.mp4';media.write_bytes(b'synthetic-media')
        qc=live/'qc.json';qc.write_text(json.dumps({'status':'passed','taskId':'child',
            'canonicalTaskId':'parent','fileName':'video.mp4','fileSize':media.stat().st_size,
            'sha256':hashlib.sha256(media.read_bytes()).hexdigest()}),encoding='utf-8')
        repository=self.root/'repository';(repository/'data').mkdir(parents=True)
        plan={'schema':1,'roots':{'workbench':str(live),'repository':str(repository)},'files':{'workbench/qc.json':{'root':'workbench','path':'qc.json'}},
            'trees':{'workbench/final':{'root':'workbench','path':'final'}},'verifiedFinalMedia':['workbench/final/video.mp4'],
            'absent':{'repository/data/test_reset_state.json':{'root':'repository','path':'data/test_reset_state.json'}},
            'facts':{'scan':False}}
        processes={'processRecords':[],'processIds':[]}
        def capture(**kw):
            destination=self.root/kw.pop('destination_name','captured')
            return aligned_capture(plan,destination,source_path=source,
                process_probe=lambda:processes,http_probe=lambda:{},**kw)
        return source,media,plan,capture

    def test_new_combination_is_captured_and_replayed_without_media_read(self):
        source,media,plan,capture=self.capture_fixture()
        snap=capture();facts=snap.manifest['facts']
        identity=facts['captureProof']['helperIdentities']['verified_final.py']
        self.assertIn('inode',identity);self.assertIn('device',identity)
        proof=facts['verifiedFinalMedia']['workbench/final/video.mp4']
        self.assertEqual(proof['before'],proof['after'])
        self.assertEqual(2*media.stat().st_size,facts['captureProof']['verifiedFinalDigestReadBytes'])
        with Oracle(self.source,snap,self.root/'replay',collect=False) as env:
            metadata={'taskId':'child','remotePipelineTaskId':'parent','productionStatus':'completed',
                'draftReleaseStatus':'released','qualityStatus':'passed',
                'qualityReportPath':str(env.root/'workbench/qc.json'),
                'finalOutputPath':str(env.root/'workbench/final/video.mp4')}
            self.assertTrue(self.helper().released_final_verified(metadata))
            self.assertEqual([],env.io.denied)

    def test_single_helper_byte_change_is_rejected_even_if_normalized_hash_unchanged(self):
        source,media,plan,capture=self.capture_fixture()
        helper=source.with_name('verified_final.py')
        raw=helper.read_bytes().replace(b'\n',b'\r\n')
        helper.write_bytes(raw.replace(b'\r\n',b'\n',1))
        with self.assertRaisesRegex(SnapshotError,'source_dependency_byte_hash_mismatch'):capture()

    def test_media_budget_exhaustion_retains_missing_fact_instead_of_inventing_hash(self):
        source,media,plan,capture=self.capture_fixture()
        snap=capture(max_hash_bytes=1)
        self.assertEqual({},snap.manifest['facts']['verifiedFinalMedia'])
        self.assertTrue(snap.manifest['facts']['filesystem']['workbench/final/video.mp4']['hashPending'])

    def test_media_digest_is_fresh_each_window_even_with_a_digest_cache(self):
        from tools.shadow_capture import DigestCache,_stat
        source,media,plan,capture=self.capture_fixture()
        cache=DigestCache()
        cache.values[str(media)]={'identity':_stat(media),'sha256':'0'*64}
        one=capture(digest_cache=cache)
        two=capture(digest_cache=cache,destination_name='second')
        expected=hashlib.sha256(media.read_bytes()).hexdigest()
        for snap in (one,two):
            facts=snap.manifest['facts']
            self.assertIn('workbench/final/video.mp4',facts['verifiedFinalMedia'],
                          facts['filesystem']['workbench/final/video.mp4'])
            self.assertEqual(expected,facts['verifiedFinalMedia']['workbench/final/video.mp4']['sha256'])
            self.assertEqual(2*media.stat().st_size,facts['captureProof']['verifiedFinalDigestReadBytes'])

    def test_replaced_dependency_with_identical_text_rejects_window(self):
        from tools.shadow_capture import _observations
        source,media,plan,capture=self.capture_fixture()
        original=_observations;calls=[]
        def observations(*args):
            calls.append(1)
            if len(calls)==2:
                helper=source.with_name('verified_final.py')
                replacement=source.with_name('replacement.tmp')
                replacement.write_bytes(helper.read_bytes());replacement.replace(helper)
            return original(*args)
        with patch('tools.shadow_capture._observations',side_effect=observations):
            with self.assertRaisesRegex(CaptureError,'dependency_changed_in_window'):capture()

    def test_changed_media_is_pending_and_never_publishes_an_aligned_digest(self):
        from tools.shadow_capture import _verified_media
        source,media,plan,capture=self.capture_fixture()
        def changing(*args,**kwargs):
            media.write_bytes(b'now-writing-another-synthetic-frame')
            return _verified_media(*args,**kwargs)
        with patch('tools.shadow_capture._verified_media',side_effect=changing):snap=capture()
        self.assertEqual({},snap.manifest['facts']['verifiedFinalMedia'])
        self.assertTrue(snap.manifest['facts']['filesystem']['workbench/final/video.mp4']['hashPending'])

    def test_same_stat_content_overwrite_is_detected_by_fresh_closing_digest(self):
        from tools.shadow_capture import _verified_media,_stat
        source,media,plan,capture=self.capture_fixture()
        identity=_stat(media);calls=[]
        def changing(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:
                media.write_bytes(b'X'*identity['size'])
                # Explicitly simulate an unchanged full stat tuple. The closing
                # digest must still observe different bytes, without cache reuse.
                with patch('tools.shadow_capture._stat',return_value=identity),patch('tools.shadow_capture._info',return_value=identity):
                    return _verified_media(*args,**kwargs)
            return _verified_media(*args,**kwargs)
        with patch('tools.shadow_capture._verified_media',side_effect=changing):snap=capture()
        self.assertEqual({},snap.manifest['facts']['verifiedFinalMedia'])
        self.assertTrue(snap.manifest['facts']['filesystem']['workbench/final/video.mp4']['hashPending'])

    def test_fd_ctime_is_preserved_separately_from_path_ctime(self):
        import os,types
        from tools.shadow_capture import _verified_media
        source,media,plan,capture=self.capture_fixture()
        original=os.fstat
        def fstat(fd):
            value=original(fd)
            return types.SimpleNamespace(st_mode=value.st_mode,st_size=value.st_size,
                st_mtime_ns=value.st_mtime_ns,st_ctime_ns=value.st_ctime_ns+100,
                st_dev=value.st_dev,st_ino=value.st_ino)
        def different_ctime(*args,**kwargs):
            with patch('tools.shadow_capture.os.fstat',side_effect=fstat):
                return _verified_media(*args,**kwargs)
        with patch('tools.shadow_capture._verified_media',side_effect=different_ctime):snap=capture()
        proof=snap.manifest['facts']['verifiedFinalMedia']['workbench/final/video.mp4']
        self.assertNotEqual(proof['before']['ctimeNs'],proof['opened']['ctimeNs'])
        self.assertEqual(proof['before'],proof['after'])
        self.assertEqual(proof['opened'],proof['closed'])

    def test_old_combination_retains_original_frozen_helper(self):
        self.profile['facts'].pop('verifiedFinalMedia')
        self.profile['facts']['captureProof']={'helperHashes':{'verified_final.py':PR49_HELPER}}
        with Oracle(self.source,self.snapshot(),self.root/'old',collect=False) as env:
            self.assertEqual(PR49_HELPER,env.helper_hash)
            self.assertFalse(hasattr(env,'fresh_helper_ports'))
            self.assertTrue(self.helper().released_final_verified(self.metadata(env)))
