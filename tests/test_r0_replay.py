import copy,hashlib,json,os,sqlite3,unittest
from unittest.mock import patch
from agent.core.snapshot import safe_facts
from pathlib import Path
from tempfile import TemporaryDirectory
from agent.core.snapshot import capture,Snapshot,SnapshotError,relative,canonical
from agent.core.comparison import compare,evidence_gate
from agent.core.oracle import Oracle
from agent.core.replay import make_fixture,replay,read_targets

ROOT=Path(__file__).resolve().parents[1]

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r0-unit-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=(ROOT/'app.py').read_text(encoding='utf-8');self.sha=hashlib.sha256(self.source.encode()).hexdigest()
    def capture(self,**extra):return capture(self.root/'snapshot',facts={},frozen_at='2026-10-16T00:00:00+08:00',legacy_sha256=self.sha,**extra)
    def test_explicit_bounded_input_and_no_live_fallback(self):
        source=self.root/'state.json';source.write_text('{"x":null}',encoding='utf-8')
        snap=self.capture(files={'data/state.json':source});self.assertEqual({'x':None},snap.json('data/state.json'))
        with self.assertRaisesRegex(SnapshotError,'undeclared'):snap.read('../state.json')
        (snap.root/'data/state.json').write_text('{"x":1}',encoding='utf-8')
        with self.assertRaisesRegex(SnapshotError,'hash_mismatch'):Snapshot(snap.root)
    def test_paths_and_credentials_fail_closed(self):
        for value in ('../x','/x','C:foo','a\\b','a//b','snapshot.json'):
            with self.subTest(value=value),self.assertRaises(SnapshotError):relative(value)
        for key in ('password','authorization','access_token','agent_token_sha256','invite_hash','webhook'):
            with self.subTest(key=key),self.assertRaisesRegex(SnapshotError,'credential'):
                capture(self.root/'bad',facts={key:'synthetic-only'},frozen_at='2026-10-16T00:00:00+08:00',legacy_sha256=self.sha)
    def test_sqlite_is_consistent_and_closed_and_rejects_other_databases(self):
        source=self.root/'ops.db';db=sqlite3.connect(source);db.execute('create table tasks(task_id text primary key,state text)');db.execute("insert into tasks values('one','Completed')");db.commit();db.close()
        snap=self.capture(databases={'data/ops.db':source});self.assertEqual('sqlite',snap.manifest['files']['data/ops.db']['kind'])
        source.unlink() # No leaked read handle on Windows.
        self.assertTrue((snap.root/'data/ops.db').is_file())
    def test_capture_limit_and_manifest_tampering(self):
        source=self.root/'state.json';source.write_bytes(b'x'*20)
        with self.assertRaisesRegex(SnapshotError,'too_large'):self.capture(files={'state.json':source},max_file_bytes=10)
        snap=self.capture();manifest=snap.root/'snapshot.json';data=json.loads(manifest.read_text());data['facts']['changed']=True;manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(SnapshotError,'manifest_hash'):Snapshot(snap.root)
    def test_zero_diff_does_not_erase_missing_null_types_order_or_business_time(self):
        for left,right in [({}, {'x':None}),({'n':0},{'n':False}),([1,2],[2,1]),({'requestedAt':1},{'requestedAt':2})]:self.assertTrue(compare(left,right))
        with self.assertRaises(ValueError):compare({}, {}, ignored=['/observation/observedAt'])
        with self.assertRaises(ValueError):compare({}, {}, mode='real-shadow',ignored=['/expiresAt'])
        with self.assertRaises(ValueError):compare({'observation':{'observedAt':{}}},{'observation':{'observedAt':{}}},mode='real-shadow',ignored=['/observation/observedAt'])
        self.assertEqual([],compare({'observation':{'observedAt':1}},{'observation':{'observedAt':2}},mode='real-shadow',ignored=['/observation/observedAt']))
    def test_gate_blocks_simulation_incomplete_and_unaligned_windows(self):
        report={'mode':'isolated','batchId':'one','batchStarted':True,'batchCompleted':True,'windows':[{'target':'x','sourceIdentity':'a','candidateSourceIdentity':'a','comparable':True,'caseCount':1,'mismatchCount':0}]}
        self.assertTrue(evidence_gate(report,['x']));report['mode']='real-shadow';self.assertEqual([],evidence_gate(report,['x']))
        report['windows'][0]['comparable']=False;self.assertTrue(evidence_gate(report,['x']))
    def test_all_read_routes_and_persistent_effects_replay_frozen_golden(self):
        profiles=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))
        golden=json.loads((ROOT/'tests/fixtures/r0/expected.json').read_text(encoding='utf-8'))
        targets=read_targets(json.loads((ROOT/'contracts/endpoints.json').read_text(encoding='utf-8')))
        self.assertEqual(28,len(targets));self.assertEqual(set(profiles),set(golden))
        for index,(name,profile) in enumerate(profiles.items()):
            with self.subTest(profile=name):
                snapshot=make_fixture(profile,self.source,self.root/('snapshot-'+str(index)))
                result=replay(self.source,snapshot,self.root/('scratch-'+str(index)),targets)
                # The identity includes captured file mtimes. It is compared, never ignored.
                self.assertEqual([],compare(golden[name],result))
                self.assertFalse(result['realShadowPassed']);self.assertFalse(result['switchAccepted'])
    def test_oracle_rejects_other_source_and_live_io_even_if_caught(self):
        snapshot=self.capture()
        with self.assertRaisesRegex(SnapshotError,'source_hash'):Oracle(self.source+'\n',snapshot,self.root/'wrong')
        with self.assertRaisesRegex(SnapshotError,'live_io'):
            with Oracle(self.source,snapshot,self.root/'scratch') as oracle:
                with self.assertRaises(PermissionError):Path('E:/not-a-snapshot/private.json').read_text()
    def test_oracle_never_starts_threads_processes_or_sends_post(self):
        snapshot=self.capture()
        with Oracle(self.source,snapshot,self.root/'scratch') as oracle:
            with self.assertRaisesRegex(RuntimeError,'non_get'):oracle.namespace['urllib'].request.urlopen(oracle.namespace['urllib'].request.Request('http://127.0.0.1/api/tasks',method='POST'))
            with self.assertRaisesRegex(RuntimeError,'thread_start'):oracle.namespace['threading'].Thread(target=lambda:None).start()
            with self.assertRaisesRegex(RuntimeError,'process_start'):oracle.namespace['subprocess'].Popen(['not-a-real-program'])

    def test_secret_text_and_business_snapshot_tokens_are_distinct(self):
        safe_facts({'snapshotToken':'synthetic-preview','expiresAt':'fixture-time'})
        for text in ('authorization = Bearer synthetic-value','password: synthetic-value','https://open.feishu.cn/open-apis/bot/v2/hook/synthetic-only'):
            with self.subTest(text=text),self.assertRaisesRegex(SnapshotError,'credential'):safe_facts(text)
    def test_same_size_same_mtime_source_change_is_not_comparable(self):
        source=self.root/'state.json';source.write_text('{"a":1}',encoding='utf-8');metadata=source.stat()
        from agent.core import snapshot as module
        original=module.digest_file
        def mutate(path):
            result=original(path)
            if Path(path)!=source:
                source.write_text('{"a":2}',encoding='utf-8');os.utime(source,ns=(metadata.st_atime_ns,metadata.st_mtime_ns))
            return result
        with patch.object(module,'digest_file',side_effect=mutate),self.assertRaisesRegex(SnapshotError,'unaligned_file_content'):
            self.capture(files={'state.json':source})
    def test_trusted_oracle_cannot_be_replaced_by_self_declared_source_hash(self):
        altered=self.source+'\n# different source'
        snapshot=capture(self.root/'snapshot',facts={},frozen_at='2026-10-16T00:00:00+08:00',legacy_sha256=hashlib.sha256(altered.encode()).hexdigest())
        with self.assertRaisesRegex(SnapshotError,'source_hash'):Oracle(altered,snapshot,self.root/'scratch')
    def test_metadata_only_files_keep_stat_and_deny_fabricated_content(self):
        facts={'scan':False,'filesystem':{'final/one.mp4':{'kind':'file','size':987654321,'mtimeNs':1700000000000000000}}}
        snapshot=capture(self.root/'snapshot',facts=facts,frozen_at='2026-10-16T00:00:00+08:00',legacy_sha256=self.sha)
        with self.assertRaisesRegex(SnapshotError,'live_io'):
            with Oracle(self.source,snapshot,self.root/'scratch') as oracle:
                file=oracle.root/'final/one.mp4';self.assertTrue(file.is_file());self.assertEqual(987654321,file.stat().st_size)
                with self.assertRaisesRegex(PermissionError,'metadata_only'):file.read_bytes()
    def test_sqlite_unknown_tables_are_never_exported_as_ops_history(self):
        path=self.root/'not-ops.db';db=sqlite3.connect(path);db.execute('create table users(name text)');db.close()
        with self.assertRaisesRegex(SnapshotError,'unexpected_ops_table'):self.capture(databases={'ops.db':path})

    def test_process_identity_and_disks_are_frozen_without_real_inspection(self):
        facts={'scan':False,'processRecords':[{'pid':424242,'name':'CapCut.exe','cmdline':['CapCut.exe'],'create_time':100.0}],'diskUsage':{'total':1000,'used':250,'free':750,'percent':25}}
        snapshot=capture(self.root/'snapshot',facts=facts,frozen_at='2026-10-16T00:00:00+08:00',legacy_sha256=self.sha)
        with Oracle(self.source,snapshot,self.root/'scratch') as oracle:
            psutil=oracle.namespace['psutil'];process=psutil.Process(424242)
            self.assertEqual(['CapCut.exe'],process.cmdline());self.assertTrue(psutil.pid_exists(424242))
            self.assertEqual(750,psutil.disk_usage('not-a-real-drive').free)
            with self.assertRaises(psutil.NoSuchProcess):psutil.Process(1)
            with self.assertRaisesRegex(RuntimeError,'control_forbidden'):process.kill()

    def test_health_log_and_naive_times_use_the_frozen_timezone(self):
        profile=json.loads((ROOT/'tests/fixtures/r0/profiles.json').read_text(encoding='utf-8'))['health_logs_and_process_identity']
        snapshot=make_fixture(profile,self.source,self.root/'snapshot')
        with Oracle(self.source,snapshot,self.root/'scratch') as oracle:
            health=oracle.namespace['workbench_health_payload']()
            self.assertTrue(health['logAvailable']);self.assertEqual(1,len(health['recentErrors']))
            self.assertEqual(59,health['openCommands'][0]['ageSeconds'])
            self.assertEqual(oracle.namespace['time'].time(),oracle.namespace['datetime'].now().timestamp())

    def test_explicit_alias_redirects_path_strings_without_touching_original(self):
        source=self.root/'state.json';source.write_text('{"fixture":true}',encoding='utf-8')
        snapshot=capture(self.root/'snapshot',files={'workbench/state.json':source},facts={'scan':False,'pathAliases':{'E:/synthetic-never-live':'workbench'}},frozen_at='2026-10-16T00:00:00+08:00',legacy_sha256=self.sha)
        with Oracle(self.source,snapshot,self.root/'scratch') as oracle:
            virtual=Path('E:/synthetic-never-live/state.json')
            self.assertTrue(virtual.is_file());self.assertEqual({'fixture':True},json.loads(virtual.read_text()))
            self.assertTrue(virtual.resolve().is_relative_to(oracle.root.resolve()))

    def test_cli_capture_replay_compare_and_output_no_overwrite(self):
        import io
        from contextlib import redirect_stdout
        from tools.r0_replay import main
        recipe=self.root/'recipe.json';recipe.write_text(json.dumps({'facts':{'scan':False},'frozenAt':'2026-10-16T00:00:00+08:00','legacySha256':self.sha}),encoding='utf-8')
        output=self.root/'output.json';delta=self.root/'delta.json'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0,main(['capture','--recipe',str(recipe),'--out',str(self.root/'snapshot')]))
            self.assertEqual(0,main(['replay','--source',str(ROOT/'app.py'),'--snapshot',str(self.root/'snapshot'),'--scratch',str(self.root/'scratch'),'--out',str(output)]))
            self.assertEqual(28,len(json.loads(output.read_text(encoding='utf-8'))['responses']))
            self.assertEqual(0,main(['compare','--expected',str(output),'--actual',str(output),'--out',str(delta)]))
            self.assertFalse(json.loads(delta.read_text(encoding='utf-8'))['switchAccepted'])
            with self.assertRaisesRegex(ValueError,'output_exists'):main(['compare','--expected',str(output),'--actual',str(output),'--out',str(delta)])
        self.assertTrue(evidence_gate({'mode':'real-shadow','windows':[{}]},[]))
