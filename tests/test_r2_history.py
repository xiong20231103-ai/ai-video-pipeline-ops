"""Synthetic temp databases/evidence only; all HTTP is in-process ASGI."""
import copy,hashlib,json,sqlite3,unittest
from contextlib import closing
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from agent.core.snapshot import capture,canonical
from agent.core.history_export import build_bundle,export_records,write_bundle
from agent.core.history_transfer import transfer
from cloud.history import HistoryStore
from contracts.history import HistoryError,summary,sha,manifest
from contracts.timeline import make_event,analyze,eta

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix='r2-isolated-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.now=[1000.]
        self.store=HistoryStore(self.root/'history.db',clock=lambda:self.now[0]);self.index=0
    def snapshot(self,*,tasks=None,aliases=(),reset='fixture-reset-1',extra_files=None):
        self.index+=1;dbfile=self.root/('ops'+str(self.index)+'.db')
        with closing(sqlite3.connect(dbfile)) as db:
            db.execute('CREATE TABLE tasks(task_id TEXT PRIMARY KEY,state TEXT)')
            db.executemany('INSERT INTO tasks VALUES(?,?)',tasks or [('fixture-video-1','Waiting')])
            db.execute('CREATE TABLE task_history(id INTEGER PRIMARY KEY,task_id TEXT,state TEXT,recorded_at TEXT)')
            db.execute('INSERT INTO task_history VALUES(1,?,?,?)',('fixture-video-1','Waiting','2026-10-19T10:00:00+08:00'))
            db.commit()
        return capture(self.root/('snapshot'+str(self.index)),databases={'repository/data/ops.db':dbfile},files=extra_files or {},facts={'historyResetGeneration':reset,'historyAliases':list(aliases)},frozen_at='2026-10-19T10:00:00+08:00',legacy_sha256='a'*64)
    def bundle(self,**kwargs):return build_bundle(self.snapshot(**kwargs),source='home',sequence=self.index)
    def install(self,bundle):
        result=self.store.begin(bundle['manifest']);self.assertEqual(bundle['generationId'],result['generationId'])
        for i,chunk in enumerate(bundle['chunks']):self.store.put(bundle['generationId'],i,chunk)
        return self.store.finish(bundle['generationId'])
    def repack(self,bundle,records):
        result=copy.deepcopy(bundle);result['records']=sorted(records,key=lambda x:(x['kind'],x['key']));result['chunks']=[[{'op':'upsert','record':x} for x in result['records']]];result['manifest']['chunks']=[sha(c) for c in result['chunks']];result['manifest']['summary']=summary(result['records']);result['generationId']=sha(result['manifest']);return result
    def test_initial_import_counts_primary_keys_hashes_and_idempotency(self):
        bundle=self.bundle();self.install(bundle);again=self.install(bundle)
        self.assertEqual('ready',again['state']);self.assertTrue(again['active'])
        self.assertEqual(bundle['manifest']['summary']['counts']['ops.tasks'],len(self.store.listing('home','ops.tasks')['items']))
        self.assertFalse(self.store.source('home')['legacySourceChanged']);self.assertFalse(self.store.source('home')['realShadowPassed'])
    def test_incomplete_staging_never_changes_visible_source(self):
        first=self.bundle();self.install(first)
        next_bundle=build_bundle(self.snapshot(tasks=[('fixture-video-1','Completed')]),source='home',sequence=2,previous=first)
        self.store.begin(next_bundle['manifest'])
        with self.assertRaisesRegex(HistoryError,'chunks_missing'):self.store.finish(next_bundle['generationId'])
        self.assertEqual(first['generationId'],self.store.source('home')['active'])
    def test_update_insert_delete_delta_and_complete_reimport(self):
        first=self.bundle(tasks=[('one','Waiting'),('removed','Waiting')]);self.install(first)
        second=build_bundle(self.snapshot(tasks=[('one','Completed'),('new','Waiting')]),source='home',sequence=2,previous=first);self.install(second)
        changes={(v['record_key'],v['operation']) for v in self.store.changes(second['generationId']) if v['kind']=='ops.tasks'}
        self.assertEqual({('one','update'),('removed','delete'),('new','insert')},changes)
        third=build_bundle(self.snapshot(tasks=[('final','Completed')]),source='home',sequence=3,base_generation=second['generationId']);self.install(third)
        self.assertEqual(['final'],[x['key'] for x in self.store.listing('home','ops.tasks')['items']])
        self.store.select('home',first['generationId'],'ROLLBACK_HISTORY_SOURCE')
        self.assertEqual(3,self.store.source('home')['highwater']);self.assertEqual(2,len(self.store.listing('home','ops.tasks')['items']))
    def test_chunk_corruption_is_rejected_and_can_resume(self):
        bundle=self.bundle();self.store.begin(bundle['manifest']);bad=copy.deepcopy(bundle['chunks'][0]);bad[0]['record']['value']={'changed':True}
        with self.assertRaisesRegex(HistoryError,'hash_mismatch'):self.store.put(bundle['generationId'],0,bad)
        self.assertEqual([],self.store.status(bundle['generationId'])['receivedChunks'])
        self.install(bundle)
    def test_false_counts_and_rows_hash_prevent_activation(self):
        bundle=self.bundle();bundle['manifest']['summary']['rowsHash']='0'*64;bundle['generationId']=sha(bundle['manifest'])
        with self.assertRaisesRegex(HistoryError,'rows_or_counts'):self.install(bundle)
        self.assertIsNone(self.store.source('home')['active'])
    def test_expired_staging_refuses_and_active_unchanged(self):
        bundle=self.bundle();self.store.begin(bundle['manifest']);self.now[0]+=86401
        with self.assertRaisesRegex(HistoryError,'expired'):self.store.put(bundle['generationId'],0,bundle['chunks'][0])
    def test_quota_and_duplicate_sequence_refuse(self):
        bundle=self.bundle();tiny=HistoryStore(self.root/'tiny.db',quota_bytes=1)
        with self.assertRaisesRegex(HistoryError,'quota'):tiny.begin(bundle['manifest'])
        self.store.begin(bundle['manifest']);other=copy.deepcopy(bundle['manifest']);other['sourceIdentity']='b'*64
        with self.assertRaisesRegex(HistoryError,'sequence_conflict'):self.store.begin(other)
    def test_two_staged_generations_compare_and_swap_base(self):
        first=self.bundle();self.install(first)
        second=build_bundle(self.snapshot(),source='home',sequence=2,previous=first)
        third=build_bundle(self.snapshot(),source='home',sequence=3,previous=first)
        self.store.begin(second['manifest']);self.store.begin(third['manifest']);self.install(second)
        with self.assertRaisesRegex(HistoryError,'base_changed'):self.install(third)
        self.assertEqual(second['generationId'],self.store.source('home')['active'])
    def test_alias_cycle_and_reset_namespace_are_not_accepted(self):
        bundle=self.bundle(aliases=[{'alias':'a','canonical':'b','resetGeneration':'fixture-reset-1'},{'alias':'b','canonical':'a','resetGeneration':'fixture-reset-1'}])
        with self.assertRaisesRegex(HistoryError,'alias_cycle'):self.install(bundle)
        self.assertIsNone(self.store.source('home')['active'])
    def test_reset_requires_full_generation_and_old_source_remains_queryable(self):
        first=self.bundle();self.install(first);snapshot=self.snapshot(reset='fixture-reset-2')
        with self.assertRaisesRegex(HistoryError,'across_reset'):build_bundle(snapshot,source='home',sequence=2,previous=first)
        second=build_bundle(snapshot,source='home',sequence=2,base_generation=first['generationId']);self.install(second)
        self.assertTrue(self.store.listing('home','ops.tasks',generation=first['generationId'])['items'])
    def test_pagination_requires_pinned_generation(self):
        bundle=self.bundle(tasks=[('one','Waiting'),('two','Completed')]);self.install(bundle)
        page=self.store.listing('home','ops.tasks',limit=1);self.assertIsNotNone(page['next'])
        with self.assertRaisesRegex(HistoryError,'pinned_generation'):self.store.listing('home','ops.tasks',after=page['next'])
        self.assertEqual(1,len(self.store.listing('home','ops.tasks',after=page['next'],generation=page['generationId'])['items']))
    def test_exact_evidence_bytes_reassembled_and_verified(self):
        receipt=self.root/'receipt.json';receipt.write_bytes(canonical({'batchId':'fixture-batch','items':['合成证据'*40000]}))
        bundle=self.bundle(extra_files={'repository/data/task-box-completion-receipts/fixture.json':receipt});self.install(bundle)
        self.assertGreater(bundle['manifest']['summary']['counts']['evidence'],1)
    def test_secret_encoded_evidence_and_missing_parts_rejected(self):
        import base64
        bundle=self.bundle();raw=b'{"password":"synthetic-inert-test-value"}'
        evidence={'kind':'evidence','key':'fixture.json#0','value':{'path':'fixture.json','index':0,'parts':1,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'encoding':'utf-8-json','data':base64.b64encode(raw).decode()}}
        altered=self.repack(bundle,bundle['records']+[evidence])
        with self.assertRaisesRegex(HistoryError,'unsafe_history_evidence'):self.install(altered)
    def test_recipe_driven_normalization_is_stored_and_queryable_by_project(self):
        path=self.root/'capcut.json';path.write_bytes(canonical([{'ContractBatchId':'fixture-batch','RemotePipelineTaskId':'fixture-project','CanonicalTaskId':'fixture-video','HandoffAttemptId':'attempt-1','HandoffManifestId':'manifest-1','StartedAt':'2026-10-19T10:00:00+08:00','FinishedAt':'2026-10-19T10:00:10+08:00','State':'Completed'}]))
        snapshot=self.snapshot(extra_files={'capcut/data/capcut-tasks.json':path})
        recipes=[{'path':'capcut/data/capcut-tasks.json','format':'capcut_tasks','version':'0.6.21','networkProfile':'direct','options':{}}]
        bundle=build_bundle(snapshot,source='home',sequence=1,recipes=recipes);self.install(bundle)
        report=self.store.timeline('home','fixture-batch','fixture-project')['analysis']
        self.assertEqual(10,report['intervals'][0]['elapsedSeconds']);self.assertEqual('normalized',bundle['manifest']['coverage']['timelineNormalization']['status'])
        self.assertEqual([],self.store.timeline('home','other-batch','fixture-project')['analysis']['intervals'])
    def test_missing_timestamps_remain_visible_in_recipe_coverage(self):
        path=self.root/'capcut.json';path.write_bytes(canonical([{'ContractBatchId':'fixture-batch','RemotePipelineTaskId':'fixture-project','CanonicalTaskId':'fixture-video','HandoffAttemptId':'attempt-1','HandoffManifestId':'manifest-1','StartedAt':'2026-10-19T10:00:00','State':'Waiting'}]))
        snapshot=self.snapshot(extra_files={'capcut/data/capcut-tasks.json':path})
        bundle=build_bundle(snapshot,source='home',sequence=1,recipes=[{'path':'capcut/data/capcut-tasks.json','format':'capcut_tasks','version':'0.6.21','networkProfile':'direct'}])
        self.assertEqual(2,bundle['manifest']['coverage']['timelineNormalization']['unresolvedCount'])
        self.assertFalse(bundle['manifest']['coverage']['timelineNormalization']['status']=='normalized')
    def test_csv_exact_evidence_and_staging_discard_protect_ready_generations(self):
        csvfile=self.root/'voice.csv';csvfile.write_bytes('task_id,status\r\nfixture,completed\r\n'.encode())
        bundle=self.bundle(extra_files={'voice/data/tasks.csv':csvfile});self.install(bundle)
        self.assertEqual(1,bundle['manifest']['summary']['counts']['evidence'])
        with self.assertRaisesRegex(HistoryError,'protected'):self.store.discard_staging(bundle['generationId'],'DISCARD_UNSELECTED_STAGING')
        second=build_bundle(self.snapshot(),source='home',sequence=2,previous=bundle);self.store.begin(second['manifest']);self.store.discard_staging(second['generationId'],'DISCARD_UNSELECTED_STAGING')
        self.assertEqual(bundle['generationId'],self.store.source('home')['active'])
    def test_client_understated_reservation_cannot_fill_cloud_database(self):
        bundle=self.bundle();bundle['manifest']['summary']['bytes']=1;bundle['generationId']=sha(bundle['manifest']);self.store.begin(bundle['manifest'])
        with self.assertRaisesRegex(HistoryError,'dataset_limit'):self.store.put(bundle['generationId'],0,bundle['chunks'][0])
        self.assertEqual([],self.store.status(bundle['generationId'])['receivedChunks'])
    def test_alias_resolution_is_scoped_to_selected_reset_generation(self):
        first=self.bundle(aliases=[{'alias':'old','canonical':'current','resetGeneration':'fixture-reset-1'}]);self.install(first)
        self.assertEqual('current',self.store.resolve_alias('home','old')['canonical'])
        second=build_bundle(self.snapshot(reset='fixture-reset-2'),source='home',sequence=2,base_generation=first['generationId']);self.install(second)
        self.assertEqual('old',self.store.resolve_alias('home','old')['canonical'])
        self.assertEqual('current',self.store.resolve_alias('home','old',generation=first['generationId'])['canonical'])
    def test_transfer_lost_ack_resumes_without_recreating_generation(self):
        bundle=self.bundle();store=self.store
        class Client:
            lost=True
            def get(self,path):return store.status(bundle['generationId'])
            def post(self,path,data):
                if path.endswith('/begin'):return store.begin(data)
                if '/chunks/' in path:
                    reply=store.put(bundle['generationId'],int(path.rsplit('/',1)[1]),data['operations'])
                    if self.lost:self.lost=False;raise OSError('synthetic_lost_cloud_ack')
                    return reply
                return store.finish(bundle['generationId'])
        client=Client()
        with self.assertRaises(OSError):transfer(bundle,client)
        self.assertEqual('ready',transfer(bundle,client)['state'])
        self.assertEqual(bundle['manifest']['summary']['rowCount'],sum(len(self.store.listing('home',k,limit=1000)['items']) for k in bundle['manifest']['summary']['counts']))
    def test_cli_isolated_export_import_and_no_existing_database_overwrite(self):
        import io
        from contextlib import redirect_stdout
        from tools.r2_history import main
        snapshot=self.snapshot();package=self.root/'package';database=self.root/'new-history.db'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0,main(['export','--snapshot',str(snapshot.root),'--source','home','--sequence','1','--out',str(package)]))
            self.assertEqual(0,main(['verify-import','--package',str(package),'--new-db',str(database)]))
            with self.assertRaisesRegex(ValueError,'new_isolated'):main(['verify-import','--package',str(package),'--new-db',str(database)])

