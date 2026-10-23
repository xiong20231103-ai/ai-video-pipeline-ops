"""Opt-in evidence API. Separate credentials from the existing agent."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from cloud.link_evidence import Evidence


def mount_links(app, config, session, csrf, rate):
    if config.get('link_evidence_enabled') is not True:
        return
    evidence = Evidence(config.get('link_evidence_dir','/srv/ops-console/link-evidence'))
    app.state.link_evidence = evidence
    from cloud.link_delivery import LinkDelivery
    delivery = LinkDelivery(evidence,app.state.commands) if hasattr(app.state,'commands') else None

    def auth(request):
        token = os.environ.get('LINK_EVIDENCE_TOKEN','')
        if not token:
            raise HTTPException(503,'link_token_not_configured')
        if not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+token):
            raise HTTPException(401,'link_auth_required')
        rate(request,'links',60)

    async def body(request):
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>2*1024*1024:
                raise HTTPException(413,'link_request_too_large')
        try:
            value=json.loads(raw)
            if not isinstance(value,dict): raise ValueError()
            return value
        except (ValueError,UnicodeError):
            raise HTTPException(400,'invalid_link_json') from None

    @app.post('/api/links/ingest')
    async def ingest(request:Request):
        auth(request)
        data=await body(request)
        try:
            return evidence.ingest(data)
        except (ValueError,TypeError,OSError):
            raise HTTPException(400,'invalid_link_event') from None

    @app.get('/api/links')
    def listing(request:Request):
        session(request)
        return evidence.listing()

    @app.get('/api/links/shots/{sha}')
    def shot(sha:str,request:Request):
        session(request)
        if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
            raise HTTPException(404,'image_not_found')
        with evidence.db() as db:
            row=db.execute('SELECT path FROM shots WHERE sha=?',(sha,)).fetchone()
        if not row or not (evidence.root/row['path']).is_file():
            raise HTTPException(404,'image_expired')
        return FileResponse(evidence.root/row['path'],media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})

    @app.post('/api/links/{identifier}/decision')
    async def decide(identifier:str,request:Request):
        # A separate rollout gate: ingest/read can ship before remote decisions.
        if config.get('link_decisions_enabled') is not True:
            raise HTTPException(409,'remote_decisions_not_enabled')
        row=session(request)
        csrf(request,row)
        data=await body(request)
        try:
            return evidence.decide(identifier,data.get('revision'),data.get('decision'),data.get('requestId'),'user:'+str(row['user_id']))
        except ValueError:
            raise HTTPException(409,'decision_conflict_or_not_displayable') from None

    @app.get('/links')
    def page(request:Request):
        session(request)
        return HTMLResponse((Path(__file__).parent/'links.html').read_text(encoding='utf-8'))

    @app.post('/api/links/deliveries')
    async def submit_links(request:Request):
        if config.get('link_delivery_enabled') is not True or delivery is None:
            raise HTTPException(409,'link_delivery_not_enabled')
        user=session(request);csrf(request,user);rate(request,'link-delivery',30)
        data=await body(request)
        actor='user:'+str(user['user_id'])
        try:
            delivery.prepare(actor,data.get('requestId'),data.get('ids'),data.get('payload'),data.get('kind'),data.get('confirm'))
            return delivery.dispatch(actor,data['requestId'])
        except ValueError:
            raise HTTPException(409,'link_delivery_selection_or_identity_conflict') from None

    @app.get('/api/links/deliveries/{request_id}')
    def submission_status(request_id:str,request:Request):
        user=session(request)
        if delivery is None:
            raise HTTPException(409,'link_delivery_not_enabled')
        try:
            return delivery.status('user:'+str(user['user_id']),request_id)
        except ValueError:
            raise HTTPException(404,'link_delivery_not_found') from None
