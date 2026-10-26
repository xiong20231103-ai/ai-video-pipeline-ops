const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const fixture=require('../src/test/fixture.json'),root=path.resolve(__dirname,'../../static/v2'),evidence=process.env.V2_EVIDENCE_DIR,requests=[],errors=[],expectedRejections=[],violations=[],screenshots=[],dialogs=[];
const csp="default-src 'self'; script-src 'self' ; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'";
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.OPS_UI_BROWSER_PATH});try{if(evidence)fs.mkdirSync(evidence,{recursive:true});
 for(const mode of ['home','cloud'])for(const [width,height] of [[1920,1080],[1440,900],[1366,768],[375,812]]){
 const origin=mode==='home'?'http://100.92.17.9:8765':'https://cloud-fixture.invalid',context=await browser.newContext({viewport:{width,height}});
 await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url()),key=url.pathname;assert.equal(url.origin,origin);requests.push({mode,path:key,method:req.method(),intercepted:true});
 if(key.startsWith('/static/v2/')){const file=path.resolve(root,decodeURIComponent(key.slice(11)));assert(file.startsWith(root+path.sep));return route.fulfill({contentType:{'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'}[path.extname(file)]||'text/plain',headers:{'Content-Security-Policy':csp},body:fs.readFileSync(file)});}
 if(req.method()==='POST'){
  if(mode==='home'){assert.equal(key,'/api/controls/testing/reset');assert.deepEqual(req.postDataJSON(),{confirm:'RESET_TEST_RECORDS'});return route.fulfill({json:{message:'隔离测试记录重置',resetAt:'2026-10-20T00:00:00+08:00'}});}
  assert(req.headers()['x-csrf-token']);if(key==='/auth/password'){assert.deepEqual(req.postDataJSON(),{oldPassword:'synthetic-old',newPassword:'synthetic-new-only'});return route.fulfill({status:400,json:{detail:'synthetic-rejected'}})}
  if(key==='/console/backups/request')return route.fulfill({json:{requested:true}});if(key==='/console/backups/fixture-backup/verify')return route.fulfill({json:{verified:false}});throw Error('unexpected cloud POST '+key);
 }
 if(key==='/auth/options')return route.fulfill({json:{registrationOpen:false}});if(key==='/auth/session')return route.fulfill({json:{username:'隔离账号',csrf:'synthetic-only'}});
 const body=key==='/console/status'?fixture.status:key==='/console/commands'?fixture.commands:key==='/console/backups'?fixture.backups:key==='/api/controls/pending-delete'?fixture.pendingDelete:key==='/api/safety'?fixture.safety:key.startsWith('/api/dashboard')?fixture.dashboard:null;assert(body,'Unexpected GET '+key);return route.fulfill({json:body});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',e=>{if(e.type()!=='error')return;const at=e.location().url;if(at===origin+'/auth/password'&&e.text()==='Failed to load resource: the server responded with a status of 400 (Bad Request)')expectedRejections.push({path:'/auth/password',status:400,message:e.text()});else errors.push(e.text())});page.on('dialog',async d=>{dialogs.push({mode,text:d.message()});await d.accept()});await page.exposeFunction('recordCsp',x=>violations.push(x));await page.addInitScript(()=>document.addEventListener('securitypolicyviolation',e=>window.recordCsp({directive:e.violatedDirective,blocked:e.blockedURI})));
 await page.goto(origin+'/static/v2/index.html#commands',{waitUntil:'networkidle'});
 const label=async()=>page.evaluate(()=>{if(document.querySelector('[data-test-label]'))return;const n=document.createElement('div');n.dataset.testLabel='true';n.textContent='隔离夹具 · 非真实生产';n.style.cssText='position:fixed;bottom:8px;left:8px;z-index:2147483647;background:#132033;color:white;padding:6px;border-radius:5px';document.body.append(n)});
 const snap=async suffix=>{await label();const name=`${mode}-${suffix}-${width}x${height}.png`;if(evidence)await page.screenshot({path:path.join(evidence,name),animations:'disabled'});screenshots.push(name);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'page overflow')};
 if(mode==='home'){
 for(const theme of ['dark','light']){if(theme==='light')await page.getByRole('button',{name:'切换到浅色主题'}).click();await page.getByRole('button',{name:'重置全部测试记录'}).click();await page.getByRole('status').filter({hasText:'隔离测试记录重置'}).waitFor();await snap(theme+'-reset');}
 }else{
 assert(await page.getByRole('button',{name:'重置全部测试记录'}).isDisabled());
 // Cloud account actions live on the health view.
 await page.evaluate(()=>{window.location.hash='health'});await page.getByRole('button',{name:'修改密码',exact:true}).waitFor();
 await page.getByRole('button',{name:'修改密码',exact:true}).click();const old=page.getByLabel('当前密码',{exact:true}),next=page.getByLabel('新密码（至少12个字符）',{exact:true});assert.equal(await old.getAttribute('maxlength'),'256');assert.equal(await next.getAttribute('minlength'),'12');assert.equal(await next.getAttribute('maxlength'),'256');
 await old.fill('synthetic-old');await next.fill('synthetic-new-only');await page.getByRole('button',{name:'保存新密码'}).click();await page.getByLabel('账号管理').getByText('未修改，请核对密码后重试',{exact:true}).waitFor();
 for(const theme of ['dark','light']){if(theme==='light')await page.getByRole('button',{name:'切换到浅色主题'}).click();await snap(theme+'-account');}
 await page.evaluate(()=>{window.location.hash='health'});
 await page.getByText('查看备份状态与已完成备份包',{exact:true}).click();await page.getByRole('button',{name:'校验云端文件',exact:true}).click();await page.locator('[data-panel="异地备份（台账与配置）"]').getByText('校验失败：fixture-backup',{exact:true}).waitFor();await page.getByRole('button',{name:'请求一次备份',exact:true}).click();await page.locator('[data-panel="异地备份（台账与配置）"]').getByText('请求已排队；代理配置就绪后执行。稍后刷新列表查看。',{exact:true}).waitFor();assert.equal(await page.getByRole('link',{name:'下载 ledger.enc'}).getAttribute('href'),'/console/backups/fixture-backup/ledger.enc');
 for(const theme of ['light','dark']){if(theme==='dark')await page.getByRole('button',{name:'切换到深色主题'}).click();await snap(theme+'-backup');}
 assert.equal(await page.evaluate(()=>Object.values(window.localStorage).some(x=>/synthetic-old|synthetic-new-only/.test(x))),false);
 }
 await context.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(violations,[]);if(evidence)fs.writeFileSync(path.join(evidence,'admin-browser-result.json'),JSON.stringify({verified:true,productionAccess:false,allRequestsIntercepted:true,requests,errors,expectedRejections,violations,screenshots,dialogs},null,2));console.log(JSON.stringify({verified:true,requests:requests.length,posts:requests.filter(r=>r.method==='POST').length,screenshots:screenshots.length,expectedRejections:expectedRejections.length,errors,violations}));
}finally{await browser.close()}})().catch(error=>{console.error(error);process.exitCode=1});
