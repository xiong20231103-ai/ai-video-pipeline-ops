"""Synthetic fixtures discovered by tools/run_isolated_tests.py; no pytest."""
import base64
from contextlib import closing
from io import BytesIO
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from PIL import Image
from cloud.link_evidence import Evidence, DAY


def event(seq=1,**extra):
    data=dict(source='test-company',platform='douyin',video_id='123',judge_round='v1:1',seq=seq,
              url='https://www.douyin.com/video/123',review='pending',delivery='not_applicable',displayable=True)
    return {**data,**extra}


def image(color='red'):
    out=BytesIO();Image.new('RGB',(80,40),color).save(out,'JPEG')
    return base64.b64encode(out.getvalue()).decode()


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory(prefix='link-evidence-fixture-');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.now=100*DAY
        self.store=Evidence(self.root,clock=lambda:self.now)

    def row(self):return self.store.listing()['items'][0]

    def test_newer_state_wins_and_duplicate_is_idempotent(self):
        first=self.store.ingest(event())
        self.store.ingest(event(3,review='confirmed',delivery='waiting',decidedAt=self.now))
        self.store.ingest(event(2,review='rejected'))
        self.assertTrue(self.store.ingest(event(3))['stale'])
        row=self.row()
        self.assertEqual((row['seq'],row['review'],row['delivery']),(3,'confirmed','waiting'))
        self.assertEqual(row['id'],first['id']);self.assertEqual(self.store.listing()['total'],1)

    def test_equal_sequence_only_repairs_missing_image(self):
        self.store.ingest(event(2,review='confirmed',delivery='waiting',decidedAt=self.now));old=self.row()
        result=self.store.ingest(event(2,image=image(),url='https://example.invalid/old'))
        self.assertEqual(result['image'],'stored');self.assertTrue(result['stale'])
        row=self.row()
        for key in ('seq','review','delivery','decided','payload'):self.assertEqual(row[key],old[key])
        self.store.ingest(event(2,image=image('blue'),review='rejected'))
        self.assertEqual(self.row()['sha'],row['sha'])

    def test_lower_sequence_cannot_replace_new_screenshot(self):
        self.store.ingest(event(1,image=image()))
        self.store.ingest(event(4,image=image('blue'),review='confirmed',delivery='waiting',decidedAt=self.now))
        old=self.row();result=self.store.ingest(event(2,image=image('green')))
        self.assertTrue(result['stale']);self.assertEqual(result['image'],'unchanged');self.assertEqual(self.row(),old)

    def test_lower_sequence_only_fills_absent_image_without_state_replay(self):
        self.store.ingest(event(4,review='confirmed',delivery='waiting'))
        self.assertEqual(self.store.ingest(event(1,image=image()))['image'],'stored')
        self.assertEqual((self.row()['seq'],self.row()['review']),(4,'confirmed'))

    def test_pending_image_survives_age_and_capacity_pressure(self):
        raw=image();self.store.cap=len(base64.b64decode(raw))
        first=self.store.ingest(event(image=raw));sha=self.row()['sha'];self.now+=40*DAY
        second=self.store.ingest(event(video_id='456',url='https://www.douyin.com/video/456',image=image('blue')))
        self.store.cleanup();rows={r['id']:r for r in self.store.listing()['items']}
        self.assertEqual(second['image'],'capacity_rejected');self.assertEqual(rows[first['id']]['sha'],sha)
        with self.store.db() as db:path=db.execute('SELECT path FROM shots WHERE sha=?',(sha,)).fetchone()['path']
        self.assertTrue((self.root/path).is_file());self.assertTrue(self.store.listing()['capacityReached'])

    def test_retention_starts_at_decision_not_upload(self):
        self.store.ingest(event(image=image()));self.now+=30*DAY
        self.store.ingest(event(2,review='rejected',decidedAt=self.now));self.now+=14*DAY
        self.store.cleanup();self.assertIsNotNone(self.row()['sha'])
        self.now+=2*DAY;self.store.cleanup();self.assertIsNone(self.row()['sha'])
        self.assertEqual(self.store.listing()['total'],1)

    def test_historical_unknown_time_uses_first_upload(self):
        self.store.ingest(event(image=image(),review='confirmed',delivery='waiting'));uploaded=self.row()['uploaded']
        self.now+=14*DAY;self.store.ingest(event(2,review='confirmed',delivery='sent'))
        self.now+=2*DAY;self.store.cleanup()
        self.assertEqual(self.row()['uploaded'],uploaded);self.assertIsNone(self.row()['decided']);self.assertIsNone(self.row()['sha'])

    def test_unreviewed_expires_image_but_keeps_link(self):
        self.store.ingest(event(image=image(),review=None,rawReviewState=None));self.now+=16*DAY
        with self.assertLogs('cloud.link_evidence',level='INFO') as logs:self.store.cleanup()
        self.assertIsNone(self.row()['review']);self.assertIsNone(self.row()['sha'])
        self.assertEqual(self.row()['payload']['url'],'https://www.douyin.com/video/123')
        self.assertEqual(self.store.listing()['total'],1);self.assertIn('count=1',logs.output[-1])

    def test_capacity_rejects_only_image_sets_alarm_and_can_repair(self):
        self.store.cap=1;result=self.store.ingest(event(image=image()))
        self.assertEqual(result['image'],'capacity_rejected');self.assertEqual(self.store.listing()['total'],1)
        self.assertTrue(self.store.listing()['capacityReached'])
        self.store.ingest(event(2,review='confirmed',delivery='waiting',decidedAt=self.now))
        self.assertEqual((self.row()['review'],self.row()['delivery']),('confirmed','waiting'))
        self.store.cap=1024*1024
        self.assertEqual(self.store.ingest(event(2,image=image()))['image'],'stored')
        self.store.cleanup();self.assertFalse(self.store.listing()['capacityReached'])

    def test_processed_image_evicted_before_pending(self):
        red,blue=image(),image('blue');self.store.cap=max(len(base64.b64decode(red)),len(base64.b64decode(blue)))
        first=self.store.ingest(event(image=red,review='rejected',decidedAt=self.now));self.now+=DAY
        second=self.store.ingest(event(video_id='456',url='https://www.douyin.com/video/456',image=blue))
        rows={r['id']:r for r in self.store.listing()['items']}
        self.assertEqual(second['image'],'stored');self.assertIsNone(rows[first['id']]['sha'])
        self.assertIsNotNone(rows[second['id']]['sha']);self.assertEqual(len(rows),2)

    def test_later_state_event_preserves_decision_time(self):
        self.store.ingest(event(review='confirmed',decidedAt=self.now));decided=self.row()['decided']
        self.now+=DAY;self.store.ingest(event(2,review='confirmed',delivery='sent'))
        self.assertEqual(self.row()['decided'],decided)

    def test_invalid_image_and_nonfinite_time_rejected(self):
        with self.assertRaises((ValueError,OSError)):self.store.ingest(event(image=base64.b64encode(b'bad').decode()))
        with self.assertRaises(ValueError):self.store.ingest(event(decidedAt=float('nan')))
        self.assertEqual(self.store.listing()['total'],0)

    def test_backup_keeps_seven_readable_databases_no_images(self):
        self.store.ingest(event(image=image()))
        for _ in range(9):self.now+=DAY;self.store.backup()
        folder=self.root/'db-backups';files=list(folder.glob('*.db'))
        self.assertEqual(len(files),7);self.assertEqual(len(list(folder.iterdir())),7)
        with closing(sqlite3.connect(files[-1])) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],1)

    def test_authentication_body_limit_and_no_token_logs(self):
        from fastapi import FastAPI,HTTPException
        from fastapi.testclient import TestClient
        from cloud.link_routes import mount_links
        token='fixture-evidence-token-not-a-secret';app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        def session(request):
            if request.headers.get('x-fixture-session')!='yes':raise HTTPException(401,'login_required')
            return {'user_id':1}
        mount_links(app,{'link_evidence_enabled':True,'link_evidence_dir':str(self.root/'routes')},session,lambda *a:None)
        with patch.dict(os.environ,{'LINK_EVIDENCE_TOKEN':token}),TestClient(app) as client:
            self.assertEqual(client.post('/api/links/ingest',json=event()).status_code,401)
            headers={'Authorization':'Bearer '+token}
            with self.assertLogs('cloud.link_evidence',level='INFO') as logs:
                response=client.post('/api/links/ingest',json=event(image=image()),headers=headers)
            self.assertEqual(response.status_code,200);self.assertNotIn(token,'\n'.join(logs.output))
            self.assertEqual(client.post('/api/links/ingest',content=b'x'*(2*1024*1024+1),headers=headers).status_code,413)
            self.assertEqual(client.get('/api/links').status_code,401)
            listing=client.get('/api/links',headers={'x-fixture-session':'yes'}).json();sha=listing['items'][0]['sha']
            self.assertEqual(client.get('/api/links/shots/'+sha).status_code,401)
            self.assertEqual(client.get('/api/links/shots/'+sha,headers={'x-fixture-session':'yes'}).status_code,200)

    def test_pagination_stable_unique_ids(self):
        for n in range(3):self.store.ingest(event(video_id=str(100+n),url=f'https://www.douyin.com/video/{100+n}'))
        first=self.store.listing(limit=2);second=self.store.listing(limit=2,offset=first['nextOffset'])
        self.assertEqual(first['total'],3);self.assertIsNone(second['nextOffset'])
        self.assertEqual(len({r['id'] for r in first['items']+second['items']}),3)

    def test_exactly_four_routes_even_with_old_write_flags(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from cloud.link_routes import mount_links
        app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        mount_links(app,{'link_evidence_enabled':True,'link_evidence_dir':str(self.root/'route-inventory'),
                        'link_decisions_enabled':True,'link_delivery_enabled':True},lambda r:{'user_id':1},lambda *a:None)
        routes={(method,r.path) for r in app.routes for method in r.methods}
        self.assertEqual(routes,{('POST','/api/links/ingest'),('GET','/api/links'),('GET','/api/links/shots/{sha}'),('GET','/links')})
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/links/changes?source=fixture').status_code,404)
            self.assertEqual(client.post('/api/links/record/decision',json={}).status_code,404)
            self.assertEqual(client.post('/api/links/deliveries',json={}).status_code,404)


if __name__=='__main__':unittest.main()
