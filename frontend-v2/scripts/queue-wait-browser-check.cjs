// One REAL 30-second wait in Chromium; every HTTP request is locally intercepted.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const{chromium}=require(process.env.OPS_UI_PLAYWRIGHT||'playwright');
const fixture=require('../src/test/fixture.json'),root=path.resolve(__dirname,'../../static/v2'),evidence=process.env.V2_EVIDENCE_DIR;
const csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'";
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.OPS_UI_BROWSER_PATH});try{
const context=await browser.newContext({viewport:{width:1440,height:900}}),origin='https://queue-fixture.invalid',requests=[],errors=[],violations=[];let queueStarted=null,pendingReplies=0;
await context.route('**/*',async route=>{const request=route.request(),url=new URL(request.url()),key=url.pathname;assert.equal(url.origin,origin);assert.equal(request.method(),'GET');requests.push({path:key,method:'GET',intercepted:true});
if(key.startsWith('/static/v2/')){const file=path.resolve(root,decodeURIComponent(key.slice(11)));assert(file.startsWith(root+path.sep));return route.fulfill({body:fs.readFileSync(file),contentType:{'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'}[path.extname(file)]||'text/plain',headers:{'Content-Security-Policy':csp}});}
if(key.startsWith('/api/dashboard')){queueStarted??=Date.now();if(Date.now()-queueStarted<30000){pendingReplies++;return route.fulfill({status:202,json:{queued:true}});}return route.fulfill({json:fixture.dashboard});}
const body=key==='/auth/options'?{registrationOpen:false}:key==='/auth/session'?{username:'隔离账号',csrf:'synthetic-only'}:key==='/console/status'?fixture.status:key==='/console/commands'?fixture.commands:key==='/api/safety'?fixture.safety:key==='/api/health'?{ok:true}:key==='/api/controls/pending-delete'?fixture.pendingDelete:null;assert(body,'Unexpected GET '+key);return route.fulfill({json:body});
});
const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.on('console',entry=>{if(entry.type()==='error')errors.push(entry.text())});await page.exposeFunction('recordCsp',value=>violations.push(value));await page.addInitScript(()=>document.addEventListener('securitypolicyviolation',event=>window.recordCsp({directive:event.violatedDirective,blocked:event.blockedURI})));
await page.goto(origin+'/static/v2/index.html',{waitUntil:'domcontentloaded'});await page.locator('[data-legacy="heroTitle"]').waitFor({timeout:60000});const elapsedMs=Date.now()-queueStarted;
assert(elapsedMs>=30000);assert(pendingReplies>0&&pendingReplies<120);assert.equal(requests.filter(row=>row.path==='/api/health').length,0,'queue wait was incorrectly interrupted and fell back to health');assert.deepEqual(errors,[]);assert.deepEqual(violations,[]);
if(evidence){fs.mkdirSync(evidence,{recursive:true});await page.screenshot({path:path.join(evidence,'queue-30s-browser.png'),animations:'disabled'});fs.writeFileSync(path.join(evidence,'queue-30s-browser-result.json'),JSON.stringify({verified:true,productionAccess:false,allRequestsIntercepted:true,elapsedMs,pendingReplies,healthFallbacks:0,requests,errors,violations},null,2));}
console.log(JSON.stringify({verified:true,productionAccess:false,elapsedMs,pendingReplies,healthFallbacks:0,errors,violations}));await context.close();
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1});
