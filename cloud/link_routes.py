"""Opt-in evidence API. Separate credentials from the existing agent."""
import json
import os
from pathlib import Path
import secrets
from PIL import Image
from fastapi import Request, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from cloud.link_evidence import Evidence


def mount_links(app, config, session, rate):
    if config.get('link_evidence_enabled') is not True:
        return
    evidence = Evidence(config.get('link_evidence_dir','/srv/ops-console/link-evidence'))
    app.state.link_evidence = evidence
    def auth(request):
        rate(request,'links',60)
        token = os.environ.get('LINK_EVIDENCE_TOKEN','')
        if not token:
            raise HTTPException(503,'link_token_not_configured')
        header=request.headers.get('authorization','').encode('utf-8','surrogateescape')
        if not secrets.compare_digest(header, ('Bearer '+token).encode('utf-8','surrogateescape')):
            raise HTTPException(401,'link_auth_required')

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
        except (ValueError,TypeError,OSError,Image.DecompressionBombError):
            raise HTTPException(400,'invalid_link_event') from None

    @app.get('/api/links')
    def listing(request:Request,limit:int=1000,offset:int=0):
        session(request)
        try:return evidence.listing(limit,offset)
        except ValueError:raise HTTPException(400,'invalid_link_page') from None

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

    @app.get('/links')
    def page(request:Request):
        session(request)
        return HTMLResponse((Path(__file__).parent/'links.html').read_text(encoding='utf-8'))
