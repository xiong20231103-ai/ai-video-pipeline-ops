# V2-2B 任务操作逐行对照

补链、建任务、启动首项和撤回。仅前端改动，家里直接调用原接口，云端同源请求仍收件入队；不接安全继续或清理。全部测试使用隔离夹具，不部署。

| 原行 | 原代码 | V2 位置与对应行为 |
|---|---|---|
| [app.js:1](../../static/app.js#L1) | `function currentLocalDateLabel() {` | [TaskOperations.tsx:24](../../frontend-v2/src/components/views/TaskOperations.tsx#L24)；本机日期默认值 |
| [app.js:2](../../static/app.js#L2) | `const value = new Date();` | [TaskOperations.tsx:24](../../frontend-v2/src/components/views/TaskOperations.tsx#L24)；本机日期默认值 |
| [app.js:3](../../static/app.js#L3) | `return \`${value.getMonth() + 1}.${value.getDate()}\`;` | [TaskOperations.tsx:24](../../frontend-v2/src/components/views/TaskOperations.tsx#L24)；本机日期默认值 |
| [app.js:4](../../static/app.js#L4) | `}` | [TaskOperations.tsx:24](../../frontend-v2/src/components/views/TaskOperations.tsx#L24)；本机日期默认值 |
| [app.js:993](../../static/app.js#L993) | `function renderGapQuickBar(items = []) {` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:994](../../static/app.js#L994) | `const bar = $("gapQuickBar");` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:995](../../static/app.js#L995) | `const title = $("gapQuickTitle");` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:996](../../static/app.js#L996) | `const summary = $("gapQuickSummary");` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:997](../../static/app.js#L997) | `const actions = $("gapQuickActions");` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:998](../../static/app.js#L998) | `if (!bar \|\| !title \|\| !summary \|\| !actions) return;` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:999](../../static/app.js#L999) | `const active = items.filter(item => Boolean(item.gapActive) && String(item.taskId \|\| ""));` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1000](../../static/app.js#L1000) | `if (!active.length) {` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1001](../../static/app.js#L1001) | `bar.classList.add("hidden");` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1002](../../static/app.js#L1002) | `actions.innerHTML = "";` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1003](../../static/app.js#L1003) | `return;` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1004](../../static/app.js#L1004) | `}` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1005](../../static/app.js#L1005) | `const missingFor = item => Number(item.missingCount ?? Math.max(` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1006](../../static/app.js#L1006) | `0,` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1007](../../static/app.js#L1007) | `Number(item.expectedCount \|\| 0) - Number(item.completed \|\| 0),` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1008](../../static/app.js#L1008) | `));` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1009](../../static/app.js#L1009) | `const totalMissing = active.reduce((total, item) => total + missingFor(item), 0);` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1010](../../static/app.js#L1010) | `title.textContent = active.length === 1 ? "当前项目需要补链" : \`${active.length} 个项目需要补链\`;` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1011](../../static/app.js#L1011) | `summary.textContent = \`合计缺少 ${totalMissing} 条，点击项目直接补充\`;` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1012](../../static/app.js#L1012) | `actions.innerHTML = active.map(item => \`` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1013](../../static/app.js#L1013) | `<button type="button" data-task-id="${escapeHtml(String(item.taskId \|\| ""))}" onclick="openReplenishment(this.dataset.taskId)">` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1014](../../static/app.js#L1014) | `${escapeHtml(item.project \|\| "未分类")} / ${escapeHtml(item.material \|\| "--")} · 缺 ${missingFor(item)} 条` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1015](../../static/app.js#L1015) | `</button>\`).join("");` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1016](../../static/app.js#L1016) | `bar.classList.remove("hidden");` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1017](../../static/app.js#L1017) | `}` | [Dashboard.tsx:634](../../frontend-v2/src/components/views/Dashboard.tsx#L634)；模板/材料/默认数量和补链入口 |
| [app.js:1058](../../static/app.js#L1058) | `function renderTemplates(items) {` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1059](../../static/app.js#L1059) | `const nextTemplates = Array.isArray(items) ? items : [];` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1060](../../static/app.js#L1060) | `const signature = JSON.stringify(nextTemplates);` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1061](../../static/app.js#L1061) | `const select = $("createTemplate");` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1062](../../static/app.js#L1062) | `if (!select) return;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1063](../../static/app.js#L1063) | `if (signature === state.templateSignature && select.options.length > 1) return;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1064](../../static/app.js#L1064) | `state.templates = nextTemplates;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1065](../../static/app.js#L1065) | `state.templateSignature = signature;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1066](../../static/app.js#L1066) | `const previous = select.value;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1067](../../static/app.js#L1067) | `select.innerHTML = \`<option value="">请选择项目</option>${state.templates.map(item =>` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1068](../../static/app.js#L1068) | `\`<option value="${escapeHtml(item.id)}">${escapeHtml(item.label \|\| \`${item.project} / ${item.material}\`)}</option>\`` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1069](../../static/app.js#L1069) | `).join("")}\`;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1070](../../static/app.js#L1070) | `if (previous && state.templates.some(item => String(item.id) === previous)) select.value = previous;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1071](../../static/app.js#L1071) | `updateMaterialOptions();` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1072](../../static/app.js#L1072) | `}` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1074](../../static/app.js#L1074) | `function updateMaterialOptions() {` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1075](../../static/app.js#L1075) | `const template = state.templates.find(item => String(item.id) === String($("createTemplate")?.value \|\| ""));` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1076](../../static/app.js#L1076) | `const select = $("createMaterial");` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1077](../../static/app.js#L1077) | `const count = $("createExpectedCount");` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1078](../../static/app.js#L1078) | `if (!select) return;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1079](../../static/app.js#L1079) | `const materials = template?.materials?.length ? template.materials : (template?.material ? [template.material] : []);` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1080](../../static/app.js#L1080) | `select.innerHTML = materials.map(item => \`<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>\`).join("");` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1081](../../static/app.js#L1081) | `if (count && template?.expectedCount) count.value = template.expectedCount;` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1082](../../static/app.js#L1082) | `}` | [TaskOperations.tsx:54](../../frontend-v2/src/components/views/TaskOperations.tsx#L54)；模板/材料/默认数量和补链入口 |
| [app.js:1117](../../static/app.js#L1117) | `function openReplenishment(taskId) {` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1118](../../static/app.js#L1118) | `const item = state.gaps[String(taskId)];` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1119](../../static/app.js#L1119) | `const panel = $("replenishPanel");` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1120](../../static/app.js#L1120) | `const dialog = $("replenishDialog");` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1121](../../static/app.js#L1121) | `if (!item \|\| !panel) return;` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1122](../../static/app.js#L1122) | `const expected = Number(item.expectedCount \|\| 0);` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1123](../../static/app.js#L1123) | `const completed = Number(item.completed \|\| 0);` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1124](../../static/app.js#L1124) | `const missing = Number(item.missingCount ?? Math.max(0, expected - completed));` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1125](../../static/app.js#L1125) | `panel.innerHTML = \`<header><div><strong>补链：${escapeHtml(item.project)} / ${escapeHtml(item.material)}</strong>` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1126](../../static/app.js#L1126) | `<p>原计划 ${expected} 条，已完成 ${completed} 条；请只粘贴 ${missing} 条新链接。</p></div>` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1127](../../static/app.js#L1127) | `<button id="closeReplenishDialog" type="button" aria-label="关闭补链窗口">×</button></header>` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1128](../../static/app.js#L1128) | `<form id="replenishForm"><label class="wide">新链接（每行一条）<textarea id="replenishUrls" rows="4" required></textarea></label>` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1129](../../static/app.js#L1129) | `<label class="wide checkbox"><input id="replenishStartNow" type="checkbox" checked>补链后继续当前项目</label>` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1130](../../static/app.js#L1130) | `<button class="primary wide" type="submit">提交补链</button></form>\`;` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1131](../../static/app.js#L1131) | `$("closeReplenishDialog")?.addEventListener("click", () => dialog?.close());` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1132](../../static/app.js#L1132) | `$("replenishForm").addEventListener("submit", async (event) => {` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1133](../../static/app.js#L1133) | `event.preventDefault();` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1134](../../static/app.js#L1134) | `const button = event.currentTarget.querySelector("button");` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1135](../../static/app.js#L1135) | `button.disabled = true;` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1136](../../static/app.js#L1136) | `try {` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1137](../../static/app.js#L1137) | `const result = await postJson(\`/api/controls/tasks/${encodeURIComponent(taskId)}/replenish\`, {` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1138](../../static/app.js#L1138) | `urls: $("replenishUrls").value,` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1139](../../static/app.js#L1139) | `startNow: $("replenishStartNow").checked,` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1140](../../static/app.js#L1140) | `});` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1141](../../static/app.js#L1141) | `renderActionResult("queueActionResult", {` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1142](../../static/app.js#L1142) | `state: "completed",` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1143](../../static/app.js#L1143) | `message: result.message \|\| "补链任务已提交",` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1144](../../static/app.js#L1144) | `updatedAt: new Date().toISOString(),` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1145](../../static/app.js#L1145) | `});` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1146](../../static/app.js#L1146) | `if (dialog?.open) dialog.close();` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1147](../../static/app.js#L1147) | `panel.innerHTML = "";` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1148](../../static/app.js#L1148) | `await refresh();` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1149](../../static/app.js#L1149) | `} catch (error) {` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1150](../../static/app.js#L1150) | `renderActionResult("queueActionResult", {` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1151](../../static/app.js#L1151) | `state: "failed",` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1152](../../static/app.js#L1152) | `message: error.message \|\| "补链失败",` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1153](../../static/app.js#L1153) | `updatedAt: new Date().toISOString(),` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1154](../../static/app.js#L1154) | `});` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1155](../../static/app.js#L1155) | `button.disabled = false;` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1156](../../static/app.js#L1156) | `}` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1157](../../static/app.js#L1157) | `});` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1158](../../static/app.js#L1158) | `if (dialog && !dialog.open) dialog.showModal();` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1159](../../static/app.js#L1159) | `$("replenishUrls")?.focus();` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1160](../../static/app.js#L1160) | `}` | [TaskOperations.tsx:118](../../frontend-v2/src/components/views/TaskOperations.tsx#L118)；补链表单、缺口、默认继续勾选、原 URL 正文 |
| [app.js:1162](../../static/app.js#L1162) | `function renderReceiverQueue(items) {` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1163](../../static/app.js#L1163) | `const node = $("receiverQueue");` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1164](../../static/app.js#L1164) | `if (!node) return;` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1165](../../static/app.js#L1165) | `if (!items.length) {` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1166](../../static/app.js#L1166) | `node.innerHTML = \`<p class="empty">暂无可确认或撤回的队列任务</p>\`;` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1167](../../static/app.js#L1167) | `return;` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1168](../../static/app.js#L1168) | `}` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1169](../../static/app.js#L1169) | `// 223 items imported in July-September stayed "imported_waiting_start" and` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1170](../../static/app.js#L1170) | `// made this list 25,000 px long.  Keep what can need a decision in view.` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1171](../../static/app.js#L1171) | `const recentMs = 3 * 24 * 3600 * 1000;` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1172](../../static/app.js#L1172) | `const isRecent = item => String(item.status \|\| "") === "pending_confirmation" \|\|` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1173](../../static/app.js#L1173) | `Date.now() - Date.parse(item.importedAt \|\| item.createdAt \|\| "") < recentMs;` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1174](../../static/app.js#L1174) | `const recent = items.filter(isRecent);` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1175](../../static/app.js#L1175) | `const older = items.filter(item => !isRecent(item));` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1176](../../static/app.js#L1176) | `const render = list => list.map(item => {` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1177](../../static/app.js#L1177) | `const taskId = String(item.taskId \|\| "");` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1178](../../static/app.js#L1178) | `const status = String(item.status \|\| "");` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1179](../../static/app.js#L1179) | `const canStart = status === "pending_confirmation" && !["auto_start_first", "auto_start_sequential"].includes(String(item.startMode \|\| ""));` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1180](../../static/app.js#L1180) | `const canCancel = status === "pending_confirmation" \|\| status === "imported_waiting_start";` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1181](../../static/app.js#L1181) | `const sequence = item.batchId ? \`第 ${item.batchSequence \|\| 1} / ${item.batchSize \|\| 1} 项\` : "单条任务";` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1182](../../static/app.js#L1182) | `const actions = [` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1183](../../static/app.js#L1183) | `canStart ? \`<button class="start" data-task-id="${escapeHtml(taskId)}" onclick="controlTask(this, 'start')">启动首项</button>\` : "",` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1184](../../static/app.js#L1184) | `canCancel ? \`<button class="cancel" data-task-id="${escapeHtml(taskId)}" onclick="controlTask(this, 'cancel')">撤回</button>\` : "",` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1185](../../static/app.js#L1185) | `].join("");` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1186](../../static/app.js#L1186) | `return \`<article class="receiver-queue-item">` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1187](../../static/app.js#L1187) | `<div><strong>${escapeHtml(item.project \|\| "未分类")} / ${escapeHtml(item.material \|\| "--")}</strong><span class="task-state neutral">${escapeHtml(status)}</span></div>` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1188](../../static/app.js#L1188) | `<small>${escapeHtml(item.date \|\| "--")} · ${escapeHtml(sequence)} · ${Number((item.urls \|\| []).length)} 条链接</small>` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1189](../../static/app.js#L1189) | `${actions ? \`<div class="queue-actions">${actions}</div>\` : ""}` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1190](../../static/app.js#L1190) | `</article>\`;` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1191](../../static/app.js#L1191) | `}).join("");` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1192](../../static/app.js#L1192) | `const wasOpen = Boolean(node.querySelector("details.receiver-queue-older")?.open);` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1193](../../static/app.js#L1193) | `node.innerHTML = (recent.length ? render(recent) : \`<p class="empty">最近 3 天没有需要确认或撤回的任务</p>\`)` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1194](../../static/app.js#L1194) | `+ (older.length ? \`<details class="receiver-queue-older"${wasOpen ? " open" : ""}>` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1195](../../static/app.js#L1195) | `<summary>更早导入的 ${older.length} 条任务（超过 3 天，通常无需操作）</summary>${render(older)}</details>\` : "");` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1196](../../static/app.js#L1196) | `}` | [TaskViews.tsx:445](../../frontend-v2/src/components/views/TaskViews.tsx#L445)；原队列筛选与启动/撤回资格 |
| [app.js:1578](../../static/app.js#L1578) | `async function controlTask(button, action) {` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1579](../../static/app.js#L1579) | `const taskId = String(button.dataset.taskId \|\| "");` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1580](../../static/app.js#L1580) | `if (!taskId) return;` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1581](../../static/app.js#L1581) | `const isStart = action === "start";` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1582](../../static/app.js#L1582) | `const question = isStart` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1583](../../static/app.js#L1583) | `? "确认启动这个批次的首项吗？工作台会继续按原有顺序处理。"` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1584](../../static/app.js#L1584) | `: "确认撤回这个尚未开始的任务吗？不会删除任何视频、音频或素材。";` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1585](../../static/app.js#L1585) | `if (!window.confirm(question)) return;` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1586](../../static/app.js#L1586) | `button.disabled = true;` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1587](../../static/app.js#L1587) | `button.textContent = isStart ? "正在启动…" : "正在撤回…";` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1588](../../static/app.js#L1588) | `try {` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1589](../../static/app.js#L1589) | `const response = await fetch(\`/api/controls/tasks/${encodeURIComponent(taskId)}/${action}\`, { method: "POST" });` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1590](../../static/app.js#L1590) | `const result = await response.json();` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1591](../../static/app.js#L1591) | `if (!response.ok) throw new Error(result.detail \|\| "操作失败");` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1592](../../static/app.js#L1592) | `renderActionResult("queueActionResult", {` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1593](../../static/app.js#L1593) | `state: window.opsCloudPostJson ? (result.state \|\| "requested") : "completed",` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1594](../../static/app.js#L1594) | `message: result.message \|\| (isStart ? "启动命令已发送" : "撤回命令已发送"),` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1595](../../static/app.js#L1595) | `updatedAt: new Date().toISOString(),` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1596](../../static/app.js#L1596) | `});` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1597](../../static/app.js#L1597) | `await refresh();` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1598](../../static/app.js#L1598) | `} catch (error) {` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1599](../../static/app.js#L1599) | `renderActionResult("queueActionResult", {` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1600](../../static/app.js#L1600) | `state: "failed",` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1601](../../static/app.js#L1601) | `message: error.message \|\| "操作失败",` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1602](../../static/app.js#L1602) | `updatedAt: new Date().toISOString(),` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1603](../../static/app.js#L1603) | `});` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1604](../../static/app.js#L1604) | `button.disabled = false;` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1605](../../static/app.js#L1605) | `button.textContent = isStart ? "启动首项" : "撤回";` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1606](../../static/app.js#L1606) | `}` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1607](../../static/app.js#L1607) | `}` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1609](../../static/app.js#L1609) | `// The 5-second status refresh keeps an 8 s limit; the file managers scan` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:1610](../../static/app.js#L1610) | `// thousands of files (production files: 2,752 in about 12 s on 2026-10-11)` | [TaskOperations.tsx:87](../../frontend-v2/src/components/views/TaskOperations.tsx#L87)；原确认文字、无正文家里 POST 与禁用/错误处理 |
| [app.js:2152](../../static/app.js#L2152) | `$("createTemplate").addEventListener("change", updateMaterialOptions);` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2153](../../static/app.js#L2153) | `$("createTaskForm").addEventListener("submit", async (event) => {` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2154](../../static/app.js#L2154) | `event.preventDefault();` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2155](../../static/app.js#L2155) | `const form = event.currentTarget;` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2156](../../static/app.js#L2156) | `const button = form.querySelector("button[type='submit']");` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2157](../../static/app.js#L2157) | `button.disabled = true;` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2158](../../static/app.js#L2158) | `try {` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2159](../../static/app.js#L2159) | `const result = await postJson("/api/controls/tasks/create", {` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2160](../../static/app.js#L2160) | `date: $("createDate").value.trim(),` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2161](../../static/app.js#L2161) | `templateId: $("createTemplate").value,` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2162](../../static/app.js#L2162) | `material: $("createMaterial").value,` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2163](../../static/app.js#L2163) | `audioBatch: $("createAudioBatch").value.trim(),` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2164](../../static/app.js#L2164) | `voicePlan: $("createVoicePlan").value,` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2165](../../static/app.js#L2165) | `expectedCount: $("createExpectedCount").value,` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2166](../../static/app.js#L2166) | `urls: $("createUrls").value,` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2167](../../static/app.js#L2167) | `startNow: $("createStartNow").checked,` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2168](../../static/app.js#L2168) | `});` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2169](../../static/app.js#L2169) | `form.reset();` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2170](../../static/app.js#L2170) | `$("createDate").value = currentLocalDateLabel();` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2171](../../static/app.js#L2171) | `renderActionResult("queueActionResult", {` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2172](../../static/app.js#L2172) | `state: "completed",` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2173](../../static/app.js#L2173) | `message: result.message \|\| "任务已提交",` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2174](../../static/app.js#L2174) | `updatedAt: new Date().toISOString(),` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2175](../../static/app.js#L2175) | `});` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2176](../../static/app.js#L2176) | `await refresh();` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2177](../../static/app.js#L2177) | `} catch (error) {` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2178](../../static/app.js#L2178) | `renderActionResult("queueActionResult", {` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2179](../../static/app.js#L2179) | `state: "failed",` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2180](../../static/app.js#L2180) | `message: error.message \|\| "提交失败",` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2181](../../static/app.js#L2181) | `updatedAt: new Date().toISOString(),` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2182](../../static/app.js#L2182) | `});` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2183](../../static/app.js#L2183) | `}` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2184](../../static/app.js#L2184) | `finally { button.disabled = false; }` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |
| [app.js:2185](../../static/app.js#L2185) | `});` | [TaskOperations.tsx:153](../../frontend-v2/src/components/views/TaskOperations.tsx#L153)；原八个字段、成功重置、失败保留 |

## 云端原实现 → V2

| 来源 | V2 | 不变契约 |
|---|---|---|
| [commands.js:64](../../cloud/commands.js#L64) `throw new Error(labels[value?.state]\|\|'尚未得到家里回执；请看云端命令面板，不要重复提交');` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:65](../../cloud/commands.js#L65) `}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:66](../../cloud/commands.js#L66) `async function dispatch(path,payload){` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:67](../../cloud/commands.js#L67) `if(!allowedPath(path))throw new Error('此操作尚未开放云端执行');` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:68](../../cloud/commands.js#L68) `if(path==='/api/controls/cloud-cleanup/preview'){records=records.filter(r=>r.path!==path\|\|pending.has(r.state));save();}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:69](../../cloud/commands.js#L69) `const comparable={...payload};if(path==='/api/control-commands')delete comparable.clientRequestId;` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:70](../../cloud/commands.js#L70) `const fingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(path+'\n'+JSON.stringify(stable(comparable))))),v=>v.toString(16).padStart(2,'0')).join('');` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:71](../../cloud/commands.js#L71) `if(active.has(fingerprint))return (await active.get(fingerprint)).clone();` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:72](../../cloud/commands.js#L72) `const work=(async()=>{` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:73](../../cloud/commands.js#L73) `let record=records.find(r=>r.fingerprint===fingerprint),value;` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:74](../../cloud/commands.js#L74) `if(!record){` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:75](../../cloud/commands.js#L75) `if(!health.executorAvailable\|\|!health.homeReady\|\|health.commandBlocker\|\|unfinished())throw new Error('家里未就绪，或有待对账命令；尚未提交');` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:76](../../cloud/commands.js#L76) `record={path,fingerprint,requestId:crypto.randomUUID(),state:'submitting',updatedAt:Date.now()};records.push(record);save();paint();` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:77](../../cloud/commands.js#L77) `const body={...payload};if(path==='/api/control-commands')body.clientRequestId=record.requestId;` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:78](../../cloud/commands.js#L78) `const info=await credentials();` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:79](../../cloud/commands.js#L79) `try{` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:80](../../cloud/commands.js#L80) `const response=await network(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf,'X-Client-Request-ID':record.requestId},body:JSON.stringify(body)});` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:81](../../cloud/commands.js#L81) `const answer=await response.json();` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:82](../../cloud/commands.js#L82) `if(response.status===202&&answer.cloudCommand) value=capture(record,answer);` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:83](../../cloud/commands.js#L83) `else if(response.ok)throw new Error('云端未返回排队契约，停止自动处理');` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:84](../../cloud/commands.js#L84) `else{record.state='not_sent';save();paint();throw new Error(answer.detail\|\|'云端拒绝收件');}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:85](../../cloud/commands.js#L85) `}catch(error){if(record.state==='not_sent')throw error;/* Lost acknowledgement: GET only, never repeat POST. */}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:86](../../cloud/commands.js#L86) `}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:87](../../cloud/commands.js#L87) `for(let n=0;n<(path.endsWith('/cloud-cleanup/execute')?1000:180);n++){` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:88](../../cloud/commands.js#L88) `value=value\|\|await query(record);` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:89](../../cloud/commands.js#L89) `if(value&&!['queued','leased','sent'].includes(value.state))return finalResponse(value);` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:90](../../cloud/commands.js#L90) `await delay(1000);value=null;` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:91](../../cloud/commands.js#L91) `}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:92](../../cloud/commands.js#L92) `throw new Error('仍在查询命令回执；面板将继续查询，不会自动重发。输入内容保留。');` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:93](../../cloud/commands.js#L93) `})();active.set(fingerprint,work);` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:94](../../cloud/commands.js#L94) `try{return (await work).clone();}finally{active.delete(fingerprint);paint();}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:95](../../cloud/commands.js#L95) `}` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:96](../../cloud/commands.js#L96) `window.opsCloudDispatch=dispatch;` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:97](../../cloud/commands.js#L97) `window.opsCloudWriteFetch=(url,init={})=>{` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:98](../../cloud/commands.js#L98) `if((init.method\|\|'GET').toUpperCase()!=='POST')throw new Error('仅支持已声明的 POST 命令');` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:99](../../cloud/commands.js#L99) `const path=new URL(url,location.origin).pathname;return dispatch(path,init.body?JSON.parse(init.body):{});` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:100](../../cloud/commands.js#L100) `};` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |
| [commands.js:101](../../cloud/commands.js#L101) `window.opsCloudPostJson=async(url,body)=>{const r=await dispatch(new URL(url,location.origin).pathname,body);const result=await r.json();if(!r.ok)throw new Error(result.detail\|\|'家里拒绝该操作');return result;};` | [upload-writer.ts:148](../../frontend-v2/src/data/upload-writer.ts#L148) | 原指纹/身份/CSRF、一次入队、GET 查回执、HTTP 错误原文、结果不明不重发；家里 start/cancel 无正文，云端由旧适配器语义转为 {}。 |

## 验证与边界

42项前端测试；home/cloud 两模式分别验证建任务字段、补链 URL 原文与 startNow、启动/撤回原确认、取消不发送、防重复和失败保留。继承上传传输的超时、身份与结果不明测试。同数据只读对比继续运行。浏览器所有请求全拦截，四尺寸深浅表单和补链截图；每次重载不重复 POST。无新增依赖；复用已固定的 shadcn Sheet/Button/Input。原始 Sheet 来源和许可证见 README。

未实现：云端回执管理中的取消/人工对账、其他操作、真实完整生产影子和切换；相关清单保持未完成。新建任务和补链失败时保持输入；模板列表变化时按旧规则保留有效选择、重建材料和默认数量。回滚 revert 本 PR 和 static/v2 产物，旧页面不受影响，无需重启家里。
