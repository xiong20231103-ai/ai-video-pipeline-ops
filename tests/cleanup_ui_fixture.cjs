const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.OPS_UI_PLAYWRIGHT||'playwright');
const root=path.resolve(__dirname,'..'),read=n=>fs.readFileSync(path.join(root,n));
const data={updatedAt:new Date().toISOString(),templates:{items:[]},receiverQueue:{items:[]},projectGaps:{items:[]},controls:{continue:{allowed:false,state:'idle'}}};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.OPS_UI_BROWSER_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'}),results=[];
 try{
  async function scenario(name,run){
   const context=await browser.newContext(),page=await context.newPage(),posts=[],errors=[],dialogs=[],receipts=new Map();let delayExecute=false,extraTest=false,extraManual=false;
   page.on('pageerror',e=>errors.push(e.message));
   page.on('dialog',async d=>{dialogs.push({type:d.type(),message:d.message()});if(d.type()==='prompt')await d.accept(d.message().includes('EMPTY_PENDING')?'EMPTY_PENDING_DELETE_NOW':d.message().includes('RECYCLE_SELECTED_PRODUCTION')?'RECYCLE_SELECTED_PRODUCTION_FILES':d.message().includes('RECYCLE_SELECTED_CAPCUT')?'RECYCLE_SELECTED_CAPCUT_DRAFTS':'RECYCLE_SELECTED_AUDIO_FILES');else await d.accept();});
   const P='/api/controls/cloud-cleanup/';
   function complete(row){const body=row.target.endsWith('/preview')?{...row.payload,ticket:'opaque-fixture-ticket',snapshotToken:'snapshot-fixture',expiresAt:Math.floor(Date.now()/1000)+120,deletableCount:1,selectedCount:1,blockedCount:0,message:'合成清理预览',count:1,sizeBytes:7,containsTestFiles:extraTest,containsManualOrUnknown:extraManual}: {state:'partial',message:'合成结果：1项移入待删区，1项受保护',moved:1,blocked:[{name:'fixture-protected',reason:'active'}]};return {...row,state:row.target.endsWith('/execute')&&delayExecute?'sent':'completed',result:row.target.endsWith('/execute')&&delayExecute?null:{kind:'http',httpStatus:200,bodyBase64:Buffer.from(JSON.stringify(body)).toString('base64'),contentType:'application/json'}};}
   await page.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());assert.equal(url.origin,'https://fixture.ts.net','No external network allowed');const u=url.pathname;
    if(u==='/')return route.fulfill({contentType:'text/html; charset=utf-8',body:read('static/index.html').toString().replace('<head>','<head><script src="/cloud-readonly.js"></script><script src="/cloud-commands.js"></script><script src="/cloud-cleanup.js"></script>')});
    if(/^\/cloud-(readonly|commands|cleanup)\.js$/.test(u))return route.fulfill({contentType:'text/javascript',body:read('cloud/'+u.slice(7))});
    if(u.startsWith('/static/'))return route.fulfill({contentType:u.endsWith('.js')?'text/javascript':'text/css',body:read(u.slice(1))});
    if(u==='/auth/session')return route.fulfill({json:{csrf:'fixture-csrf'}});
    if(u==='/console/status')return route.fulfill({json:{executorAvailable:true,homeReady:true,canCleanup:true,canContinue:false,agentOnline:true,engineState:'healthy',heartbeatAgeSeconds:1}});
    if(u==='/console/commands')return route.fulfill({json:{items:[...receipts.values()].map(complete)}});
    if(u.startsWith('/console/commands/')){const row=[...receipts.values()].find(x=>u.endsWith(x.cloudCommandId)||u.endsWith(x.requestId));return row?route.fulfill({json:complete(row)}):route.fulfill({status:404,json:{detail:'missing'}});}
    if(request.method()==='POST'){
     assert(u===P+'preview'||u===P+'execute','Old unsafe POST must never escape');const payload=request.postDataJSON();posts.push({u,payload});assert.equal(request.headers()['x-csrf-token'],'fixture-csrf');
     const row={cloudCommand:true,cloudCommandId:'fixture-cloud-'+posts.length,requestId:request.headers()['x-client-request-id'],target:u,payload,state:'queued',result:null};receipts.set(row.requestId,row);return route.fulfill({status:202,json:row});
    }
    let body={items:[]};
    if(u.startsWith('/api/dashboard'))body=data;
    if(u==='/api/controls/audio-files')body={items:[{audioId:'fixture-audio',name:'合成音频.wav',protected:false,state:'ready',sizeBytes:7}],snapshotToken:'legacy-unused',summary:{}};
    if(u==='/api/controls/production-files')body={items:[{fileId:'fixture-file',name:'合成测试.mp4',protected:false,category:'capcut_test',sizeBytes:7}],summary:{}};
    if(u==='/api/controls/capcut-drafts')body={items:[{draftId:'fixture-draft',name:'合成人工草稿',protected:false,category:'manual',sizeBytes:7}],summary:{}};
    if(u==='/api/controls/pending-delete')body={count:1,sizeBytes:7,needsReview:0};
    if(u===P+'capabilities')body={protocol:1,retentionDays:3,forbiddenDraftRootProtected:true};
    return route.fulfill({headers:{'Content-Type':'application/json','X-Cache-Age-Seconds':'1','X-Source-Health':'{"scanAgeSeconds":1}'},body:JSON.stringify(body)});
   });
   await page.goto('https://fixture.ts.net');await page.waitForFunction(()=>window.opsCloudCanWrite(document.getElementById('previewAudioCleanupButton')));
   await run({page,posts,dialogs,receipts,setDelay:v=>delayExecute=v,setTest:()=>extraTest=true,setManual:()=>extraManual=true});assert.deepEqual(errors,[]);results.push({name,posts:posts.map(x=>({path:x.u,kind:x.payload.kind})),dialogs:dialogs.length,passed:true});await context.close();
  }
  async function choose(page){await page.click('#openAudioManagerButton');await page.check('input[data-audio-id="fixture-audio"]');await page.click('#previewAudioCleanupButton');await page.waitForFunction(()=>document.getElementById('audioCleanupPreview').textContent.includes('合成清理预览'));}
  await scenario('checkbox-preview-typed-confirm-partial-result',async({page,posts,dialogs})=>{await choose(page);await page.click('#confirmAudioCleanupButton');await page.waitForFunction(()=>document.getElementById('audioCleanupResult').textContent.includes('1项移入待删区'));assert.equal(posts.length,2);assert.deepEqual(posts[1].payload.ids,['fixture-audio']);assert(dialogs.some(x=>x.type==='prompt'));assert(!(await page.evaluate(()=>JSON.stringify(localStorage))).includes('opaque-fixture-ticket'));});
  await scenario('expired-preview-no-execute-post',async({page,posts})=>{await choose(page);await page.evaluate(()=>{const old=performance.now.bind(performance);performance.now=()=>old()+121000;});await page.click('#confirmAudioCleanupButton');await page.waitForFunction(()=>document.getElementById('audioCleanupPreview').textContent.includes('已过期'));assert.equal(posts.length,1);});
  await scenario('reload-query-original-id-no-repost',async({page,posts,setDelay})=>{await choose(page);setDelay(true);await page.click('#confirmAudioCleanupButton');await page.waitForTimeout(300);assert.equal(posts.length,2);await page.reload();await page.waitForTimeout(1200);assert.equal(posts.length,2);assert((await page.locator('[data-cloud-commands]').innerText()).includes('已发家里'));});
  await scenario('pending-delete-two-typed-confirmations',async({page,posts,dialogs})=>{await page.evaluate(()=>refreshPendingDelete());await page.click('#emptyPendingDeleteButton');await page.waitForFunction(()=>document.getElementById('pendingDeleteLastResult')?.textContent.includes('合成结果'));assert.equal(posts.length,2);assert.equal(posts[1].payload.kind,'pending');assert.equal(dialogs.filter(x=>x.type==='prompt').length,2);});
  await scenario('test-files-extra-confirmation',async({page,posts,dialogs,setTest})=>{setTest();await page.click('#openProductionManagerButton');await page.check('input[data-production-id="fixture-file"]');await page.click('#previewProductionCleanupButton');await page.waitForFunction(()=>document.getElementById('productionCleanupPreview').textContent.includes('合成清理预览'));await page.click('#confirmProductionCleanupButton');await page.waitForFunction(()=>document.getElementById('productionCleanupResult').textContent.includes('合成结果'));assert.equal(posts.length,2);assert(dialogs.some(x=>x.message.includes('包含测试文件')));});
  await scenario('manual-unknown-extra-confirmation',async({page,posts,dialogs,setManual})=>{setManual();await page.click('#openDraftManagerButton');await page.check('input[data-draft-id="fixture-draft"]');await page.click('#previewDraftCleanupButton');await page.waitForFunction(()=>document.getElementById('draftCleanupPreview').textContent.includes('合成清理预览'));await page.click('#confirmDraftCleanupButton');await page.waitForFunction(()=>document.getElementById('draftCleanupResult').textContent.includes('合成结果'));assert.equal(posts.length,2);assert.equal(posts[1].payload.includeUnknown,true);assert(dialogs.filter(x=>x.message.includes('人工或来源不明')).length>=2);});
  console.log(JSON.stringify({network:'ALL intercepted; no home or cloud reached',results},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