class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.identity={'batchId':'fixture-batch','projectId':'fixture-project','videoId':'fixture-video','stage':'capcut','attemptId':'attempt-1','manifestId':'manifest-1'}
        self.source={'sourceId':'fixture-log','sha256':'a'*64,'cursor':'1','version':'0.6.21','networkProfile':'direct-20261020'};self.n=0
    def e(self,kind,seconds,**kwargs):
        self.n+=1;identity={**self.identity,**kwargs.pop('identity',{})};source={**self.source,'cursor':str(self.n)}
        return make_event(identity,kind,(datetime(2026,10,19,tzinfo=timezone(timedelta(hours=8)))+timedelta(seconds=seconds)).isoformat(),source,outcome='success' if kind=='end' else 'unknown',**kwargs)
    def test_exact_per_video_stage_and_attempts(self):
        values=[self.e('start',0),self.e('end',10),self.e('start',20,identity={'attemptId':'attempt-2'}),self.e('end',35,identity={'attemptId':'attempt-2'})]
        report=analyze(values);self.assertEqual([10,15],[v['elapsedSeconds'] for v in report['intervals']]);self.assertEqual(25,report['videos'][0]['unionElapsedSeconds'])
    def test_overlapping_prefetch_is_union_not_sum(self):
        values=[self.e('start',0,identity={'stage':'download'},prefetch=True),self.e('end',10,identity={'stage':'download'}),self.e('start',5,identity={'stage':'voice'}),self.e('end',15,identity={'stage':'voice'})]
        report=analyze(values);self.assertEqual(15,report['unionElapsedSeconds']);self.assertEqual(15,report['projects'][0]['unionElapsedSeconds'])
    def test_failure_wait_and_deliberate_pause_are_distinct(self):
        values=[self.e('failed',0,error_code='CAPCUT_DRAFT_AUDIO_MISSING'),self.e('human_wait_start',1),self.e('human_wait_end',101),self.e('pause',110),self.e('resume',310)]
        report=analyze(values);self.assertEqual('CAPCUT_DRAFT_AUDIO_MISSING',report['failures'][0]['errorCode']);self.assertEqual(100,report['confirmedHumanWaits'][0]['elapsedSeconds']);self.assertEqual(200,report['deliberatePauses'][0]['elapsedSeconds'])
    def test_big_completion_gap_is_heuristic_not_human_wait(self):
        values=[self.e('start',0),self.e('end',10),self.e('start',2000,identity={'videoId':'other'}),self.e('end',2010,identity={'videoId':'other'})]
        report=analyze(values);self.assertEqual([],report['confirmedHumanWaits']);self.assertFalse(report['unclassifiedGaps'][0]['isConfirmedHumanWait'])
    def test_observed_75_seconds_never_claims_exact_duration(self):
        report=analyze([self.e('start',0,precision='observed',uncertainty=75),self.e('end',100,precision='observed',uncertainty=75)])
        self.assertIsNone(report['intervals'][0]['elapsedSeconds']);self.assertEqual([0,250],report['intervals'][0]['rangeSeconds']);self.assertEqual(0,report['unionElapsedSeconds'])
    def test_missing_start_end_and_ambiguous_retries_are_visible(self):
        report=analyze([self.e('end',0),self.e('start',1),self.e('start',2),self.e('end',3),self.e('start',5)])
        self.assertEqual({'missing_start','duplicate_start','open_interval'},{x['code'] for x in report['issues']});self.assertIsNone(report['intervals'][0]['elapsedSeconds'])
    def test_naive_timestamp_and_event_identity_conflict_rejected(self):
        from contracts.timeline import event
        value=self.e('start',0);bad={**value,'at':'2026-10-19T10:00:00'}
        with self.assertRaisesRegex(HistoryError,'timezone_required'):event(bad)
        with self.assertRaisesRegex(HistoryError,'identity_conflict'):analyze([value,{**value,'errorCode':'FIXTURE_CHANGED'}])
    def test_eta_paused_missing_version_and_parallel_plan(self):
        events=[]
        for i in range(3):
            for stage,duration in [('download',10),('voice',20)]:events +=[self.e('start',i*100,identity={'videoId':str(i),'stage':stage}),self.e('end',i*100+duration,identity={'videoId':str(i),'stage':stage})]
        report=analyze(events);kwargs={'version':'0.6.21','network_profile':'direct-20261020','plan':[['download','voice']]}
        self.assertEqual(40,eta(report,{'download':2,'voice':2},**kwargs)['seconds'])
        self.assertFalse(eta(report,{'download':2,'voice':2},paused=True,**kwargs)['available'])
        kwargs['version']='other';self.assertFalse(eta(report,{'download':2,'voice':2},**kwargs)['available'])
        self.assertFalse(eta(report,{'download':1},version='0.6.21',network_profile='direct-20261020')['available'])
    def test_historical_rows_do_not_borrow_current_attempt_identity(self):
        from agent.core.history_timeline import sampled_task_history
        rows=[{'id':1,'task_id':'old','state':'Completed','recorded_at':'2026-10-19T10:00:00+08:00'}]
        result,issues=sampled_task_history(rows,{'old':{'attempt_id':'new-attempt'}},self.source)
        self.assertEqual([],result);self.assertEqual('historical_attempt_identity_unproven',issues[0]['reason'])
        result,issues=sampled_task_history(rows,{},self.source,identity_by_row={1:self.identity})
        self.assertEqual('observed',result[0]['precision']);self.assertEqual([],issues)
    def test_log_parser_preserves_explicit_context_and_reported_duration(self):
        from agent.core.history_timeline import capcut_log_events
        text='2026-10-19 10:00:00.000 [INFO] fixture.mp4: 导入视频（第 1 次）\n2026-10-19 10:00:03.100 [INFO] 步骤完成: 导入视频，耗时 3.0s'
        kwargs={'source_id':'capcut-log','source_sha':'a'*64,'version':'0.6.21','network_profile':'direct','offset':timedelta(hours=8)}
        values,issues=capcut_log_events(text,contexts=[{'firstLine':1,'lastLine':2,'identity':self.identity,'stageByName':{'导入视频':'capcut.import'}}],**kwargs)
        self.assertEqual(2,len(values));self.assertEqual(3.0,analyze(values)['intervals'][0]['reportedSeconds']);self.assertEqual([],issues)
        values,issues=capcut_log_events(text,contexts=[],**kwargs);self.assertEqual([],values);self.assertEqual(2,len(issues))
    def test_capcut_failed_task_is_not_counted_as_successful_completion(self):
        from agent.core.history_timeline import capcut_task_events
        values,issues=capcut_task_events({'ContractBatchId':'fixture-batch','RemotePipelineTaskId':'fixture-project','CanonicalTaskId':'fixture-video','HandoffAttemptId':'attempt-1','HandoffManifestId':'manifest-1','StartedAt':'2026-10-19T10:00:00+08:00','FinishedAt':'2026-10-19T10:00:10+08:00','State':'Failed','Error':'CAPCUT_DRAFT_AUDIO_MISSING: inert fixture'},self.source)
        report=analyze(values);self.assertEqual([],issues);self.assertEqual('failed',report['intervals'][0]['outcome']);self.assertEqual('CAPCUT_DRAFT_AUDIO_MISSING',report['failures'][0]['errorCode']);self.assertFalse(report['intervals'][0]['eligibleForEta'])
    def test_log_append_hash_changes_do_not_duplicate_event_identity(self):
        value=self.e('start',0);source={**value['source'],'sha256':'b'*64}
        new=make_event(self.identity,'start',value['at'],source)
        self.assertEqual(value['eventId'],new['eventId'])


    def test_workbench_markers_require_context_and_do_not_split_combined_step(self):
        from agent.core.history_timeline import workbench_log_events
        text='2026-10-19T10:00:00 [pid 123] 后台任务已启动，共 3 个链接\n2026-10-19T10:01:00 [pid 123] 第 1/2 步完成，正在按任务指令启动语音客户端：fixture'
        values,issues=workbench_log_events(text,source=self.source,offset=timedelta(hours=8),contexts=[{'firstLine':1,'lastLine':2,'identity':self.identity}])
        self.assertEqual({'download_subtitle','voice'},{v['stage'] for v in values});self.assertEqual([],issues)
        interval=analyze(values)['intervals'][0];self.assertIsNone(interval['elapsedSeconds']);self.assertEqual([58,62],interval['rangeSeconds'])
    def test_json_stage_mappings_cover_project_and_per_video_steps_without_fabrication(self):
        from agent.core.history_timeline import structured_stage_events
        bindings={'batchId':'batchId','projectId':'projectId','videoId':'videoId','attemptId':'attemptId','manifestId':'manifestId'}
        values=[]
        for i,stage in enumerate(('download','subtitle','voice','stitch','upload')):
            row={**self.identity,'status':'completed','startedAt':'2026-10-19T10:00:00+08:00','completedAt':'2026-10-19T10:00:10+08:00'}
            events,issues=structured_stage_events([row],identity_fields=bindings,time_fields={'start':'startedAt','end':'completedAt'},source={**self.source,'cursor':stage},stage=stage)
            values.extend(events);self.assertEqual([],issues)
        report=analyze(values);self.assertEqual(5,len(report['intervals']));self.assertEqual(10,report['videos'][0]['unionElapsedSeconds'])
        events,issues=structured_stage_events([{**row,'completedAt':None}],identity_fields=bindings,time_fields={'start':'startedAt','end':'completedAt'},source=self.source,stage='voice')
        self.assertEqual(1,len(events));self.assertEqual('timestamp_missing',issues[0]['reason'])
    def test_eta_excludes_explicit_human_wait_and_cross_version_intervals(self):
        values=[]
        for i in range(3):values.extend([self.e('start',i*100),self.e('end',i*100+50),self.e('human_wait_start',i*100+10),self.e('human_wait_end',i*100+40)])
        report=analyze(values);self.assertTrue(all(not x['eligibleForEta'] for x in report['intervals']))
        self.assertFalse(eta(report,{'capcut':1},version='0.6.21',network_profile='direct-20261020',plan=[['capcut']])['available'])

