# V2-2A 上传重扫 / 历史核验逐行对照

仅静态前端；家里直接 POST，云端仍由原同源接口收件入队。所有验证均 mock/全网络拦截，不执行生产操作。

| 原实现行 | 原代码 | V2 对应 |
|---|---|---|
| [app.js:1087](../../static/app.js#L1087) | `async function postJson(url, payload, options = {}) {` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1088](../../static/app.js#L1088) | `if (window.opsCloudPostJson) return window.opsCloudPostJson(url, payload);` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1089](../../static/app.js#L1089) | `const timeoutMs = Number.isFinite(Number(options.timeoutMs))` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1090](../../static/app.js#L1090) | `? Math.max(1000, Number(options.timeoutMs))` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1091](../../static/app.js#L1091) | `: 10000;` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1092](../../static/app.js#L1092) | `const controller = new AbortController();` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1093](../../static/app.js#L1093) | `const timer = window.setTimeout(() => controller.abort(), timeoutMs);` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1094](../../static/app.js#L1094) | `try {` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1095](../../static/app.js#L1095) | `const response = await fetch(url, {` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1096](../../static/app.js#L1096) | `method: "POST",` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1097](../../static/app.js#L1097) | `headers: { "Content-Type": "application/json" },` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1098](../../static/app.js#L1098) | `body: JSON.stringify(payload),` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1099](../../static/app.js#L1099) | `signal: controller.signal,` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1100](../../static/app.js#L1100) | `});` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1101](../../static/app.js#L1101) | `const result = await response.json();` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1102](../../static/app.js#L1102) | `if (!response.ok) throw new Error(result.detail \|\| "操作失败");` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1103](../../static/app.js#L1103) | `return result;` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1104](../../static/app.js#L1104) | `} catch (error) {` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1105](../../static/app.js#L1105) | `if (error?.name === "AbortError") {` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1106](../../static/app.js#L1106) | `const timeoutError = new Error(\`操作仍在后台处理（已等待 ${Math.ceil(timeoutMs / 60000)} 分钟），请刷新状态后再继续\`);` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1107](../../static/app.js#L1107) | `timeoutError.code = "CONTROL_REQUEST_TIMEOUT";` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1108](../../static/app.js#L1108) | `timeoutError.cause = error;` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1109](../../static/app.js#L1109) | `throw timeoutError;` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1110](../../static/app.js#L1110) | `}` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1111](../../static/app.js#L1111) | `throw error;` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1112](../../static/app.js#L1112) | `} finally {` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1113](../../static/app.js#L1113) | `window.clearTimeout(timer);` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1114](../../static/app.js#L1114) | `}` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1115](../../static/app.js#L1115) | `}` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1117](../../static/app.js#L1117) | `function openReplenishment(taskId) {` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1118](../../static/app.js#L1118) | `const item = state.gaps[String(taskId)];` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1119](../../static/app.js#L1119) | `const panel = $("replenishPanel");` | [upload-writer.ts:77](../../frontend-v2/src/data/upload-writer.ts#L77)；home：10 秒超时，不重发，原错误提示 |
| [app.js:1549](../../static/app.js#L1549) | `function renderActionResult(id, result = {}) {` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1550](../../static/app.js#L1550) | `const node = $(id);` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1551](../../static/app.js#L1551) | `const stateName = String(result.state \|\| "idle");` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1552](../../static/app.js#L1552) | `node.className = \`action-result ${stateName === "completed" ? "completed" : stateName === "failed" ? "failed" : "neutral"}\`;` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1553](../../static/app.js#L1553) | `node.textContent = \`${result.message \|\| "尚无操作记录"}${result.updatedAt ? \` · ${formatDateTime(result.updatedAt)}\` : ""}\`;` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1554](../../static/app.js#L1554) | `}` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1556](../../static/app.js#L1556) | `function renderHistoricalCloudVerification(result = {}) {` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1557](../../static/app.js#L1557) | `const stateName = String(result.state \|\| "idle");` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1558](../../static/app.js#L1558) | `const total = Number(result.total ?? result.eligible ?? 0);` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1559](../../static/app.js#L1559) | `const processed = Number(result.processed \|\| 0);` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1560](../../static/app.js#L1560) | `const verified = Number(result.verified \|\| 0);` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1561](../../static/app.js#L1561) | `const failed = Number(result.failed \|\| 0);` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1562](../../static/app.js#L1562) | `const summary = total` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1563](../../static/app.js#L1563) | `? \` · ${processed}/${total}，通过 ${verified}，失败 ${failed}\`` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1564](../../static/app.js#L1564) | `: "";` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1565](../../static/app.js#L1565) | `renderActionResult("historicalCloudVerificationResult", {` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1566](../../static/app.js#L1566) | `...result,` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1567](../../static/app.js#L1567) | `message: \`${result.message \|\| "尚未核验历史百度云文件"}${summary}\`,` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1568](../../static/app.js#L1568) | `});` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1569](../../static/app.js#L1569) | `const button = $("historicalCloudVerifyButton");` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1570](../../static/app.js#L1570) | `if (!button) return;` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1571](../../static/app.js#L1571) | `const running = ["requested", "running"].includes(stateName);` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1572](../../static/app.js#L1572) | `button.disabled = running;` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1573](../../static/app.js#L1573) | `button.textContent = running` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1574](../../static/app.js#L1574) | `? \`正在核验历史云端文件 ${processed}/${total \|\| "…"}\`` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1575](../../static/app.js#L1575) | `: "核验历史云端文件";` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:1576](../../static/app.js#L1576) | `}` | [upload-writer.ts:34](../../frontend-v2/src/components/views/UploadActions.tsx#L34)；历史结果摘要、请求后运行禁用及时间显示 |
| [app.js:2083](../../static/app.js#L2083) | `$("uploadRescanButton")?.addEventListener("click", async (event) => {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2084](../../static/app.js#L2084) | `const button = event.currentTarget;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2085](../../static/app.js#L2085) | `if (!window.confirm("确认重新对账正式清单，补传遗漏成片，并对云端已实时核验的任务继续安全清理吗？不会重新剪辑等待中的任务，也不会清理配音、公共素材、Logo或公共样品。")) return;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2086](../../static/app.js#L2086) | `button.disabled = true;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2087](../../static/app.js#L2087) | `button.textContent = "正在检查上传缺口…";` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2088](../../static/app.js#L2088) | `try {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2089](../../static/app.js#L2089) | `const result = await postJson("/api/controls/upload/rescan", {});` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2090](../../static/app.js#L2090) | `renderActionResult("uploadActionResult", {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2091](../../static/app.js#L2091) | `state: window.opsCloudPostJson ? (result.state \|\| "requested") : "completed",` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2092](../../static/app.js#L2092) | `message: result.message \|\| (window.opsCloudPostJson ? "家里已接收上传检查请求，请查看实际上传状态" : "上传检查已完成"),` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2093](../../static/app.js#L2093) | `updatedAt: new Date().toISOString(),` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2094](../../static/app.js#L2094) | `});` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2095](../../static/app.js#L2095) | `await refresh();` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2096](../../static/app.js#L2096) | `} catch (error) {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2097](../../static/app.js#L2097) | `renderActionResult("uploadActionResult", {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2098](../../static/app.js#L2098) | `state: "failed",` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2099](../../static/app.js#L2099) | `message: error.message \|\| "上传检查失败",` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2100](../../static/app.js#L2100) | `updatedAt: new Date().toISOString(),` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2101](../../static/app.js#L2101) | `});` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2102](../../static/app.js#L2102) | `} finally {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2103](../../static/app.js#L2103) | `button.disabled = false;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2104](../../static/app.js#L2104) | `button.textContent = "重新对账、补传并清理";` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2105](../../static/app.js#L2105) | `}` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2106](../../static/app.js#L2106) | `});` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2107](../../static/app.js#L2107) | `$("historicalCloudVerifyButton")?.addEventListener("click", async (event) => {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2108](../../static/app.js#L2108) | `const button = event.currentTarget;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2109](../../static/app.js#L2109) | `if (!window.confirm("确认核验历史百度云文件吗？系统只会查询云端文件是否存在，并核对云端路径和文件大小；不会补传、不会删除本地或云端文件，也不会改变项目完成状态。")) return;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2110](../../static/app.js#L2110) | `button.disabled = true;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2111](../../static/app.js#L2111) | `button.textContent = "正在提交历史核验…";` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2112](../../static/app.js#L2112) | `try {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2113](../../static/app.js#L2113) | `const result = await postJson("/api/controls/upload/verify-history", {});` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2114](../../static/app.js#L2114) | `renderHistoricalCloudVerification(result);` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2115](../../static/app.js#L2115) | `await refresh();` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2116](../../static/app.js#L2116) | `} catch (error) {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2117](../../static/app.js#L2117) | `renderHistoricalCloudVerification({` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2118](../../static/app.js#L2118) | `state: "failed",` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2119](../../static/app.js#L2119) | `message: error.message \|\| "历史百度云核验提交失败",` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2120](../../static/app.js#L2120) | `updatedAt: new Date().toISOString(),` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2121](../../static/app.js#L2121) | `});` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2122](../../static/app.js#L2122) | `}` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2123](../../static/app.js#L2123) | `});` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2124](../../static/app.js#L2124) | `$("resetTestRecordsButton")?.addEventListener("click", async (event) => {` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2125](../../static/app.js#L2125) | `const button = event.currentTarget;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |
| [app.js:2126](../../static/app.js#L2126) | `if (!window.confirm("确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。")) return;` | [UploadActions.tsx:41](../../frontend-v2/src/components/views/UploadActions.tsx#L41)；run：原确认文字、禁用、空请求体、结果显示、刷新和错误处理 |

云端命令传输（保留 shared localStorage key 与原指纹、requestId 语义）：

| 原实现行 | 原代码 | V2 对应 |
|---|---|---|
| [commands.js:48](../../cloud/commands.js#L48) | `if(record.path==='/api/control-commands'&&value.result?.kind==='http'){` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:49](../../cloud/commands.js#L49) | `try{const body=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(value.result.bodyBase64),c=>c.charCodeAt(0))));if(typeof body.commandId==='string')record.homeCommandId=body.commandId;}catch{}` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:50](../../cloud/commands.js#L50) | `}` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:51](../../cloud/commands.js#L51) | `save();paint();return value;` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:52](../../cloud/commands.js#L52) | `}` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:53](../../cloud/commands.js#L53) | `async function query(record){` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:54](../../cloud/commands.js#L54) | `const url=record.cloudCommandId?'/console/commands/'+record.cloudCommandId:'/console/commands/request/'+record.requestId;` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:55](../../cloud/commands.js#L55) | `const response=await network(url);if(response.status===404)return null;` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:56](../../cloud/commands.js#L56) | `if(response.status===401)throw new Error('请重新登录');if(!response.ok)throw new Error('命令状态暂不可用');` | [upload-writer.ts:109](../../frontend-v2/src/data/upload-writer.ts#L109)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:57](../../cloud/commands.js#L57) | `return capture(record,await response.json());` | [upload-writer.ts:123](../../frontend-v2/src/data/upload-writer.ts#L123)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:58](../../cloud/commands.js#L58) | `}` | [upload-writer.ts:123](../../frontend-v2/src/data/upload-writer.ts#L123)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:59](../../cloud/commands.js#L59) | `function finalResponse(value){` | [upload-writer.ts:123](../../frontend-v2/src/data/upload-writer.ts#L123)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:60](../../cloud/commands.js#L60) | `if(value?.state==='completed'&&value.result?.kind==='http'){` | [upload-writer.ts:123](../../frontend-v2/src/data/upload-writer.ts#L123)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:61](../../cloud/commands.js#L61) | `const r=value.result,bytes=Uint8Array.from(atob(r.bodyBase64),c=>c.charCodeAt(0));` | [upload-writer.ts:123](../../frontend-v2/src/data/upload-writer.ts#L123)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:62](../../cloud/commands.js#L62) | `return new Response([204,205,304].includes(r.httpStatus)?null:bytes,{status:r.httpStatus,headers:{'Content-Type':r.contentType}});` | [upload-writer.ts:123](../../frontend-v2/src/data/upload-writer.ts#L123)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:63](../../cloud/commands.js#L63) | `}` | [upload-writer.ts:123](../../frontend-v2/src/data/upload-writer.ts#L123)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:64](../../cloud/commands.js#L64) | `throw new Error(labels[value?.state]\|\|'尚未得到家里回执；请看云端命令面板，不要重复提交');` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:65](../../cloud/commands.js#L65) | `}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:66](../../cloud/commands.js#L66) | `async function dispatch(path,payload){` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:67](../../cloud/commands.js#L67) | `if(!allowedPath(path))throw new Error('此操作尚未开放云端执行');` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:68](../../cloud/commands.js#L68) | `if(path==='/api/controls/cloud-cleanup/preview'){records=records.filter(r=>r.path!==path\|\|pending.has(r.state));save();}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:69](../../cloud/commands.js#L69) | `const comparable={...payload};if(path==='/api/control-commands')delete comparable.clientRequestId;` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:70](../../cloud/commands.js#L70) | `const fingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(path+'\n'+JSON.stringify(stable(comparable))))),v=>v.toString(16).padStart(2,'0')).join('');` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:71](../../cloud/commands.js#L71) | `if(active.has(fingerprint))return (await active.get(fingerprint)).clone();` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:72](../../cloud/commands.js#L72) | `const work=(async()=>{` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:73](../../cloud/commands.js#L73) | `let record=records.find(r=>r.fingerprint===fingerprint),value;` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:74](../../cloud/commands.js#L74) | `if(!record){` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:75](../../cloud/commands.js#L75) | `if(!health.executorAvailable\|\|!health.homeReady\|\|health.commandBlocker\|\|unfinished())throw new Error('家里未就绪，或有待对账命令；尚未提交');` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:76](../../cloud/commands.js#L76) | `record={path,fingerprint,requestId:crypto.randomUUID(),state:'submitting',updatedAt:Date.now()};records.push(record);save();paint();` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:77](../../cloud/commands.js#L77) | `const body={...payload};if(path==='/api/control-commands')body.clientRequestId=record.requestId;` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:78](../../cloud/commands.js#L78) | `const info=await credentials();` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:79](../../cloud/commands.js#L79) | `try{` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:80](../../cloud/commands.js#L80) | `const response=await network(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf,'X-Client-Request-ID':record.requestId},body:JSON.stringify(body)});` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:81](../../cloud/commands.js#L81) | `const answer=await response.json();` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:82](../../cloud/commands.js#L82) | `if(response.status===202&&answer.cloudCommand) value=capture(record,answer);` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:83](../../cloud/commands.js#L83) | `else if(response.ok)throw new Error('云端未返回排队契约，停止自动处理');` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:84](../../cloud/commands.js#L84) | `else{record.state='not_sent';save();paint();throw new Error(answer.detail\|\|'云端拒绝收件');}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:85](../../cloud/commands.js#L85) | `}catch(error){if(record.state==='not_sent')throw error;/* Lost acknowledgement: GET only, never repeat POST. */}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:86](../../cloud/commands.js#L86) | `}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:87](../../cloud/commands.js#L87) | `for(let n=0;n<(path.endsWith('/cloud-cleanup/execute')?1000:180);n++){` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:88](../../cloud/commands.js#L88) | `value=value\|\|await query(record);` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:89](../../cloud/commands.js#L89) | `if(value&&!['queued','leased','sent'].includes(value.state))return finalResponse(value);` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:90](../../cloud/commands.js#L90) | `await delay(1000);value=null;` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:91](../../cloud/commands.js#L91) | `}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:92](../../cloud/commands.js#L92) | `throw new Error('仍在查询命令回执；面板将继续查询，不会自动重发。输入内容保留。');` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:93](../../cloud/commands.js#L93) | `})();active.set(fingerprint,work);` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:94](../../cloud/commands.js#L94) | `try{return (await work).clone();}finally{active.delete(fingerprint);paint();}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:95](../../cloud/commands.js#L95) | `}` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:96](../../cloud/commands.js#L96) | `window.opsCloudDispatch=dispatch;` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:97](../../cloud/commands.js#L97) | `window.opsCloudWriteFetch=(url,init={})=>{` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:98](../../cloud/commands.js#L98) | `if((init.method\|\|'GET').toUpperCase()!=='POST')throw new Error('仅支持已声明的 POST 命令');` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:99](../../cloud/commands.js#L99) | `const path=new URL(url,location.origin).pathname;return dispatch(path,init.body?JSON.parse(init.body):{});` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:100](../../cloud/commands.js#L100) | `};` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |
| [commands.js:101](../../cloud/commands.js#L101) | `window.opsCloudPostJson=async(url,body)=>{const r=await dispatch(new URL(url,location.origin).pathname,body);const result=await r.json();if(!r.ok)throw new Error(result.detail\|\|'家里拒绝该操作');return result;};` | [upload-writer.ts:139](../../frontend-v2/src/data/upload-writer.ts#L139)；同源队列 POST 一次、原编号 GET 查询、HTTP 回执解码、结果不明不重发 |

## 验证与边界

- 两种模式分别覆盖确认取消、请求体、同时点击、超时/错误；云端额外覆盖 CSRF、202、丢失回包与重载、unknown、180 次查询上限和拒绝收口。
- 家里模式共享在途状态，切换视图后同一请求仍防重复；界面同时禁用两类上传操作。
- 跨重载沿用 ops-command-receipts-v1，仅查询已有身份；结束终态回执需原确认文字，之后同输入才可生成新命令。
- 其他业务按钮保持禁用，云端清理仍关闭。此 PR 不接安全继续或任务操作。
- 原生确认对话框与旧实现一致；隔离浏览器记录其完整文字和接受/取消行为。
- 未验证真实生产、完整批次影子及默认入口切换。无新增依赖，回滚 revert 本 PR，旧页不受影响。
