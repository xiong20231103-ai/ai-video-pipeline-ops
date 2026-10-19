const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{Buffer}=require('node:buffer');
const {chromium}=require('playwright'),fixture=require('../src/test/fixture.json'),root=path.resolve(__dirname,'../../static/v2'),evidence=process.env.V2_EVIDENCE_DIR;
const requests=[],errors=[],violations=[],screenshots=[],dialogs=[];
const csp="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'";
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.OPS_UI_BROWSER_PATH});try{
 if(evidence)fs.mkdirSync(evidence,{recursive:true});
 for(const mode of ['home','cloud'])for(const [width,height]of [[1920,1080],[1440,900],[1366,768],[375,812]])for(const theme of ['dark','light']){
 const origin=mode==='home'?'http://100.92.17.9:8765':'https://cloud-fixture.invalid',context=await browser.newContext({viewport:{width,height}});let stage='idle',accepted=false,proof=false,received;
 const data=JSON.parse(JSON.stringify(fixture.dashboard));data.services=[{key:'workbench',online:false}];data.currentTaskBox={batchId:'synthetic-batch',current:{taskId:'synthetic-task',attemptId:'synthetic-attempt'}};data.controls.continue={state:'idle',allowed:true};
 await context.route('**/*',async route=>{const req=route.request(),url=new URL(req.url()),key=url.pathname;assert.equal(url.origin,origin);requests.push({mode,path:key,method:req.method(),intercepted:true});
 if(key.startsWith('/static/v2/')){const file=path.resolve(root,decodeURIComponent(key.slice(11)));assert(file.startsWith(root+path.sep));return route.fulfill({contentType:{'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml'}[path.extname(file)]||'text/plain',headers:{'Content-Security-Policy':csp},body:fs.readFileSync(file)});}
 if(req.method()==='POST'){
  assert.equal(key,'/api/control-commands');const body=req.postDataJSON();assert.deepEqual(body.expectedTarget,{batchId:'synthetic-batch',taskId:'synthetic-task',attemptId:'synthetic-attempt'});assert.equal(typeof body.clientRequestId,'string');accepted=true;stage='running';received=body;
  if(mode==='home')return route.fulfill({json:{commandId:'synthetic-home',state:'persisted',allowed:false,message:'隔离命令已保存'}});
  assert.equal(body.clientRequestId,req.headers()['x-client-request-id']);assert(req.headers()['x-csrf-token']);return route.fulfill({status:202,json:{cloudCommand:true,state:'queued',cloudCommandId:'synthetic-cloud'}});
 }
 if(key==='/console/commands/synthetic-cloud'||key.startsWith('/console/commands/request/'))return route.fulfill({json:{state:'completed',cloudCommandId:'synthetic-cloud',result:{kind:'http',httpStatus:200,bodyBase64:Buffer.from(JSON.stringify({commandId:'synthetic-home',state:'persisted',allowed:false,message:'隔离命令已保存'})).toString('base64')}}});
 if(key.startsWith('/api/control-commands/')){const result={commandId:accepted?'synthetic-home':'synthetic-initial',state:stage==='running'?'executing':'idle',allowed:stage!=='running',message:'隔离状态 · 非真实生产'};if(mode==='cloud'&&accepted)assert.equal(key,'/api/control-commands/synthetic-home','must query original home identity');proof=true;return route.fulfill({json:result});}
 if(key==='/auth/options')return route.fulfill({json:{registrationOpen:false}});
 if(key==='/auth/session')return route.fulfill({json:{username:'隔离账号',csrf:'synthetic-csrf'}});
 if(key==='/console/status')return route.fulfill({json:{...fixture.status,canContinue:true,executorAvailable:true,homeReady:true,commandBlocker:null}});
 if(key==='/console/commands')return route.fulfill({json:{items:[]}});
 if(key==='/api/controls/pending-delete')return route.fulfill({json:fixture.pendingDelete});
 if(key==='/api/safety')return route.fulfill({json:fixture.safety});
 if(key.startsWith('/api/dashboard')){data.controls.continue=accepted?{commandId:'synthetic-home',state:'executing',allowed:false,message:'隔离模拟：运行中'}:{state:'idle',allowed:true};return route.fulfill({json:data});}
 throw Error('Unexpected request '+key);
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',e=>{if(e.type()==='error')errors.push(e.text())});page.on('dialog',async d=>{dialogs.push({mode,message:d.message(),accept:stage!=='cancel'});if(stage==='cancel')await d.dismiss();else await d.accept();});await page.exposeFunction('recordCsp',x=>violations.push(x));await page.addInitScript(()=>document.addEventListener('securitypolicyviolation',e=>window.recordCsp({directive:e.violatedDirective,blocked:e.blockedURI})));
 await page.goto(origin+'/static/v2/index.html#commands',{waitUntil:'networkidle'});if(theme==='light')await page.getByRole('button',{name:'切换到浅色主题'}).click();await page.evaluate(()=>{const label=document.createElement('div');label.textContent='隔离夹具 · 非真实生产';label.style.cssText='position:fixed;bottom:8px;left:8px;z-index:2147483647;background:#132033;color:white;padding:6px;border-radius:5px';document.body.append(label)});
 const snap=async suffix=>{const name=`${mode}-${theme}-${suffix}-${width}x${height}.png`;if(evidence)await page.screenshot({path:path.join(evidence,name),animations:'disabled'});screenshots.push(name);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),'page overflow')};
 const button=page.getByRole('button',{name:'安全继续当前项目',exact:true});await button.waitFor();await button.isEnabled();await snap('eligible');stage='cancel';const before=requests.filter(x=>x.method==='POST').length;await button.click();assert.equal(requests.filter(x=>x.method==='POST').length,before);stage='idle';await button.click();await page.getByRole('button',{name:/正在安全继续/}).waitFor({timeout:10000}).catch(async error=>{console.error(JSON.stringify({mode,stage,accepted,received,proof,dialogs,requests:requests.slice(-12),body:(await page.locator('body').innerText()).slice(-4500)}));if(evidence)await page.screenshot({path:path.join(evidence,'failed-debug.png')});throw error});assert(received);await snap('locked');assert(await page.getByRole('button',{name:/正在安全继续/}).isDisabled());
 if(mode==='cloud'){await page.reload({waitUntil:'networkidle'});await page.getByRole('button',{name:'按原命令编号查询与对账'}).click();assert(proof);assert.equal(requests.filter(x=>x.method==='POST').length,before+1);}
 await context.close();
 }
 assert.deepEqual(errors,[]);assert.deepEqual(violations,[]);const result={verified:true,productionAccess:false,allRequestsIntercepted:true,requests,errors,violations,screenshots,dialogs};if(evidence)fs.writeFileSync(path.join(evidence,'safe-continue-browser-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({verified:true,requests:requests.length,posts:requests.filter(r=>r.method==='POST').length,screenshots:screenshots.length,errors,violations}));
}finally{await browser.close()}})().catch(error=>{console.error(error);process.exitCode=1});
