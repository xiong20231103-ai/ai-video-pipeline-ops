import base64
from io import BytesIO
import sys
from pathlib import Path

import pytest
from PIL import Image
from cloud.link_evidence import Evidence, DAY


def event(seq=1, **extra):
    return dict(source='test-company',platform='douyin',video_id='123',judge_round='v1:1',seq=seq,url='https://www.douyin.com/video/123',review='pending',delivery='not_applicable',displayable=True,**extra)


def image():
    out=BytesIO();Image.new('RGB',(80,40),'red').save(out,'JPEG');return base64.b64encode(out.getvalue()).decode()


def test_stale_and_cloud_decision(tmp_path):
    store=Evidence(tmp_path)
    identifier=store.ingest(event(image=image()))['id']
    result=store.decide(identifier,0,'confirmed','decision-1','user:1')
    assert store.decide(identifier,0,'confirmed','decision-1','user:1')==result
    with pytest.raises(ValueError):store.decide(identifier,0,'rejected','decision-2','user:1')
    store.ingest(event(2))
    store.ingest(event(1))
    row=store.listing()['items'][0]
    assert (row['review'],row['delivery'])==('confirmed','waiting')
    assert row['seq']==2
    changes=store.changes('test-company')
    assert len(changes['items'])==1
    assert changes['items'][0]['data']['review']=='confirmed'
    assert store.changes('other-company')['items']==[]
    assert store.changes('test-company',changes['nextCursor'])['items']==[]


def test_retention_and_pending_protection(tmp_path):
    clock=[100*DAY];store=Evidence(tmp_path,clock=lambda:clock[0])
    identifier=store.ingest(event(image=image()))['id']
    clock[0]+=30*DAY;store.cleanup()
    assert store.listing()['items'][0]['sha']
    store.decide(identifier,0,'rejected','reject','user:1')
    clock[0]+=14*DAY;store.cleanup();assert store.listing()['items'][0]['sha']
    clock[0]+=2*DAY;store.cleanup();assert not store.listing()['items'][0]['sha']
    assert len(store.listing()['items'])==1


def test_historical_and_capacity(tmp_path):
    clock=[100*DAY];store=Evidence(tmp_path,clock=lambda:clock[0],cap=1)
    result=store.ingest(event(image=image()))
    assert result['image']=='capacity_rejected'
    assert store.listing()['capacityReached'] is True
    assert len(store.listing()['items'])==1
    store.cap=100000
    assert store.ingest(event(image=image()))['image']=='stored'
    # Historical processed records use upload time, never updated timestamps.
    data=event(2,image=image());data['review']='confirmed';data['delivery']='waiting'
    store.ingest(data);clock[0]+=16*DAY;store.cleanup()
    assert not store.listing()['items'][0]['sha']


def test_routes_auth_and_body_limit(tmp_path,monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from cloud.link_routes import mount_links
    monkeypatch.setenv('LINK_EVIDENCE_TOKEN','test-only-not-a-real-token')
    app=FastAPI()
    mount_links(app,{'link_evidence_enabled':True,'link_evidence_dir':str(tmp_path)},lambda r:None,lambda *a:None,lambda *a:None)
    client=TestClient(app)
    assert client.post('/api/links/ingest',json=event()).status_code==401
    headers={'Authorization':'Bearer test-only-not-a-real-token'}
    assert client.post('/api/links/ingest',json=event(),headers=headers).status_code==200
    assert client.post('/api/links/ingest',content=b'x'*(2*1024*1024+1),headers=headers).status_code==413
    assert client.post('/api/links/abc/decision',json={},headers=headers).status_code==409


def test_backup_retains_seven(tmp_path):
    clock=[100*DAY];store=Evidence(tmp_path,clock=lambda:clock[0]);store.ingest(event())
    for _ in range(9):
        clock[0]+=DAY;store.backup()
    assert len(list((tmp_path/'db-backups').glob('*.db')))==7
