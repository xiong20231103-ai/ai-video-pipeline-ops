 'use strict';
// Cloud adapter over the existing managers. No home deletion implementation.
(() => {
 const endpoint='/api/controls/cloud-cleanup/',previews=new Map();
 const kinds={Draft:'drafts',Audio:'audio',Production:'production'};
 const spec={drafts:{prefix:'draft',selection:'selectedDraftIds',confirm:'RECYCLE_SELECTED_CAPCUT_DRAFTS'},audio:{prefix:'audio',selection:'selectedAudioIds',confirm:'RECYCLE_SELECTED_AUDIO_FILES'},production:{prefix:'production',selection:'selectedProductionIds',confirm:'RECYCLE_SELECTED_PRODUCTION_FILES'},pending:{confirm:'EMPTY_PENDING_DELETE_NOW'}};
 async function send(action,payload){const r=await window.opsCloudDispatch(endpoint+action,payload),body=await r.json();if(!r.ok)throw new Error(body.detail||'家里拒绝清理');return body;}
 async function capability(){try{await fetch(endpoint+'capabilities');}catch{}}
 function show(kind,message){const node=document.getElementById(spec[kind]?.prefix+'CleanupPreview')||document.getElementById('pendingDeleteStatus');if(node){node.classList.remove('hidden');node.textContent=message;}}
 async function preview(kind){
  previews.delete(kind);const item=spec[kind],ids=kind==='pending'?[]:[...state[item.selection]];
  if(kind!=='pending'&&!ids.length)throw new Error('请先勾选对象');
  const includeUnknown=kind==='drafts'&&confirm('本次选择是否包含人工或来源不明草稿？选“取消”将保护这类草稿。');
  const value=await send('preview',{kind,ids,includeUnknown});
  if(value.kind!==kind||!Array.isArray(value.ids)||JSON.stringify(value.ids)!==JSON.stringify(ids)||typeof value.ticket!=='string'||typeof value.expiresAt!=='number')throw new Error('预览契约不完整，请重新预览');
  previews.set(kind,{...value,ids,includeUnknown,received:performance.now()});
  if(kind!=='pending'){
   state[item.prefix+'Preview']=value;
   const label=kind==='Draft'?'Draft':Object.keys(kinds).find(k=>kinds[k]===kind);
   document.getElementById('confirm'+label+'CleanupButton')?.classList.toggle('hidden',!value.deletableCount);
  }
  show(kind,(value.message||'预览完成')+'；可处理 '+value.deletableCount+'，阻止 '+value.blockedCount+'。预览有效期至 '+new Date(value.expiresAt*1000).toLocaleTimeString()+'。'+(value.blocked||[]).map(x=>x.name+'：'+x.reason).join('；'));
  return value;
 }
 async function execute(kind){
  const item=spec[kind],p=kind==='pending'?await preview(kind):previews.get(kind);
  if(!p||performance.now()-p.received>=120000)throw new Error('预览已过期或页面已重载，请重新预览');
  if(kind!=='pending'&&JSON.stringify([...state[item.selection]])!==JSON.stringify(p.ids))throw new Error('选择已变化，请重新预览');
  if(p.containsManualOrUnknown&&!confirm('包含人工或来源不明草稿，请再次确认所选对象。'))return;
  if(p.containsTestFiles&&!confirm('包含测试文件，请再次确认所选对象。'))return;
  const question=kind==='pending'?'将立即永久清除待删区，不能恢复。是否继续？':'所选对象将移入待删区，保留3天后清除。是否继续？';
  if(!confirm(question))return;
  if(prompt('请输入 '+item.confirm+' 确认本次操作')!==item.confirm)return;
  if(kind==='pending'&&prompt('再次输入 EMPTY_PENDING_DELETE_NOW 确认永久清除')!==item.confirm)return;
  if(performance.now()-p.received>=120000)throw new Error('确认期间预览已过期，请重新预览');
  const result=await send('execute',{kind,ids:p.ids,includeUnknown:p.includeUnknown,snapshotToken:p.snapshotToken,ticket:p.ticket,expiresAt:p.expiresAt,confirm:item.confirm});
  previews.delete(kind);show(kind,result.message||'已收到家里清理回执，请查看逐项结果');
  if(kind==='pending'){let node=document.getElementById('pendingDeleteLastResult');if(!node){node=document.createElement('p');node.id='pendingDeleteLastResult';node.setAttribute('role','status');document.getElementById('pendingDeleteStatus')?.after(node);}node.textContent=result.message||'已收到清空回执，请核对逐项结果';}
  if(kind!=='pending'&&typeof renderActionResult==='function')renderActionResult(item.prefix+'CleanupResult',result);
  if(kind==='drafts')await loadDraftManager();else if(kind==='audio')await loadAudioManager();else if(kind==='production')await loadProductionManager();
  if(typeof refreshPendingDelete==='function')await refreshPendingDelete();
 }
 document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  const match=/^(preview|confirm)(Draft|Audio|Production)CleanupButton$/.exec(button.id),pending=button.id==='emptyPendingDeleteButton';
  if(!match&&!pending){if(/(Draft|Audio|Production)ManagerButton$/.test(button.id))void capability();return;}
  event.preventDefault();event.stopImmediatePropagation();if(button.disabled||!window.opsCloudCanWrite(button))return;
  button.disabled=true;const kind=pending?'pending':kinds[match[2]];
  Promise.resolve(match?.[1]==='preview'?preview(kind):execute(kind)).catch(error=>show(kind,error.message)).finally(()=>{button.disabled=false;window.dispatchEvent(new Event('ops-cloud-write-state'));});
 },true);
 // Capability is fetched only while a cleanup manager is open, never during idle.
 document.addEventListener('DOMContentLoaded',()=>{const button=document.createElement('button');button.type='button';button.textContent='检查清理通道';button.id='checkCleanupCapabilityButton';button.addEventListener('click',()=>void capability());document.getElementById('pendingDeleteStatus')?.after(button);setInterval(()=>{if(document.querySelector('#draftManagerDialog[open],#audioManagerDialog[open],#productionManagerDialog[open]'))void capability();},30000);});
})();
