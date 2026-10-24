"""Explicit local-only browser proof, independent of production/WebChat.

Run from repo root: python tests/link_browser_smoke.py --chrome PATH
Requires Playwright package and an existing Chrome; never downloads a browser.
"""
import argparse
import base64
from io import BytesIO
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from PIL import Image
from playwright.sync_api import sync_playwright
import uvicorn
from cloud.link_routes import mount_links


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chrome',required=True);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='cloud-links-browser-') as directory:
        app=FastAPI()
        mount_links(app,{'link_evidence_enabled':True,'link_evidence_dir':directory},
                    lambda r:{'user_id':1},lambda *a:None)
        evidence=app.state.link_evidence
        for n in range(5):
            data={'source':'browser-test','platform':'douyin','video_id':str(100+n),'judge_round':'v1:1','seq':n+1,
                  'url':f'https://www.douyin.com/video/{100+n}','review':'pending' if n<2 else 'confirmed',
                  'delivery':'not_applicable' if n<2 else 'waiting','date':'2026-10-23','category':'synthetic',
                  'displayable':True,'replace_id':'24' if n==3 else None}
            if n<4:
                out=BytesIO();Image.new('RGB',(100,50),(40*n,40,150)).save(out,'JPEG')
                data['image']=base64.b64encode(out.getvalue()).decode()
            evidence.ingest(data)
        listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.05)
            if not server.started:raise RuntimeError('test_server_not_started')
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=args.chrome,headless=True)
                try:
                    page=browser.new_page()
                    origin=f'http://127.0.0.1:{port}'
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin+'/') else route.abort())
                    page.goto(origin+'/links')
                    page.wait_for_function("document.querySelectorAll('article').length===5 && [...document.images].length===4 && [...document.images].every(i=>i.complete&&i.naturalWidth>0)")
                    initial=page.locator('img').count()
                    page.select_option('#review','confirmed')
                    page.wait_for_function("document.querySelectorAll('article').length===3")
                    page.reload()
                    page.wait_for_function("document.querySelectorAll('article').length===5 && [...document.images].length===4 && [...document.images].every(i=>i.complete&&i.naturalWidth>0)")
                    print(json.dumps({'expectedImages':4,'loadedImages':initial,'loadedAfterRefresh':page.locator('img').count(),
                                      'historyLinks':5,'filterConfirmed':3,'network':'isolated_loopback_only','webchatVerified':False}))
                finally:browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=10);listener.close()


if __name__=='__main__':main()
