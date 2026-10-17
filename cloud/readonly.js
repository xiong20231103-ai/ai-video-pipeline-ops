'use strict';
(() => {
  const original = window.fetch.bind(window);
  const samples = new Map();
  const inflight = new Map();
  let sourcePanel;
  const writeIds=['continueCurrentButton','uploadRescanButton','historicalCloudVerifyButton','resetTestRecordsButton','previewDraftCleanupButton','confirmDraftCleanupButton','previewAudioCleanupButton','confirmAudioCleanupButton','previewProductionCleanupButton','confirmProductionCleanupButton'];
  document.addEventListener('submit', event => {
    if (!event.target.closest('[data-cloud-account]')) { event.preventDefault(); event.stopImmediatePropagation(); }
  }, true);
  const wait = (ms, signal) => new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
    signal?.addEventListener('abort', abort, {once: true});
  });
  function observe(url, response) {
    const age = response.headers.get('X-Cache-Age-Seconds');
    if (age !== null) {
      let health={};try{health=JSON.parse(response.headers.get('X-Source-Health')||'{}');}catch{}
      samples.set(url, {age: Number(age), received: performance.now(), scan: response.headers.get('X-Source-Scanned-At') || '源扫描时间未知', sourceAge:typeof health.scanAgeSeconds==='number'?health.scanAgeSeconds:null});
    }
  }
  window.fetch = async (input, init = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return original(input, init);
    const method = (init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (method !== 'GET') throw new Error('当前里程碑只读，写命令尚未启用');
    init={...init,headers:new Headers(init.headers || (input instanceof Request ? input.headers : undefined))};
    init.headers.set('X-Ops-Page-Visible',String(document.visibilityState==='visible'));
    const key = url.pathname + url.search;
    // Coalesce browser retries too; the cloud independently coalesces all devices.
    if (inflight.has(key)) return (await inflight.get(key)).clone();
    const work = (async () => {
      for (let attempt = 0; attempt < 30; attempt++) {
        const response = await original(input, init);
        if (response.status === 401) { location.assign('/login'); throw new Error('请重新登录'); }
        if (response.status !== 202) { observe(key, response); return response; }
        // A pending envelope is never delivered to the old business renderer.
        await wait(2000, init.signal || (input instanceof Request ? input.signal : undefined));
      }
      throw new Error('正在向家里取数，稍后自动刷新；已有数据显示保留');
    })();
    inflight.set(key, work);
    try { return (await work).clone(); } finally { inflight.delete(key); }
  };
  document.addEventListener('DOMContentLoaded', () => {
    sourcePanel = document.createElement('details'); sourcePanel.open = true;
    sourcePanel.style.cssText = 'margin:12px;padding:12px;background:#fff5cf;color:#513f00;border-radius:8px';
    const summary = document.createElement('summary'); summary.textContent = '云端只读预览 · 家里代理部署前等待取数 · 写命令尚未启用';
    sourcePanel.append(summary, document.createElement('ul')); document.body.prepend(sourcePanel);
    for (const id of writeIds) {
      const button = document.getElementById(id); if (button) { button.disabled = true; button.title = '当前云端为只读里程碑'; }
    }
    const account = document.createElement('details');
    account.dataset.cloudAccount='true';
    const title = document.createElement('summary'); title.textContent = '账号'; account.append(title);
    const password = document.createElement('button'); password.textContent = '修改密码';
    const logout = document.createElement('button'); logout.textContent = '退出登录';
    async function credentials() { const response = await original('/auth/session'); if (!response.ok) throw new Error(); return response.json(); }
    logout.onclick = async () => { const info = await credentials(); await original('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':info.csrf}}); location.assign('/login'); };
    password.onclick = () => {
      if (account.querySelector('form')) return;
      const form = document.createElement('form');
      for (const [name,label] of [['oldPassword','当前密码'],['newPassword','新密码（至少12个字符）']]) {
        const input = document.createElement('input'); input.type='password'; input.name=name; input.required=true; input.placeholder=label; input.maxLength=256; input.autocomplete=name==='newPassword'?'new-password':'current-password'; if(name==='newPassword') input.minLength=12; form.append(input);
      }
      const submit=document.createElement('button'); submit.textContent='提交修改'; form.append(submit);
      form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{const info=await credentials();const response=await original('/auth/password',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify(Object.fromEntries(new FormData(form)))});if(response.ok){form.reset();location.assign('/login');}else alert('未修改，请核对密码后重试');}finally{submit.disabled=false;}};
      account.append(form);
    };
    account.append(password,logout); sourcePanel.append(account);
    const disableWrites=()=>{
      const buttons=[...document.querySelectorAll('button[onclick], #createTaskForm button, #replenishForm button[type="submit"]'),...writeIds.map(id=>document.getElementById(id)).filter(Boolean)];
      for(const button of buttons) {
        if(!button.disabled)button.disabled=true; button.title='当前云端只读，写命令尚未启用';
      }
    };
    disableWrites(); new MutationObserver(disableWrites).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});
    async function pollHealth() {
      try {
        const response=await original('/console/status',{headers:{'X-Ops-Page-Visible':String(document.visibilityState==='visible')}});
        if(response.status===401){location.assign('/login');return;}
        if(!response.ok)throw new Error();
        const health=await response.json();
        const text=health.heartbeatAgeSeconds===null?'等待家里代理部署/连接':!health.agentOnline?'家里离线，距心跳 '+Math.floor(health.heartbeatAgeSeconds)+' 秒':health.engineState==='healthy'?'家里在线':health.engineState==='busy'?'引擎忙，保留已有数据':'代理在线，旧引擎状态不可用/尚待确认';
        summary.textContent='云端只读 · '+text+' · 写命令尚未启用';
        sourcePanel.style.background=health.agentOnline&&health.engineState==='healthy'?'#e8f5e9':'#fff0ee';
      } catch {summary.textContent='云端连接暂不可用，已有数据可能过期';sourcePanel.style.background='#fff0ee';}
    }
    pollHealth();setInterval(pollHealth,5000);
    // The old page switches to summary-only polling after its first full load.
    // Refresh the full cached page independently so events/templates/history do
    // not silently depend on summary changes. This only requests the cloud.
    setInterval(()=>{
      if(typeof state!=='undefined'&&!state.refreshBusy&&typeof refresh==='function'){
        state.fullDashboardLoaded=false;void refresh();
      }
    },60000);
    setInterval(() => {
      const list=sourcePanel.querySelector('ul'); list.replaceChildren();
      for (const [key,sample] of samples) {
        const age=Math.floor(sample.age+(performance.now()-sample.received)/1000); const row=document.createElement('li');
        const parsed=new URL(key,location.origin);
        const names={'/api/dashboard':'完整看板','/api/dashboard/summary':'当前摘要','/api/task-boxes/current':'当前任务箱','/api/task-boxes/history':'历史任务箱','/api/controls/tasks':'任务队列','/api/controls/templates':'任务模板','/api/safety':'安全面板','/api/project-gaps':'项目缺口','/api/pipeline':'历史流水线','/api/controls/continue-current/status':'恢复状态','/api/control-commands/current':'命令状态','/api/subtitle-verification/current':'字幕核验'};
        const name=(names[parsed.pathname]||'页面数据')+(parsed.searchParams.get('date')?' '+parsed.searchParams.get('date'):'');
        const stamp=new Date(sample.scan);
        const effective=sample.sourceAge===null?null:sample.sourceAge+age;
        row.textContent=name+'：'+(Number.isNaN(stamp.getTime())||effective===null?'源扫描时间未知，最近取数 '+age+' 秒前':'数据截至 '+stamp.toLocaleTimeString('zh-CN',{hour12:false})+'（'+Math.floor(effective)+' 秒前）；最近取数 '+age+' 秒前');
        row.style.color=age>120||(effective!==null&&effective>120)?'#b42318':age>30||effective===null||effective>30?'#8a5c00':'#38533a'; list.append(row);
      }
    },1000);
  });
})();
