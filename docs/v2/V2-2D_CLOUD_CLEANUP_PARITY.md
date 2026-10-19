# V2-2D 云端三类清理与待删区

仅前端。五类目录扩展未包含。使用现有 cloud-cleanup preview/execute 云端命令队列，家里执行与 H2 保持原样。生产 cleanup 开关仍由现有云端状态控制，本 PR 没有配置或部署步骤。

## cloud/cleanup.js → V2 逐行对照

| 原行号/代码 | V2 实现与语义 |
|---|---|
| [1](../../cloud/cleanup.js#L1) `'use strict';` | [cloud-cleanup.ts:12](../../frontend-v2/src/data/cloud-cleanup.ts#L12)：同源云端接口、分类与页面内票据映射 |
| [2](../../cloud/cleanup.js#L2) `// Cloud adapter over the existing managers. No home deletion implementation.` | [cloud-cleanup.ts:12](../../frontend-v2/src/data/cloud-cleanup.ts#L12)：同源云端接口、分类与页面内票据映射 |
| [3](../../cloud/cleanup.js#L3) `(() => {` | [cloud-cleanup.ts:12](../../frontend-v2/src/data/cloud-cleanup.ts#L12)：同源云端接口、分类与页面内票据映射 |
| [4](../../cloud/cleanup.js#L4) `const endpoint='/api/controls/cloud-cleanup/',previews=new Map();` | [cloud-cleanup.ts:12](../../frontend-v2/src/data/cloud-cleanup.ts#L12)：同源云端接口、分类与页面内票据映射 |
| [5](../../cloud/cleanup.js#L5) `const kinds={Draft:'drafts',Audio:'audio',Production:'production'};` | [cloud-cleanup.ts:12](../../frontend-v2/src/data/cloud-cleanup.ts#L12)：同源云端接口、分类与页面内票据映射 |
| [6](../../cloud/cleanup.js#L6) `const spec={drafts:{prefix:'draft',selection:'selectedDraftIds',confirm:'RECYCLE_SELECTED_CAPCUT_DRAFTS'},audio:{prefix:'audio',selection:'selectedAudioIds',confirm:'RECYCLE_SELECTED_AUDIO_FILES'},production:{prefix:'production',selection:'selectedProductionIds',confirm:'RECYCLE_SELECTED_PRODUCTION_FILES'},pending:{confirm:'EMPTY_PENDING_DELETE_NOW'}};` | [cloud-cleanup.ts:12](../../frontend-v2/src/data/cloud-cleanup.ts#L12)：同源云端接口、分类与页面内票据映射 |
| [7](../../cloud/cleanup.js#L7) `async function send(action,payload){const r=await window.opsCloudDispatch(endpoint+action,payload),body=await r.json();if(!r.ok)throw new Error(body.detail¦¦'家里拒绝清理');return body;}` | [cloud-cleanup.ts:41](../../frontend-v2/src/data/cloud-cleanup.ts#L41)：共享队列写入器解包家里 HTTP 回执；不向家里直连 |
| [8](../../cloud/cleanup.js#L8) `async function capability(){try{await fetch(endpoint+'capabilities');}catch{}}` | [cloud-cleanup.ts:38](../../frontend-v2/src/data/cloud-cleanup.ts#L38)：只读能力查询 |
| [9](../../cloud/cleanup.js#L9) `function show(kind,message){const node=document.getElementById(spec[kind]?.prefix+'CleanupPreview')¦¦document.getElementById('pendingDeleteStatus');if(node){node.classList.remove('hidden');node.textContent=message;}}` | [FileManagers.tsx:646](../../frontend-v2/src/components/views/FileManagers.tsx#L646)：React 状态展示预览/错误/执行结果 |
| [10](../../cloud/cleanup.js#L10) `async function preview(kind){` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [11](../../cloud/cleanup.js#L11) `previews.delete(kind);const item=spec[kind],ids=kind==='pending'?[]:[...state[item.selection]];` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [12](../../cloud/cleanup.js#L12) `if(kind!=='pending'&&!ids.length)throw new Error('请先勾选对象');` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [13](../../cloud/cleanup.js#L13) `const includeUnknown=kind==='drafts'&&confirm('本次选择是否包含人工或来源不明草稿？选“取消”将保护这类草稿。');` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [14](../../cloud/cleanup.js#L14) `const value=await send('preview',{kind,ids,includeUnknown});` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [15](../../cloud/cleanup.js#L15) `if(value.kind!==kind¦¦!Array.isArray(value.ids)¦¦JSON.stringify(value.ids)!==JSON.stringify(ids)¦¦typeof value.ticket!=='string'¦¦typeof value.expiresAt!=='number')throw new Error('预览契约不完整，请重新预览');` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [16](../../cloud/cleanup.js#L16) `previews.set(kind,{...value,ids,includeUnknown,received:performance.now()});` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [17](../../cloud/cleanup.js#L17) `if(kind!=='pending'){` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [18](../../cloud/cleanup.js#L18) `state[item.prefix+'Preview']=value;` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [19](../../cloud/cleanup.js#L19) `const label=kind==='Draft'?'Draft':Object.keys(kinds).find(k=>kinds[k]===kind);` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [20](../../cloud/cleanup.js#L20) `document.getElementById('confirm'+label+'CleanupButton')?.classList.toggle('hidden',!value.deletableCount);` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [21](../../cloud/cleanup.js#L21) `}` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [22](../../cloud/cleanup.js#L22) `show(kind,(value.message¦¦'预览完成')+'；可处理 '+value.deletableCount+'，阻止 '+value.blockedCount+'。预览有效期至 '+new Date(value.expiresAt*1000).toLocaleTimeString()+'。'+(value.blocked¦¦[]).map(x=>x.name+'：'+x.reason).join('；'));` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [23](../../cloud/cleanup.js#L23) `return value;` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [24](../../cloud/cleanup.js#L24) `}` | [cloud-cleanup.ts:46](../../frontend-v2/src/data/cloud-cleanup.ts#L46)：精确对象ID顺序、草稿提示、原请求字段及票据契约、单调计时 |
| [25](../../cloud/cleanup.js#L25) `async function execute(kind){` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [26](../../cloud/cleanup.js#L26) `const item=spec[kind],p=kind==='pending'?await preview(kind):previews.get(kind);` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [27](../../cloud/cleanup.js#L27) `if(!p¦¦performance.now()-p.received>=120000)throw new Error('预览已过期或页面已重载，请重新预览');` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [28](../../cloud/cleanup.js#L28) `if(kind!=='pending'&&JSON.stringify([...state[item.selection]])!==JSON.stringify(p.ids))throw new Error('选择已变化，请重新预览');` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [29](../../cloud/cleanup.js#L29) `if(p.containsManualOrUnknown&&!confirm('包含人工或来源不明草稿，请再次确认所选对象。'))return;` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [30](../../cloud/cleanup.js#L30) `if(p.containsTestFiles&&!confirm('包含测试文件，请再次确认所选对象。'))return;` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [31](../../cloud/cleanup.js#L31) `const question=kind==='pending'?'将立即永久清除待删区，不能恢复。是否继续？':'所选对象将移入待删区，保留3天后清除。是否继续？';` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [32](../../cloud/cleanup.js#L32) `if(!confirm(question))return;` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [33](../../cloud/cleanup.js#L33) `if(prompt('请输入 '+item.confirm+' 确认本次操作')!==item.confirm)return;` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [34](../../cloud/cleanup.js#L34) `if(kind==='pending'&&prompt('再次输入 EMPTY_PENDING_DELETE_NOW 确认永久清除')!==item.confirm)return;` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [35](../../cloud/cleanup.js#L35) `if(performance.now()-p.received>=120000)throw new Error('确认期间预览已过期，请重新预览');` | [cloud-cleanup.ts:76](../../frontend-v2/src/data/cloud-cleanup.ts#L76)：120秒票据、选择一致性、人工/测试确认、原确认文字及两次输入 |
| [36](../../cloud/cleanup.js#L36) `const result=await send('execute',{kind,ids:p.ids,includeUnknown:p.includeUnknown,snapshotToken:p.snapshotToken,ticket:p.ticket,expiresAt:p.expiresAt,confirm:item.confirm});` | [cloud-cleanup.ts:113](../../frontend-v2/src/data/cloud-cleanup.ts#L113)：精确 execute 请求字段；队列 GET 查询至家里结果 |
| [37](../../cloud/cleanup.js#L37) `previews.delete(kind);show(kind,result.message¦¦'已收到家里清理回执，请查看逐项结果');` | [cloud-cleanup.ts:47](../../frontend-v2/src/data/cloud-cleanup.ts#L47)：成功回执后移除票据 |
| [38](../../cloud/cleanup.js#L38) `if(kind==='pending'){let node=document.getElementById('pendingDeleteLastResult');if(!node){node=document.createElement('p');node.id='pendingDeleteLastResult';node.setAttribute('role','status');document.getElementById('pendingDeleteStatus')?.after(node);}node.textContent=result.message¦¦'已收到清空回执，请核对逐项结果';}` | [FileManagers.tsx:174](../../frontend-v2/src/components/views/FileManagers.tsx#L174)：显示逐项/部分失败、刷新清单与待删区；清空结果保留 |
| [39](../../cloud/cleanup.js#L39) `if(kind!=='pending'&&typeof renderActionResult==='function')renderActionResult(item.prefix+'CleanupResult',result);` | [FileManagers.tsx:174](../../frontend-v2/src/components/views/FileManagers.tsx#L174)：显示逐项/部分失败、刷新清单与待删区；清空结果保留 |
| [40](../../cloud/cleanup.js#L40) `if(kind==='drafts')await loadDraftManager();else if(kind==='audio')await loadAudioManager();else if(kind==='production')await loadProductionManager();` | [FileManagers.tsx:174](../../frontend-v2/src/components/views/FileManagers.tsx#L174)：显示逐项/部分失败、刷新清单与待删区；清空结果保留 |
| [41](../../cloud/cleanup.js#L41) `if(typeof refreshPendingDelete==='function')await refreshPendingDelete();` | [FileManagers.tsx:174](../../frontend-v2/src/components/views/FileManagers.tsx#L174)：显示逐项/部分失败、刷新清单与待删区；清空结果保留 |
| [42](../../cloud/cleanup.js#L42) `}` | [FileManagers.tsx:174](../../frontend-v2/src/components/views/FileManagers.tsx#L174)：显示逐项/部分失败、刷新清单与待删区；清空结果保留 |
| [43](../../cloud/cleanup.js#L43) `document.addEventListener('click',event=>{` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [44](../../cloud/cleanup.js#L44) `const button=event.target.closest('button');if(!button)return;` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [45](../../cloud/cleanup.js#L45) `const match=/^(preview¦confirm)(Draft¦Audio¦Production)CleanupButton$/.exec(button.id),pending=button.id==='emptyPendingDeleteButton';` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [46](../../cloud/cleanup.js#L46) `if(!match&&!pending){if(/(Draft¦Audio¦Production)ManagerButton$/.test(button.id))void capability();return;}` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [47](../../cloud/cleanup.js#L47) `event.preventDefault();event.stopImmediatePropagation();if(button.disabled¦¦!window.opsCloudCanWrite(button))return;` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [48](../../cloud/cleanup.js#L48) `button.disabled=true;const kind=pending?'pending':kinds[match[2]];` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [49](../../cloud/cleanup.js#L49) `Promise.resolve(match?.[1]==='preview'?preview(kind):execute(kind)).catch(error=>show(kind,error.message)).finally(()=>{button.disabled=false;window.dispatchEvent(new Event('ops-cloud-write-state'));});` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [50](../../cloud/cleanup.js#L50) `},true);` | [FileManagers.tsx:61](../../frontend-v2/src/components/views/FileManagers.tsx#L61)：共享写门禁、inFlight、按 kind 调度与错误反馈，云端 canCleanup 为 true 才开放 |
| [51](../../cloud/cleanup.js#L51) `// Capability is fetched only while a cleanup manager is open, never during idle.` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：仅管理弹层打开时每30秒查能力、关闭即清 timer，保留手动检查入口 |
| [52](../../cloud/cleanup.js#L52) `document.addEventListener('DOMContentLoaded',()=>{const button=document.createElement('button');button.type='button';button.textContent='检查清理通道';button.id='checkCleanupCapabilityButton';button.addEventListener('click',()=>void capability());document.getElementById('pendingDeleteStatus')?.after(button);setInterval(()=>{if(document.querySelector('#draftManagerDialog[open],#audioManagerDialog[open],#productionManagerDialog[open]'))void capability();},30000);});` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：仅管理弹层打开时每30秒查能力、关闭即清 timer，保留手动检查入口 |
| [53](../../cloud/cleanup.js#L53) `})();` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：仅管理弹层打开时每30秒查能力、关闭即清 timer，保留手动检查入口 |

## 共享队列契约

- [upload-writer.ts:12](../../frontend-v2/src/data/upload-writer.ts#L12)：仅增加 preview/execute 两个同源路径。
- [upload-writer.ts:39](../../frontend-v2/src/data/upload-writer.ts#L39)：门禁包含当前活动请求，与旧 commands.js 一致。
- [upload-writer.ts:150](../../frontend-v2/src/data/upload-writer.ts#L150)：重新预览只丢弃旧终态预览回执；未决回执保留并只查询。
- [upload-writer.ts:202](../../frontend-v2/src/data/upload-writer.ts#L202)：execute 最多1000轮，其余180轮，1秒查询间隔不变。

每条云端写入先持久化原 requestId/fingerprint，再带 CSRF 发送一次 POST；202 不作为家里最终结果。丢回包、重载后只按原编号 GET，unknown 不自动重发。票据不持久化，重载后重新预览。前端轮询通过 compare-before-write 合并回执，异步旧查询不能覆盖更新的终态、人工对账或复活已移除预览。

## 验证

132项前端测试（新增26项），typecheck/lint/摘录校验通过。新增覆盖三类原正文和确认、待删区两次输入、过期/确认中到期/改选/重载、坏票据、清理关闭/离线/阻塞/未决门禁、丢回包查询、unknown保留、旧预览终态换新、异步回执竞争。361项隔离业务测试通过（1跳过）。真实无头浏览器全部网络拦截，72张云端截图、80次模拟队列POST，无家里直接清理POST、无CSP/控制台错误；家里模式和云端关闭开关另跑回归。

复用已有固定依赖，无新增依赖；来源及许可证见 public/dependencies.json、THIRD_PARTY_NOTICES.txt 和 licenses/。未验证真实生产、完整批次影子、切换；不合并、不部署。回滚：revert 本PR及 static/v2 产物，旧入口保留。

## 2026-10-20 CI 404 定位与修复
失败 run 39282832914 的旧日志未保留URL。夹具唯一主动404分支是原请求查询，延迟收件3500ms后已强制复现：/console/commands/request/c1924d59-dae8-43a0-992f-83d917062e86。原请求已以 submitting 持久化，但 CSRF/云端收件尚未完成；是预期API缺记录响应，不是静态资源或缺路由。后端 cloud/command_routes.py:24 与 cloud/commands.py 的 command_not_found=404 一致。
修复仅把经过本地原ID及submitting核对的查询404单列 expectedNotFound/expectedConsole；其它404、缺资源、未知GET、脚本错误、CSP仍失败。强制竞争验收必须至少出现一次原ID404，并断言模拟业务POST仍为80次（不得重发）。结果先写JSON及带URL日志再断言，避免失败时丢证据。
本地复验：652请求、80模拟POST、72截图、预期404一次、其它错误0、CSP0。证据 implementation-tools/v2-cloud-cleanup-evidence/ci-404-repro/cloud-cleanup-browser-result.json；132前端测试、typecheck/lint、原12构建产物逐字节一致通过。只改测试脚本及文档，不修改运行时代码或产物。

