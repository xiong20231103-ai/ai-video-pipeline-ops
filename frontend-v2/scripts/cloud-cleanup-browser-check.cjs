const {setTimeout}=require('node:timers');
const {Buffer}=require('node:buffer');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.OPS_UI_PLAYWRIGHT||'playwright');
const fixture=require('../src/test/fixture.json'),root=path.resolve(__dirname,'../../static/v2'),evidence=process.env.V2_EVIDENCE_DIR;
const csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'";
const specs={drafts:{title:'CapCut 草稿',endpoint:'capcut-drafts',id:'draftId',ids:'draftIds',action:'cleanup',confirm:'RECYCLE_SELECTED_CAPCUT_DRAFTS'},audio:{title:'音频文件',endpoint:'audio-files',id:'audioId',ids:'audioIds',action:'recycle',confirm:'RECYCLE_SELECTED_AUDIO_FILES'},production:{title:'生产文件',endpoint:'production-files',id:'fileId',ids:'fileIds',action:'recycle',confirm:'RECYCLE_SELECTED_PRODUCTION_FILES'}};
const requests=[],errors=[],dialogs=[],screenshots=[],violations=[],expectedNotFound=[],expectedConsole=[],notFoundUrls=new Set();let raceInjected=false;
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.OPS_UI_BROWSER_PATH});try{
if(evidence)fs.mkdirSync(evidence,{recursive:true});
for(const mode of ['cloud'])for(const [width,height]of [[1920,1080],[1440,900],[1366,768],[375,812]]){
 const origin=mode==='home'?'http://100.92.17.9:8765':'https://cloud-fixture.invalid',context=await browser.newContext({viewport:{width,height}});let pendingCount=1,accept=true,sequence=0;const commands=new Map(),requestIds=new Map();
 await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url()),key=url.pathname;assert.equal(url.origin,origin);requests.push({mode,path:key,method:req.method(),intercepted:true});
 if(key.startsWith('/static/v2/')){assert.equal(req.method(),'GET');const file=path.resolve(root,decodeURIComponent(key.slice(11)));assert(file.startsWith(root+path.sep));return route.fulfill({contentType:{'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'}[path.extname(file)]||'text/plain',headers:{'Content-Security-Policy':csp},body:fs.readFileSync(file)});}
 const kind=Object.keys(specs).find(kind=>key.startsWith('/api/controls/'+specs[kind].endpoint)),spec=specs[kind];
 if(req.method()==='POST'){
  assert.equal(mode,'cloud');assert(key==='/api/controls/cloud-cleanup/preview'||key==='/api/controls/cloud-cleanup/execute','home POST forbidden '+key);const body=req.postDataJSON();assert(req.headers()['x-csrf-token']);assert(req.headers()['x-client-request-id']);
  const spec=specs[body.kind];if(body.kind!=='pending')assert.deepEqual(body.ids,['server-object']);else assert.deepEqual(body.ids,[]);
  let result;
  if(key.endsWith('/preview'))result={kind:body.kind,ids:body.ids,ticket:'synthetic-ticket-'+(++sequence),expiresAt:2000000000,snapshotToken:'synthetic-token',includeUnknown:body.includeUnknown,message:'隔离模拟预览',deletableCount:1,blockedCount:1,sizeBytes:1024,deletable:[],blocked:[{name:'模拟受保护文件',reason:'模拟活动租约'}],containsManualOrUnknown:body.kind==='drafts',containsTestFiles:body.kind==='production'};
  else {assert.equal(body.snapshotToken,'synthetic-token');assert(body.ticket.startsWith('synthetic-ticket-'));assert.equal(body.confirm,body.kind==='pending'?'EMPTY_PENDING_DELETE_NOW':spec.confirm);if(body.kind==='pending')pendingCount=0;result={state:'partial_failed',message:'隔离模拟：部分失败，请看逐项结果',results:[{name:'模拟失败文件',reason:'模拟共享引用'}]};}
  const id='synthetic-'+(++sequence);requestIds.set(req.headers()['x-client-request-id'],id);commands.set(id,{cloudCommand:true,cloudCommandId:id,state:'completed',result:{kind:'http',httpStatus:200,bodyBase64:Buffer.from(JSON.stringify(result)).toString('base64')}});return route.fulfill({status:202,json:{cloudCommand:true,cloudCommandId:id,state:'queued'}});
 }
 if(key.startsWith('/console/commands/request/')){
  const requestId=key.split('/').pop(),id=requestIds.get(requestId);
  if(id)return route.fulfill({json:commands.get(id)});
  // A persisted submitting receipt can be polled BEFORE CSRF/receive finishes.
  // This is an intentional API 404, never an asset fallback or missing route.
  const original=await req.frame().evaluate(id=>JSON.parse(window.localStorage.getItem('ops-command-receipts-v1')||'[]').some(r=>r.requestId===id&&r.state==='submitting'&&!r.cloudCommandId),requestId);
  assert(original,'unexpected missing request identity '+key);notFoundUrls.add(req.url());expectedNotFound.push({path:key,status:404,reason:'persisted request not yet received',intercepted:true});
  return route.fulfill({status:404,json:{detail:'尚未收件'}});
 }
 if(key==='/auth/session'&&!raceInjected){
  const submitting=await req.frame().evaluate(()=>JSON.parse(window.localStorage.getItem('ops-command-receipts-v1')||'[]').some(r=>r.state==='submitting'));
  if(submitting){raceInjected=true;await new Promise(resolve=>setTimeout(resolve,3500));}
 }
 if(key.startsWith('/console/commands/synthetic-')){const answer=commands.get(key.split('/').pop());assert(answer);return route.fulfill({json:answer});}
 assert.equal(req.method(),'GET');
 if(key==='/api/controls/cloud-cleanup/capabilities')return route.fulfill({json:{protocol:1}});
 if(spec)return route.fulfill({json:{items:[{[spec.id]:'server-object',name:'模拟文件',category:kind==='drafts'?'formal':'capcut_test',categoryLabel:'模拟类别',defaultSelected:kind==='production',sizeBytes:1024,date:'2026-10-19',updatedAt:'2026-10-19T12:00:00+08:00',project:'隔离项目',material:'模拟材料',language:'DE',audioBatch:'A',sourceLabel:'隔离来源'}, {[spec.id]:'locked',name:'模拟受保护文件',protected:true,protectedReason:'模拟活动租约',sizeBytes:2048}],counts:{total:2,protected:1,deletable:1,categories:{capcut_test:{label:'模拟测试文件',total:1,sizeBytes:1024,deletable:1,protected:0}}},snapshotToken:'synthetic-list'}});
 const body=key==='/auth/options'?{registrationOpen:false}:key==='/auth/session'?{username:'隔离账号',csrf:'synthetic-only'}:key==='/console/status'?{...fixture.status,canCleanup:true,executorAvailable:true,homeReady:true,commandBlocker:null}:key==='/console/commands'?fixture.commands:key==='/api/controls/pending-delete'?{count:pendingCount,sizeBytes:pendingCount*1024,nextPurgeAt:'2026-10-22T12:00:00+08:00'}:key==='/api/safety'?fixture.safety:key.startsWith('/api/dashboard')?fixture.dashboard:null;assert(body,'Unexpected GET '+key);return route.fulfill({json:body});
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));page.on('console',entry=>{if(entry.type()!=='error')return;const url=entry.location().url;
 if(notFoundUrls.has(url)&&entry.text()==='Failed to load resource: the server responded with a status of 404 (Not Found)')expectedConsole.push({url,message:entry.text(),reason:'modeled request-id query before receive'});
 else errors.push({url,message:entry.text()});});page.on('dialog',async dialog=>{dialogs.push({mode,type:dialog.type(),text:dialog.message(),accepted:accept});if(dialog.type()==='prompt'&&accept){const magic=Object.values(specs).map(s=>s.confirm).concat('EMPTY_PENDING_DELETE_NOW').find(x=>dialog.message().includes(x));assert(magic);await dialog.accept(magic);}else if(dialog.type()==='alert'||accept)await dialog.accept();else await dialog.dismiss();});
 await page.exposeFunction('recordCsp',value=>violations.push(value));await page.addInitScript(()=>document.addEventListener('securitypolicyviolation',event=>window.recordCsp({directive:event.violatedDirective,blocked:event.blockedURI})));
 await page.goto(origin+'/static/v2/index.html#files',{waitUntil:'networkidle'}); await page.evaluate(()=>{const label=document.createElement('div');label.textContent='隔离夹具 · 非真实生产';label.style.cssText='position:fixed;bottom:8px;left:8px;z-index:2147483647;background:#132033;color:#fff;border:1px solid #4499ff;border-radius:6px;padding:5px 8px;font-size:11px;pointer-events:none';document.body.append(label)});
 for(const theme of ['dark','light']){
  if(theme==='light')await page.getByRole('button',{name:'切换到浅色主题'}).click();
  for(const[kind,spec]of Object.entries(specs)){
   await page.getByRole('button',{name:'管理 '+spec.title,exact:true}).click();const checkbox=page.getByRole('checkbox',{name:'选择 模拟文件'});await checkbox.waitFor();assert(await page.getByRole('checkbox',{name:'选择 模拟受保护文件'}).isDisabled());
   if(kind!=='production')await checkbox.check();
   const snap=async suffix=>{const name=`${mode}-${theme}-${kind}-${suffix}-${width}x${height}.png`;if(evidence)await page.screenshot({path:path.join(evidence,name),animations:'disabled'});screenshots.push(name);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'horizontal page overflow');};
   await snap('list');const preview=page.getByRole('button',{name:kind==='production'?'预览清理':'预览删除',exact:true});
   {
    await preview.click();await page.getByRole('button',{name:'确认移入待删区',exact:true}).waitFor();await snap('preview');
    await page.getByRole('searchbox',{name:'搜索文件'}).fill('模拟');assert.equal(await page.getByRole('button',{name:'确认移入待删区',exact:true}).count(),0);
    await preview.click();const execute=page.getByRole('button',{name:'确认移入待删区',exact:true});await execute.waitFor();const before=requests.filter(row=>row.method==='POST'&&!row.path.endsWith('/preview')).length;
    accept=false;await execute.click();assert.equal(requests.filter(row=>row.method==='POST'&&!row.path.endsWith('/preview')).length,before);accept=true;await execute.click();await page.getByRole('status').filter({hasText:'隔离模拟：部分失败'}).waitFor();await snap('result');
   }
   await page.keyboard.press('Escape');await page.getByRole('heading',{name:'管理 '+spec.title,exact:true}).waitFor({state:'hidden'});
  }
 }
 if(mode==='cloud'){await page.getByRole('button',{name:/^立即清空待删区（/}).click();await page.getByRole('button',{name:/^立即清空待删区（/}).waitFor({state:'hidden'});}
 await context.close();
}
const result={productionAccess:false,allRequestsIntercepted:true,requests,errors,violations,dialogs,screenshots,raceInjected,expectedNotFound,expectedConsole};
if(evidence)fs.writeFileSync(path.join(evidence,'cloud-cleanup-browser-result.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({requests:requests.length,posts:requests.filter(row=>row.method==='POST').length,screenshots:screenshots.length,raceInjected,expectedNotFound,expectedConsole,errors,violations}));
assert(raceInjected,'receive race must be exercised');assert(expectedNotFound.length>0,'poll-before-receive must query original missing identity');assert.deepEqual(errors,[]);assert.deepEqual(violations,[]);
assert.equal(requests.filter(row=>row.method==='POST').length,80,'a pending receive must not cause duplicate command POST');
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1});