class HistoryRouteTests(unittest.TestCase):
    def setUp(self):
        from cloud.store import Store
        from cloud.app import create_app,HASHER
        self.temp=TemporaryDirectory(prefix='r2-route-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.console=Store(self.root/'console.db');self.token='fixture-history-not-real';self.password='fixture-history-password-not-real'
        self.config={'origin':'https://console.fixture.ts.net','agent_token_sha256':hashlib.sha256(self.token.encode()).hexdigest(),'invite_hash':HASHER.hash('fixture-history-invitation-not-real'),'max_accounts':2}
        self.create_app=create_app;self.root_static=Path(__file__).resolve().parents[1]/'static'
    def client(self,enabled=False):
        return TestClient(self.create_app({**self.config,'history_enabled':enabled},self.console,self.root_static),base_url=self.config['origin'],headers={'Origin':self.config['origin']})
    def test_default_off_adds_no_history_database_or_routes_and_no_cache_change(self):
        client=self.client();self.assertFalse((self.root/'history.db').exists())
        self.assertEqual(404,client.get('/console/history/home').status_code)
        with self.console.db() as db:self.assertEqual(0,db.execute('SELECT count(*) FROM responses').fetchone()[0])
    def test_enabled_agent_auth_session_and_csrf_boundaries(self):
        from cloud.app import HASHER
        client=self.client(True)
        self.assertEqual(401,client.get('/console/history/home').status_code)
        self.assertEqual(401,client.post('/agent/history/begin',json={}).status_code)
        self.assertEqual(400,client.post('/agent/history/begin',json={},headers={'Authorization':'Bearer '+self.token}).status_code)
        self.console.register('fixture-history-user',HASHER.hash(self.password),2)
        self.assertEqual(200,client.post('/auth/login',json={'username':'fixture-history-user','password':self.password}).status_code)
        self.assertEqual(200,client.get('/console/history/home').status_code)
        self.assertEqual(403,client.post('/console/history/home/select',json={}).status_code)
        csrf=client.get('/auth/session').json()['csrf']
        self.assertEqual(400,client.post('/console/history/home/select',json={'confirmation':'wrong'},headers={'X-CSRF-Token':csrf}).status_code)
    def test_authenticated_empty_history_is_not_legacy_acceptance(self):
        from cloud.app import HASHER
        client=self.client(True);self.console.register('fixture-history-user',HASHER.hash(self.password),2);client.post('/auth/login',json={'username':'fixture-history-user','password':self.password})
        result=client.get('/console/history/home').json()
        self.assertIsNone(result['active']);self.assertFalse(result['switchAccepted']);self.assertFalse(result['realShadowPassed'])
        self.assertEqual(200,client.get('/console/history/home/timeline?batchId=fixture-batch&projectId=fixture-project').status_code)
