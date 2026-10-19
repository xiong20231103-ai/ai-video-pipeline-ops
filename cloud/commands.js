'use strict';
// Cloud-only adapter: a 202 receipt never reaches the legacy business renderer.
(() => {
  const network=window.opsCloudNetwork||window.fetch.bind(window), key='ops-command-receipts-v1';
  const active=new Map();let health={},panel,list,specificResult;const eligibility=new Map();
  const pending=new Set(['submitting','queued','leased','sent','unknown']);
  const labels={submitting:'收件结果待查询',queued:'云端排队',leased:'代理已领取，尚未发送',sent:'已发家里，等待 HTTP 回执',unknown:'结果不明，必须在家里对账',completed:'已收到家里 HTTP 回执（业务进度请看原状态）',not_sent:'未发家里',cancelled:'已撤销发送前命令',expired:'发送前已过期',resolved_unknown:'已人工对账；原命令不再重试'};
  let remoteRecords=[];let records=[];
  try{const saved=JSON.parse(localStorage.getItem(key)||'[]');if(Array.isArray(saved))records=saved.filter(r=>r&&typeof r.requestId==='string'&&typeof r.fingerprint==='string'&&typeof r.path==='string').slice(-100);}catch{}
  const save=()=>localStorage.setItem(key,JSON.stringify(records.slice(-100)));
  const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const stable=value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,stable(value[k])])):value;
  const allowedPath=path=>/^\/api\/controls\/tasks\/(create|[^/]+\/(start|cancel|replenish))$/.test(path)||/^\/api\/controls\/upload\/(rescan|verify-history)$/.test(path)||path==='/api/control-commands'||/^\/api\/controls\/cloud-cleanup\/(preview|execute)$/.test(path);
  const unfinished=()=>records.some(r=>pending.has(r.state));
  window.opsCloudCanWrite=button=>{
    if(!health.executorAvailable||!health.homeReady||health.commandBlocker||unfinished()||active.size)return false;
    if(/^(preview|confirm)(Draft|Audio|Production)CleanupButton$/.test(button?.id||'')||button?.id==='emptyPendingDeleteButton')return health.canCleanup===true;
    if(button?.id==='continueCurrentButton')return health.canContinue===true&&button.dataset.allowed==='true';
    if(['uploadRescanButton','historicalCloudVerifyButton'].includes(button?.id))return true;
    return Boolean(button?.closest('#createTaskForm,#replenishForm')||button?.dataset.cloudControl);
  };
  window.opsCloudAcceptForm=form=>Boolean(form.closest('#createTaskForm,#replenishForm'))&&health.executorAvailable&&health.homeReady&&!health.commandBlocker&&!unfinished();
  window.opsCloudContinueResult=result=>{
    const record=[...records].reverse().find(r=>r.path==='/api/control-commands');
    if(record&&pending.has(record.state))return {...result,state:record.state,allowed:false,continueCanRetry:false,message:labels[record.state],cloudCommandId:record.cloudCommandId};
    let observedEligibility=true;
    if(record?.homeCommandId&&result.commandId!==record.homeCommandId){
      observedEligibility=false;
      result=specificResult?.commandId===record.homeCommandId?specificResult:{commandId:record.homeCommandId,state:'persisted',allowed:false,message:'正在按原命令编号查询业务状态'};
    }else if(record?.homeCommandId===result.commandId){specificResult=result;}
    const identity=result.commandId||'';
    if(observedEligibility&&typeof result.allowed==='boolean')eligibility.set(identity,{allowed:result.allowed,continueCanRetry:result.continueCanRetry,continueLockReason:result.continueLockReason,at:performance.now()});
    const proof=eligibility.get(identity),fresh=proof&&performance.now()-proof.at<=10000;
    return {...result,...(fresh?{continueCanRetry:proof.continueCanRetry,continueLockReason:proof.continueLockReason}:{}),allowed:fresh&&proof.allowed===true&&health.canContinue===true&&!health.commandBlocker};
  };
  window.opsCloudContinueTarget=()=>{
    const record=[...records].reverse().find(r=>r.path==='/api/control-commands');
    if(record&&pending.has(record.state))return null;
    return record?.homeCommandId?'/api/control-commands/'+encodeURIComponent(record.homeCommandId):'/api/control-commands/current';
  };
  async function credentials(){const r=await network('/auth/session');if(!r.ok)throw new Error('请重新登录');return r.json();}
  async function postControl(url,body={}){
    const info=await credentials();const r=await network(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify(body)});
    const value=await r.json();if(!r.ok)throw new Error(value.detail||'操作失败');return value;
  }
  function capture(record,value){
    record.state=value.state;record.cloudCommandId=value.cloudCommandId;record.updatedAt=Date.now();
    if(record.path==='/api/control-commands'&&value.result?.kind==='http'){
      try{const body=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(value.result.bodyBase64),c=>c.charCodeAt(0))));if(typeof body.commandId==='string')record.homeCommandId=body.commandId;}catch{}
    }
    save();paint();return value;
  }
  async function query(record){
    const url=record.cloudCommandId?'/console/commands/'+record.cloudCommandId:'/console/commands/request/'+record.requestId;
    const response=await network(url);if(response.status===404)return null;
    if(response.status===401)throw new Error('请重新登录');if(!response.ok)throw new Error('命令状态暂不可用');
    return capture(record,await response.json());
  }
  function finalResponse(value){
    if(value?.state==='completed'&&value.result?.kind==='http'){
      const r=value.result,bytes=Uint8Array.from(atob(r.bodyBase64),c=>c.charCodeAt(0));
      return new Response([204,205,304].includes(r.httpStatus)?null:bytes,{status:r.httpStatus,headers:{'Content-Type':r.contentType}});
    }
    throw new Error(labels[value?.state]||'尚未得到家里回执；请看云端命令面板，不要重复提交');
  }
  async function dispatch(path,payload){
    if(!allowedPath(path))throw new Error('此操作尚未开放云端执行');
    if(path==='/api/controls/cloud-cleanup/preview'){records=records.filter(r=>r.path!==path||pending.has(r.state));save();}
    const comparable={...payload};if(path==='/api/control-commands')delete comparable.clientRequestId;
    const fingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(path+'\n'+JSON.stringify(stable(comparable))))),v=>v.toString(16).padStart(2,'0')).join('');
    if(active.has(fingerprint))return (await active.get(fingerprint)).clone();
    const work=(async()=>{
      let record=records.find(r=>r.fingerprint===fingerprint),value;
      if(!record){
        if(!health.executorAvailable||!health.homeReady||health.commandBlocker||unfinished())throw new Error('家里未就绪，或有待对账命令；尚未提交');
        record={path,fingerprint,requestId:crypto.randomUUID(),state:'submitting',updatedAt:Date.now()};records.push(record);save();paint();
        const body={...payload};if(path==='/api/control-commands')body.clientRequestId=record.requestId;
        const info=await credentials();
        try{
          const response=await network(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf,'X-Client-Request-ID':record.requestId},body:JSON.stringify(body)});
          const answer=await response.json();
          if(response.status===202&&answer.cloudCommand) value=capture(record,answer);
          else if(response.ok)throw new Error('云端未返回排队契约，停止自动处理');
          else{record.state='not_sent';save();paint();throw new Error(answer.detail||'云端拒绝收件');}
        }catch(error){if(record.state==='not_sent')throw error;/* Lost acknowledgement: GET only, never repeat POST. */}
      }
      for(let n=0;n<(path.endsWith('/cloud-cleanup/execute')?1000:180);n++){
        value=value||await query(record);
        if(value&&!['queued','leased','sent'].includes(value.state))return finalResponse(value);
        await delay(1000);value=null;
      }
      throw new Error('仍在查询命令回执；面板将继续查询，不会自动重发。输入内容保留。');
    })();active.set(fingerprint,work);
    try{return (await work).clone();}finally{active.delete(fingerprint);paint();}
  }
  window.opsCloudDispatch=dispatch;
  window.opsCloudWriteFetch=(url,init={})=>{
    if((init.method||'GET').toUpperCase()!=='POST')throw new Error('仅支持已声明的 POST 命令');
    const path=new URL(url,location.origin).pathname;return dispatch(path,init.body?JSON.parse(init.body):{});
  };
  window.opsCloudPostJson=async(url,body)=>{const r=await dispatch(new URL(url,location.origin).pathname,body);const result=await r.json();if(!r.ok)throw new Error(result.detail||'家里拒绝该操作');return result;};
  function paint(){
    if(!list)return;list.replaceChildren();
    for(const record of [...records].reverse().concat(remoteRecords).slice(0,50)){
      const item=document.createElement('li'),text=document.createElement('span');
      text.textContent=record.path+' · '+(labels[record.state]||record.state)+' · '+(record.cloudCommandId||record.requestId);item.append(text);
      if(['submitting','queued','leased'].includes(record.state)){
        const button=document.createElement('button');button.textContent='撤销发送前命令';button.onclick=async()=>{button.disabled=true;try{await postControl(record.remote?'/console/commands/'+record.cloudCommandId+'/cancel':'/console/commands/request/'+record.requestId+'/cancel');record.state='cancelled';save();paint();}catch(error){alert(error.message);}};item.append(button);
      }
      if(record.state==='unknown'){
        const button=document.createElement('button');button.textContent='人工对账后解除阻塞';button.onclick=async()=>{
          const note=prompt('先在家里核实原请求已停止及业务实际结果，再填写对账依据（至少10字）。此操作不会重试原命令。');if(!note)return;
          if(prompt('输入 CONFIRMED_HOME_REQUEST_STOPPED 确认原请求已停止')!=='CONFIRMED_HOME_REQUEST_STOPPED')return;
          try{capture(record,await postControl('/console/commands/'+record.cloudCommandId+'/resolve',{note,confirmation:'CONFIRMED_HOME_REQUEST_STOPPED'}));}catch(error){alert(error.message);}
        };item.append(button);
      }
      if(!record.remote&&!pending.has(record.state)){
        const button=document.createElement('button');button.textContent='结束本次回执，允许新操作';button.onclick=()=>{if(!confirm('结束本次回执后，相同输入的下一次点击将创建新命令。确认？'))return;records=records.filter(r=>r!==record);save();paint();};item.append(button);
      }
      list.append(item);
    }
    window.dispatchEvent(new Event('ops-cloud-write-state'));
  }
  document.addEventListener('DOMContentLoaded',()=>{
    document.addEventListener('click',event=>{const button=event.target.closest('button[data-cloud-control]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();if(!button.disabled&&window.opsCloudCanWrite(button)){if(button.dataset.cloudControl==='replenish-open')openReplenishment(button.dataset.taskId);else void controlTask(button,button.dataset.cloudControl);}},true);
    panel=document.createElement('details');panel.open=true;panel.dataset.cloudCommands='true';panel.style.cssText='margin:12px;padding:12px;box-sizing:border-box;max-width:calc(100% - 24px);overflow-wrap:anywhere';
    const title=document.createElement('summary');title.textContent='云端命令回执（HTTP 回执与业务完成分开）';list=document.createElement('ul');panel.append(title,list);document.body.prepend(panel);
    const cancelForm=document.createElement('form');cancelForm.dataset.cloudAccount='true';const input=document.createElement('input');input.placeholder='递交器原请求ID（仅用于收件回包丢失）';input.required=true;const cancel=document.createElement('button');cancel.textContent='撤销该递交器请求（仅发送前）';cancelForm.append(input,cancel);panel.append(cancelForm);cancelForm.onsubmit=async event=>{event.preventDefault();try{await postControl('/console/submission-requests/'+encodeURIComponent(input.value.trim())+'/cancel');alert('发送前撤销已记录；晚到收件也会被拒绝。请让递交器重新查询。');}catch(error){alert(error.message);}};
    paint();
    let polling=false;
    async function poll(){if(polling)return;polling=true;try{
      const response=await network('/console/status',{headers:{'X-Ops-Page-Visible':String(document.visibilityState==='visible')}});
      if(response.ok)health=await response.json();else health={};
      for(const record of records.filter(r=>pending.has(r.state)))await query(record);
      const all=await network('/console/commands');if(all.ok){const body=await all.json();remoteRecords=(body.items||[]).filter(r=>!records.some(local=>local.cloudCommandId===r.cloudCommandId)).map(r=>({...r,path:r.target,remote:true}));}
      paint();
    }catch{health={};window.dispatchEvent(new Event('ops-cloud-write-state'));}finally{polling=false;}}
    poll();setInterval(poll,3000);
  });
})();
