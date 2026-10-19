# V2-2F 已登录账号、备份与家里重置

按用户2026-10-20确认：本轮不实现未登录V2登录/注册页，沿用/login（含邀请码注册）；401仍跳/login。登录注册清单明确延期到V2-4。未来单独cloud PR需支持原页面返回和仅登录所需最小静态访问及安全测试，本轮不改cloud/。

## 新功能原实现逐行对照

### cloud/readonly.js

| 原行/代码 | V2实现 |
|---|---|
| [106](../../cloud/readonly.js#L106) `async function credentials() { const response = await original('/auth/session'); if (!response.ok) throw new Error(); return response.json(); }` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [107](../../cloud/readonly.js#L107) `logout.onclick = async () => { const info = await credentials(); await original('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':info.csrf}}); location.assign('/login'); };` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [108](../../cloud/readonly.js#L108) `password.onclick = () => {` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [109](../../cloud/readonly.js#L109) `if (account.querySelector('form')) return;` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [110](../../cloud/readonly.js#L110) `const form = document.createElement('form');` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [111](../../cloud/readonly.js#L111) `for (const [name,label] of [['oldPassword','当前密码'],['newPassword','新密码（至少12个字符）']]) {` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [112](../../cloud/readonly.js#L112) `const input = document.createElement('input'); input.type='password'; input.name=name; input.required=true; input.placeholder=label; input.maxLength=256; input.autocomplete=name==='newPassword'?'new-password':'current-password'; if(name==='newPassword') input.minLength=12; form.append(input);` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [113](../../cloud/readonly.js#L113) `}` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [114](../../cloud/readonly.js#L114) `const submit=document.createElement('button'); submit.textContent='提交修改'; form.append(submit);` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| [115](../../cloud/readonly.js#L115) `form.onsubmit=async event=>{event.preventDefault();submit.disabled=true;try{const info=await credentials();const response=await original('/auth/password',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify(Object.fromEntries(new FormData(form)))});if(response.ok){form.reset();location.assign('/login');}else alert('未修改，请核对密码后重试');}finally{submit.disabled=false;}};` | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6)：已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |

### cloud/backups.js

| 原行/代码 | V2实现 |
|---|---|
| [1](../../cloud/backups.js#L1) `/* Cloud-only backup catalog. Downloaded material remains ciphertext. */` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [2](../../cloud/backups.js#L2) `(() => {` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [3](../../cloud/backups.js#L3) `const api = async (path, method = 'GET') => {` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [4](../../cloud/backups.js#L4) `const headers = {};` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [5](../../cloud/backups.js#L5) `if (method !== 'GET') {` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [6](../../cloud/backups.js#L6) `const session = await fetch('/auth/session').then(r => r.json());` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [7](../../cloud/backups.js#L7) `headers['X-CSRF-Token'] = session.csrf;` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [8](../../cloud/backups.js#L8) `}` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [9](../../cloud/backups.js#L9) `const response = await fetch(path, {method, headers});` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [10](../../cloud/backups.js#L10) `if (!response.ok) throw new Error(ˋ请求失败 (${response.status})ˋ);` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [11](../../cloud/backups.js#L11) `return response.json();` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [12](../../cloud/backups.js#L12) `};` | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11)：账号CSRF及原方法/状态码；读取目录仍用GET |
| [13](../../cloud/backups.js#L13) `const element = (tag, text) => {` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [14](../../cloud/backups.js#L14) `const node = document.createElement(tag);` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [15](../../cloud/backups.js#L15) `if (text !== undefined) node.textContent = text;` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [16](../../cloud/backups.js#L16) `return node;` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [17](../../cloud/backups.js#L17) `};` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [18](../../cloud/backups.js#L18) `const show = async (body, message) => {` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [19](../../cloud/backups.js#L19) `try {` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [20](../../cloud/backups.js#L20) `const result = await api('/console/backups');` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [21](../../cloud/backups.js#L21) `body.replaceChildren();` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [22](../../cloud/backups.js#L22) `body.append(element('p', ˋ仅台账和配置恢复；视频、草稿不在备份中。已用及预留 ${(result.usedReservedBytes / 1048576).toFixed(1)} MiB / ${(result.quotaBytes / 1e9).toFixed(0)} GB。ˋ));` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [23](../../cloud/backups.js#L23) `const phase = result.agentState?.phase ¦¦ 'waiting_configuration';` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [24](../../cloud/backups.js#L24) `const phases = {waiting_configuration: '等待本机配置恢复密钥', creating: '正在生成', uploading: '正在上传', completed: '最近一次已上传', failed: '备份失败，请检查代理状态'};` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [25](../../cloud/backups.js#L25) `body.append(element('p', ˋ家里备份：${phases[phase] ¦¦ phase}。${result.recipientConfigured ? '云端已登记公钥。' : '云端尚未登记公钥。'}ˋ));` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [26](../../cloud/backups.js#L26) `body.append(element('p', ˋ实际保留日期：${result.retainedDates.join('、') ¦¦ '尚无备份'}ˋ));` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [27](../../cloud/backups.js#L27) `if (!result.items.length) body.append(element('p', '尚无已完成的备份包；未完成上传不会显示为可恢复备份。'));` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [28](../../cloud/backups.js#L28) `for (const item of result.items) {` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [29](../../cloud/backups.js#L29) `const row = element('div');` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [30](../../cloud/backups.js#L30) `row.style.cssText = 'padding:8px 0;border-bottom:1px solid #888';` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [31](../../cloud/backups.js#L31) `row.append(element('p', ˋ${item.kind === 'home' ? '家里台账/配置' : '云端数据库'} · ${item.date} · ${(item.bytes / 1048576).toFixed(2)} MiB · ${item.packageId}ˋ));` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [32](../../cloud/backups.js#L32) `for (const name of ['manifest.json', ...item.manifest.artifacts.map(p => p.name)]) {` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [33](../../cloud/backups.js#L33) `const link = element('a', ˋ下载 ${name}ˋ);` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [34](../../cloud/backups.js#L34) `link.href = ˋ/console/backups/${item.packageId}/${name}ˋ;` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [35](../../cloud/backups.js#L35) `link.download = name; link.style.marginRight = '16px'; row.append(link);` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [36](../../cloud/backups.js#L36) `}` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [37](../../cloud/backups.js#L37) `const verify = element('button', '校验云端文件');` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [38](../../cloud/backups.js#L38) `verify.type = 'button';` | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215)：目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| [39](../../cloud/backups.js#L39) `verify.onclick = async () => {` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [40](../../cloud/backups.js#L40) `verify.disabled = true;` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [41](../../cloud/backups.js#L41) `try { const checked = await api(ˋ/console/backups/${item.packageId}/verifyˋ, 'POST'); message.textContent = checked.verified ? ˋ校验通过：${item.packageId}ˋ : ˋ校验失败：${item.packageId}ˋ; }` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [42](../../cloud/backups.js#L42) `catch (error) { message.textContent = error.message; }` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [43](../../cloud/backups.js#L43) `finally { verify.disabled = false; }` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [44](../../cloud/backups.js#L44) `};` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [45](../../cloud/backups.js#L45) `row.append(verify); body.append(row);` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [46](../../cloud/backups.js#L46) `}` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [47](../../cloud/backups.js#L47) `if (result.events.length) body.append(element('p', '保留/容量事件：' + result.events.map(e => ˋ${new Date(e.at * 1000).toLocaleString()} ${e.code}ˋ).join('；')));` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：逐包校验与失败提示、防重复 |
| [48](../../cloud/backups.js#L48) `} catch (error) { message.textContent = error.message; }` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [49](../../cloud/backups.js#L49) `};` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [50](../../cloud/backups.js#L50) `document.addEventListener('DOMContentLoaded', () => {` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [51](../../cloud/backups.js#L51) `const panel = element('details'); panel.id = 'cloudBackupPanel';` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [52](../../cloud/backups.js#L52) `panel.style.cssText = 'margin:16px;padding:12px;border:1px solid #888;border-radius:8px;overflow-wrap:anywhere';` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [53](../../cloud/backups.js#L53) `panel.append(element('summary', '异地备份（台账与配置）'));` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [54](../../cloud/backups.js#L54) `const refresh = element('button', '刷新列表'), request = element('button', '请求一次备份');` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [55](../../cloud/backups.js#L55) `refresh.type = request.type = 'button';` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [56](../../cloud/backups.js#L56) `const message = element('p'), body = element('div'); message.setAttribute('role', 'status');` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [57](../../cloud/backups.js#L57) `refresh.onclick = () => show(body, message);` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [58](../../cloud/backups.js#L58) `request.onclick = async () => {` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [59](../../cloud/backups.js#L59) `request.disabled = true;` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [60](../../cloud/backups.js#L60) `try { await api('/console/backups/request', 'POST'); message.textContent = '请求已排队；代理配置就绪后执行。稍后刷新列表查看。'; }` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [61](../../cloud/backups.js#L61) `catch (error) { message.textContent = error.message; }` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [62](../../cloud/backups.js#L62) `finally { request.disabled = false; }` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [63](../../cloud/backups.js#L63) `};` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [64](../../cloud/backups.js#L64) `panel.append(refresh, request, message, body);` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [65](../../cloud/backups.js#L65) `panel.addEventListener('toggle', () => { if (panel.open) show(body, message); });` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [66](../../cloud/backups.js#L66) `document.body.append(panel);` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [67](../../cloud/backups.js#L67) `});` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |
| [68](../../cloud/backups.js#L68) `})();` | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15)：请求一次备份、排队反馈；目录按需展开和刷新 |

### static/app.js

| 原行/代码 | V2实现 |
|---|---|
| [2124](../../static/app.js#L2124) `$("resetTestRecordsButton")?.addEventListener("click", async (event) => {` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2125](../../static/app.js#L2125) `const button = event.currentTarget;` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2126](../../static/app.js#L2126) `if (!window.confirm("确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。")) return;` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2127](../../static/app.js#L2127) `if (!window.confirm("再次确认：Dashboard、工作台、接收器和 CapCut 的任务进度将从空状态重新开始。")) return;` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2128](../../static/app.js#L2128) `button.disabled = true;` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2129](../../static/app.js#L2129) `button.textContent = "正在备份并重置…";` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2130](../../static/app.js#L2130) `try {` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2131](../../static/app.js#L2131) `const result = await postJson("/api/controls/testing/reset", { confirm: "RESET_TEST_RECORDS" });` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2132](../../static/app.js#L2132) `state.date = "";` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2133](../../static/app.js#L2133) `state.batchId = "";` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2134](../../static/app.js#L2134) `renderActionResult("resetRecordsResult", {` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2135](../../static/app.js#L2135) `state: "completed",` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2136](../../static/app.js#L2136) `message: result.message ¦¦ "测试记录已重置",` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2137](../../static/app.js#L2137) `updatedAt: result.resetAt ¦¦ new Date().toISOString(),` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2138](../../static/app.js#L2138) `});` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2139](../../static/app.js#L2139) `await refresh();` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2140](../../static/app.js#L2140) `} catch (error) {` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2141](../../static/app.js#L2141) `renderActionResult("resetRecordsResult", {` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2142](../../static/app.js#L2142) `state: "failed",` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2143](../../static/app.js#L2143) `message: error.message ¦¦ "测试记录重置失败",` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2144](../../static/app.js#L2144) `updatedAt: new Date().toISOString(),` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2145](../../static/app.js#L2145) `});` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2146](../../static/app.js#L2146) `} finally {` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2147](../../static/app.js#L2147) `button.disabled = false;` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2148](../../static/app.js#L2148) `button.textContent = "重置全部测试记录";` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2149](../../static/app.js#L2149) `}` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| [2150](../../static/app.js#L2150) `});` | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18)：home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |

## 完整功能复核（此前未勾选的父区域/回调）

每一项单独列出对应实际位置；不把父容器在子功能缺失时提前勾选。

| 清单ID | V2对应位置 | 含义 |
|---|---|
| FN-171 | [home-cleanup.ts:105](../../frontend-v2/src/data/home-cleanup.ts#L105) | 原JSON正文、独立超时与错误提示；云端使用队列写入器 |
| FN-172 | [home-cleanup.ts:105](../../frontend-v2/src/data/home-cleanup.ts#L105) | 原JSON正文、独立超时与错误提示；云端使用队列写入器 |
| FN-213 | [Dashboard.tsx:259](../../frontend-v2/src/components/views/Dashboard.tsx#L259) | 原结果/历史核验状态与计数；UploadActions独立反馈 |
| FN-214 | [Dashboard.tsx:259](../../frontend-v2/src/components/views/Dashboard.tsx#L259) | 原结果/历史核验状态与计数；UploadActions独立反馈 |
| FN-220 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期/任务箱/项目筛选回调保持原选择语义 |
| FN-221 | [TaskViews.tsx:29](../../frontend-v2/src/components/views/TaskViews.tsx#L29) | 日期/任务箱/项目筛选回调保持原选择语义 |
| FN-222 | [TaskViews.tsx:324](../../frontend-v2/src/components/views/TaskViews.tsx#L324) | 日期/任务箱/项目筛选回调保持原选择语义 |
| FN-269 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| FN-273 | [client.ts:3](../../frontend-v2/src/data/client.ts#L3) | 只读网络适配、202、缓存、401及取消；子功能均已迁移 |
| FN-274 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| FN-284 | [client.ts:3](../../frontend-v2/src/data/client.ts#L3) | 只读网络适配、202、缓存、401及取消；子功能均已迁移 |
| FN-286 | [client.ts:3](../../frontend-v2/src/data/client.ts#L3) | 只读网络适配、202、缓存、401及取消；子功能均已迁移 |
| FN-288 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| FN-289 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| FN-290 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| FN-291 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| FN-292 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| FN-293 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| FN-294 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| FN-295 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| FN-296 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| FN-354 | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11) | 账号CSRF及原方法/状态码；读取目录仍用GET |
| FN-355 | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11) | 账号CSRF及原方法/状态码；读取目录仍用GET |
| FN-356 | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11) | 账号CSRF及原方法/状态码；读取目录仍用GET |
| FN-357 | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215) | 目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| FN-358 | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215) | 目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| FN-359 | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215) | 目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| FN-360 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 逐包校验与失败提示、防重复 |
| FN-361 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 逐包校验与失败提示、防重复 |
| FN-362 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| FN-363 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| FN-364 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| FN-365 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| NET-005 | [home-cleanup.ts:105](../../frontend-v2/src/data/home-cleanup.ts#L105) | 原JSON正文、独立超时与错误提示；云端使用队列写入器 |
| NET-023 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| NET-028 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| NET-029 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| NET-030 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| NET-031 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| NET-046 | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11) | 账号CSRF及原方法/状态码；读取目录仍用GET |
| NET-047 | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11) | 账号CSRF及原方法/状态码；读取目录仍用GET |
| NET-048 | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215) | 目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| NET-049 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 逐包校验与失败提示、防重复 |
| NET-050 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| CONF-021 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| CONF-022 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| CONF-023 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| GUARD-052 | [Dashboard.tsx:259](../../frontend-v2/src/components/views/Dashboard.tsx#L259) | 原结果/历史核验状态与计数；UploadActions独立反馈 |
| GUARD-057 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期/任务箱/项目筛选回调保持原选择语义 |
| GUARD-101 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| GUARD-102 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| GUARD-108 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 初始未知状态禁止写入 |
| GUARD-109 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| GUARD-110 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| GUARD-111 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| GUARD-112 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| GUARD-113 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| GUARD-114 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| GUARD-115 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| GUARD-116 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| GUARD-162 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 逐包校验与失败提示、防重复 |
| GUARD-163 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 逐包校验与失败提示、防重复 |
| GUARD-164 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| GUARD-165 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| DOM-001 | [App.tsx:155](../../frontend-v2/src/App.tsx#L155) | 等价页头/导航/页尾、主题与独立旧页入口 |
| DOM-002 | [Dashboard.tsx:43](../../frontend-v2/src/components/views/Dashboard.tsx#L43) | 运行提示、下一步、机器概况/当前任务与总览 |
| DOM-003 | [Dashboard.tsx:43](../../frontend-v2/src/components/views/Dashboard.tsx#L43) | 运行提示、下一步、机器概况/当前任务与总览 |
| DOM-005 | [Dashboard.tsx:43](../../frontend-v2/src/components/views/Dashboard.tsx#L43) | 运行提示、下一步、机器概况/当前任务与总览 |
| DOM-006 | [TaskViews.tsx:29](../../frontend-v2/src/components/views/TaskViews.tsx#L29) | 任务箱选择和历史区域 |
| DOM-007 | [TaskViews.tsx:29](../../frontend-v2/src/components/views/TaskViews.tsx#L29) | 任务箱选择和历史区域 |
| DOM-008 | [TaskViews.tsx:29](../../frontend-v2/src/components/views/TaskViews.tsx#L29) | 任务箱选择和历史区域 |
| DOM-009 | [Dashboard.tsx:604](../../frontend-v2/src/components/views/Dashboard.tsx#L604) | 系统健康与资源指标 |
| DOM-010 | [Dashboard.tsx:604](../../frontend-v2/src/components/views/Dashboard.tsx#L604) | 系统健康与资源指标 |
| DOM-011 | [Dashboard.tsx:604](../../frontend-v2/src/components/views/Dashboard.tsx#L604) | 系统健康与资源指标 |
| DOM-012 | [Dashboard.tsx:604](../../frontend-v2/src/components/views/Dashboard.tsx#L604) | 系统健康与资源指标 |
| DOM-013 | [Dashboard.tsx:604](../../frontend-v2/src/components/views/Dashboard.tsx#L604) | 系统健康与资源指标 |
| DOM-014 | [Dashboard.tsx:604](../../frontend-v2/src/components/views/Dashboard.tsx#L604) | 系统健康与资源指标 |
| DOM-015 | [Dashboard.tsx:604](../../frontend-v2/src/components/views/Dashboard.tsx#L604) | 系统健康与资源指标 |
| DOM-016 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期选择、五步卡片和明细 |
| DOM-017 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期选择、五步卡片和明细 |
| DOM-018 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期选择、五步卡片和明细 |
| DOM-019 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期选择、五步卡片和明细 |
| DOM-020 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期选择、五步卡片和明细 |
| DOM-021 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期选择、五步卡片和明细 |
| DOM-022 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期选择、五步卡片和明细 |
| DOM-023 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 下载失败清单与空状态 |
| DOM-024 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-025 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-026 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-027 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-028 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-029 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-030 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-031 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-032 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-033 | [Dashboard.tsx:119](../../frontend-v2/src/components/views/Dashboard.tsx#L119) | 生产安全八类卡片与计数 |
| DOM-034 | [TaskViews.tsx:324](../../frontend-v2/src/components/views/TaskViews.tsx#L324) | 第五步列表及项目筛选 |
| DOM-035 | [TaskViews.tsx:324](../../frontend-v2/src/components/views/TaskViews.tsx#L324) | 第五步列表及项目筛选 |
| DOM-036 | [Dashboard.tsx:268](../../frontend-v2/src/components/views/Dashboard.tsx#L268) | 上传进度、重扫及历史核验、项目缺口与任务操作 |
| DOM-037 | [Dashboard.tsx:268](../../frontend-v2/src/components/views/Dashboard.tsx#L268) | 上传进度、重扫及历史核验、项目缺口与任务操作 |
| DOM-038 | [Dashboard.tsx:268](../../frontend-v2/src/components/views/Dashboard.tsx#L268) | 上传进度、重扫及历史核验、项目缺口与任务操作 |
| DOM-041 | [Dashboard.tsx:268](../../frontend-v2/src/components/views/Dashboard.tsx#L268) | 上传进度、重扫及历史核验、项目缺口与任务操作 |
| DOM-042 | [CloudViews.tsx:336](../../frontend-v2/src/components/views/CloudViews.tsx#L336) | 三类入口和待删区，FileManagers承载实际管理视图 |
| DOM-043 | [CloudViews.tsx:336](../../frontend-v2/src/components/views/CloudViews.tsx#L336) | 三类入口和待删区，FileManagers承载实际管理视图 |
| DOM-044 | [CloudViews.tsx:336](../../frontend-v2/src/components/views/CloudViews.tsx#L336) | 三类入口和待删区，FileManagers承载实际管理视图 |
| DOM-045 | [CloudViews.tsx:336](../../frontend-v2/src/components/views/CloudViews.tsx#L336) | 三类入口和待删区，FileManagers承载实际管理视图 |
| DOM-046 | [CloudViews.tsx:336](../../frontend-v2/src/components/views/CloudViews.tsx#L336) | 三类入口和待删区，FileManagers承载实际管理视图 |
| DOM-047 | [CloudViews.tsx:336](../../frontend-v2/src/components/views/CloudViews.tsx#L336) | 三类入口和待删区，FileManagers承载实际管理视图 |
| DOM-048 | [ResetAction.tsx:6](../../frontend-v2/src/components/views/ResetAction.tsx#L6) | 安全继续及重置显示区；ContinueActions独立门禁和确认 |
| DOM-049 | [ResetAction.tsx:6](../../frontend-v2/src/components/views/ResetAction.tsx#L6) | 安全继续及重置显示区；ContinueActions独立门禁和确认 |
| DOM-050 | [ResetAction.tsx:6](../../frontend-v2/src/components/views/ResetAction.tsx#L6) | 安全继续及重置显示区；ContinueActions独立门禁和确认 |
| DOM-051 | [ResetAction.tsx:6](../../frontend-v2/src/components/views/ResetAction.tsx#L6) | 安全继续及重置显示区；ContinueActions独立门禁和确认 |
| DOM-052 | [TaskViews.tsx:324](../../frontend-v2/src/components/views/TaskViews.tsx#L324) | TaskOperations新建/补链表单；测试与任务浏览器验证 |
| DOM-063 | [Dashboard.tsx:444](../../frontend-v2/src/components/views/Dashboard.tsx#L444) | 项目状态/最近事件 |
| DOM-064 | [Dashboard.tsx:444](../../frontend-v2/src/components/views/Dashboard.tsx#L444) | 项目状态/最近事件 |
| DOM-116 | [App.tsx:155](../../frontend-v2/src/App.tsx#L155) | 等价页头/导航/页尾、主题与独立旧页入口 |
| EVENT-007 | [home-cleanup.ts:105](../../frontend-v2/src/data/home-cleanup.ts#L105) | 原JSON正文、独立超时与错误提示；云端使用队列写入器 |
| EVENT-012 | [TaskViews.tsx:165](../../frontend-v2/src/components/views/TaskViews.tsx#L165) | 日期/任务箱/项目筛选回调保持原选择语义 |
| EVENT-013 | [TaskViews.tsx:29](../../frontend-v2/src/components/views/TaskViews.tsx#L29) | 日期/任务箱/项目筛选回调保持原选择语义 |
| EVENT-014 | [TaskViews.tsx:324](../../frontend-v2/src/components/views/TaskViews.tsx#L324) | 日期/任务箱/项目筛选回调保持原选择语义 |
| EVENT-046 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| EVENT-054 | [client.ts:3](../../frontend-v2/src/data/client.ts#L3) | 只读网络适配、202、缓存、401及取消；子功能均已迁移 |
| EVENT-055 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| EVENT-058 | [client.ts:3](../../frontend-v2/src/data/client.ts#L3) | 只读网络适配、202、缓存、401及取消；子功能均已迁移 |
| EVENT-059 | [client.ts:3](../../frontend-v2/src/data/client.ts#L3) | 只读网络适配、202、缓存、401及取消；子功能均已迁移 |
| EVENT-060 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| EVENT-061 | [upload-writer.ts:37](../../frontend-v2/src/data/upload-writer.ts#L37) | 显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver |
| EVENT-062 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| EVENT-063 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| EVENT-064 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| EVENT-075 | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11) | 账号CSRF及原方法/状态码；读取目录仍用GET |
| EVENT-076 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| EVENT-077 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |
| PATH-022 | [ResetAction.tsx:18](../../frontend-v2/src/components/views/ResetAction.tsx#L18) | home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用 |
| PATH-028 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| PATH-029 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| PATH-030 | [AccountActions.tsx:6](../../frontend-v2/src/components/views/AccountActions.tsx#L6) | 已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login |
| PATH-031 | [useDashboard.ts:197](../../frontend-v2/src/data/useDashboard.ts#L197) | 共享只读轮询与状态、完整看板定时刷新 |
| PATH-032 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-033 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-034 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-035 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-036 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-037 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-038 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-039 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-040 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-041 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-042 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-043 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-044 | [CloudViews.tsx:69](../../frontend-v2/src/components/views/CloudViews.tsx#L69) | 数据来源、名称、年龄和新鲜度颜色 |
| PATH-065 | [console-admin.ts:11](../../frontend-v2/src/data/console-admin.ts#L11) | 账号CSRF及原方法/状态码；读取目录仍用GET |
| PATH-066 | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215) | 目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| PATH-067 | [CloudViews.tsx:215](../../frontend-v2/src/components/views/CloudViews.tsx#L215) | 目录、加密下载链接、容量、日期/阶段、事件及空状态 |
| PATH-068 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 逐包校验与失败提示、防重复 |
| PATH-069 | [BackupAction.tsx:15](../../frontend-v2/src/components/views/BackupAction.tsx#L15) | 请求一次备份、排队反馈；目录按需展开和刷新 |

## 延期范围（用户明确批准）

FN-366、FN-367、FN-368、NET-051、NET-052、GUARD-166、GUARD-167、DOM-117、DOM-118、DOM-119、DOM-120、DOM-121、DOM-122、DOM-123、DOM-124、DOM-125、DOM-126、EVENT-078、PATH-070、PATH-071、PATH-072、PATH-073。这些条目保持未勾选，disposition=user-deferred-login-registration-2026-10-20。其余条目仅标注实现/隔离验证，不代表真实生产影子或默认切换。

## 测试及边界

208项前端测试（新增22项），typecheck/lint通过；361项隔离业务测试通过（1跳过）。账号/备份仅云端接口及CSRF，不经过家里业务队列；家里重置保持直接原接口、两次确认、10秒超时，云端永远禁用。不保存密码、口令或邀请码。备份下载仅密文，不增加恢复执行。

无新增依赖，复用已有shadcn Button/Input，来源与许可证见public/dependencies.json及licenses/。不修改后端/旧页面、不合并、不部署、不重启家里程序。回滚revert本PR和static/v2产物，旧入口保留。浏览器截图为模拟夹具，密码拒绝HTTP400属于预期负例，原始日志单列。
