const { Buffer } = require('node:buffer')
// All requests are intercepted. Even home-shaped origins never reach a network.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.OPS_UI_PLAYWRIGHT||'playwright');
const fixture=require('../src/test/fixture.json'),root=path.resolve(__dirname,'../../static/v2'),evidence=process.env.V2_EVIDENCE_DIR;
const csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'";
const errors=[],requests=[],dialogs=[],shots=[];
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.OPS_UI_BROWSER_PATH});try{
if(evidence)fs.mkdirSync(evidence,{recursive:true});
for(const mode of ['home','cloud'])for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[375,812]]){
const origin=mode==='home'?'http://100.92.17.9:8765':'https://cloud-fixture.invalid';
const context=await browser.newContext({viewport:{width,height}}),commands=new Map();let next=0;
await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url());assert.equal(url.origin,origin);requests.push({mode,path:url.pathname,method:req.method(),intercepted:true});
if(url.pathname.startsWith('/static/v2/')){assert.equal(req.method(),'GET');const file=path.resolve(root,decodeURIComponent(url.pathname.slice(11)));assert(file.startsWith(root+path.sep));return route.fulfill({status:200,contentType:{'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'}[path.extname(file)]||'text/plain',headers:{'Content-Security-Policy':csp},body:fs.readFileSync(file)});}
const key=url.pathname;
if(req.method()==='POST'){
assert(['/api/controls/upload/rescan','/api/controls/upload/verify-history'].includes(key));assert.deepEqual(req.postDataJSON(),{});
if(mode==='cloud'){assert.equal(req.headers()['x-csrf-token'],'synthetic-only');assert(req.headers()['x-client-request-id']);const id='fixture-'+(++next);commands.set(id,{cloudCommandId:id,state:'completed',result:{kind:'http',httpStatus:200,bodyBase64:Buffer.from(JSON.stringify({state:'completed',message:'隔离模拟：已收到家里 HTTP 回执'})).toString('base64')}});return route.fulfill({status:202,json:{cloudCommand:true,state:'queued',cloudCommandId:id}});}
return route.fulfill({json:{state:'completed',message:'隔离模拟：上传检查已完成'}});
}
assert.equal(req.method(),'GET');
const command=[...commands].find(([id])=>key==='/console/commands/'+id)?.[1];
const body=command|| (key==='/auth/options'?{registrationOpen:false}:key==='/auth/session'?{username:'隔离账号',csrf:'synthetic-only'}:key==='/console/status'?fixture.status:key==='/console/commands'?{items:[...commands.values()]}:key==='/api/safety'?fixture.safety:key==='/api/controls/pending-delete'?fixture.pendingDelete:key.startsWith('/api/dashboard')?fixture.dashboard:null);
assert(body,'Unexpected endpoint '+key);return route.fulfill({json:body});});
const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',entry=>{if(entry.type()==='error')errors.push(entry.text())});
let accept=false;page.on('dialog',async dialog=>{dialogs.push({mode,text:dialog.message()});if(accept)await dialog.accept();else await dialog.dismiss();});
await page.goto(origin+'/static/v2/index.html#uploads',{waitUntil:'networkidle'});
for(const theme of ['dark','light']){if(theme==='light')await page.getByRole('button',{name:'切换到浅色主题'}).click();await page.locator('[data-v2-upload="rescan"]').waitFor();if(evidence){const name=`${mode}-${theme}-uploads-${width}x${height}.png`;await page.screenshot({path:path.join(evidence,name),animations:'disabled'});shots.push(name);}}
const before=requests.filter(x=>x.method==='POST').length;
await page.locator('[data-v2-upload="rescan"]').click();assert.equal(requests.filter(x=>x.method==='POST').length,before,'cancel sent a POST');
accept=true;await page.locator('[data-v2-upload="rescan"]').click();await page.getByRole('status').filter({hasText:'隔离模拟'}).waitFor();
assert.equal(requests.filter(x=>x.method==='POST').length,before+1);
await page.reload({waitUntil:'networkidle'});await page.locator('[data-v2-upload="verify-history"]').waitFor();assert.equal(requests.filter(x=>x.method==='POST').length,before+1,'reload repeated POST');
await page.locator('[data-v2-upload="verify-history"]').click();await page.getByRole('status').filter({hasText:'隔离模拟'}).waitFor();assert.equal(requests.filter(x=>x.method==='POST').length,before+2);
assert.equal(await page.locator('[data-v2-write]:not(:disabled)').count(),0,'unrelated write was enabled');
await context.close();}
assert.deepEqual(errors,[]);const result={verified:true,productionAccess:false,allRequestsIntercepted:true,requests,dialogs,screenshots:shots,errors};if(evidence)fs.writeFileSync(path.join(evidence,'upload-browser-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({verified:true,productionAccess:false,requests:requests.length,posts:requests.filter(x=>x.method==='POST').length,screenshots:shots.length,errors}));
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1});
