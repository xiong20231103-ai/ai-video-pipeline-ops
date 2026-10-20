# Dashboard V2 功能迁移清单（唯一验收账本）

基线：main `07f87bb7f0dbbd797dd5bec1494b87e5dc1979c7`。自动枚举包含嵌套函数、匿名回调和动态事件，保留行号与原实现摘录，不能仅迁移可见主面板。所有条目初始未勾选；以后须附实现位置、家里/云端测试证据和 PR 号才能勾选。清单勾完表示实现与隔离验证完成，**不代表真实生产/切换验收**。

## PR 顺序

| 阶段 | 范围 |
|---|---|
| V2-1 | 双模式只读数据层、全部展示/筛选/来源/命令列表/备份状态、写入口禁用 |
| V2-2A | 命令队列基础设施、上传重扫与历史核验 |
| V2-2B | 补链、建任务、开始/撤回；家里测试记录重置（云端保持不开放） |
| V2-2C | 家里三类清理、待删区、预览与二次确认 |
| V2-2D | 云端清理队列、120 秒票据、capabilities 开关 |
| V2-2E | 安全继续、expectedTarget、原命令编号查询与对账 |
| V2-2F | 云端账号/登录/注册/退出/修改密码、备份请求/校验/下载；云端本地 API，不伪装成家里命令 |
| V2-3 | React Bits 标题/卡片/数值、提示、空状态、十分钟隔离性能观察 |

## 关键契约（逐项验收）

- [x] K-01：启动先可靠识别模式；仅经 `/auth/options` 证明家里/云端，不因云端超时降级为家里直写。（PR #30，仅隔离）
- [ ] K-02：云端家里业务写请求仍发原 URL，由服务器收件成队列，携带 CSRF / X-Client-Request-ID；不能从云端直连家里。
- [x] K-03：家里 GET 的 ETag/304、默认 8 秒及文件清单 60 秒超时、重试，首页 5/隐藏20 秒刷新与摘要模式保留。（PR #30，仅隔离）
- [x] K-04：云端 202 每500ms、最多120次，inflight合并，60秒完整缓存刷新，按需缓存更新监视保留；401转登录。（PR #30，仅隔离）（PR #34修复计时范围，另增30秒真实浏览器与120轮单请求8秒回归）
- [x] K-05：新鲜度家里以浏览器成功接收计时；云端叠加 sourceAge+cacheAge+本地经过时间；未知扫描时间明确警告；30/120秒阈值。（PR #30，仅隔离）
- [ ] K-06：receipts 与 ops-command-receipts-v1 兼容、最多100条；相同语义指纹跨刷新只查询、不重发；submitting先落本地记录。
- [ ] K-07：全部云端回执状态按 commands.js 原文；completed 仅是 HTTP 回执，绝非业务完成；unknown只人工对账。
- [ ] K-08：撤回仅 submitting/queued/leased；未知结果要求至少10字依据和 CONFIRMED_HOME_REQUEST_STOPPED；结束回执需再次确认。
- [ ] K-09：家里清理与云端清理分别遵守原契约；过期/选择变化/刷新丢票据拒绝；人工草稿/测试文件额外确认；不改变排除/保护规则。
- [ ] K-10：云端 canCleanup=false 保持入口禁用；testing/reset 原本不在云端白名单，云端继续禁用，不新增后端。
- [ ] K-11：安全继续原有运行中锁、故障两次后离线锁、期望目标、10秒资格证明及指定 commandId 查询保留。
- [ ] K-12：备份仅台账/配置，密文下载，request/verify 走本云端CSRF，不经过家里命令通道。
- [ ] K-13：登录/注册/改密/退出有原字段长度、registrationOpen、禁用/防重复及错误说明；不保存密码或邀请。
- [ ] K-14：新旧同数据逐项比对（家里/云端），状态/数字/原消息零差异；每个写类有双模式负例/超时/重复/回执测试。
- [ ] K-15：动效只在首次或数值变化时触发，减少动态效果关闭；10分钟轮询无持续内存增长；CSP/八尺寸截图。

注意：`/api/controls/testing/reset`、账号与备份都已明确列入范围，不能因最初阶段标题未提及而遗漏。第一份 PR 只含文档，不修改运行代码。

## functions（368 项）

- [x] **FN-001** `currentLocalDateLabel` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1](../../static/app.js#L1)。
  - 原实现：`function currentLocalDateLabel() { const value = new Date(); return ˋ${value.getMonth() + 1}.${value.getDate()}ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 任务表单相关行为留待 V2-2B，不记为只读完成。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-002** `$` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:20](../../static/app.js#L20)。
  - 原实现：`(id) => document.getElementById(id)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-003** `escapeHtml` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:21](../../static/app.js#L21)。
  - 原实现：`(value) => String(value ?? "") .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;") .replaceAll('"', "&quot;").replaceAll("'", "&#039;")`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-004** `formatClock` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:25](../../static/app.js#L25)。
  - 原实现：`function formatClock(value) { if (!value) return "--"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-005** `updateDataFreshness` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:35](../../static/app.js#L35)。
  - 原实现：`function updateDataFreshness() { const received = state.freshnessReceivedAt !== null; const elapsed = Math.max(0, performance.now() - (state.freshnessReceivedTick ?? state.freshnessStartedAt)); const level = elapsed > 120000 ? "stale" : elapsed > 30000 ? "warning" : "fresh"; const node = $("dataFreshness"); node.classList.toggle("warning", level === "warning"); node.classList.toggle("stale", level === "stale"); $("lastUpdated"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-006** `recordDashboardReception` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:47](../../static/app.js#L47)。
  - 原实现：`function recordDashboardReception() { state.freshnessReceivedAt = new Date(); state.freshnessReceivedTick = performance.now(); updateDataFreshness(); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-007** `formatDateTime` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:53](../../static/app.js#L53)。
  - 原实现：`function formatDateTime(value) { if (!value) return "--"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-008** `formatAge` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:61](../../static/app.js#L61)。
  - 原实现：`function formatAge(seconds) { if (seconds == null) return "无状态时间"; if (seconds < 10) return "刚刚"; if (seconds < 60) return ˋ${seconds}秒前ˋ; if (seconds < 3600) return ˋ${Math.floor(seconds / 60)}分钟前ˋ; if (seconds < 86400) return ˋ${Math.floor(seconds / 3600)}小时前ˋ; return ˋ${Math.floor(seconds / 86400)}天前ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-009** `formatBytes` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:70](../../static/app.js#L70)。
  - 原实现：`function formatBytes(value) { let size = Number(value ¦¦ 0); if (!Number.isFinite(size) ¦¦ size <= 0) return "0 B"; const units = ["B", "KB", "MB", "GB"]; let unit = 0; while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; } return ˋ${size >= 10 ¦¦ unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-010** `formatDuration` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:79](../../static/app.js#L79)。
  - 原实现：`function formatDuration(value) { const seconds = Math.max(0, Math.round(Number(value ¦¦ 0))); if (!seconds) return "正在测算"; if (seconds < 60) return ˋ约 ${seconds} 秒ˋ; if (seconds < 3600) return ˋ约 ${Math.ceil(seconds / 60)} 分钟ˋ; const hours = Math.floor(seconds / 3600); const minutes = Math.ceil((seconds % 3600) / 60); return ˋ约 ${hours} 小时${minutes ? ˋ ${minutes} 分钟ˋ : ""}ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-011** `renderSafety` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:89](../../static/app.js#L89)。
  - 原实现：`function renderSafety(data) { state.safety = data; const hasActiveProject = data?.productionContext?.hasActiveProject === true; const updated = $("safetyUpdatedAt"); if (updated) updated.textContent = ˋ最后检查 ${formatDateTime(data?.updatedAt)}ˋ; const entries = [ ["去字幕质检", data?.subtitleVerification, value => ˋ干净 ${value.counts?.verified_clean ¦¦ 0} · 少量残留已放行 ${value.counts?.warning ¦¦ 0} · 完整残留 ${value.counts?.residual_detected`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-012** `匿名回调@96` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:96](../../static/app.js#L96)。
  - 原实现：`value => ˋ干净 ${value.counts?.verified_clean ¦¦ 0} · 少量残留已放行 ${value.counts?.warning ¦¦ 0} · 完整残留 ${value.counts?.residual_detected ¦¦ 0} · 待审计 ${value.counts?.audit_pending ¦¦ 0}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-013** `匿名回调@97` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:97](../../static/app.js#L97)。
  - 原实现：`value => Number(value.counts?.residual_detected ¦¦ 0) ¦¦ Number(value.counts?.verification_failed ¦¦ 0) ? "blocked" : Number(value.counts?.warning ¦¦ 0) ¦¦ Number(value.counts?.audit_pending ¦¦ 0) ? "warning" : "good"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-014** `匿名回调@99` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:99](../../static/app.js#L99)。
  - 原实现：`value => ˋ${value.stateText ¦¦ "空闲"} · 已尝试 ${value.attemptCount ¦¦ 0}/1${value.commandState ? ˋ · 命令 ${value.commandState}ˋ : ""}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-015** `匿名回调@100` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:100](../../static/app.js#L100)。
  - 原实现：`value => ["failed", "unavailable"].includes(value.state) ? "blocked" : ["observing", "waiting_stable", "starting", "command_persisted", "receiver_acknowledged", "workbench_acknowledged", "executing", "recovering"].includes(value.state) ? "warning" : "good"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-016** `匿名回调@102` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:102](../../static/app.js#L102)。
  - 原实现：`value => ˋ${hasActiveProject ? "当前" : "历史审计"}：通过 ${value.passed ¦¦ 0}/${value.total ¦¦ 0} · 提醒 ${value.warning ¦¦ 0} · 阻止 ${value.blocked ¦¦ 0}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-017** `匿名回调@103` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:103](../../static/app.js#L103)。
  - 原实现：`value => Number(value.blocked ¦¦ 0) ? "blocked" : Number(value.warning ¦¦ 0) ? "warning" : "good"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-018** `匿名回调@105` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:105](../../static/app.js#L105)。
  - 原实现：`value => ˋ${value.items?.length ¦¦ 0} 个组件 · ${Number(value.driftCount ¦¦ 0) ? ˋ检测到 ${value.driftCount} 项已变更，待确认基线ˋ : "基线一致"}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-019** `匿名回调@106` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:106](../../static/app.js#L106)。
  - 原实现：`value => Number(value.driftCount ¦¦ 0) ? "warning" : "good"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-020** `匿名回调@108` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:108](../../static/app.js#L108)。
  - 原实现：`value => ˋ实时核验 ${value.verified ¦¦ 0}/${value.total ¦¦ 0} · 阻止 ${value.blocked ¦¦ 0}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-021** `匿名回调@109` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:109](../../static/app.js#L109)。
  - 原实现：`value => Number(value.blocked ¦¦ 0) ? "warning" : "good"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-022** `匿名回调@111` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:111](../../static/app.js#L111)。
  - 原实现：`value => ˋ剩余 ${value.remainingVideos ¦¦ 0} 条 · 需要 ${formatBytes(value.requiredFreeBytes)} · 可用 ${formatBytes(value.freeBytes)}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-023** `匿名回调@112` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:112](../../static/app.js#L112)。
  - 原实现：`value => value.ready ? "good" : "blocked"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-024** `匿名回调@114` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:114](../../static/app.js#L114)。
  - 原实现：`value => { const required = (value.items ¦¦ []).filter(item => item.required !== false); const optionalOffline = (value.items ¦¦ []).filter(item => item.required === false && !item.online).length; return ˋ${required.length} 个当前必需服务 · ${value.ready ? "可用" : "需要处理"}${optionalOffline ? ˋ · ${optionalOffline} 个未到阶段ˋ : ""}ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-025** `匿名回调@115` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:115](../../static/app.js#L115)。
  - 原实现：`item => item.required !== false`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-026** `匿名回调@116` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:116](../../static/app.js#L116)。
  - 原实现：`item => item.required === false && !item.online`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-027** `匿名回调@119` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:119](../../static/app.js#L119)。
  - 原实现：`value => value.ready ? "good" : "warning"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-028** `匿名回调@121` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:121](../../static/app.js#L121)。
  - 原实现：`value => ˋ活动 ${value.activeRecords ¦¦ 0} · 硬错误 ${value.hardFailureCount ¦¦ 0}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-029** `匿名回调@122` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:122](../../static/app.js#L122)。
  - 原实现：`value => value.safe ? "good" : "blocked"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-030** `匿名回调@124` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:124](../../static/app.js#L124)。
  - 原实现：`value => value.incident ? ˋ${value.incident.incidentId ¦¦ "历史故障"} · 历史证据已保存，不代表当前仍异常ˋ : "当前没有故障证据"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-031** `匿名回调@125` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:125](../../static/app.js#L125)。
  - 原实现：`value => value.incident ? "warning" : "good"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-032** `匿名回调@129` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:129](../../static/app.js#L129)。
  - 原实现：`([title, value, text, klass]) => { if (!value ¦¦ value.error) { const reason = value?.message ¦¦ "状态源暂不可用，保留其他检查结果"; return ˋ<article class="safety-card warning"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(reason)}</span></article>ˋ; } return ˋ<article class="safety-card ${klass(value)}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(text(value))}</span></article>ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-033** `refreshSafety` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:138](../../static/app.js#L138)。
  - 原实现：`async function refreshSafety(force = false) { if (!force && Date.now() - state.safetyLoadedAt < 30000) return; try { const data = await getJson("/api/safety"); state.safetyLoadedAt = Date.now(); renderSafety(data); } catch (error) { renderSafety({ updatedAt: new Date().toISOString(), quality: { error: true, message: "生产安全控制面暂不可用；不会影响生产任务" }, }); } }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-034** `draftCategoryLabel` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:152](../../static/app.js#L152)。
  - 原实现：`function draftCategoryLabel(value) { if (value === "formal") return "正式自动"; if (value === "lab") return "内测"; return "人工/不明"; }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-035** `draftDateKey` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:158](../../static/app.js#L158)。
  - 原实现：`function draftDateKey(value) { const date = new Date(value ¦¦ ""); if (Number.isNaN(date.getTime())) return ""; const month = String(date.getMonth() + 1).padStart(2, "0"); const day = String(date.getDate()).padStart(2, "0"); return ˋ${date.getFullYear()}-${month}-${day}ˋ; }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-036** `renderDraftDateFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:166](../../static/app.js#L166)。
  - 原实现：`function renderDraftDateFilter() { const select = $("draftDateFilter"); if (!select) return; const selected = select.value ¦¦ ""; const counts = new Map(); state.drafts.forEach(item => { const key = draftDateKey(item.updatedAt ¦¦ item.createdAt); if (key) counts.set(key, (counts.get(key) ¦¦ 0) + 1); }); const dates = [...counts.keys()].sort((a, b) => b.localeCompare(a)); select.innerHTML = [ ˋ<option value="">全部日期（${state.draf`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-037** `匿名回调@171` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:171](../../static/app.js#L171)。
  - 原实现：`item => { const key = draftDateKey(item.updatedAt ¦¦ item.createdAt); if (key) counts.set(key, (counts.get(key) ¦¦ 0) + 1); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-038** `匿名回调@175` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:175](../../static/app.js#L175)。
  - 原实现：`(a, b) => b.localeCompare(a)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-039** `匿名回调@178` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:178](../../static/app.js#L178)。
  - 原实现：`value => ˋ<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-040** `filteredDrafts` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:185](../../static/app.js#L185)。
  - 原实现：`function filteredDrafts() { const category = $("draftCategoryFilter")?.value ¦¦ ""; const date = $("draftDateFilter")?.value ¦¦ ""; const query = ($("draftSearchFilter")?.value ¦¦ "").trim().toLocaleLowerCase(); return state.drafts.filter(item => { if (category && item.category !== category) return false; if (date && draftDateKey(item.updatedAt ¦¦ item.createdAt) !== date) return false; if (query && !ˋ${item.name ¦¦ ""} ${item`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-041** `匿名回调@189` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:189](../../static/app.js#L189)。
  - 原实现：`item => { if (category && item.category !== category) return false; if (date && draftDateKey(item.updatedAt ¦¦ item.createdAt) !== date) return false; if (query && !ˋ${item.name ¦¦ ""} ${item.sourceLabel ¦¦ ""}ˋ.toLocaleLowerCase().includes(query)) return false; return true; }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-042** `resetDraftPreview` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:197](../../static/app.js#L197)。
  - 原实现：`function resetDraftPreview() { state.draftPreview = null; $("draftCleanupPreview")?.classList.add("hidden"); $("confirmDraftCleanupButton")?.classList.add("hidden"); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-043** `updateDraftSelectionSummary` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:203](../../static/app.js#L203)。
  - 原实现：`function updateDraftSelectionSummary() { const selected = state.drafts.filter(item => state.selectedDraftIds.has(item.draftId)); const size = selected.reduce((total, item) => total + Number(item.sizeBytes ¦¦ 0), 0); const node = $("draftSelectionSummary"); if (node) node.textContent = ˋ已选择 ${selected.length} 个 · ${formatBytes(size)}ˋ; }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-044** `匿名回调@204` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:204](../../static/app.js#L204)。
  - 原实现：`item => state.selectedDraftIds.has(item.draftId)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-045** `匿名回调@205` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:205](../../static/app.js#L205)。
  - 原实现：`(total, item) => total + Number(item.sizeBytes ¦¦ 0)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-046** `renderDraftManager` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:210](../../static/app.js#L210)。
  - 原实现：`function renderDraftManager() { const node = $("draftManagerList"); if (!node) return; const items = filteredDrafts(); if (!items.length) { node.innerHTML = ˋ<p class="empty">当前筛选条件下没有草稿</p>ˋ; updateDraftSelectionSummary(); return; } node.innerHTML = items.map(item => { const checked = state.selectedDraftIds.has(item.draftId) ? "checked" : ""; const disabled = item.protected ? "disabled" : ""; const detail = item.protected ? i`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-047** `匿名回调@219` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:219](../../static/app.js#L219)。
  - 原实现：`item => { const checked = state.selectedDraftIds.has(item.draftId) ? "checked" : ""; const disabled = item.protected ? "disabled" : ""; const detail = item.protected ? item.protectedReason : (item.inIndex ? "索引正常" : "目录未登记在首页索引"); return ˋ<label class="draft-manager-row ${item.protected ? "protected" : ""}" title="${escapeHtml(detail)}"> <input type="checkbox" data-draft-id="${escapeHtml(item.draftId)}" ${checked} ${disabled}>`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-048** `匿名回调@232` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:232](../../static/app.js#L232)。
  - 原实现：`input => { input.addEventListener("change", event => { const draftId = event.currentTarget.dataset.draftId; if (event.currentTarget.checked) state.selectedDraftIds.add(draftId); else state.selectedDraftIds.delete(draftId); resetDraftPreview(); updateDraftSelectionSummary(); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-049** `匿名回调@233` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:233](../../static/app.js#L233)。
  - 原实现：`event => { const draftId = event.currentTarget.dataset.draftId; if (event.currentTarget.checked) state.selectedDraftIds.add(draftId); else state.selectedDraftIds.delete(draftId); resetDraftPreview(); updateDraftSelectionSummary(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-050** `loadDraftManager` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:244](../../static/app.js#L244)。
  - 原实现：`async function loadDraftManager() { const button = $("openDraftManagerButton"); const refreshButton = $("refreshDraftManagerButton"); if (button) { button.disabled = true; button.textContent = "正在读取草稿…"; } if (refreshButton) refreshButton.disabled = true; try { const payload = await getJson("/api/controls/capcut-drafts", 1, 60000); state.drafts = payload.items ¦¦ []; state.draftSnapshot = payload.snapshotToken ¦¦ ""; renderDra`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-051** `匿名回调@255` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:255](../../static/app.js#L255)。
  - 原实现：`id => state.drafts.some(item => item.draftId === id && !item.protected)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-052** `匿名回调@255` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:255](../../static/app.js#L255)。
  - 原实现：`item => item.draftId === id && !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-053** `populateAudioFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:272](../../static/app.js#L272)。
  - 原实现：`function populateAudioFilter(id, values, label) { const select = $(id); if (!select) return; const selected = select.value ¦¦ ""; const counts = new Map(); values.filter(Boolean).forEach(value => counts.set(value, (counts.get(value) ¦¦ 0) + 1)); const options = [...counts.keys()].sort((a, b) => a.localeCompare(b, "zh-CN")); select.innerHTML = [ ˋ<option value="">全部${escapeHtml(label)}（${state.audioFiles.length}）</option>ˋ, ...`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-054** `匿名回调@277` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:277](../../static/app.js#L277)。
  - 原实现：`value => counts.set(value, (counts.get(value) ¦¦ 0) + 1)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-055** `匿名回调@278` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:278](../../static/app.js#L278)。
  - 原实现：`(a, b) => a.localeCompare(b, "zh-CN")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-056** `匿名回调@281` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:281](../../static/app.js#L281)。
  - 原实现：`value => ˋ<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-057** `renderAudioFilters` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:286](../../static/app.js#L286)。
  - 原实现：`function renderAudioFilters() { populateAudioFilter("audioDateFilter", state.audioFiles.map(item => item.date ¦¦ draftDateKey(item.updatedAt)), "日期"); populateAudioFilter("audioProjectFilter", state.audioFiles.map(item => item.project), "项目"); populateAudioFilter("audioMaterialFilter", state.audioFiles.map(item => item.material), "材料"); populateAudioFilter("audioLanguageFilter", state.audioFiles.map(item => item.language), "语言`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-058** `匿名回调@287` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:287](../../static/app.js#L287)。
  - 原实现：`item => item.date ¦¦ draftDateKey(item.updatedAt)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-059** `匿名回调@288` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:288](../../static/app.js#L288)。
  - 原实现：`item => item.project`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-060** `匿名回调@289` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:289](../../static/app.js#L289)。
  - 原实现：`item => item.material`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-061** `匿名回调@290` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:290](../../static/app.js#L290)。
  - 原实现：`item => item.language`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-062** `匿名回调@291` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:291](../../static/app.js#L291)。
  - 原实现：`item => item.audioBatch`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-063** `filteredAudioFiles` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:294](../../static/app.js#L294)。
  - 原实现：`function filteredAudioFiles() { const date = $("audioDateFilter")?.value ¦¦ ""; const project = $("audioProjectFilter")?.value ¦¦ ""; const material = $("audioMaterialFilter")?.value ¦¦ ""; const language = $("audioLanguageFilter")?.value ¦¦ ""; const batch = $("audioBatchFilter")?.value ¦¦ ""; const taskState = $("audioStateFilter")?.value ¦¦ ""; const query = ($("audioSearchFilter")?.value ¦¦ "").trim().toLocaleLowerCase(); `；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-064** `匿名回调@302` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:302](../../static/app.js#L302)。
  - 原实现：`item => { const itemDate = item.date ¦¦ draftDateKey(item.updatedAt); if (date && itemDate !== date) return false; if (project && item.project !== project) return false; if (material && item.material !== material) return false; if (language && item.language !== language) return false; if (batch && item.audioBatch !== batch) return false; if (taskState === "deletable" && item.protected) return false; if (taskState === "protecte`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-065** `resetAudioPreview` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:317](../../static/app.js#L317)。
  - 原实现：`function resetAudioPreview() { state.audioPreview = null; $("audioCleanupPreview")?.classList.add("hidden"); $("confirmAudioCleanupButton")?.classList.add("hidden"); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-066** `updateAudioSelectionSummary` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:323](../../static/app.js#L323)。
  - 原实现：`function updateAudioSelectionSummary() { const selected = state.audioFiles.filter(item => state.selectedAudioIds.has(item.audioId)); const size = selected.reduce((total, item) => total + Number(item.sizeBytes ¦¦ 0), 0); const node = $("audioSelectionSummary"); if (node) node.textContent = ˋ已选择 ${selected.length} 个 · ${formatBytes(size)}ˋ; }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-067** `匿名回调@324` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:324](../../static/app.js#L324)。
  - 原实现：`item => state.selectedAudioIds.has(item.audioId)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-068** `匿名回调@325` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:325](../../static/app.js#L325)。
  - 原实现：`(total, item) => total + Number(item.sizeBytes ¦¦ 0)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-069** `audioIdentity` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:330](../../static/app.js#L330)。
  - 原实现：`function audioIdentity(item) { return [item.project, item.material, item.language].filter(Boolean).join(" / ") ¦¦ "历史或未登记任务"; }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-070** `showAudioProtection` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:334](../../static/app.js#L334)。
  - 原实现：`function showAudioProtection(item) { const identity = audioIdentity(item); const reason = item.protectedReason ¦¦ "任务正在使用，禁止删除"; $("audioProtectionIdentity").textContent = identity; $("audioProtectionState").textContent = item.taskState ¦¦ "等待恢复"; $("audioProtectionReason").textContent = reason; const dialog = $("audioProtectionDialog"); if (dialog && !dialog.open) dialog.showModal(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-071** `renderAudioManager` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:344](../../static/app.js#L344)。
  - 原实现：`function renderAudioManager() { const node = $("audioManagerList"); if (!node) return; const items = filteredAudioFiles(); if (!items.length) { node.innerHTML = ˋ<p class="empty">当前筛选条件下没有音频文件</p>ˋ; updateAudioSelectionSummary(); return; } node.innerHTML = items.map(item => { const checked = state.selectedAudioIds.has(item.audioId) ? "checked" : ""; const disabled = item.protected ? "disabled" : ""; const stateLabel = item.pro`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-072** `匿名回调@353` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:353](../../static/app.js#L353)。
  - 原实现：`item => { const checked = state.selectedAudioIds.has(item.audioId) ? "checked" : ""; const disabled = item.protected ? "disabled" : ""; const stateLabel = item.protected ? "任务正在使用，禁止删除" : "可手动删除"; return ˋ<div class="draft-manager-row audio-manager-row ${item.protected ? "protected" : ""}" data-audio-row-id="${escapeHtml(item.audioId)}" title="${escapeHtml(item.protectedReason ¦¦ stateLabel)}"> <input type="checkbox" data-audi`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-073** `匿名回调@368` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:368](../../static/app.js#L368)。
  - 原实现：`input => { input.addEventListener("change", event => { const audioId = event.currentTarget.dataset.audioId; if (event.currentTarget.checked) state.selectedAudioIds.add(audioId); else state.selectedAudioIds.delete(audioId); resetAudioPreview(); updateAudioSelectionSummary(); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-074** `匿名回调@369` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:369](../../static/app.js#L369)。
  - 原实现：`event => { const audioId = event.currentTarget.dataset.audioId; if (event.currentTarget.checked) state.selectedAudioIds.add(audioId); else state.selectedAudioIds.delete(audioId); resetAudioPreview(); updateAudioSelectionSummary(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-075** `匿名回调@377` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:377](../../static/app.js#L377)。
  - 原实现：`row => { row.addEventListener("click", event => { const item = state.audioFiles.find(value => value.audioId === row.dataset.audioRowId); if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return; event.preventDefault(); showAudioProtection(item); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-076** `匿名回调@378` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:378](../../static/app.js#L378)。
  - 原实现：`event => { const item = state.audioFiles.find(value => value.audioId === row.dataset.audioRowId); if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return; event.preventDefault(); showAudioProtection(item); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-077** `匿名回调@379` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:379](../../static/app.js#L379)。
  - 原实现：`value => value.audioId === row.dataset.audioRowId`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-078** `loadAudioManager` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:388](../../static/app.js#L388)。
  - 原实现：`async function loadAudioManager() { const button = $("openAudioManagerButton"); const refreshButton = $("refreshAudioManagerButton"); if (button) { button.disabled = true; button.textContent = "正在读取音频…"; } if (refreshButton) refreshButton.disabled = true; try { const payload = await getJson("/api/controls/audio-files", 1, 60000); state.audioFiles = payload.items ¦¦ []; state.audioSnapshot = payload.snapshotToken ¦¦ ""; renderA`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-079** `匿名回调@399` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:399](../../static/app.js#L399)。
  - 原实现：`id => state.audioFiles.some(item => item.audioId === id && !item.protected)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-080** `匿名回调@400` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:400](../../static/app.js#L400)。
  - 原实现：`item => item.audioId === id && !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-081** `populateProductionFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:420](../../static/app.js#L420)。
  - 原实现：`function populateProductionFilter(id, values, label) { const select = $(id); if (!select) return; const selected = select.value ¦¦ ""; const counts = new Map(); values.filter(Boolean).forEach(value => counts.set(value, (counts.get(value) ¦¦ 0) + 1)); const options = [...counts.keys()].sort((a, b) => a.localeCompare(b, "zh-CN")); select.innerHTML = [ ˋ<option value="">全部${escapeHtml(label)}（${state.productionFiles.length}）</opt`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-082** `匿名回调@425` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:425](../../static/app.js#L425)。
  - 原实现：`value => counts.set(value, (counts.get(value) ¦¦ 0) + 1)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-083** `匿名回调@426` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:426](../../static/app.js#L426)。
  - 原实现：`(a, b) => a.localeCompare(b, "zh-CN")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-084** `匿名回调@429` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:429](../../static/app.js#L429)。
  - 原实现：`value => ˋ<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-085** `renderProductionFilters` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:434](../../static/app.js#L434)。
  - 原实现：`function renderProductionFilters() { populateProductionFilter( "productionDateFilter", state.productionFiles.map(item => item.date ¦¦ draftDateKey(item.updatedAt)), "日期" ); populateProductionFilter("productionProjectFilter", state.productionFiles.map(item => item.project), "项目"); populateProductionFilter("productionMaterialFilter", state.productionFiles.map(item => item.material), "材料"); const select = $("productionCategoryFil`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-086** `匿名回调@437` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:437](../../static/app.js#L437)。
  - 原实现：`item => item.date ¦¦ draftDateKey(item.updatedAt)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-087** `匿名回调@440` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:440](../../static/app.js#L440)。
  - 原实现：`item => item.project`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-088** `匿名回调@441` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:441](../../static/app.js#L441)。
  - 原实现：`item => item.material`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-089** `匿名回调@448` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:448](../../static/app.js#L448)。
  - 原实现：`([key, value]) => ˋ<option value="${escapeHtml(key)}">${escapeHtml(value.label ¦¦ key)}（${Number(value.total ¦¦ 0)}）</option>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-090** `renderProductionCategorySummary` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:456](../../static/app.js#L456)。
  - 原实现：`function renderProductionCategorySummary() { const node = $("productionCategorySummary"); if (!node) return; const categories = state.productionCounts?.categories ¦¦ {}; const rows = Object.entries(categories); if (!rows.length) { node.innerHTML = ˋ<p class="empty">没有发现已登记的生产文件</p>ˋ; return; } node.innerHTML = rows.map(([key, value]) => ˋ<button type="button" class="production-category-card" data-production-category="${escapeH`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-091** `匿名回调@465` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:465](../../static/app.js#L465)。
  - 原实现：`([key, value]) => ˋ<button type="button" class="production-category-card" data-production-category="${escapeHtml(key)}"> <span>${escapeHtml(value.label ¦¦ key)}</span> <strong>${Number(value.total ¦¦ 0)} 个 · ${escapeHtml(formatBytes(value.sizeBytes))}</strong> <small>可清理 ${Number(value.deletable ¦¦ 0)} · 保护 ${Number(value.protected ¦¦ 0)}</small> </button>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-092** `匿名回调@472` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:472](../../static/app.js#L472)。
  - 原实现：`button => { button.addEventListener("click", () => { const select = $("productionCategoryFilter"); if (select) select.value = button.dataset.productionCategory ¦¦ ""; resetProductionPreview(); renderProductionManager(); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-093** `匿名回调@473` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:473](../../static/app.js#L473)。
  - 原实现：`() => { const select = $("productionCategoryFilter"); if (select) select.value = button.dataset.productionCategory ¦¦ ""; resetProductionPreview(); renderProductionManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-094** `filteredProductionFiles` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:482](../../static/app.js#L482)。
  - 原实现：`function filteredProductionFiles() { const date = $("productionDateFilter")?.value ¦¦ ""; const project = $("productionProjectFilter")?.value ¦¦ ""; const material = $("productionMaterialFilter")?.value ¦¦ ""; const category = $("productionCategoryFilter")?.value ¦¦ ""; const taskState = $("productionStateFilter")?.value ¦¦ ""; const query = ($("productionSearchFilter")?.value ¦¦ "").trim().toLocaleLowerCase(); return state.pr`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-095** `匿名回调@489` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:489](../../static/app.js#L489)。
  - 原实现：`item => { const itemDate = item.date ¦¦ draftDateKey(item.updatedAt); if (date && itemDate !== date) return false; if (project && item.project !== project) return false; if (material && item.material !== material) return false; if (category && item.category !== category) return false; if (taskState === "deletable" && item.protected) return false; if (taskState === "protected" && !item.protected) return false; const haystack = `；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-096** `resetProductionPreview` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:506](../../static/app.js#L506)。
  - 原实现：`function resetProductionPreview() { state.productionPreview = null; $("productionCleanupPreview")?.classList.add("hidden"); $("confirmProductionCleanupButton")?.classList.add("hidden"); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-097** `updateProductionSelectionSummary` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:512](../../static/app.js#L512)。
  - 原实现：`function updateProductionSelectionSummary() { const selected = state.productionFiles.filter(item => state.selectedProductionIds.has(item.fileId)); const size = selected.reduce((total, item) => total + Number(item.sizeBytes ¦¦ 0), 0); const testCount = selected.filter(item => item.category === "capcut_test").length; const node = $("productionSelectionSummary"); if (node) { node.textContent = ˋ已选择 ${selected.length} 个 · ${format`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-098** `匿名回调@513` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:513](../../static/app.js#L513)。
  - 原实现：`item => state.selectedProductionIds.has(item.fileId)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-099** `匿名回调@514` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:514](../../static/app.js#L514)。
  - 原实现：`(total, item) => total + Number(item.sizeBytes ¦¦ 0)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-100** `匿名回调@515` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:515](../../static/app.js#L515)。
  - 原实现：`item => item.category === "capcut_test"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-101** `productionIdentity` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:522](../../static/app.js#L522)。
  - 原实现：`function productionIdentity(item) { return [item.project, item.material, item.language].filter(Boolean).join(" / ") ¦¦ (item.category === "capcut_test" ? "隔离测试文件" : "历史或未登记任务"); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-102** `showProductionProtection` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:527](../../static/app.js#L527)。
  - 原实现：`function showProductionProtection(item) { $("productionProtectionName").textContent = item.name ¦¦ "--"; $("productionProtectionIdentity").textContent = productionIdentity(item); $("productionProtectionState").textContent = item.taskState ¦¦ "受保护"; $("productionProtectionReason").textContent = item.protectedReason ¦¦ "当前文件禁止清理"; const dialog = $("productionProtectionDialog"); if (dialog && !dialog.open) dialog.showModal(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-103** `renderProductionManager` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:536](../../static/app.js#L536)。
  - 原实现：`function renderProductionManager() { const node = $("productionManagerList"); if (!node) return; const items = filteredProductionFiles(); if (!items.length) { node.innerHTML = ˋ<p class="empty">当前筛选条件下没有生产文件</p>ˋ; updateProductionSelectionSummary(); return; } node.innerHTML = items.map(item => { const checked = state.selectedProductionIds.has(item.fileId) ? "checked" : ""; const disabled = item.protected ? "disabled" : ""; con`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-104** `匿名回调@545` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:545](../../static/app.js#L545)。
  - 原实现：`item => { const checked = state.selectedProductionIds.has(item.fileId) ? "checked" : ""; const disabled = item.protected ? "disabled" : ""; const stateLabel = item.protected ? "受保护" : (item.category === "capcut_test" ? "测试文件，可手动清理" : "云端已核验，可清理"); return ˋ<div class="draft-manager-row production-manager-row ${item.protected ? "protected" : ""}" data-production-row-id="${escapeHtml(item.fileId)}" title="${escapeHtml(item.protec`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-105** `匿名回调@560` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:560](../../static/app.js#L560)。
  - 原实现：`input => { input.addEventListener("change", event => { const fileId = event.currentTarget.dataset.productionId; if (event.currentTarget.checked) state.selectedProductionIds.add(fileId); else state.selectedProductionIds.delete(fileId); resetProductionPreview(); updateProductionSelectionSummary(); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-106** `匿名回调@561` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:561](../../static/app.js#L561)。
  - 原实现：`event => { const fileId = event.currentTarget.dataset.productionId; if (event.currentTarget.checked) state.selectedProductionIds.add(fileId); else state.selectedProductionIds.delete(fileId); resetProductionPreview(); updateProductionSelectionSummary(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-107** `匿名回调@569` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:569](../../static/app.js#L569)。
  - 原实现：`row => { row.addEventListener("click", event => { const item = state.productionFiles.find(value => value.fileId === row.dataset.productionRowId); if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return; event.preventDefault(); showProductionProtection(item); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-108** `匿名回调@570` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:570](../../static/app.js#L570)。
  - 原实现：`event => { const item = state.productionFiles.find(value => value.fileId === row.dataset.productionRowId); if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return; event.preventDefault(); showProductionProtection(item); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-109** `匿名回调@571` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:571](../../static/app.js#L571)。
  - 原实现：`value => value.fileId === row.dataset.productionRowId`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-110** `loadProductionManager` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:580](../../static/app.js#L580)。
  - 原实现：`async function loadProductionManager({ applyDefaults = false } = {}) { const button = $("openProductionManagerButton"); const refreshButton = $("refreshProductionManagerButton"); if (button) { button.disabled = true; button.textContent = "正在读取生产文件…"; } if (refreshButton) refreshButton.disabled = true; try { const payload = await getJson("/api/controls/production-files", 1, 60000); state.productionFiles = payload.items ¦¦ []; s`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-111** `匿名回调@593` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:593](../../static/app.js#L593)。
  - 原实现：`item => item.defaultSelected && !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-112** `匿名回调@593` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:593](../../static/app.js#L593)。
  - 原实现：`item => item.fileId`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-113** `匿名回调@597` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:597](../../static/app.js#L597)。
  - 原实现：`id => state.productionFiles.some(item => item.fileId === id && !item.protected)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-114** `匿名回调@598` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:598](../../static/app.js#L598)。
  - 原实现：`item => item.fileId === id && !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-115** `ageFromTime` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:619](../../static/app.js#L619)。
  - 原实现：`function ageFromTime(value) { if (!value) return "无成功更新时间"; const timestamp = new Date(value).getTime(); if (Number.isNaN(timestamp)) return "时间未知"; return formatAge(Math.max(0, Math.floor((Date.now() - timestamp) / 1000))); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-116** `setBar` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:626](../../static/app.js#L626)。
  - 原实现：`function setBar(id, value) { const safe = Number.isFinite(Number(value)) ? Math.min(100, Math.max(0, Number(value))) : 0; $(id).style.width = ˋ${safe}%ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-117** `renderProcess` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:631](../../static/app.js#L631)。
  - 原实现：`function renderProcess(id, label, running) { const node = $(id); node.textContent = ˋ${label} · ${running ? "运行中" : "未运行"}ˋ; node.className = ˋprocess-pill ${running ? "running" : "stopped"}ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-118** `renderMetrics` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:637](../../static/app.js#L637)。
  - 原实现：`function renderMetrics(metrics = {}) { const cpu = metrics.cpu; $("cpuValue").textContent = cpu == null ? "--" : ˋ${cpu}%ˋ; setBar("cpuBar", cpu); const memory = metrics.memory; $("memoryValue").textContent = memory == null ? "--" : ˋ${memory}%ˋ; $("memoryNote").textContent = metrics.memory_used_gb == null ? "正在读取" : ˋ${metrics.memory_used_gb} / ${metrics.memory_total_gb} GBˋ; setBar("memoryBar", memory); const gpu = metrics.g`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-119** `stageClass` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:663](../../static/app.js#L663)。
  - 原实现：`function stageClass(value) { if (value === "completed") return "completed"; if (value === "failed") return "failed"; if (value === "running") return "active"; if (value === "unconfigured") return "disabled"; if (value === "offline") return "failed"; return "idle"; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-120** `renderStage` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:672](../../static/app.js#L672)。
  - 原实现：`function renderStage(name, data = {}) { const suffix = name[0].toUpperCase() + name.slice(1); const step = $(ˋpipe${suffix}ˋ); const text = $(ˋpipe${suffix}Textˋ); if (step) step.className = ˋpipe-step ${stageClass(data.state)}ˋ; if (text) text.textContent = ˋ${data.stateText ¦¦ "等待状态"} · ${Number(data.progress ¦¦ 0)}%ˋ; const card = $(ˋstage${suffix}ˋ); if (!card) return; const klass = stageClass(data.state); card.className =`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-121** `renderPipeline` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:690](../../static/app.js#L690)。
  - 原实现：`function renderPipeline(pipeline = {}) { ["download", "voice", "stitch", "capcut", "upload"].forEach(name => renderStage(name, pipeline[name])); renderDownloadFailures(pipeline.download ¦¦ {}); renderUploadSummary(pipeline.upload ¦¦ {}); renderPipelineRows(pipeline); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-122** `匿名回调@691` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:691](../../static/app.js#L691)。
  - 原实现：`name => renderStage(name, pipeline[name])`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-123** `renderUploadSummary` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:697](../../static/app.js#L697)。
  - 原实现：`function renderUploadSummary(upload = {}) { const configured = upload.state !== "unconfigured"; $("uploadCardTitle").textContent = configured ? (upload.state === "running" ? "百度网盘上传中" : upload.stateText ¦¦ "百度网盘上传服务") : "百度网盘未配置"; $("uploadCardMessage").textContent = configured ? ˋ等待 ${upload.waiting ¦¦ 0}，上传中 ${upload.uploading ¦¦ 0}，云端已核验 ${upload.cloudVerified ¦¦ 0}，失败 ${upload.failed ¦¦ 0}。本条文件已清理 ${upload.taskFilesCleaned`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-124** `renderDownloadFailures` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:728](../../static/app.js#L728)。
  - 原实现：`function renderDownloadFailures(download = {}) { const panel = $("downloadFailurePanel"); const list = $("downloadFailureList"); const count = $("downloadFailureCount"); if (!panel ¦¦ !list ¦¦ !count) return; const items = Array.isArray(download.failureItems) ? download.failureItems : []; const failed = Math.max(Number(download.failed ¦¦ 0), items.length); panel.classList.toggle("hidden", failed <= 0); count.textContent = ˋ${f`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-125** `匿名回调@739` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:739](../../static/app.js#L739)。
  - 原实现：`item => ˋ<li><code>${escapeHtml(item.url ¦¦ "未记录链接")}</code><span>${escapeHtml(item.reason ¦¦ "下载或 AI 去字幕失败")}</span></li>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-126** `currentProjectPipeline` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:743](../../static/app.js#L743)。
  - 原实现：`function currentProjectPipeline(payload = {}, currentProjectStatus = {}) { const identity = currentProjectStatus?.identity ¦¦ {}; const taskId = identity.canonicalTaskId ¦¦ identity.taskId ¦¦ ""; const stages = Array.isArray(currentProjectStatus?.stages) ? currentProjectStatus.stages : []; if (!taskId ¦¦ !stages.length) return null; const datePipeline = {}; (payload.items ¦¦ []).forEach(item => { datePipeline[item.key] = item;`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-127** `匿名回调@750` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:750](../../static/app.js#L750)。
  - 原实现：`item => { datePipeline[item.key] = item; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-128** `匿名回调@762` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:762](../../static/app.js#L762)。
  - 原实现：`stage => { const key = stage.step; const base = datePipeline[key] ¦¦ {}; const total = Number(stage.total ¦¦ 0); const completed = Number(stage.completed ¦¦ 0); const failed = Number(stage.failed ¦¦ 0); const state = stateMap[String(stage.status ¦¦ "unknown").toLowerCase()] ¦¦ "idle"; const stateText = stage.message ¦¦ ({ completed: "当前项目已完成", running: "当前项目处理中", failed: "当前项目被阻止", idle: stage.status === "unknown" ? "当前项目状态未知，`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-129** `renderPipelinePayload` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:794](../../static/app.js#L794)。
  - 原实现：`function renderPipelinePayload(payload = {}, currentProjectStatus = {}) { const pipeline = {}; (payload.items ¦¦ []).forEach(item => { pipeline[item.key] = item; }); // The date ledger remains available for history, but it must never be used // as the live progress of a different active project. renderPipeline(currentProjectPipeline(payload, currentProjectStatus) ¦¦ pipeline); renderPipelineDateOptions(payload.availableDates ¦`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-130** `匿名回调@796` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:796](../../static/app.js#L796)。
  - 原实现：`item => { pipeline[item.key] = item; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-131** `renderPipelineDateOptions` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:803](../../static/app.js#L803)。
  - 原实现：`function renderPipelineDateOptions(dates, selected) { const select = $("pipelineDateSelect"); const values = Array.from(new Set([selected, ...dates].filter(Boolean))); const signature = values.join("¦"); if (select.dataset.signature !== signature) { select.innerHTML = values.map(value => ˋ<option value="${escapeHtml(value)}">生产日期 ${escapeHtml(value)}</option>ˋ ).join(""); select.dataset.signature = signature; } select.value = `；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-132** `匿名回调@808` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:808](../../static/app.js#L808)。
  - 原实现：`value => ˋ<option value="${escapeHtml(value)}">生产日期 ${escapeHtml(value)}</option>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-133** `renderPipelineRows` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:818](../../static/app.js#L818)。
  - 原实现：`function renderPipelineRows(pipeline = {}) { const order = ["download", "voice", "stitch", "capcut", "upload"]; const rows = $("pipelineRows"); rows.innerHTML = order.map(key => { const item = pipeline[key] ¦¦ {}; const onlineText = item.state === "unconfigured" ? "尚未接入" : (item.programOnline ? "程序运行中" : "程序未运行"); const onlineClass = item.programOnline ? "online" : "offline"; const phase = item.phaseText ¦¦ item.currentPhase ¦`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-134** `匿名回调@821` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:821](../../static/app.js#L821)。
  - 原实现：`key => { const item = pipeline[key] ¦¦ {}; const onlineText = item.state === "unconfigured" ? "尚未接入" : (item.programOnline ? "程序运行中" : "程序未运行"); const onlineClass = item.programOnline ? "online" : "offline"; const phase = item.phaseText ¦¦ item.currentPhase ¦¦ ""; const current = [item.current ¦¦ item.todaySummary ¦¦ item.source ¦¦ "暂无当前任务", phase] .filter(Boolean).join(" · "); const testHistory = Number(item.testHistoryCount `；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-135** `categoryFor` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:846](../../static/app.js#L846)。
  - 原实现：`function categoryFor(raw) { if (["Completed", "completed"].includes(raw)) return "completed"; if (["Failed", "failed", "validation_failed", "manual_review"].includes(raw)) return "failed"; if (["Waiting", "waiting_capcut", "waiting_client", "stopped"].includes(raw)) return "waiting"; return "running"; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-136** `step5FilterKey` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:853](../../static/app.js#L853)。
  - 原实现：`function step5FilterKey(item) { return JSON.stringify([item.project ¦¦ "未分类", item.material ¦¦ "--"]); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-137** `renderOverview` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:857](../../static/app.js#L857)。
  - 原实现：`function renderOverview(data, projectGaps = []) { state.overview = data; const machine = data.machine ¦¦ {}; const badge = $("machineBadge"); badge.className = ˋstatus-badge ${machine.online ? "online" : "offline"}ˋ; badge.innerHTML = ˋ<span></span>${escapeHtml(machine.name ¦¦ "--")} · ${machine.online ? "在线" : "离线"}ˋ; $("footerMachine").textContent = ˋ${machine.name ¦¦ "--"} · ${machine.status ¦¦ "--"}ˋ; const counts = data.c`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-138** `匿名回调@878` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:878](../../static/app.js#L878)。
  - 原实现：`key => pipeline[key]`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-139** `匿名回调@878` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:878](../../static/app.js#L878)。
  - 原实现：`item => item && item.state === "running"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-140** `匿名回调@888` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:888](../../static/app.js#L888)。
  - 原实现：`item => item.gapActive`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-141** `匿名回调@890` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:890](../../static/app.js#L890)。
  - 原实现：`(total, item) => total + Number(item.missingCount ¦¦ 0)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-142** `匿名回调@892` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:892](../../static/app.js#L892)。
  - 原实现：`item => ˋ${item.date ¦¦ ""} ${item.project ¦¦ "未分类"}/${item.material ¦¦ "--"} 缺 ${Number(item.missingCount ¦¦ 0)} 条ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-143** `renderTasks` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:914](../../static/app.js#L914)。
  - 原实现：`function renderTasks(items) { const rows = $("taskRows"); const cards = $("taskCards"); const select = $("step5ProjectFilter"); const filters = new Map(); items.forEach(item => { const project = item.project ¦¦ "未分类"; const material = item.material ¦¦ "--"; const key = step5FilterKey(item); if (!filters.has(key)) filters.set(key, { project, material }); }); if (!filters.has(state.step5Filter)) state.step5Filter = ""; const fil`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-144** `匿名回调@919` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:919](../../static/app.js#L919)。
  - 原实现：`item => { const project = item.project ¦¦ "未分类"; const material = item.material ¦¦ "--"; const key = step5FilterKey(item); if (!filters.has(key)) filters.set(key, { project, material }); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-145** `匿名回调@928` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:928](../../static/app.js#L928)。
  - 原实现：`([key, filter]) => ˋ<option value="${escapeHtml(key)}">${escapeHtml(filter.project)} / ${escapeHtml(filter.material)}</option>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-146** `匿名回调@936` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:936](../../static/app.js#L936)。
  - 原实现：`item => step5FilterKey(item) === state.step5Filter`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-147** `匿名回调@938` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:938](../../static/app.js#L938)。
  - 原实现：`(counts, item) => { counts.total += 1; counts[item.category] = (counts[item.category] ¦¦ 0) + 1; return counts; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-148** `匿名回调@955` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:955](../../static/app.js#L955)。
  - 原实现：`item => { const key = ˋ${item.project ¦¦ "未分类"} / ${item.material ¦¦ "--"}ˋ; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(item); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-149** `匿名回调@960` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:960](../../static/app.js#L960)。
  - 原实现：`([label, group]) => { const done = group.filter(item => item.category === "completed").length; return ˋ<tr class="task-group-row"><td colspan="6"><strong>${escapeHtml(label)}</strong><span>${done} / ${group.length} 完成</span></td></tr>${group.map(item => ˋ <tr> <td><strong>${escapeHtml(item.project ¦¦ "未分类")}</strong><span class="subtext">${escapeHtml(item.date_label ¦¦ "")}</span></td> <td>${escapeHtml(item.material ¦¦ "--")}<`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-150** `匿名回调@961` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:961](../../static/app.js#L961)。
  - 原实现：`item => item.category === "completed"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-151** `匿名回调@962` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:962](../../static/app.js#L962)。
  - 原实现：`item => ˋ <tr> <td><strong>${escapeHtml(item.project ¦¦ "未分类")}</strong><span class="subtext">${escapeHtml(item.date_label ¦¦ "")}</span></td> <td>${escapeHtml(item.material ¦¦ "--")}<span class="subtext">${escapeHtml(item.language ¦¦ "--")}</span></td> <td>${escapeHtml(item.number ¦¦ "--")}${item.sequence ? ˋ-${escapeHtml(item.sequence)}ˋ : ""}</td> <td>${escapeHtml(item.phase_text ¦¦ item.state_text ¦¦ item.phase ¦¦ item.sta`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-152** `匿名回调@972` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:972](../../static/app.js#L972)。
  - 原实现：`([label, group]) => { const done = group.filter(item => item.category === "completed").length; return ˋ<details class="task-card-group" ${done < group.length ? "open" : ""}> <summary><strong>${escapeHtml(label)}</strong><span>${done} / ${group.length}</span></summary> ${group.map(item => ˋ<article class="task-card-item"> <div><b>${escapeHtml(item.language ¦¦ "--")} · ${escapeHtml(item.number ¦¦ "--")}${item.sequence ? ˋ-${esca`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-153** `匿名回调@973` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:973](../../static/app.js#L973)。
  - 原实现：`item => item.category === "completed"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-154** `匿名回调@976` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:976](../../static/app.js#L976)。
  - 原实现：`item => ˋ<article class="task-card-item"> <div><b>${escapeHtml(item.language ¦¦ "--")} · ${escapeHtml(item.number ¦¦ "--")}${item.sequence ? ˋ-${escapeHtml(item.sequence)}ˋ : ""}</b><span class="task-state ${escapeHtml(item.category)}">${escapeHtml(item.category === "running" ? "处理中" : item.state_text)}</span></div> <p>${escapeHtml(item.phase_text ¦¦ item.state_text ¦¦ item.state)}</p><small>${escapeHtml(item.output_name ¦¦ "尚`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-155** `renderEvents` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:984](../../static/app.js#L984)。
  - 原实现：`function renderEvents(items) { const node = $("eventList"); if (!items.length) { node.innerHTML = ˋ<p class="empty">暂无事件</p>ˋ; return; } node.innerHTML = items.slice(0, 20).map(item => { const severity = String(item.severity ¦¦ "INFO").toLowerCase(); return ˋ<div class="event-item ${escapeHtml(severity)}"><i class="event-dot"></i><div><strong>${escapeHtml(item.message)}</strong><small>${escapeHtml(formatClock(item.created_at))`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-156** `匿名回调@987` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:987](../../static/app.js#L987)。
  - 原实现：`item => { const severity = String(item.severity ¦¦ "INFO").toLowerCase(); return ˋ<div class="event-item ${escapeHtml(severity)}"><i class="event-dot"></i><div><strong>${escapeHtml(item.message)}</strong><small>${escapeHtml(formatClock(item.created_at))}</small></div></div>ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-157** `renderGapQuickBar` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:993](../../static/app.js#L993)。
  - 原实现：`function renderGapQuickBar(items = []) { const bar = $("gapQuickBar"); const title = $("gapQuickTitle"); const summary = $("gapQuickSummary"); const actions = $("gapQuickActions"); if (!bar ¦¦ !title ¦¦ !summary ¦¦ !actions) return; const active = items.filter(item => Boolean(item.gapActive) && String(item.taskId ¦¦ "")); if (!active.length) { bar.classList.add("hidden"); actions.innerHTML = ""; return; } const missingFor = it`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-158** `匿名回调@999` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:999](../../static/app.js#L999)。
  - 原实现：`item => Boolean(item.gapActive) && String(item.taskId ¦¦ "")`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-159** `missingFor` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1005](../../static/app.js#L1005)。
  - 原实现：`item => Number(item.missingCount ?? Math.max( 0, Number(item.expectedCount ¦¦ 0) - Number(item.completed ¦¦ 0), ))`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-160** `匿名回调@1009` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1009](../../static/app.js#L1009)。
  - 原实现：`(total, item) => total + missingFor(item)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-161** `匿名回调@1012` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1012](../../static/app.js#L1012)。
  - 原实现：`item => ˋ <button type="button" data-task-id="${escapeHtml(String(item.taskId ¦¦ ""))}" onclick="openReplenishment(this.dataset.taskId)"> ${escapeHtml(item.project ¦¦ "未分类")} / ${escapeHtml(item.material ¦¦ "--")} · 缺 ${missingFor(item)} 条 </button>ˋ`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-162** `renderProjectGaps` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1019](../../static/app.js#L1019)。
  - 原实现：`function renderProjectGaps(items) { const node = $("projectGapList"); if (!node) return; state.gaps = {}; if (!items.length) { renderGapQuickBar([]); node.innerHTML = ˋ<p class="empty">暂无项目级下载记录</p>ˋ; return; } node.innerHTML = items.map(item => { const expected = Number(item.expectedCount ¦¦ 0); const completed = Number(item.completed ¦¦ 0); const storedMissing = item.missingCount; const missing = Number(storedMissing !== und`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-163** `匿名回调@1028` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1028](../../static/app.js#L1028)。
  - 原实现：`item => { const expected = Number(item.expectedCount ¦¦ 0); const completed = Number(item.completed ¦¦ 0); const storedMissing = item.missingCount; const missing = Number(storedMissing !== undefined && storedMissing !== null && storedMissing !== "" ? storedMissing : Math.max(0, expected - completed)); const notStarted = Boolean(item.notStarted); const blocked = Boolean(item.gapActive); const historicalFailed = Number(item.hist`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-164** `匿名回调@1043` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1043](../../static/app.js#L1043)。
  - 原实现：`video => ˋ<li><span>${escapeHtml(video.url ¦¦ "--")}</span><b>${escapeHtml(video.stage ¦¦ "waiting")}</b><em>${escapeHtml(video.error ¦¦ video.message ¦¦ video.status ¦¦ "等待")}</em></li>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-165** `renderTemplates` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1058](../../static/app.js#L1058)。
  - 原实现：`function renderTemplates(items) { const nextTemplates = Array.isArray(items) ? items : []; const signature = JSON.stringify(nextTemplates); const select = $("createTemplate"); if (!select) return; if (signature === state.templateSignature && select.options.length > 1) return; state.templates = nextTemplates; state.templateSignature = signature; const previous = select.value; select.innerHTML = ˋ<option value="">请选择项目</option>$`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 任务表单相关行为留待 V2-2B，不记为只读完成。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-166** `匿名回调@1067` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1067](../../static/app.js#L1067)。
  - 原实现：`item => ˋ<option value="${escapeHtml(item.id)}">${escapeHtml(item.label ¦¦ ˋ${item.project} / ${item.material}ˋ)}</option>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 任务表单相关行为留待 V2-2B，不记为只读完成。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-167** `匿名回调@1070` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1070](../../static/app.js#L1070)。
  - 原实现：`item => String(item.id) === previous`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 任务表单相关行为留待 V2-2B，不记为只读完成。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-168** `updateMaterialOptions` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1074](../../static/app.js#L1074)。
  - 原实现：`function updateMaterialOptions() { const template = state.templates.find(item => String(item.id) === String($("createTemplate")?.value ¦¦ "")); const select = $("createMaterial"); const count = $("createExpectedCount"); if (!select) return; const materials = template?.materials?.length ? template.materials : (template?.material ? [template.material] : []); select.innerHTML = materials.map(item => ˋ<option value="${escapeHtml(i`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 任务表单相关行为留待 V2-2B，不记为只读完成。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-169** `匿名回调@1075` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1075](../../static/app.js#L1075)。
  - 原实现：`item => String(item.id) === String($("createTemplate")?.value ¦¦ "")`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 任务表单相关行为留待 V2-2B，不记为只读完成。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-170** `匿名回调@1080` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1080](../../static/app.js#L1080)。
  - 原实现：`item => ˋ<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 任务表单相关行为留待 V2-2B，不记为只读完成。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-171** `postJson` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1087](../../static/app.js#L1087)。
  - 原实现：`async function postJson(url, payload, options = {}) { if (window.opsCloudPostJson) return window.opsCloudPostJson(url, payload); const timeoutMs = Number.isFinite(Number(options.timeoutMs)) ? Math.max(1000, Number(options.timeoutMs)) : 10000; const controller = new AbortController(); const timer = window.setTimeout(() => controller.abort(), timeoutMs); try { const response = await fetch(url, { method: "POST", headers: { "Conte`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/home-cleanup.ts:105（原JSON正文、独立超时与错误提示；云端使用队列写入器）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-172** `匿名回调@1093` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1093](../../static/app.js#L1093)。
  - 原实现：`() => controller.abort()`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/home-cleanup.ts:105（原JSON正文、独立超时与错误提示；云端使用队列写入器）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-173** `openReplenishment` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1117](../../static/app.js#L1117)。
  - 原实现：`function openReplenishment(taskId) { const item = state.gaps[String(taskId)]; const panel = $("replenishPanel"); const dialog = $("replenishDialog"); if (!item ¦¦ !panel) return; const expected = Number(item.expectedCount ¦¦ 0); const completed = Number(item.completed ¦¦ 0); const missing = Number(item.missingCount ?? Math.max(0, expected - completed)); panel.innerHTML = ˋ<header><div><strong>补链：${escapeHtml(item.project)} / $`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-174** `匿名回调@1131` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1131](../../static/app.js#L1131)。
  - 原实现：`() => dialog?.close()`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-175** `匿名回调@1132` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1132](../../static/app.js#L1132)。
  - 原实现：`async (event) => { event.preventDefault(); const button = event.currentTarget.querySelector("button"); button.disabled = true; try { const result = await postJson(ˋ/api/controls/tasks/${encodeURIComponent(taskId)}/replenishˋ, { urls: $("replenishUrls").value, startNow: $("replenishStartNow").checked, }); renderActionResult("queueActionResult", { state: "completed", message: result.message ¦¦ "补链任务已提交", updatedAt: new Date().to`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-176** `renderReceiverQueue` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1162](../../static/app.js#L1162)。
  - 原实现：`function renderReceiverQueue(items) { const node = $("receiverQueue"); if (!node) return; if (!items.length) { node.innerHTML = ˋ<p class="empty">暂无可确认或撤回的队列任务</p>ˋ; return; } // 223 items imported in July-September stayed "imported_waiting_start" and // made this list 25,000 px long. Keep what can need a decision in view. const recentMs = 3 * 24 * 3600 * 1000; const isRecent = item => String(item.status ¦¦ "") === "pending_co`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-177** `isRecent` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1172](../../static/app.js#L1172)。
  - 原实现：`item => String(item.status ¦¦ "") === "pending_confirmation" ¦¦ Date.now() - Date.parse(item.importedAt ¦¦ item.createdAt ¦¦ "") < recentMs`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-178** `匿名回调@1175` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1175](../../static/app.js#L1175)。
  - 原实现：`item => !isRecent(item)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-179** `render` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1176](../../static/app.js#L1176)。
  - 原实现：`list => list.map(item => { const taskId = String(item.taskId ¦¦ ""); const status = String(item.status ¦¦ ""); const canStart = status === "pending_confirmation" && !["auto_start_first", "auto_start_sequential"].includes(String(item.startMode ¦¦ "")); const canCancel = status === "pending_confirmation" ¦¦ status === "imported_waiting_start"; const sequence = item.batchId ? ˋ第 ${item.batchSequence ¦¦ 1} / ${item.batchSize ¦¦ 1}`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-180** `匿名回调@1176` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1176](../../static/app.js#L1176)。
  - 原实现：`item => { const taskId = String(item.taskId ¦¦ ""); const status = String(item.status ¦¦ ""); const canStart = status === "pending_confirmation" && !["auto_start_first", "auto_start_sequential"].includes(String(item.startMode ¦¦ "")); const canCancel = status === "pending_confirmation" ¦¦ status === "imported_waiting_start"; const sequence = item.batchId ? ˋ第 ${item.batchSequence ¦¦ 1} / ${item.batchSize ¦¦ 1} 项ˋ : "单条任务"; con`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-181** `renderTaskBoxes` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1198](../../static/app.js#L1198)。
  - 原实现：`function renderTaskBoxes(payload = {}) { const boxes = Array.isArray(payload.items) ? payload.items : []; const history = Array.isArray(payload.history) ? payload.history : []; const historyPanel = $("taskBoxHistory"); historyPanel.classList.toggle("hidden", !history.length); $("taskBoxHistoryCount").textContent = String(history.length); $("taskBoxHistoryItems").innerHTML = history.map(item => ˋ<article class="taskbox-history-`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-182** `匿名回调@1204` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1204](../../static/app.js#L1204)。
  - 原实现：`item => ˋ<article class="taskbox-history-item"> <strong>${escapeHtml(item.project ¦¦ "未分类")} / ${escapeHtml(item.material ¦¦ "--")}</strong> <span>${escapeHtml(item.productionDate ¦¦ "--")} · ${escapeHtml(item.status ¦¦ "cancelled")} · ${escapeHtml(item.reason ¦¦ "已撤回")}</span> </article>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-183** `匿名回调@1208` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1208](../../static/app.js#L1208)。
  - 原实现：`item => item.batchId === state.batchId`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-184** `匿名回调@1212` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1212](../../static/app.js#L1212)。
  - 原实现：`item => ˋ${item.batchId}:${item.productionDate}:${item.completedProjects}/${item.projectCount}:${item.state}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-185** `匿名回调@1216` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1216](../../static/app.js#L1216)。
  - 原实现：`item => ˋ<option value="${escapeHtml(item.batchId)}">${escapeHtml(item.productionDate ¦¦ "未定日期")} · ${item.completedProjects}/${item.projectCount} 项${item.state === "stale" ? " · 历史未完成" : ""} · ${escapeHtml(item.batchId.slice(-8))}</option>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-186** `匿名回调@1251` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1251](../../static/app.js#L1251)。
  - 原实现：`item => ˋ <article class="taskbox-item ${escapeHtml(item.status)} ${current && current.taskId === item.taskId ? "current" : ""}"> <div><span class="taskbox-sequence">${item.sequence}</span><strong>${escapeHtml(item.project)} / ${escapeHtml(item.material ¦¦ "--")}</strong><span class="task-state ${item.status === "blocked" ? "failed" : item.status === "planned" ? "neutral" : escapeHtml(item.status)}">${escapeHtml(item.currentSt`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-187** `renderServices` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1259](../../static/app.js#L1259)。
  - 原实现：`function renderServices(items = []) { const node = $("serviceHealthGrid"); node.innerHTML = items.map(item => ˋ<div class="service-health ${item.online ? "online" : "offline"}"> <i></i><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.stateText ¦¦ (item.online ? "运行中" : "未运行"))} · ${escapeHtml(ageFromTime(item.updatedAt))}</span> </div>ˋ).join(""); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-188** `匿名回调@1261` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1261](../../static/app.js#L1261)。
  - 原实现：`item => ˋ<div class="service-health ${item.online ? "online" : "offline"}"> <i></i><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.stateText ¦¦ (item.online ? "运行中" : "未运行"))} · ${escapeHtml(ageFromTime(item.updatedAt))}</span> </div>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-189** `runtimeFacts` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1269](../../static/app.js#L1269)。
  - 原实现：`function runtimeFacts(services = [], currentProjectStatus = {}) { const items = Array.isArray(services) ? services : []; const online = key => Boolean(items.find(item => item.key === key)?.online); const stages = Array.isArray(currentProjectStatus?.stages) ? currentProjectStatus.stages : []; const download = stages.find(item => item.step === "download") ¦¦ {}; const identity = currentProjectStatus?.identity ¦¦ {}; const facts `；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-190** `online` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1271](../../static/app.js#L1271)。
  - 原实现：`key => Boolean(items.find(item => item.key === key)?.online)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-191** `匿名回调@1271` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1271](../../static/app.js#L1271)。
  - 原实现：`item => item.key === key`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-192** `匿名回调@1273` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1273](../../static/app.js#L1273)。
  - 原实现：`item => item.step === "download"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-193** `renderRuntimeGuidance` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1289](../../static/app.js#L1289)。
  - 原实现：`function renderRuntimeGuidance(services = [], currentProjectStatus = {}) { const facts = runtimeFacts(services, currentProjectStatus); state.runtime = facts; const node = $("runtimeGuidance"); let tone = ""; let html = ""; if (facts.offline) { tone = "offline"; html = ˋ<strong>工作台已离线，生产实际已停止</strong>当前项目${facts.projectLabel ? ˋ（${escapeHtml(facts.projectLabel)}）ˋ : ""}显示为运行中，但工作台没有在运行。点击“安全继续当前项目”会自动启动工作台，并从断点继续。ˋ; } else if (`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-194** `nextActionFor` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1313](../../static/app.js#L1313)。
  - 原实现：`function nextActionFor(currentProjectStatus = {}) { const errors = Array.isArray(currentProjectStatus?.errors) ? currentProjectStatus.errors : []; if (!errors.length) return null; const identity = currentProjectStatus?.identity ¦¦ {}; const label = [identity.project, identity.material].filter(Boolean).join(" / "); const where = label ? ˋ${label}：ˋ : ""; const first = errors[0] ¦¦ {}; const reasons = items => items.map(item => `；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-195** `reasons` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1320](../../static/app.js#L1320)。
  - 原实现：`items => items.map(item => String(item.message ¦¦ "").trim()).filter(Boolean)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-196** `匿名回调@1320` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1320](../../static/app.js#L1320)。
  - 原实现：`item => String(item.message ¦¦ "").trim()`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-197** `匿名回调@1321` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1321](../../static/app.js#L1321)。
  - 原实现：`item => item.component === "capcut"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-198** `匿名回调@1322` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1322](../../static/app.js#L1322)。
  - 原实现：`item => item.component === "upload"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-199** `renderNextAction` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1346](../../static/app.js#L1346)。
  - 原实现：`function renderNextAction(currentProjectStatus = {}) { const node = $("nextAction"); if (!node) return; const facts = state.runtime ¦¦ {}; // While a client is working (or the workbench is offline) the banner above // already says what to do; a "click Safe Continue" line would contradict it. const next = facts.busy ¦¦ facts.offline ? null : nextActionFor(currentProjectStatus); node.classList.toggle("hidden", !next); if (!next)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-200** `renderHealth` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1365](../../static/app.js#L1365)。
  - 原实现：`function renderHealth(health = {}) { const body = $("healthBody"); if (!body) return; // No data (older backend or a failed read) must never read as "healthy". $("healthPanel").classList.toggle("hidden", !health.updatedAt); if (!health.updatedAt) return; const commands = Array.isArray(health.openCommands) ? health.openCommands : []; const errors = Array.isArray(health.recentErrors) ? health.recentErrors : []; const stuck = com`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-201** `匿名回调@1373` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1373](../../static/app.js#L1373)。
  - 原实现：`item => Number(item.ageSeconds ¦¦ 0) > 600 ¦¦ item.state === "reconciliation_required"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-202** `匿名回调@1379` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1379](../../static/app.js#L1379)。
  - 原实现：`item => ˋ<li><b>${escapeHtml(item.step ¦¦ "--")} · ${escapeHtml(item.state)}</b> <span>${escapeHtml(item.taskId ¦¦ item.commandId)}</span> <em>已持续 ${escapeHtml(formatAge(item.ageSeconds).replace("前", ""))}</em></li>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-203** `匿名回调@1384` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1384](../../static/app.js#L1384)。
  - 原实现：`item => ˋ<li><b>${escapeHtml(String(item.lastAt ¦¦ "").slice(5, 16).replace("T", " "))}</b> <span>${escapeHtml(item.message)}</span>${Number(item.count) > 1 ? ˋ<em>${Number(item.count)} 次</em>ˋ : ""}</li>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-204** `describeSourceErrors` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1392](../../static/app.js#L1392)。
  - 原实现：`function describeSourceErrors(errors = []) { const groups = new Map(); errors.forEach(item => { const name = String(item.name ¦¦ ""); const key = name === "第四步到第五步.json" ? "handoff" : name === "last_batch_handoff.json" ? "voice" : ˋother:${name}:${item.error ¦¦ ""}ˋ; groups.set(key, [...(groups.get(key) ¦¦ []), item]); }); return [...groups.entries()].map(([key, items]) => { if (key === "handoff") return ˋ${items.length} 个日期的剪`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-205** `匿名回调@1394` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1394](../../static/app.js#L1394)。
  - 原实现：`item => { const name = String(item.name ¦¦ ""); const key = name === "第四步到第五步.json" ? "handoff" : name === "last_batch_handoff.json" ? "voice" : ˋother:${name}:${item.error ¦¦ ""}ˋ; groups.set(key, [...(groups.get(key) ¦¦ []), item]); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-206** `匿名回调@1400` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1400](../../static/app.js#L1400)。
  - 原实现：`([key, items]) => { if (key === "handoff") return ˋ${items.length} 个日期的剪映交接记录（第四步到第五步.json）无法读取，这些日期的第 5 步历史暂时不完整ˋ; if (key === "voice") return "语音交接记录（last_batch_handoff.json）无法读取；下一批配音开始后会重新生成"; return ˋ${items[0].name}：${items[0].error}ˋ; }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-207** `renderSources` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1407](../../static/app.js#L1407)。
  - 原实现：`function renderSources(source = {}) { const panel = $("sourceWarningPanel"); const errors = Array.isArray(source.errors) ? source.errors : []; const messages = []; if (source.stale) messages.push("Dashboard采集状态已经过期"); if (source.receiverError) messages.push(ˋ接收器状态读取失败：${source.receiverError}ˋ); if (source.watchdog && source.watchdog.state === "failed") { messages.push(ˋDashboard守护启动失败：${source.watchdog.message ¦¦ "原因未知"}ˋ); } `；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-208** `匿名回调@1416` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1416](../../static/app.js#L1416)。
  - 原实现：`message => messages.push(message)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-209** `匿名回调@1419` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1419](../../static/app.js#L1419)。
  - 原实现：`message => ˋ<li>${escapeHtml(message)}</li>ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-210** `renderContinueResult` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1423](../../static/app.js#L1423)。
  - 原实现：`function renderContinueResult(result = {}) { if (window.opsCloudContinueResult) result = window.opsCloudContinueResult(result); state.lastContinueResult = result; const node = $("continueResult"); const stateName = String(result.state ¦¦ "idle"); state.continueCommandId = String(result.commandId ¦¦ state.continueCommandId ¦¦ ""); // A continue command is durable on the receiver. Keep the button locked for // every non-terminal`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-211** `匿名回调@1472` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1472](../../static/app.js#L1472)。
  - 原实现：`item => ˋ<div><span>${item.step}. ${escapeHtml(item.name)}</span><b>${Number(item.actual ¦¦ 0)} / ${Number(item.expected ¦¦ 0)}</b></div>ˋ`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-212** `refreshContinueStatus` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1514](../../static/app.js#L1514)。
  - 原实现：`async function refreshContinueStatus() { if (state.continueStatusBusy) return; state.continueStatusBusy = true; try { const target = window.opsCloudContinueTarget ? window.opsCloudContinueTarget() : "/api/control-commands/current"; if (!target) return; const result = await getJson(target); state.continueStatusFailures = 0; renderContinueResult(result ¦¦ {}); } catch (error) { state.continueStatusFailures += 1; // Never leave a`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-213** `renderActionResult` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1549](../../static/app.js#L1549)。
  - 原实现：`function renderActionResult(id, result = {}) { const node = $(id); const stateName = String(result.state ¦¦ "idle"); node.className = ˋaction-result ${stateName === "completed" ? "completed" : stateName === "failed" ? "failed" : "neutral"}ˋ; node.textContent = ˋ${result.message ¦¦ "尚无操作记录"}${result.updatedAt ? ˋ · ${formatDateTime(result.updatedAt)}ˋ : ""}ˋ; }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:259（原结果/历史核验状态与计数；UploadActions独立反馈）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-214** `renderHistoricalCloudVerification` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1556](../../static/app.js#L1556)。
  - 原实现：`function renderHistoricalCloudVerification(result = {}) { const stateName = String(result.state ¦¦ "idle"); const total = Number(result.total ?? result.eligible ?? 0); const processed = Number(result.processed ¦¦ 0); const verified = Number(result.verified ¦¦ 0); const failed = Number(result.failed ¦¦ 0); const summary = total ? ˋ · ${processed}/${total}，通过 ${verified}，失败 ${failed}ˋ : ""; renderActionResult("historicalCloudVer`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:259（原结果/历史核验状态与计数；UploadActions独立反馈）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-215** `controlTask` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1578](../../static/app.js#L1578)。
  - 原实现：`async function controlTask(button, action) { const taskId = String(button.dataset.taskId ¦¦ ""); if (!taskId) return; const isStart = action === "start"; const question = isStart ? "确认启动这个批次的首项吗？工作台会继续按原有顺序处理。" : "确认撤回这个尚未开始的任务吗？不会删除任何视频、音频或素材。"; if (!window.confirm(question)) return; button.disabled = true; button.textContent = isStart ? "正在启动…" : "正在撤回…"; try { const response = await fetch(ˋ/api/controls/tasks/${encodeURICom`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-216** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1612](../../static/app.js#L1612)。
  - 原实现：`async function getJson(url, retries = 1, timeoutMs = 8000) { let lastError; for (let attempt = 0; attempt <= retries; attempt += 1) { const controller = new AbortController(); const timer = window.setTimeout(() => controller.abort(), timeoutMs); try { const headers = {}; if (state.etags[url]) headers["If-None-Match"] = state.etags[url]; const response = await fetch(url, { cache: "no-cache", headers, signal: controller.signal }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-217** `匿名回调@1616` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1616](../../static/app.js#L1616)。
  - 原实现：`() => controller.abort()`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-218** `匿名回调@1630` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1630](../../static/app.js#L1630)。
  - 原实现：`resolve => window.setTimeout(resolve, 500 * (2 ** attempt))`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-219** `refresh` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1638](../../static/app.js#L1638)。
  - 原实现：`async function refresh() { if (state.refreshBusy) return; state.refreshBusy = true; try { const useSummary = state.fullDashboardLoaded && !state.historyExplicit && !state.batchId; const params = new URLSearchParams(); if (state.date) params.set("date", state.date); if (state.batchId) params.set("batchId", state.batchId); const url = useSummary ? "/api/dashboard/summary" : ˋ/api/dashboard${params.toString() ? ˋ?${params}ˋ : ""}`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-220** `匿名回调@1714` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1714](../../static/app.js#L1714)。
  - 原实现：`event => { state.date = event.target.value; state.historyExplicit = true; refresh(); }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期/任务箱/项目筛选回调保持原选择语义）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-221** `匿名回调@1719` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1719](../../static/app.js#L1719)。
  - 原实现：`event => { state.batchId = event.target.value; state.date = ""; state.historyExplicit = Boolean(state.batchId); refresh(); }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:29（日期/任务箱/项目筛选回调保持原选择语义）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-222** `匿名回调@1725` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1725](../../static/app.js#L1725)。
  - 原实现：`event => { state.step5Filter = event.target.value; renderTasks(state.step5Items); }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:324（日期/任务箱/项目筛选回调保持原选择语义）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-223** `匿名回调@1729` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1729](../../static/app.js#L1729)。
  - 原实现：`async () => { const dialog = $("draftManagerDialog"); if (dialog && !dialog.open) dialog.showModal(); await loadDraftManager(); }`；实现/测试证据：待补。 实现：FileManagers/useDashboard 家里清理与60秒待删区读取；PR #34，仅隔离。
- [x] **FN-224** `匿名回调@1734` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1734](../../static/app.js#L1734)。
  - 原实现：`() => $("draftManagerDialog")?.close()`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-225** `匿名回调@1736` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1736](../../static/app.js#L1736)。
  - 原实现：`id => { $(id)?.addEventListener(id === "draftSearchFilter" ? "input" : "change", () => { resetDraftPreview(); renderDraftManager(); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-226** `匿名回调@1737` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1737](../../static/app.js#L1737)。
  - 原实现：`() => { resetDraftPreview(); renderDraftManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-227** `匿名回调@1742` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1742](../../static/app.js#L1742)。
  - 原实现：`() => { filteredDrafts().filter(item => !item.protected).forEach(item => state.selectedDraftIds.add(item.draftId)); resetDraftPreview(); renderDraftManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-228** `匿名回调@1743` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1743](../../static/app.js#L1743)。
  - 原实现：`item => !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-229** `匿名回调@1743` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1743](../../static/app.js#L1743)。
  - 原实现：`item => state.selectedDraftIds.add(item.draftId)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-230** `匿名回调@1747` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1747](../../static/app.js#L1747)。
  - 原实现：`() => { state.selectedDraftIds.clear(); resetDraftPreview(); renderDraftManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-231** `匿名回调@1752` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1752](../../static/app.js#L1752)。
  - 原实现：`async event => { const button = event.currentTarget; const draftIds = [...state.selectedDraftIds]; if (!draftIds.length) { $("draftCleanupPreview").classList.remove("hidden"); $("draftCleanupPreview").innerHTML = "<strong>尚未选择草稿</strong>请先勾选要移入待删区的草稿。"; return; } button.disabled = true; button.textContent = "正在核对…"; try { const preview = await postJson("/api/controls/capcut-drafts/preview", { draftIds }, { timeoutMs: 60000 });`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-232** `匿名回调@1766` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1766](../../static/app.js#L1766)。
  - 原实现：`item => ˋ<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-233** `匿名回调@1783` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1783](../../static/app.js#L1783)。
  - 原实现：`async event => { const button = event.currentTarget; const preview = state.draftPreview; if (!preview?.deletableCount) return; if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个草稿移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除视频、音频、成片或生产任务。ˋ)) return; if (preview.containsManualOrUnknown && !window.confirm("选择中包含人工或来源不明草稿。再次确认仍要将这些草稿移入待删区。")) return; button.disabled = true; button.textContent = "正在移入待删区…"; try { const draftIds = (preview.delet`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-234** `匿名回调@1792` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1792](../../static/app.js#L1792)。
  - 原实现：`item => item.draftId`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-235** `匿名回调@1814` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1814](../../static/app.js#L1814)。
  - 原实现：`async () => { const dialog = $("audioManagerDialog"); if (dialog && !dialog.open) dialog.showModal(); await loadAudioManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-236** `匿名回调@1819` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1819](../../static/app.js#L1819)。
  - 原实现：`() => $("audioManagerDialog")?.close()`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-237** `匿名回调@1820` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1820](../../static/app.js#L1820)。
  - 原实现：`() => $("audioProtectionDialog")?.close()`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-238** `匿名回调@1825` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1825](../../static/app.js#L1825)。
  - 原实现：`id => { $(id)?.addEventListener(id === "audioSearchFilter" ? "input" : "change", () => { resetAudioPreview(); renderAudioManager(); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-239** `匿名回调@1826` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1826](../../static/app.js#L1826)。
  - 原实现：`() => { resetAudioPreview(); renderAudioManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-240** `匿名回调@1831` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1831](../../static/app.js#L1831)。
  - 原实现：`() => { filteredAudioFiles().filter(item => !item.protected).forEach(item => state.selectedAudioIds.add(item.audioId)); resetAudioPreview(); renderAudioManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-241** `匿名回调@1832` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1832](../../static/app.js#L1832)。
  - 原实现：`item => !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-242** `匿名回调@1832` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1832](../../static/app.js#L1832)。
  - 原实现：`item => state.selectedAudioIds.add(item.audioId)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-243** `匿名回调@1836` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1836](../../static/app.js#L1836)。
  - 原实现：`() => { state.selectedAudioIds.clear(); resetAudioPreview(); renderAudioManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-244** `匿名回调@1841` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1841](../../static/app.js#L1841)。
  - 原实现：`async event => { const button = event.currentTarget; const audioIds = [...state.selectedAudioIds]; if (!audioIds.length) { $("audioCleanupPreview").classList.remove("hidden"); $("audioCleanupPreview").innerHTML = "<strong>尚未选择音频</strong>请先勾选要移入待删区的音频文件。"; return; } button.disabled = true; button.textContent = "正在重新对账…"; try { const preview = await postJson("/api/controls/audio-files/preview", { audioIds }, { timeoutMs: 60000 }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-245** `匿名回调@1855` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1855](../../static/app.js#L1855)。
  - 原实现：`item => ˋ<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-246** `匿名回调@1876` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1876](../../static/app.js#L1876)。
  - 原实现：`async event => { const button = event.currentTarget; const preview = state.audioPreview; if (!preview?.deletableCount) return; if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个音频文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除文件夹，也不会改变任务完成状态。ˋ)) return; button.disabled = true; button.textContent = "正在移入待删区…"; try { const audioIds = (preview.deletable ¦¦ []).map(item => item.audioId); const result = await p`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-247** `匿名回调@1884` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1884](../../static/app.js#L1884)。
  - 原实现：`item => item.audioId`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-248** `匿名回调@1908` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1908](../../static/app.js#L1908)。
  - 原实现：`async () => { const dialog = $("productionManagerDialog"); if (dialog && !dialog.open) dialog.showModal(); await loadProductionManager({ applyDefaults: true }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-249** `匿名回调@1913` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1913](../../static/app.js#L1913)。
  - 原实现：`() => $("productionManagerDialog")?.close()`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-250** `匿名回调@1914` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1914](../../static/app.js#L1914)。
  - 原实现：`() => $("productionProtectionDialog")?.close()`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-251** `匿名回调@1915` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1915](../../static/app.js#L1915)。
  - 原实现：`() => loadProductionManager()`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-252** `匿名回调@1919` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1919](../../static/app.js#L1919)。
  - 原实现：`id => { $(id)?.addEventListener(id === "productionSearchFilter" ? "input" : "change", () => { resetProductionPreview(); renderProductionManager(); }); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-253** `匿名回调@1920` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1920](../../static/app.js#L1920)。
  - 原实现：`() => { resetProductionPreview(); renderProductionManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-254** `匿名回调@1925` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1925](../../static/app.js#L1925)。
  - 原实现：`() => { filteredProductionFiles() .filter(item => !item.protected) .forEach(item => state.selectedProductionIds.add(item.fileId)); resetProductionPreview(); renderProductionManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-255** `匿名回调@1927` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1927](../../static/app.js#L1927)。
  - 原实现：`item => !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-256** `匿名回调@1928` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1928](../../static/app.js#L1928)。
  - 原实现：`item => state.selectedProductionIds.add(item.fileId)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-257** `匿名回调@1932` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1932](../../static/app.js#L1932)。
  - 原实现：`() => { state.selectedProductionIds.clear(); resetProductionPreview(); renderProductionManager(); }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-258** `匿名回调@1937` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1937](../../static/app.js#L1937)。
  - 原实现：`async event => { const button = event.currentTarget; const fileIds = [...state.selectedProductionIds]; if (!fileIds.length) { $("productionCleanupPreview").classList.remove("hidden"); $("productionCleanupPreview").innerHTML = "<strong>尚未选择生产文件</strong>请先勾选要移入待删区的文件。"; return; } button.disabled = true; button.textContent = "正在重新核验云端与引用…"; try { const preview = await postJson("/api/controls/production-files/preview", { fileIds }`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-259** `匿名回调@1951` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1951](../../static/app.js#L1951)。
  - 原实现：`item => ˋ<li>${escapeHtml(item.label)}：${Number(item.count ¦¦ 0)} 个 · ${escapeHtml(formatBytes(item.sizeBytes))}</li>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-260** `匿名回调@1954` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1954](../../static/app.js#L1954)。
  - 原实现：`item => ˋ<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-261** `匿名回调@1978` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1978](../../static/app.js#L1978)。
  - 原实现：`async event => { const button = event.currentTarget; const preview = state.productionPreview; if (!preview?.deletableCount) return; if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个生产文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；项目状态、上传记录及云端文件不会改变。ˋ)) return; if (preview.containsTestFiles && !window.confirm("选择中包含 CapCut 测试或首帧测试文件。再次确认仍要将这些测试文件移入待删区。")) return; button.disabled = true; button.textContent = "正`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-262** `匿名回调@1987` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1987](../../static/app.js#L1987)。
  - 原实现：`item => item.fileId`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-263** `refreshPendingDelete` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2015](../../static/app.js#L2015)。
  - 原实现：`async function refreshPendingDelete() { const node = $("pendingDeleteStatus"); const button = $("emptyPendingDeleteButton"); if (!node ¦¦ !button) return; try { const result = await getJson("/api/controls/pending-delete"); state.pendingDelete = result; const count = Number(result.count ¦¦ 0); const review = Number(result.needsReview ¦¦ 0); node.textContent = count ? ˋ待删区：${count} 项，约 ${formatBytes(result.sizeBytes)}；${result.n`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-264** `匿名回调@2035` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2035](../../static/app.js#L2035)。
  - 原实现：`async (event) => { const button = event.currentTarget; const info = state.pendingDelete ¦¦ {}; if (!window.confirm(ˋ确认立即永久清除待删区的 ${Number(info.count ¦¦ 0)} 项（约 ${formatBytes(info.sizeBytes)}）吗？清除后无法恢复。ˋ)) return; if (!window.confirm("再次确认：这一步会永久删除，不进入回收站。")) return; button.disabled = true; try { const result = await postJson("/api/controls/pending-delete/empty", { confirm: "EMPTY_PENDING_DELETE_NOW" }, { timeoutMs: 600000 }); `；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **FN-265** `匿名回调@2051` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2051](../../static/app.js#L2051)。
  - 原实现：`async (event) => { const button = event.currentTarget; if (button.dataset.allowed === "false") return; if (!window.confirm("确认让家里工作台安全继续当前项目吗？它会先核对任务清单，不会删除素材或重做有效成片。")) return; button.disabled = true; button.textContent = "正在发送继续指令…"; try { const clientRequestId = (window.crypto?.randomUUID?.() ¦¦ ˋdashboard-${Date.now()}-${Math.random()}ˋ); // Name the project this page showed when the user confirmed, so a stale // page cann`；实现/测试证据：待补。 安全继续留独立2E，用户亲自确认后才可合并。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-266** `匿名回调@2066` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2066](../../static/app.js#L2066)。
  - 原实现：`([, value]) => typeof value === "string" && value`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-267** `匿名回调@2083` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2083](../../static/app.js#L2083)。
  - 原实现：`async (event) => { const button = event.currentTarget; if (!window.confirm("确认重新对账正式清单，补传遗漏成片，并对云端已实时核验的任务继续安全清理吗？不会重新剪辑等待中的任务，也不会清理配音、公共素材、Logo或公共样品。")) return; button.disabled = true; button.textContent = "正在检查上传缺口…"; try { const result = await postJson("/api/controls/upload/rescan", {}); renderActionResult("uploadActionResult", { state: window.opsCloudPostJson ? (result.state ¦¦ "requested") : "completed", message: result.m`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **FN-268** `匿名回调@2107` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2107](../../static/app.js#L2107)。
  - 原实现：`async (event) => { const button = event.currentTarget; if (!window.confirm("确认核验历史百度云文件吗？系统只会查询云端文件是否存在，并核对云端路径和文件大小；不会补传、不会删除本地或云端文件，也不会改变项目完成状态。")) return; button.disabled = true; button.textContent = "正在提交历史核验…"; try { const result = await postJson("/api/controls/upload/verify-history", {}); renderHistoricalCloudVerification(result); await refresh(); } catch (error) { renderHistoricalCloudVerification({ state: "failed", mes`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **FN-269** `匿名回调@2124` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2124](../../static/app.js#L2124)。
  - 原实现：`async (event) => { const button = event.currentTarget; if (!window.confirm("确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。")) return; if (!window.confirm("再次确认：Dashboard、工作台、接收器和 CapCut 的任务进度将从空状态重新开始。")) return; button.disabled = true; button.textContent = "正在备份并重置…"; try { const result = await postJson("/api/controls/testing/reset", { confirm: "RESET_TEST_RECORDS" }); state.date = ""; state.batchId = ""; renderActionResult("resetR`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-270** `匿名回调@2153` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2153](../../static/app.js#L2153)。
  - 原实现：`async (event) => { event.preventDefault(); const form = event.currentTarget; const button = form.querySelector("button[type='submit']"); button.disabled = true; try { const result = await postJson("/api/controls/tasks/create", { date: $("createDate").value.trim(), templateId: $("createTemplate").value, material: $("createMaterial").value, audioBatch: $("createAudioBatch").value.trim(), voicePlan: $("createVoicePlan").value, ex`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **FN-271** `refreshLoop` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:2187](../../static/app.js#L2187)。
  - 原实现：`async function refreshLoop() { await refresh(); window.setTimeout(refreshLoop, document.hidden ? 20000 : 5000); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-272** `refreshContinueLoop` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:2192](../../static/app.js#L2192)。
  - 原实现：`async function refreshContinueLoop() { if (state.continueInFlight) await refreshContinueStatus(); window.setTimeout(refreshContinueLoop, state.continueInFlight ? (document.hidden ? 5000 : 1500) : 10000); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-273** `匿名回调@2` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:2](../../cloud/readonly.js#L2)。
  - 原实现：`() => { const original = window.fetch.bind(window); window.opsCloudNetwork=original; const samples = new Map(); const inflight = new Map(); let sourcePanel, dashboardSample; const refreshWatchers = new Map(); const writeIds=['emptyPendingDeleteButton','continueCurrentButton','uploadRescanButton','historicalCloudVerifyButton','resetTestRecordsButton','previewDraftCleanupButton','confirmDraftCleanupButton','previewAudioCleanupBu`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 部分覆盖：读取已迁移，外层包装/写入拦截/账号事件尚未全部迁移，不记为完成。 完整子功能复核：frontend-v2/src/data/client.ts:3（只读网络适配、202、缓存、401及取消；子功能均已迁移）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-274** `匿名回调@10` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:10](../../cloud/readonly.js#L10)。
  - 原实现：`event => { if (!event.target.closest('[data-cloud-account]') && !window.opsCloudAcceptForm?.(event.target)) { event.preventDefault(); event.stopImmediatePropagation(); } }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 部分覆盖：读取已迁移，外层包装/写入拦截/账号事件尚未全部迁移，不记为完成。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-275** `wait` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:13](../../cloud/readonly.js#L13)。
  - 原实现：`(ms, signal) => new Promise((resolve, reject) => { if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; } const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }; const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms); signal?.addEventListener('abort', abort, {once: true}); })`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-276** `匿名回调@13` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:13](../../cloud/readonly.js#L13)。
  - 原实现：`(resolve, reject) => { if (signal?.aborted) { reject(new DOMException('Aborted', 'AbortError')); return; } const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }; const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms); signal?.addEventListener('abort', abort, {once: true}); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-277** `abort` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:15](../../cloud/readonly.js#L15)。
  - 原实现：`() => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-278** `匿名回调@16` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:16](../../cloud/readonly.js#L16)。
  - 原实现：`() => { signal?.removeEventListener('abort', abort); resolve(); }`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-279** `observe` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:19](../../cloud/readonly.js#L19)。
  - 原实现：`function observe(url, response) { const age = response.headers.get('X-Cache-Age-Seconds'); if (age !== null) { let health={};try{health=JSON.parse(response.headers.get('X-Source-Health')¦¦'{}');}catch{} samples.set(url, {age: Number(age), received: performance.now(), scan: response.headers.get('X-Source-Scanned-At') ¦¦ '源扫描时间未知', sourceAge:typeof health.scanAgeSeconds==='number'?health.scanAgeSeconds:null}); const path=new URL`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-280** `watchRefresh` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:28](../../cloud/readonly.js#L28)。
  - 原实现：`function watchRefresh(key, response) { if (response.headers.get('X-Cache-Refresh-Pending')!=='true'¦¦refreshWatchers.has(key)) return; const url=new URL(key,location.origin);const batch=url.searchParams.get('batchId'); if(url.pathname!=='/api/dashboard'¦¦!batch)return; const previous=response.headers.get('X-Cache-Version');const previousTag=response.headers.get('ETag'); const watch=(async()=>{ for(let attempt=0;attempt<60;atte`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-281** `匿名回调@33` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:33](../../cloud/readonly.js#L33)。
  - 原实现：`async()=>{ for(let attempt=0;attempt<60;attempt++){ await wait(1000); if(document.visibilityState!=='visible')return; if(typeof state==='undefined'¦¦state.batchId!==batch)return; const newer=await original(key,{headers:{'X-Ops-Page-Visible':'true'}}); if(newer.status===401){location.assign('/login');return;} if(newer.status===200&&(newer.headers.get('X-Cache-Version')!==previous¦¦newer.headers.get('ETag')!==previousTag)){ if(!`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-282** `匿名回调@45` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:45](../../cloud/readonly.js#L45)。
  - 原实现：`()=>{}`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-283** `匿名回调@45` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:45](../../cloud/readonly.js#L45)。
  - 原实现：`()=>refreshWatchers.delete(key)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-284** `匿名回调@48` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:48](../../cloud/readonly.js#L48)。
  - 原实现：`async (input, init = {}) => { const url = new URL(input instanceof Request ? input.url : input, location.href); if (url.origin !== location.origin ¦¦ !url.pathname.startsWith('/api/')) return original(input, init); const method = (init.method ¦¦ (input instanceof Request ? input.method : 'GET')).toUpperCase(); if (method !== 'GET') {if(window.opsCloudWriteFetch)return window.opsCloudWriteFetch(url.href,init);throw new Error('写`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 部分覆盖：读取已迁移，外层包装/写入拦截/账号事件尚未全部迁移，不记为完成。 完整子功能复核：frontend-v2/src/data/client.ts:3（只读网络适配、202、缓存、401及取消；子功能均已迁移）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-285** `匿名回调@58` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:58](../../cloud/readonly.js#L58)。
  - 原实现：`async () => { for (let attempt = 0; attempt < 120; attempt++) { const response = await original(input, init); if (response.status === 401) { location.assign('/login'); throw new Error('请重新登录'); } if (response.status !== 202) { observe(key, response); watchRefresh(key,response); return response; } // A pending envelope is never delivered to the old business renderer. await wait(500, init.signal ¦¦ (input instanceof Request ? in`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-286** `匿名回调@71` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:71](../../cloud/readonly.js#L71)。
  - 原实现：`() => { // The home H4 timer measures browser reception. Cloud reception is not a // fresh home scan: derive displayed age from cloud cache/source ages. const paintCloudAge=()=>{ if(!dashboardSample¦¦typeof state==='undefined')return; const sample=dashboardSample;const since=(performance.now()-sample.received)/1000; const age=sample.age+since;const known=sample.sourceAge!==null&&Number.isFinite(sample.sourceAge)&&sample.source`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 部分覆盖：读取已迁移，外层包装/写入拦截/账号事件尚未全部迁移，不记为完成。 完整子功能复核：frontend-v2/src/data/client.ts:3（只读网络适配、202、缓存、401及取消；子功能均已迁移）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-287** `paintCloudAge` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:74](../../cloud/readonly.js#L74)。
  - 原实现：`()=>{ if(!dashboardSample¦¦typeof state==='undefined')return; const sample=dashboardSample;const since=(performance.now()-sample.received)/1000; const age=sample.age+since;const known=sample.sourceAge!==null&&Number.isFinite(sample.sourceAge)&&sample.sourceAge>=0; const effective=known?sample.sourceAge+age:null; state.freshnessReceivedAt=known?new Date(Date.now()-effective*1000):null; state.freshnessReceivedTick=performance.no`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **FN-288** `credentials` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:106](../../cloud/readonly.js#L106)。
  - 原实现：`async function credentials() { const response = await original('/auth/session'); if (!response.ok) throw new Error(); return response.json(); }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-289** `匿名回调@107` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:107](../../cloud/readonly.js#L107)。
  - 原实现：`async () => { const info = await credentials(); await original('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':info.csrf}}); location.assign('/login'); }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-290** `匿名回调@108` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:108](../../cloud/readonly.js#L108)。
  - 原实现：`() => { if (account.querySelector('form')) return; const form = document.createElement('form'); for (const [name,label] of [['oldPassword','当前密码'],['newPassword','新密码（至少12个字符）']]) { const input = document.createElement('input'); input.type='password'; input.name=name; input.required=true; input.placeholder=label; input.maxLength=256; input.autocomplete=name==='newPassword'?'new-password':'current-password'; if(name==='newPassw`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-291** `匿名回调@115` — 云端；计划 **V2-2F**；来源 [cloud/readonly.js:115](../../cloud/readonly.js#L115)。
  - 原实现：`async event=>{event.preventDefault();submit.disabled=true;try{const info=await credentials();const response=await original('/auth/password',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify(Object.fromEntries(new FormData(form)))});if(response.ok){form.reset();location.assign('/login');}else alert('未修改，请核对密码后重试');}finally{submit.disabled=false;}}`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-292** `disableWrites` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:119](../../cloud/readonly.js#L119)。
  - 原实现：`()=>{ const buttons=[...document.querySelectorAll('button[onclick], button[data-cloud-control], #createTaskForm button, #replenishForm button[type="submit"]'),...writeIds.map(id=>document.getElementById(id)).filter(Boolean)]; for(const button of buttons) { const action=/^controlTask\(this, '(start¦cancel)'\)$/.exec(button.getAttribute('onclick')¦¦''); if(action){button.dataset.cloudControl=action[1];button.removeAttribute('onc`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-293** `匿名回调@120` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:120](../../cloud/readonly.js#L120)。
  - 原实现：`id=>document.getElementById(id)`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-294** `pollHealth` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:132](../../cloud/readonly.js#L132)。
  - 原实现：`async function pollHealth() { try { const response=await original('/console/status',{headers:{'X-Ops-Page-Visible':String(document.visibilityState==='visible')}}); if(response.status===401){location.assign('/login');return;} if(!response.ok)throw new Error(); const health=await response.json(); const text=health.heartbeatAgeSeconds===null?'等待家里代理部署/连接':!health.agentOnline?'家里离线，距心跳 '+Math.floor(health.heartbeatAgeSeconds)+' 秒'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-295** `匿名回调@147` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:147](../../cloud/readonly.js#L147)。
  - 原实现：`()=>{ if(typeof state!=='undefined'&&!state.refreshBusy&&typeof refresh==='function'){ state.fullDashboardLoaded=false;void refresh(); } }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-296** `匿名回调@152` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:152](../../cloud/readonly.js#L152)。
  - 原实现：`() => { const list=sourcePanel.querySelector('ul'); list.replaceChildren(); for (const [key,sample] of samples) { const age=Math.floor(sample.age+(performance.now()-sample.received)/1000); const row=document.createElement('li'); const parsed=new URL(key,location.origin); const names={'/api/health':'递交健康','/api/dashboard':'完整看板','/api/dashboard/summary':'当前摘要','/api/task-boxes/current':'当前任务箱','/api/task-boxes/history':'历史任务箱',`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-297** `匿名回调@3` — 云端；计划 **V2-1**；来源 [cloud/commands.js:3](../../cloud/commands.js#L3)。
  - 原实现：`() => { const network=window.opsCloudNetwork¦¦window.fetch.bind(window), key='ops-command-receipts-v1'; const active=new Map();let health={},panel,list,specificResult;const eligibility=new Map(); const pending=new Set(['submitting','queued','leased','sent','unknown']); const labels={submitting:'收件结果待查询',queued:'云端排队',leased:'代理已领取，尚未发送',sent:'已发家里，等待 HTTP 回执',unknown:'结果不明，必须在家里对账',completed:'已收到家里 HTTP 回执（业务进度请看原状态）',not_sent`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-298** `匿名回调@9` — 云端；计划 **V2-1**；来源 [cloud/commands.js:9](../../cloud/commands.js#L9)。
  - 原实现：`r=>r&&typeof r.requestId==='string'&&typeof r.fingerprint==='string'&&typeof r.path==='string'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-299** `save` — 云端；计划 **V2-1**；来源 [cloud/commands.js:10](../../cloud/commands.js#L10)。
  - 原实现：`()=>localStorage.setItem(key,JSON.stringify(records.slice(-100)))`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-300** `delay` — 云端；计划 **V2-1**；来源 [cloud/commands.js:11](../../cloud/commands.js#L11)。
  - 原实现：`ms=>new Promise(resolve=>setTimeout(resolve,ms))`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-301** `匿名回调@11` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:11](../../cloud/commands.js#L11)。
  - 原实现：`resolve=>setTimeout(resolve,ms)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-302** `stable` — 云端；计划 **V2-1**；来源 [cloud/commands.js:12](../../cloud/commands.js#L12)。
  - 原实现：`value=>Array.isArray(value)?value.map(stable):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,stable(value[k])])):value`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-303** `匿名回调@12` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:12](../../cloud/commands.js#L12)。
  - 原实现：`k=>[k,stable(value[k])]`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-304** `allowedPath` — 云端；计划 **V2-1**；来源 [cloud/commands.js:13](../../cloud/commands.js#L13)。
  - 原实现：`path=>/^\/api\/controls\/tasks\/(create¦[^/]+\/(start¦cancel¦replenish))$/.test(path)¦¦/^\/api\/controls\/upload\/(rescan¦verify-history)$/.test(path)¦¦path==='/api/control-commands'¦¦/^\/api\/controls\/cloud-cleanup\/(preview¦execute)$/.test(path)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-305** `unfinished` — 云端；计划 **V2-1**；来源 [cloud/commands.js:14](../../cloud/commands.js#L14)。
  - 原实现：`()=>records.some(r=>pending.has(r.state))`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-306** `匿名回调@14` — 云端；计划 **V2-1**；来源 [cloud/commands.js:14](../../cloud/commands.js#L14)。
  - 原实现：`r=>pending.has(r.state)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-307** `匿名回调@15` — 云端；计划 **V2-1**；来源 [cloud/commands.js:15](../../cloud/commands.js#L15)。
  - 原实现：`button=>{ if(!health.executorAvailable¦¦!health.homeReady¦¦health.commandBlocker¦¦unfinished()¦¦active.size)return false; if(/^(preview¦confirm)(Draft¦Audio¦Production)CleanupButton$/.test(button?.id¦¦'')¦¦button?.id==='emptyPendingDeleteButton')return health.canCleanup===true; if(button?.id==='continueCurrentButton')return health.canContinue===true&&button.dataset.allowed==='true'; if(['uploadRescanButton','historicalCloudVer`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-308** `匿名回调@22` — 云端；计划 **V2-1**；来源 [cloud/commands.js:22](../../cloud/commands.js#L22)。
  - 原实现：`form=>Boolean(form.closest('#createTaskForm,#replenishForm'))&&health.executorAvailable&&health.homeReady&&!health.commandBlocker&&!unfinished()`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-309** `匿名回调@23` — 云端；计划 **V2-1**；来源 [cloud/commands.js:23](../../cloud/commands.js#L23)。
  - 原实现：`result=>{ const record=[...records].reverse().find(r=>r.path==='/api/control-commands'); if(record&&pending.has(record.state))return {...result,state:record.state,allowed:false,continueCanRetry:false,message:labels[record.state],cloudCommandId:record.cloudCommandId}; let observedEligibility=true; if(record?.homeCommandId&&result.commandId!==record.homeCommandId){ observedEligibility=false; result=specificResult?.commandId===re`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-310** `匿名回调@24` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:24](../../cloud/commands.js#L24)。
  - 原实现：`r=>r.path==='/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-311** `匿名回调@36` — 云端；计划 **V2-1**；来源 [cloud/commands.js:36](../../cloud/commands.js#L36)。
  - 原实现：`()=>{ const record=[...records].reverse().find(r=>r.path==='/api/control-commands'); if(record&&pending.has(record.state))return null; return record?.homeCommandId?'/api/control-commands/'+encodeURIComponent(record.homeCommandId):'/api/control-commands/current'; }`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-312** `匿名回调@37` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:37](../../cloud/commands.js#L37)。
  - 原实现：`r=>r.path==='/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-313** `credentials` — 云端；计划 **V2-1**；来源 [cloud/commands.js:41](../../cloud/commands.js#L41)。
  - 原实现：`async function credentials(){const r=await network('/auth/session');if(!r.ok)throw new Error('请重新登录');return r.json();}`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-314** `postControl` — 云端；计划 **V2-1**；来源 [cloud/commands.js:42](../../cloud/commands.js#L42)。
  - 原实现：`async function postControl(url,body={}){ const info=await credentials();const r=await network(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify(body)}); const value=await r.json();if(!r.ok)throw new Error(value.detail¦¦'操作失败');return value; }`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-315** `capture` — 云端；计划 **V2-1**；来源 [cloud/commands.js:46](../../cloud/commands.js#L46)。
  - 原实现：`function capture(record,value){ record.state=value.state;record.cloudCommandId=value.cloudCommandId;record.updatedAt=Date.now(); if(record.path==='/api/control-commands'&&value.result?.kind==='http'){ try{const body=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(value.result.bodyBase64),c=>c.charCodeAt(0))));if(typeof body.commandId==='string')record.homeCommandId=body.commandId;}catch{} } save();paint();return value`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-316** `匿名回调@49` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:49](../../cloud/commands.js#L49)。
  - 原实现：`c=>c.charCodeAt(0)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-317** `query` — 云端；计划 **V2-1**；来源 [cloud/commands.js:53](../../cloud/commands.js#L53)。
  - 原实现：`async function query(record){ const url=record.cloudCommandId?'/console/commands/'+record.cloudCommandId:'/console/commands/request/'+record.requestId; const response=await network(url);if(response.status===404)return null; if(response.status===401)throw new Error('请重新登录');if(!response.ok)throw new Error('命令状态暂不可用'); return capture(record,await response.json()); }`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-318** `finalResponse` — 云端；计划 **V2-1**；来源 [cloud/commands.js:59](../../cloud/commands.js#L59)。
  - 原实现：`function finalResponse(value){ if(value?.state==='completed'&&value.result?.kind==='http'){ const r=value.result,bytes=Uint8Array.from(atob(r.bodyBase64),c=>c.charCodeAt(0)); return new Response([204,205,304].includes(r.httpStatus)?null:bytes,{status:r.httpStatus,headers:{'Content-Type':r.contentType}}); } throw new Error(labels[value?.state]¦¦'尚未得到家里回执；请看云端命令面板，不要重复提交'); }`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-319** `匿名回调@61` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:61](../../cloud/commands.js#L61)。
  - 原实现：`c=>c.charCodeAt(0)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-320** `dispatch` — 云端；计划 **V2-1**；来源 [cloud/commands.js:66](../../cloud/commands.js#L66)。
  - 原实现：`async function dispatch(path,payload){ if(!allowedPath(path))throw new Error('此操作尚未开放云端执行'); if(path==='/api/controls/cloud-cleanup/preview'){records=records.filter(r=>r.path!==path¦¦pending.has(r.state));save();} const comparable={...payload};if(path==='/api/control-commands')delete comparable.clientRequestId; const fingerprint=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(path+'\n'+J`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-321** `匿名回调@68` — 云端；计划 **V2-1**；来源 [cloud/commands.js:68](../../cloud/commands.js#L68)。
  - 原实现：`r=>r.path!==path¦¦pending.has(r.state)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-322** `匿名回调@70` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:70](../../cloud/commands.js#L70)。
  - 原实现：`v=>v.toString(16).padStart(2,'0')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-323** `匿名回调@72` — 云端；计划 **V2-1**；来源 [cloud/commands.js:72](../../cloud/commands.js#L72)。
  - 原实现：`async()=>{ let record=records.find(r=>r.fingerprint===fingerprint),value; if(!record){ if(!health.executorAvailable¦¦!health.homeReady¦¦health.commandBlocker¦¦unfinished())throw new Error('家里未就绪，或有待对账命令；尚未提交'); record={path,fingerprint,requestId:crypto.randomUUID(),state:'submitting',updatedAt:Date.now()};records.push(record);save();paint(); const body={...payload};if(path==='/api/control-commands')body.clientRequestId=record.`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-324** `匿名回调@73` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:73](../../cloud/commands.js#L73)。
  - 原实现：`r=>r.fingerprint===fingerprint`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-325** `匿名回调@97` — 云端；计划 **V2-1**；来源 [cloud/commands.js:97](../../cloud/commands.js#L97)。
  - 原实现：`(url,init={})=>{ if((init.method¦¦'GET').toUpperCase()!=='POST')throw new Error('仅支持已声明的 POST 命令'); const path=new URL(url,location.origin).pathname;return dispatch(path,init.body?JSON.parse(init.body):{}); }`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-326** `匿名回调@101` — 云端；计划 **V2-1**；来源 [cloud/commands.js:101](../../cloud/commands.js#L101)。
  - 原实现：`async(url,body)=>{const r=await dispatch(new URL(url,location.origin).pathname,body);const result=await r.json();if(!r.ok)throw new Error(result.detail¦¦'家里拒绝该操作');return result;}`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-327** `paint` — 云端；计划 **V2-1**；来源 [cloud/commands.js:102](../../cloud/commands.js#L102)。
  - 原实现：`function paint(){ if(!list)return;list.replaceChildren(); for(const record of [...records].reverse().concat(remoteRecords).slice(0,50)){ const item=document.createElement('li'),text=document.createElement('span'); text.textContent=record.path+' · '+(labels[record.state]¦¦record.state)+' · '+(record.cloudCommandId¦¦record.requestId);item.append(text); if(['submitting','queued','leased'].includes(record.state)){ const button=doc`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-328** `匿名回调@108` — 云端；计划 **V2-1**；来源 [cloud/commands.js:108](../../cloud/commands.js#L108)。
  - 原实现：`async()=>{button.disabled=true;try{await postControl(record.remote?'/console/commands/'+record.cloudCommandId+'/cancel':'/console/commands/request/'+record.requestId+'/cancel');record.state='cancelled';save();paint();}catch(error){alert(error.message);}}`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-329** `匿名回调@111` — 云端；计划 **V2-1**；来源 [cloud/commands.js:111](../../cloud/commands.js#L111)。
  - 原实现：`async()=>{ const note=prompt('先在家里核实原请求已停止及业务实际结果，再填写对账依据（至少10字）。此操作不会重试原命令。');if(!note)return; if(prompt('输入 CONFIRMED_HOME_REQUEST_STOPPED 确认原请求已停止')!=='CONFIRMED_HOME_REQUEST_STOPPED')return; try{capture(record,await postControl('/console/commands/'+record.cloudCommandId+'/resolve',{note,confirmation:'CONFIRMED_HOME_REQUEST_STOPPED'}));}catch(error){alert(error.message);} }`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-330** `匿名回调@118` — 云端；计划 **V2-1**；来源 [cloud/commands.js:118](../../cloud/commands.js#L118)。
  - 原实现：`()=>{if(!confirm('结束本次回执后，相同输入的下一次点击将创建新命令。确认？'))return;records=records.filter(r=>r!==record);save();paint();}`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-331** `匿名回调@118` — 云端；计划 **V2-1**；来源 [cloud/commands.js:118](../../cloud/commands.js#L118)。
  - 原实现：`r=>r!==record`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-332** `匿名回调@124` — 云端；计划 **V2-1**；来源 [cloud/commands.js:124](../../cloud/commands.js#L124)。
  - 原实现：`()=>{ document.addEventListener('click',event=>{const button=event.target.closest('button[data-cloud-control]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();if(!button.disabled&&window.opsCloudCanWrite(button)){if(button.dataset.cloudControl==='replenish-open')openReplenishment(button.dataset.taskId);else void controlTask(button,button.dataset.cloudControl);}},true); panel=document.createElement('d`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-333** `匿名回调@125` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:125](../../cloud/commands.js#L125)。
  - 原实现：`event=>{const button=event.target.closest('button[data-cloud-control]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();if(!button.disabled&&window.opsCloudCanWrite(button)){if(button.dataset.cloudControl==='replenish-open')openReplenishment(button.dataset.taskId);else void controlTask(button,button.dataset.cloudControl);}}`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-334** `匿名回调@128` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:128](../../cloud/commands.js#L128)。
  - 原实现：`async event=>{event.preventDefault();try{await postControl('/console/submission-requests/'+encodeURIComponent(input.value.trim())+'/cancel');alert('发送前撤销已记录；晚到收件也会被拒绝。请让递交器重新查询。');}catch(error){alert(error.message);}}`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-335** `poll` — 云端；计划 **V2-1**；来源 [cloud/commands.js:131](../../cloud/commands.js#L131)。
  - 原实现：`async function poll(){if(polling)return;polling=true;try{ const response=await network('/console/status',{headers:{'X-Ops-Page-Visible':String(document.visibilityState==='visible')}}); if(response.ok)health=await response.json();else health={}; for(const record of records.filter(r=>pending.has(r.state)))await query(record); const all=await network('/console/commands');if(all.ok){const body=await all.json();remoteRecords=(body.`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-336** `匿名回调@134` — 云端；计划 **V2-1**；来源 [cloud/commands.js:134](../../cloud/commands.js#L134)。
  - 原实现：`r=>pending.has(r.state)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-337** `匿名回调@135` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:135](../../cloud/commands.js#L135)。
  - 原实现：`r=>!records.some(local=>local.cloudCommandId===r.cloudCommandId)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-338** `匿名回调@135` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:135](../../cloud/commands.js#L135)。
  - 原实现：`local=>local.cloudCommandId===r.cloudCommandId`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-339** `匿名回调@135` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:135](../../cloud/commands.js#L135)。
  - 原实现：`r=>({...r,path:r.target,remote:true})`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **FN-340** `匿名回调@3` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:3](../../cloud/cleanup.js#L3)。
  - 原实现：`() => { const endpoint='/api/controls/cloud-cleanup/',previews=new Map(); const kinds={Draft:'drafts',Audio:'audio',Production:'production'}; const spec={drafts:{prefix:'draft',selection:'selectedDraftIds',confirm:'RECYCLE_SELECTED_CAPCUT_DRAFTS'},audio:{prefix:'audio',selection:'selectedAudioIds',confirm:'RECYCLE_SELECTED_AUDIO_FILES'},production:{prefix:'production',selection:'selectedProductionIds',confirm:'RECYCLE_SELECTED`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-341** `send` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:7](../../cloud/cleanup.js#L7)。
  - 原实现：`async function send(action,payload){const r=await window.opsCloudDispatch(endpoint+action,payload),body=await r.json();if(!r.ok)throw new Error(body.detail¦¦'家里拒绝清理');return body;}`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-342** `capability` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:8](../../cloud/cleanup.js#L8)。
  - 原实现：`async function capability(){try{await fetch(endpoint+'capabilities');}catch{}}`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-343** `show` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:9](../../cloud/cleanup.js#L9)。
  - 原实现：`function show(kind,message){const node=document.getElementById(spec[kind]?.prefix+'CleanupPreview')¦¦document.getElementById('pendingDeleteStatus');if(node){node.classList.remove('hidden');node.textContent=message;}}`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-344** `preview` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:10](../../cloud/cleanup.js#L10)。
  - 原实现：`async function preview(kind){ previews.delete(kind);const item=spec[kind],ids=kind==='pending'?[]:[...state[item.selection]]; if(kind!=='pending'&&!ids.length)throw new Error('请先勾选对象'); const includeUnknown=kind==='drafts'&&confirm('本次选择是否包含人工或来源不明草稿？选“取消”将保护这类草稿。'); const value=await send('preview',{kind,ids,includeUnknown}); if(value.kind!==kind¦¦!Array.isArray(value.ids)¦¦JSON.stringify(value.ids)!==JSON.stringify(ids)¦¦typ`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-345** `匿名回调@19` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:19](../../cloud/cleanup.js#L19)。
  - 原实现：`k=>kinds[k]===kind`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-346** `匿名回调@22` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:22](../../cloud/cleanup.js#L22)。
  - 原实现：`x=>x.name+'：'+x.reason`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-347** `execute` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:25](../../cloud/cleanup.js#L25)。
  - 原实现：`async function execute(kind){ const item=spec[kind],p=kind==='pending'?await preview(kind):previews.get(kind); if(!p¦¦performance.now()-p.received>=120000)throw new Error('预览已过期或页面已重载，请重新预览'); if(kind!=='pending'&&JSON.stringify([...state[item.selection]])!==JSON.stringify(p.ids))throw new Error('选择已变化，请重新预览'); if(p.containsManualOrUnknown&&!confirm('包含人工或来源不明草稿，请再次确认所选对象。'))return; if(p.containsTestFiles&&!confirm('包含测试文件，请再次`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-348** `匿名回调@43` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:43](../../cloud/cleanup.js#L43)。
  - 原实现：`event=>{ const button=event.target.closest('button');if(!button)return; const match=/^(preview¦confirm)(Draft¦Audio¦Production)CleanupButton$/.exec(button.id),pending=button.id==='emptyPendingDeleteButton'; if(!match&&!pending){if(/(Draft¦Audio¦Production)ManagerButton$/.test(button.id))void capability();return;} event.preventDefault();event.stopImmediatePropagation();if(button.disabled¦¦!window.opsCloudCanWrite(button))return`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-349** `匿名回调@49` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:49](../../cloud/cleanup.js#L49)。
  - 原实现：`error=>show(kind,error.message)`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-350** `匿名回调@49` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:49](../../cloud/cleanup.js#L49)。
  - 原实现：`()=>{button.disabled=false;window.dispatchEvent(new Event('ops-cloud-write-state'));}`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-351** `匿名回调@52` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:52](../../cloud/cleanup.js#L52)。
  - 原实现：`()=>{const button=document.createElement('button');button.type='button';button.textContent='检查清理通道';button.id='checkCleanupCapabilityButton';button.addEventListener('click',()=>void capability());document.getElementById('pendingDeleteStatus')?.after(button);setInterval(()=>{if(document.querySelector('#draftManagerDialog[open],#audioManagerDialog[open],#productionManagerDialog[open]'))void capability();},30000);}`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-352** `匿名回调@52` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:52](../../cloud/cleanup.js#L52)。
  - 原实现：`()=>void capability()`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-353** `匿名回调@52` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:52](../../cloud/cleanup.js#L52)。
  - 原实现：`()=>{if(document.querySelector('#draftManagerDialog[open],#audioManagerDialog[open],#productionManagerDialog[open]'))void capability();}`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **FN-354** `匿名回调@2` — 云端；计划 **V2-1**；来源 [cloud/backups.js:2](../../cloud/backups.js#L2)。
  - 原实现：`() => { const api = async (path, method = 'GET') => { const headers = {}; if (method !== 'GET') { const session = await fetch('/auth/session').then(r => r.json()); headers['X-CSRF-Token'] = session.csrf; } const response = await fetch(path, {method, headers}); if (!response.ok) throw new Error(ˋ请求失败 (${response.status})ˋ); return response.json(); }; const element = (tag, text) => { const node = document.createElement(tag); if `；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/console-admin.ts:11（账号CSRF及原方法/状态码；读取目录仍用GET）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-355** `api` — 云端；计划 **V2-1**；来源 [cloud/backups.js:3](../../cloud/backups.js#L3)。
  - 原实现：`async (path, method = 'GET') => { const headers = {}; if (method !== 'GET') { const session = await fetch('/auth/session').then(r => r.json()); headers['X-CSRF-Token'] = session.csrf; } const response = await fetch(path, {method, headers}); if (!response.ok) throw new Error(ˋ请求失败 (${response.status})ˋ); return response.json(); }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/console-admin.ts:11（账号CSRF及原方法/状态码；读取目录仍用GET）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-356** `匿名回调@6` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:6](../../cloud/backups.js#L6)。
  - 原实现：`r => r.json()`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/console-admin.ts:11（账号CSRF及原方法/状态码；读取目录仍用GET）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-357** `element` — 云端；计划 **V2-1**；来源 [cloud/backups.js:13](../../cloud/backups.js#L13)。
  - 原实现：`(tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:215（目录、加密下载链接、容量、日期/阶段、事件及空状态）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-358** `show` — 云端；计划 **V2-1**；来源 [cloud/backups.js:18](../../cloud/backups.js#L18)。
  - 原实现：`async (body, message) => { try { const result = await api('/console/backups'); body.replaceChildren(); body.append(element('p', ˋ仅台账和配置恢复；视频、草稿不在备份中。已用及预留 ${(result.usedReservedBytes / 1048576).toFixed(1)} MiB / ${(result.quotaBytes / 1e9).toFixed(0)} GB。ˋ)); const phase = result.agentState?.phase ¦¦ 'waiting_configuration'; const phases = {waiting_configuration: '等待本机配置恢复密钥', creating: '正在生成', uploading: '正在上传', completed: '最`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:215（目录、加密下载链接、容量、日期/阶段、事件及空状态）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-359** `匿名回调@32` — 云端；计划 **V2-1**；来源 [cloud/backups.js:32](../../cloud/backups.js#L32)。
  - 原实现：`p => p.name`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:215（目录、加密下载链接、容量、日期/阶段、事件及空状态）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-360** `匿名回调@39` — 云端；计划 **V2-1**；来源 [cloud/backups.js:39](../../cloud/backups.js#L39)。
  - 原实现：`async () => { verify.disabled = true; try { const checked = await api(ˋ/console/backups/${item.packageId}/verifyˋ, 'POST'); message.textContent = checked.verified ? ˋ校验通过：${item.packageId}ˋ : ˋ校验失败：${item.packageId}ˋ; } catch (error) { message.textContent = error.message; } finally { verify.disabled = false; } }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（逐包校验与失败提示、防重复）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-361** `匿名回调@47` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:47](../../cloud/backups.js#L47)。
  - 原实现：`e => ˋ${new Date(e.at * 1000).toLocaleString()} ${e.code}ˋ`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（逐包校验与失败提示、防重复）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-362** `匿名回调@50` — 云端；计划 **V2-1**；来源 [cloud/backups.js:50](../../cloud/backups.js#L50)。
  - 原实现：`() => { const panel = element('details'); panel.id = 'cloudBackupPanel'; panel.style.cssText = 'margin:16px;padding:12px;border:1px solid #888;border-radius:8px;overflow-wrap:anywhere'; panel.append(element('summary', '异地备份（台账与配置）')); const refresh = element('button', '刷新列表'), request = element('button', '请求一次备份'); refresh.type = request.type = 'button'; const message = element('p'), body = element('div'); message.setAttribute`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-363** `匿名回调@57` — 云端；计划 **V2-1**；来源 [cloud/backups.js:57](../../cloud/backups.js#L57)。
  - 原实现：`() => show(body, message)`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-364** `匿名回调@58` — 云端；计划 **V2-1**；来源 [cloud/backups.js:58](../../cloud/backups.js#L58)。
  - 原实现：`async () => { request.disabled = true; try { await api('/console/backups/request', 'POST'); message.textContent = '请求已排队；代理配置就绪后执行。稍后刷新列表查看。'; } catch (error) { message.textContent = error.message; } finally { request.disabled = false; } }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **FN-365** `匿名回调@65` — 云端；计划 **V2-1**；来源 [cloud/backups.js:65](../../cloud/backups.js#L65)。
  - 原实现：`() => { if (panel.open) show(body, message); }`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [ ] **FN-366** `匿名回调@3` — 云端；计划 **V2-4**；来源 [cloud/login.js:3](../../cloud/login.js#L3)。
  - 原实现：`response => response.json()`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **FN-367** `匿名回调@3` — 云端；计划 **V2-4**；来源 [cloud/login.js:3](../../cloud/login.js#L3)。
  - 原实现：`data => { document.getElementById('registration').hidden = !data.registrationOpen; }`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **FN-368** `匿名回调@5` — 云端；计划 **V2-4**；来源 [cloud/login.js:5](../../cloud/login.js#L5)。
  - 原实现：`async event => { event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button'); button.disabled = true; try { const response = await fetch(route, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))}); if (!response.ok) { message.textContent = '未成功，请核对填写内容或稍后重试。'; return; } if (route === '/auth/login') location.assig`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。

## interfaces（52 项）

- [x] **NET-001** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:141](../../static/app.js#L141)。
  - 原实现：`getJson("/api/safety")`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **NET-002** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:250](../../static/app.js#L250)。
  - 原实现：`getJson("/api/controls/capcut-drafts", 1, 60000)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-003** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:394](../../static/app.js#L394)。
  - 原实现：`getJson("/api/controls/audio-files", 1, 60000)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-004** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:586](../../static/app.js#L586)。
  - 原实现：`getJson("/api/controls/production-files", 1, 60000)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-005** `fetch` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1095](../../static/app.js#L1095)。
  - 原实现：`fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: controller.signal, })`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/home-cleanup.ts:105（原JSON正文、独立超时与错误提示；云端使用队列写入器）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-006** `postJson` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1137](../../static/app.js#L1137)。
  - 原实现：`postJson(ˋ/api/controls/tasks/${encodeURIComponent(taskId)}/replenishˋ, { urls: $("replenishUrls").value, startNow: $("replenishStartNow").checked, })`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **NET-007** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1520](../../static/app.js#L1520)。
  - 原实现：`getJson(target)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-008** `fetch` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1589](../../static/app.js#L1589)。
  - 原实现：`fetch(ˋ/api/controls/tasks/${encodeURIComponent(taskId)}/${action}ˋ, { method: "POST" })`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **NET-009** `fetch` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1620](../../static/app.js#L1620)。
  - 原实现：`fetch(url, { cache: "no-cache", headers, signal: controller.signal })`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **NET-010** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1647](../../static/app.js#L1647)。
  - 原实现：`getJson(url, 2)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **NET-011** `getJson` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1693](../../static/app.js#L1693)。
  - 原实现：`getJson("/api/health", 0)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **NET-012** `postJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1763](../../static/app.js#L1763)。
  - 原实现：`postJson("/api/controls/capcut-drafts/preview", { draftIds }, { timeoutMs: 60000 })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-013** `postJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1793](../../static/app.js#L1793)。
  - 原实现：`postJson("/api/controls/capcut-drafts/cleanup", { draftIds, snapshotToken: preview.snapshotToken, includeUnknown: Boolean(preview.containsManualOrUnknown), confirm: "RECYCLE_SELECTED_CAPCUT_DRAFTS", })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-014** `postJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1852](../../static/app.js#L1852)。
  - 原实现：`postJson("/api/controls/audio-files/preview", { audioIds }, { timeoutMs: 60000 })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-015** `postJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1885](../../static/app.js#L1885)。
  - 原实现：`postJson("/api/controls/audio-files/recycle", { audioIds, snapshotToken: preview.snapshotToken, confirm: "RECYCLE_SELECTED_AUDIO_FILES", })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-016** `postJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1948](../../static/app.js#L1948)。
  - 原实现：`postJson("/api/controls/production-files/preview", { fileIds }, { timeoutMs: 60000 })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-017** `postJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1992](../../static/app.js#L1992)。
  - 原实现：`postJson("/api/controls/production-files/recycle", { fileIds, snapshotToken: preview.snapshotToken, confirm: "RECYCLE_SELECTED_PRODUCTION_FILES", }, { timeoutMs: 15 * 60 * 1000 })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-018** `getJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2020](../../static/app.js#L2020)。
  - 原实现：`getJson("/api/controls/pending-delete")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-019** `postJson` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2042](../../static/app.js#L2042)。
  - 原实现：`postJson("/api/controls/pending-delete/empty", { confirm: "EMPTY_PENDING_DELETE_NOW" }, { timeoutMs: 600000 })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **NET-020** `postJson` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2068](../../static/app.js#L2068)。
  - 原实现：`postJson("/api/control-commands", payload)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-021** `postJson` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2089](../../static/app.js#L2089)。
  - 原实现：`postJson("/api/controls/upload/rescan", {})`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **NET-022** `postJson` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2113](../../static/app.js#L2113)。
  - 原实现：`postJson("/api/controls/upload/verify-history", {})`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **NET-023** `postJson` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2131](../../static/app.js#L2131)。
  - 原实现：`postJson("/api/controls/testing/reset", { confirm: "RESET_TEST_RECORDS" })`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-024** `postJson` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2159](../../static/app.js#L2159)。
  - 原实现：`postJson("/api/controls/tasks/create", { date: $("createDate").value.trim(), templateId: $("createTemplate").value, material: $("createMaterial").value, audioBatch: $("createAudioBatch").value.trim(), voicePlan: $("createVoicePlan").value, expectedCount: $("createExpectedCount").value, urls: $("createUrls").value, startNow: $("createStartNow").checked, })`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **NET-025** `original` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:38](../../cloud/readonly.js#L38)。
  - 原实现：`original(key,{headers:{'X-Ops-Page-Visible':'true'}})`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **NET-026** `original` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:50](../../cloud/readonly.js#L50)。
  - 原实现：`original(input, init)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **NET-027** `original` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:60](../../cloud/readonly.js#L60)。
  - 原实现：`original(input, init)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **NET-028** `original` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:106](../../cloud/readonly.js#L106)。
  - 原实现：`original('/auth/session')`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-029** `original` — 云端；计划 **V2-2F**；来源 [cloud/readonly.js:107](../../cloud/readonly.js#L107)。
  - 原实现：`original('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':info.csrf}})`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-030** `original` — 云端；计划 **V2-2F**；来源 [cloud/readonly.js:115](../../cloud/readonly.js#L115)。
  - 原实现：`original('/auth/password',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify(Object.fromEntries(new FormData(form)))})`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-031** `original` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:134](../../cloud/readonly.js#L134)。
  - 原实现：`original('/console/status',{headers:{'X-Ops-Page-Visible':String(document.visibilityState==='visible')}})`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-032** `network` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:41](../../cloud/commands.js#L41)。
  - 原实现：`network('/auth/session')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-033** `network` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:43](../../cloud/commands.js#L43)。
  - 原实现：`network(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf},body:JSON.stringify(body)})`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-034** `network` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:55](../../cloud/commands.js#L55)。
  - 原实现：`network(url)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-035** `network` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:80](../../cloud/commands.js#L80)。
  - 原实现：`network(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':info.csrf,'X-Client-Request-ID':record.requestId},body:JSON.stringify(body)})`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-036** `dispatch` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:99](../../cloud/commands.js#L99)。
  - 原实现：`dispatch(path,init.body?JSON.parse(init.body):{})`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-037** `dispatch` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:101](../../cloud/commands.js#L101)。
  - 原实现：`dispatch(new URL(url,location.origin).pathname,body)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-038** `postControl` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:108](../../cloud/commands.js#L108)。
  - 原实现：`postControl(record.remote?'/console/commands/'+record.cloudCommandId+'/cancel':'/console/commands/request/'+record.requestId+'/cancel')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-039** `postControl` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:114](../../cloud/commands.js#L114)。
  - 原实现：`postControl('/console/commands/'+record.cloudCommandId+'/resolve',{note,confirmation:'CONFIRMED_HOME_REQUEST_STOPPED'})`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-040** `postControl` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:128](../../cloud/commands.js#L128)。
  - 原实现：`postControl('/console/submission-requests/'+encodeURIComponent(input.value.trim())+'/cancel')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-041** `network` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:132](../../cloud/commands.js#L132)。
  - 原实现：`network('/console/status',{headers:{'X-Ops-Page-Visible':String(document.visibilityState==='visible')}})`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-042** `network` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:135](../../cloud/commands.js#L135)。
  - 原实现：`network('/console/commands')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **NET-043** `fetch` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:8](../../cloud/cleanup.js#L8)。
  - 原实现：`fetch(endpoint+'capabilities')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **NET-044** `send` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:14](../../cloud/cleanup.js#L14)。
  - 原实现：`send('preview',{kind,ids,includeUnknown})`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **NET-045** `send` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:36](../../cloud/cleanup.js#L36)。
  - 原实现：`send('execute',{kind,ids:p.ids,includeUnknown:p.includeUnknown,snapshotToken:p.snapshotToken,ticket:p.ticket,expiresAt:p.expiresAt,confirm:item.confirm})`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **NET-046** `fetch` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:6](../../cloud/backups.js#L6)。
  - 原实现：`fetch('/auth/session')`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/console-admin.ts:11（账号CSRF及原方法/状态码；读取目录仍用GET）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-047** `fetch` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:9](../../cloud/backups.js#L9)。
  - 原实现：`fetch(path, {method, headers})`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/console-admin.ts:11（账号CSRF及原方法/状态码；读取目录仍用GET）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-048** `api` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:20](../../cloud/backups.js#L20)。
  - 原实现：`api('/console/backups')`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:215（目录、加密下载链接、容量、日期/阶段、事件及空状态）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-049** `api` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:41](../../cloud/backups.js#L41)。
  - 原实现：`api(ˋ/console/backups/${item.packageId}/verifyˋ, 'POST')`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（逐包校验与失败提示、防重复）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **NET-050** `api` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:60](../../cloud/backups.js#L60)。
  - 原实现：`api('/console/backups/request', 'POST')`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [ ] **NET-051** `fetch` — 云端；计划 **V2-4**；来源 [cloud/login.js:3](../../cloud/login.js#L3)。
  - 原实现：`fetch('/auth/options')`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **NET-052** `fetch` — 云端；计划 **V2-4**；来源 [cloud/login.js:10](../../cloud/login.js#L10)。
  - 原实现：`fetch(route, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))})`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。

## confirmations（36 项）

- [x] **CONF-001** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1585](../../static/app.js#L1585)。
  - 原实现：`window.confirm(question)`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **CONF-002** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1787](../../static/app.js#L1787)。
  - 原实现：`window.confirm(ˋ确认将 ${preview.deletableCount} 个草稿移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除视频、音频、成片或生产任务。ˋ)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-003** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1788](../../static/app.js#L1788)。
  - 原实现：`window.confirm("选择中包含人工或来源不明草稿。再次确认仍要将这些草稿移入待删区。")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-004** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1864](../../static/app.js#L1864)。
  - 原实现：`window.alert(ˋ有 ${preview.blockedCount} 个音频被活动任务保护，已禁止删除。请查看页面中的具体原因。ˋ)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-005** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1870](../../static/app.js#L1870)。
  - 原实现：`window.alert(error.message ¦¦ "音频状态已变化，请重新对账")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-006** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1880](../../static/app.js#L1880)。
  - 原实现：`window.confirm(ˋ确认将 ${preview.deletableCount} 个音频文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除文件夹，也不会改变任务完成状态。ˋ)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-007** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1894](../../static/app.js#L1894)。
  - 原实现：`window.alert(result.message ¦¦ "音频已移入待删区")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-008** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1902](../../static/app.js#L1902)。
  - 原实现：`window.alert(message)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-009** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1967](../../static/app.js#L1967)。
  - 原实现：`window.alert(ˋ有 ${preview.blockedCount} 个文件被活动任务、云端核验或身份规则保护，已自动排除。ˋ)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-010** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1982](../../static/app.js#L1982)。
  - 原实现：`window.confirm(ˋ确认将 ${preview.deletableCount} 个生产文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；项目状态、上传记录及云端文件不会改变。ˋ)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-011** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1983](../../static/app.js#L1983)。
  - 原实现：`window.confirm("选择中包含 CapCut 测试或首帧测试文件。再次确认仍要将这些测试文件移入待删区。")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-012** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2001](../../static/app.js#L2001)。
  - 原实现：`window.alert(result.message ¦¦ "生产文件清理已完成")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-013** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2009](../../static/app.js#L2009)。
  - 原实现：`window.alert(message)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-014** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2038](../../static/app.js#L2038)。
  - 原实现：`window.confirm(ˋ确认立即永久清除待删区的 ${Number(info.count ¦¦ 0)} 项（约 ${formatBytes(info.sizeBytes)}）吗？清除后无法恢复。ˋ)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-015** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2039](../../static/app.js#L2039)。
  - 原实现：`window.confirm("再次确认：这一步会永久删除，不进入回收站。")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-016** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2043](../../static/app.js#L2043)。
  - 原实现：`window.alert(result.message ¦¦ "待删区已清空")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-017** `window.alert` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2045](../../static/app.js#L2045)。
  - 原实现：`window.alert(error.message ¦¦ "清空待删区失败")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **CONF-018** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2054](../../static/app.js#L2054)。
  - 原实现：`window.confirm("确认让家里工作台安全继续当前项目吗？它会先核对任务清单，不会删除素材或重做有效成片。")`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-019** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2085](../../static/app.js#L2085)。
  - 原实现：`window.confirm("确认重新对账正式清单，补传遗漏成片，并对云端已实时核验的任务继续安全清理吗？不会重新剪辑等待中的任务，也不会清理配音、公共素材、Logo或公共样品。")`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **CONF-020** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2109](../../static/app.js#L2109)。
  - 原实现：`window.confirm("确认核验历史百度云文件吗？系统只会查询云端文件是否存在，并核对云端路径和文件大小；不会补传、不会删除本地或云端文件，也不会改变项目完成状态。")`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **CONF-021** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2126](../../static/app.js#L2126)。
  - 原实现：`window.confirm("确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。")`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **CONF-022** `window.confirm` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2127](../../static/app.js#L2127)。
  - 原实现：`window.confirm("再次确认：Dashboard、工作台、接收器和 CapCut 的任务进度将从空状态重新开始。")`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **CONF-023** `alert` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:115](../../cloud/readonly.js#L115)。
  - 原实现：`alert('未修改，请核对密码后重试')`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **CONF-024** `alert` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:108](../../cloud/commands.js#L108)。
  - 原实现：`alert(error.message)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-025** `prompt` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:112](../../cloud/commands.js#L112)。
  - 原实现：`prompt('先在家里核实原请求已停止及业务实际结果，再填写对账依据（至少10字）。此操作不会重试原命令。')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-026** `prompt` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:113](../../cloud/commands.js#L113)。
  - 原实现：`prompt('输入 CONFIRMED_HOME_REQUEST_STOPPED 确认原请求已停止')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-027** `alert` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:114](../../cloud/commands.js#L114)。
  - 原实现：`alert(error.message)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-028** `confirm` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:118](../../cloud/commands.js#L118)。
  - 原实现：`confirm('结束本次回执后，相同输入的下一次点击将创建新命令。确认？')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-029** `alert` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:128](../../cloud/commands.js#L128)。
  - 原实现：`alert('发送前撤销已记录；晚到收件也会被拒绝。请让递交器重新查询。')`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-030** `alert` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:128](../../cloud/commands.js#L128)。
  - 原实现：`alert(error.message)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **CONF-031** `confirm` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:13](../../cloud/cleanup.js#L13)。
  - 原实现：`confirm('本次选择是否包含人工或来源不明草稿？选“取消”将保护这类草稿。')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **CONF-032** `confirm` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:29](../../cloud/cleanup.js#L29)。
  - 原实现：`confirm('包含人工或来源不明草稿，请再次确认所选对象。')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **CONF-033** `confirm` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:30](../../cloud/cleanup.js#L30)。
  - 原实现：`confirm('包含测试文件，请再次确认所选对象。')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **CONF-034** `confirm` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:32](../../cloud/cleanup.js#L32)。
  - 原实现：`confirm(question)`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **CONF-035** `prompt` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:33](../../cloud/cleanup.js#L33)。
  - 原实现：`prompt('请输入 '+item.confirm+' 确认本次操作')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **CONF-036** `prompt` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:34](../../cloud/cleanup.js#L34)。
  - 原实现：`prompt('再次输入 EMPTY_PENDING_DELETE_NOW 确认永久清除')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。

## guards（167 项）

- [x] **GUARD-001** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:96](../../static/app.js#L96)。
  - 原实现：`value.counts?.audit_pending ¦¦ 0`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-002** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:97](../../static/app.js#L97)。
  - 原实现：`value.counts?.audit_pending ¦¦ 0`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-003** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:121](../../static/app.js#L121)。
  - 原实现：`value.activeRecords ¦¦ 0`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-004** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:198](../../static/app.js#L198)。
  - 原实现：`state.draftPreview = null`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-005** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:247](../../static/app.js#L247)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-006** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:248](../../static/app.js#L248)。
  - 原实现：`refreshButton.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-007** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:252](../../static/app.js#L252)。
  - 原实现：`state.draftSnapshot = payload.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-008** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:252](../../static/app.js#L252)。
  - 原实现：`payload.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-009** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:267](../../static/app.js#L267)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-010** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:268](../../static/app.js#L268)。
  - 原实现：`refreshButton.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-011** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:309](../../static/app.js#L309)。
  - 原实现：`taskState === "deletable" && item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-012** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:310](../../static/app.js#L310)。
  - 原实现：`taskState === "protected" && !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-013** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:318](../../static/app.js#L318)。
  - 原实现：`state.audioPreview = null`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-014** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:380](../../static/app.js#L380)。
  - 原实现：`!item?.protected ¦¦ event.target.matches("input:not(:disabled)")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-015** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:391](../../static/app.js#L391)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-016** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:392](../../static/app.js#L392)。
  - 原实现：`refreshButton.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-017** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:396](../../static/app.js#L396)。
  - 原实现：`state.audioSnapshot = payload.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-018** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:396](../../static/app.js#L396)。
  - 原实现：`payload.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-019** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:415](../../static/app.js#L415)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-020** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:416](../../static/app.js#L416)。
  - 原实现：`refreshButton.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-021** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:495](../../static/app.js#L495)。
  - 原实现：`taskState === "deletable" && item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-022** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:496](../../static/app.js#L496)。
  - 原实现：`taskState === "protected" && !item.protected`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-023** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:507](../../static/app.js#L507)。
  - 原实现：`state.productionPreview = null`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-024** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:572](../../static/app.js#L572)。
  - 原实现：`!item?.protected ¦¦ event.target.matches("input:not(:disabled)")`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-025** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:583](../../static/app.js#L583)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-026** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:584](../../static/app.js#L584)。
  - 原实现：`refreshButton.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-027** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:589](../../static/app.js#L589)。
  - 原实现：`state.productionSnapshot = payload.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-028** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:589](../../static/app.js#L589)。
  - 原实现：`payload.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-029** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:614](../../static/app.js#L614)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-030** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:615](../../static/app.js#L615)。
  - 原实现：`refreshButton.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-031** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:879](../../static/app.js#L879)。
  - 原实现：`activeStage`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-032** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:881](../../static/app.js#L881)。
  - 原实现：`activeStage.current ¦¦ ˋ${activeStage.program}正在运行ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-033** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1000](../../static/app.js#L1000)。
  - 原实现：`!active.length`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-034** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1010](../../static/app.js#L1010)。
  - 原实现：`active.length === 1`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-035** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1135](../../static/app.js#L1135)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **GUARD-036** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1155](../../static/app.js#L1155)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **GUARD-037** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1172](../../static/app.js#L1172)。
  - 原实现：`String(item.status ¦¦ "") === "pending_confirmation" ¦¦ Date.now() - Date.parse(item.importedAt ¦¦ item.createdAt ¦¦ "") < recentMs`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-038** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1179](../../static/app.js#L1179)。
  - 原实现：`status === "pending_confirmation" && !["auto_start_first", "auto_start_sequential"].includes(String(item.startMode ¦¦ ""))`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-039** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1180](../../static/app.js#L1180)。
  - 原实现：`status === "pending_confirmation" ¦¦ status === "imported_waiting_start"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-040** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1443](../../static/app.js#L1443)。
  - 原实现：`state.continueInFlight = commandInFlight`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-041** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1482](../../static/app.js#L1482)。
  - 原实现：`result.allowed !== false`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-042** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1487](../../static/app.js#L1487)。
  - 原实现：`!commandInFlight && Boolean(state.runtime?.busy)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-043** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1488](../../static/app.js#L1488)。
  - 原实现：`allowed && !runtimeBusy && (result.continueCanRetry === true ¦¦ !commandInFlight)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-044** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1488](../../static/app.js#L1488)。
  - 原实现：`allowed && !runtimeBusy`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-045** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1489](../../static/app.js#L1489)。
  - 原实现：`button.dataset.allowed = clickable ? "true" : "false"`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-046** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1491](../../static/app.js#L1491)。
  - 原实现：`button.disabled = !clickable`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-047** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1515](../../static/app.js#L1515)。
  - 原实现：`state.continueStatusBusy`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-048** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1516](../../static/app.js#L1516)。
  - 原实现：`state.continueStatusBusy = true`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-049** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1534](../../static/app.js#L1534)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-050** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1535](../../static/app.js#L1535)。
  - 原实现：`button.dataset.allowed = "false"`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-051** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1545](../../static/app.js#L1545)。
  - 原实现：`state.continueStatusBusy = false`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-052** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1572](../../static/app.js#L1572)。
  - 原实现：`button.disabled = running`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:259（原结果/历史核验状态与计数；UploadActions独立反馈）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-053** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1586](../../static/app.js#L1586)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **GUARD-054** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1604](../../static/app.js#L1604)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **GUARD-055** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1639](../../static/app.js#L1639)。
  - 原实现：`state.refreshBusy`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-056** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1640](../../static/app.js#L1640)。
  - 原实现：`state.refreshBusy = true`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-057** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1710](../../static/app.js#L1710)。
  - 原实现：`state.refreshBusy = false`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期/任务箱/项目筛选回调保持原选择语义）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-058** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1757](../../static/app.js#L1757)。
  - 原实现：`$("draftCleanupPreview").innerHTML = "<strong>尚未选择草稿</strong>请先勾选要移入待删区的草稿。"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-059** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1760](../../static/app.js#L1760)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-060** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1764](../../static/app.js#L1764)。
  - 原实现：`state.draftPreview = preview`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-061** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1765](../../static/app.js#L1765)。
  - 原实现：`state.draftSnapshot = preview.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-062** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1765](../../static/app.js#L1765)。
  - 原实现：`preview.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-063** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1770](../../static/app.js#L1770)。
  - 原实现：`$("draftCleanupPreview").innerHTML = ˋ<strong>${escapeHtml(preview.message)}</strong> 可删除空间约 ${escapeHtml(formatBytes(preview.sizeBytes))}。 ${blocked ? ˋ<ul>${blocked}</ul>ˋ : ""}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-064** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1777](../../static/app.js#L1777)。
  - 原实现：`$("draftCleanupPreview").innerHTML = ˋ<strong>删除预览失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-065** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1779](../../static/app.js#L1779)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-066** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1789](../../static/app.js#L1789)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-067** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1808](../../static/app.js#L1808)。
  - 原实现：`$("draftCleanupPreview").innerHTML = ˋ<strong>草稿清理失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-068** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1810](../../static/app.js#L1810)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-069** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1846](../../static/app.js#L1846)。
  - 原实现：`$("audioCleanupPreview").innerHTML = "<strong>尚未选择音频</strong>请先勾选要移入待删区的音频文件。"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-070** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1849](../../static/app.js#L1849)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-071** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1853](../../static/app.js#L1853)。
  - 原实现：`state.audioPreview = preview`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-072** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1854](../../static/app.js#L1854)。
  - 原实现：`state.audioSnapshot = preview.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-073** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1854](../../static/app.js#L1854)。
  - 原实现：`preview.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-074** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1859](../../static/app.js#L1859)。
  - 原实现：`$("audioCleanupPreview").innerHTML = ˋ<strong>${escapeHtml(preview.message)}</strong> 可删除空间约 ${escapeHtml(formatBytes(preview.sizeBytes))}。 ${blocked ? ˋ<ul>${blocked}</ul>ˋ : ""}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-075** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1869](../../static/app.js#L1869)。
  - 原实现：`$("audioCleanupPreview").innerHTML = ˋ<strong>音频删除预览失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-076** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1872](../../static/app.js#L1872)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-077** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1881](../../static/app.js#L1881)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-078** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1901](../../static/app.js#L1901)。
  - 原实现：`$("audioCleanupPreview").innerHTML = ˋ<strong>音频清理已停止</strong>${escapeHtml(message)}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-079** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1904](../../static/app.js#L1904)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-080** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1942](../../static/app.js#L1942)。
  - 原实现：`$("productionCleanupPreview").innerHTML = "<strong>尚未选择生产文件</strong>请先勾选要移入待删区的文件。"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-081** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1945](../../static/app.js#L1945)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-082** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1949](../../static/app.js#L1949)。
  - 原实现：`state.productionPreview = preview`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-083** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1950](../../static/app.js#L1950)。
  - 原实现：`state.productionSnapshot = preview.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-084** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1950](../../static/app.js#L1950)。
  - 原实现：`preview.snapshotToken ¦¦ ""`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-085** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1961](../../static/app.js#L1961)。
  - 原实现：`$("productionCleanupPreview").innerHTML = ˋ<strong>${escapeHtml(preview.message)}</strong> 预计释放 ${escapeHtml(formatBytes(preview.sizeBytes))}。 ${categories ? ˋ<ul>${categories}</ul>ˋ : ""} ${blocked ? ˋ<p>以下文件不会删除：</p><ul>${blocked}</ul>${blockedMore}ˋ : ""}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-086** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1972](../../static/app.js#L1972)。
  - 原实现：`$("productionCleanupPreview").innerHTML = ˋ<strong>生产文件清理预览失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-087** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1974](../../static/app.js#L1974)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-088** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1984](../../static/app.js#L1984)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-089** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2008](../../static/app.js#L2008)。
  - 原实现：`$("productionCleanupPreview").innerHTML = ˋ<strong>生产文件清理已停止</strong>${escapeHtml(message)}ˋ`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-090** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2011](../../static/app.js#L2011)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-091** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2021](../../static/app.js#L2021)。
  - 原实现：`state.pendingDelete = result`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-092** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2037](../../static/app.js#L2037)。
  - 原实现：`state.pendingDelete ¦¦ {}`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-093** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2040](../../static/app.js#L2040)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-094** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2047](../../static/app.js#L2047)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **GUARD-095** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2053](../../static/app.js#L2053)。
  - 原实现：`button.dataset.allowed === "false"`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-096** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2053](../../static/app.js#L2053)。
  - 原实现：`button.dataset.allowed === "false"`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-097** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2055](../../static/app.js#L2055)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-098** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2086](../../static/app.js#L2086)。
  - 原实现：`button.disabled = true`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **GUARD-099** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2103](../../static/app.js#L2103)。
  - 原实现：`button.disabled = false`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **GUARD-100** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2110](../../static/app.js#L2110)。
  - 原实现：`button.disabled = true`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **GUARD-101** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2128](../../static/app.js#L2128)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-102** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2147](../../static/app.js#L2147)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-103** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2157](../../static/app.js#L2157)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **GUARD-104** `状态/防重复约束` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2184](../../static/app.js#L2184)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **GUARD-105** `条件门禁` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:2193](../../static/app.js#L2193)。
  - 原实现：`state.continueInFlight`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-106** `条件门禁` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:41](../../cloud/readonly.js#L41)。
  - 原实现：`!state.refreshBusy&&typeof refresh==='function'`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-107** `状态/防重复约束` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:41](../../cloud/readonly.js#L41)。
  - 原实现：`!state.refreshBusy&&typeof refresh==='function'`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **GUARD-108** `状态/防重复约束` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:99](../../cloud/readonly.js#L99)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（初始未知状态禁止写入）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-109** `状态/防重复约束` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:115](../../cloud/readonly.js#L115)。
  - 原实现：`submit.disabled=true`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-110** `状态/防重复约束` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:115](../../cloud/readonly.js#L115)。
  - 原实现：`submit.disabled=false`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-111** `条件门禁` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:126](../../cloud/readonly.js#L126)。
  - 原实现：`!allowed`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-112** `条件门禁` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:126](../../cloud/readonly.js#L126)。
  - 原实现：`!button.disabled`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-113** `状态/防重复约束` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:126](../../cloud/readonly.js#L126)。
  - 原实现：`button.disabled=true`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-114** `状态/防重复约束` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:127](../../cloud/readonly.js#L127)。
  - 原实现：`button.disabled=false`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-115** `条件门禁` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:148](../../cloud/readonly.js#L148)。
  - 原实现：`typeof state!=='undefined'&&!state.refreshBusy&&typeof refresh==='function'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-116** `状态/防重复约束` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:148](../../cloud/readonly.js#L148)。
  - 原实现：`typeof state!=='undefined'&&!state.refreshBusy&&typeof refresh==='function'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-117** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:9](../../cloud/commands.js#L9)。
  - 原实现：`r&&typeof r.requestId==='string'&&typeof r.fingerprint==='string'&&typeof r.path==='string'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-118** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:9](../../cloud/commands.js#L9)。
  - 原实现：`r&&typeof r.requestId==='string'&&typeof r.fingerprint==='string'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-119** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:9](../../cloud/commands.js#L9)。
  - 原实现：`typeof r.requestId==='string'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-120** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:9](../../cloud/commands.js#L9)。
  - 原实现：`typeof r.fingerprint==='string'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-121** `条件门禁` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:16](../../cloud/commands.js#L16)。
  - 原实现：`!health.executorAvailable¦¦!health.homeReady¦¦health.commandBlocker¦¦unfinished()¦¦active.size`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-122** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:18](../../cloud/commands.js#L18)。
  - 原实现：`button.dataset.allowed==='true'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-123** `条件门禁` — 云端；计划 **V2-1**；来源 [cloud/commands.js:25](../../cloud/commands.js#L25)。
  - 原实现：`record&&pending.has(record.state)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-124** `条件门禁` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:32](../../cloud/commands.js#L32)。
  - 原实现：`observedEligibility&&typeof result.allowed==='boolean'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-125** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:32](../../cloud/commands.js#L32)。
  - 原实现：`typeof result.allowed==='boolean'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-126** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:34](../../cloud/commands.js#L34)。
  - 原实现：`fresh&&proof.allowed===true&&health.canContinue===true&&!health.commandBlocker`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-127** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:34](../../cloud/commands.js#L34)。
  - 原实现：`fresh&&proof.allowed===true&&health.canContinue===true`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-128** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:34](../../cloud/commands.js#L34)。
  - 原实现：`proof.allowed===true`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-129** `条件门禁` — 云端；计划 **V2-1**；来源 [cloud/commands.js:38](../../cloud/commands.js#L38)。
  - 原实现：`record&&pending.has(record.state)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-130** `条件门禁` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:67](../../cloud/commands.js#L67)。
  - 原实现：`!allowedPath(path)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-131** `条件门禁` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:71](../../cloud/commands.js#L71)。
  - 原实现：`active.has(fingerprint)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-132** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:73](../../cloud/commands.js#L73)。
  - 原实现：`r.fingerprint===fingerprint`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-133** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:108](../../cloud/commands.js#L108)。
  - 原实现：`button.disabled=true`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-134** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:108](../../cloud/commands.js#L108)。
  - 原实现：`'/console/commands/request/'+record.requestId+'/cancel'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-135** `条件门禁` — 云端；计划 **V2-1**；来源 [cloud/commands.js:117](../../cloud/commands.js#L117)。
  - 原实现：`!record.remote&&!pending.has(record.state)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-136** `条件门禁` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:125](../../cloud/commands.js#L125)。
  - 原实现：`!button.disabled&&window.opsCloudCanWrite(button)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-137** `状态/防重复约束` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:125](../../cloud/commands.js#L125)。
  - 原实现：`!button.disabled&&window.opsCloudCanWrite(button)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **GUARD-138** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:9](../../cloud/cleanup.js#L9)。
  - 原实现：`document.getElementById(spec[kind]?.prefix+'CleanupPreview')¦¦document.getElementById('pendingDeleteStatus')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-139** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:12](../../cloud/cleanup.js#L12)。
  - 原实现：`kind!=='pending'&&!ids.length`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-140** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:12](../../cloud/cleanup.js#L12)。
  - 原实现：`kind!=='pending'&&!ids.length`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-141** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:15](../../cloud/cleanup.js#L15)。
  - 原实现：`value.kind!==kind¦¦!Array.isArray(value.ids)¦¦JSON.stringify(value.ids)!==JSON.stringify(ids)¦¦typeof value.ticket!=='string'¦¦typeof value.expiresAt!=='number'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-142** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:15](../../cloud/cleanup.js#L15)。
  - 原实现：`value.kind!==kind¦¦!Array.isArray(value.ids)¦¦JSON.stringify(value.ids)!==JSON.stringify(ids)¦¦typeof value.ticket!=='string'¦¦typeof value.expiresAt!=='number'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-143** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:15](../../cloud/cleanup.js#L15)。
  - 原实现：`typeof value.ticket!=='string'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-144** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:15](../../cloud/cleanup.js#L15)。
  - 原实现：`typeof value.expiresAt!=='number'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-145** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:17](../../cloud/cleanup.js#L17)。
  - 原实现：`kind!=='pending'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-146** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:18](../../cloud/cleanup.js#L18)。
  - 原实现：`state[item.prefix+'Preview']=value`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-147** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:22](../../cloud/cleanup.js#L22)。
  - 原实现：`(value.message¦¦'预览完成')+'；可处理 '+value.deletableCount+'，阻止 '+value.blockedCount+'。预览有效期至 '+new Date(value.expiresAt*1000).toLocaleTimeString()+'。'+(value.blocked¦¦[]).map(x=>x.name+'：'+x.reason).join('；')`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-148** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:22](../../cloud/cleanup.js#L22)。
  - 原实现：`(value.message¦¦'预览完成')+'；可处理 '+value.deletableCount+'，阻止 '+value.blockedCount+'。预览有效期至 '+new Date(value.expiresAt*1000).toLocaleTimeString()+'。'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-149** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:22](../../cloud/cleanup.js#L22)。
  - 原实现：`value.expiresAt*1000`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-150** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:28](../../cloud/cleanup.js#L28)。
  - 原实现：`kind!=='pending'&&JSON.stringify([...state[item.selection]])!==JSON.stringify(p.ids)`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-151** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:28](../../cloud/cleanup.js#L28)。
  - 原实现：`kind!=='pending'&&JSON.stringify([...state[item.selection]])!==JSON.stringify(p.ids)`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-152** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:34](../../cloud/cleanup.js#L34)。
  - 原实现：`kind==='pending'&&prompt('再次输入 EMPTY_PENDING_DELETE_NOW 确认永久清除')!==item.confirm`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-153** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:34](../../cloud/cleanup.js#L34)。
  - 原实现：`kind==='pending'&&prompt('再次输入 EMPTY_PENDING_DELETE_NOW 确认永久清除')!==item.confirm`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-154** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:38](../../cloud/cleanup.js#L38)。
  - 原实现：`kind==='pending'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-155** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:39](../../cloud/cleanup.js#L39)。
  - 原实现：`kind!=='pending'&&typeof renderActionResult==='function'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-156** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:39](../../cloud/cleanup.js#L39)。
  - 原实现：`kind!=='pending'&&typeof renderActionResult==='function'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-157** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:46](../../cloud/cleanup.js#L46)。
  - 原实现：`!match&&!pending`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-158** `条件门禁` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:47](../../cloud/cleanup.js#L47)。
  - 原实现：`button.disabled¦¦!window.opsCloudCanWrite(button)`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-159** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:47](../../cloud/cleanup.js#L47)。
  - 原实现：`button.disabled¦¦!window.opsCloudCanWrite(button)`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-160** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:48](../../cloud/cleanup.js#L48)。
  - 原实现：`button.disabled=true`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-161** `状态/防重复约束` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:49](../../cloud/cleanup.js#L49)。
  - 原实现：`button.disabled=false`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **GUARD-162** `状态/防重复约束` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:40](../../cloud/backups.js#L40)。
  - 原实现：`verify.disabled = true`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（逐包校验与失败提示、防重复）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-163** `状态/防重复约束` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:43](../../cloud/backups.js#L43)。
  - 原实现：`verify.disabled = false`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（逐包校验与失败提示、防重复）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-164** `状态/防重复约束` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:59](../../cloud/backups.js#L59)。
  - 原实现：`request.disabled = true`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **GUARD-165** `状态/防重复约束` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:62](../../cloud/backups.js#L62)。
  - 原实现：`request.disabled = false`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [ ] **GUARD-166** `状态/防重复约束` — 云端；计划 **V2-4**；来源 [cloud/login.js:8](../../cloud/login.js#L8)。
  - 原实现：`button.disabled = true`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **GUARD-167** `状态/防重复约束` — 云端；计划 **V2-4**；来源 [cloud/login.js:15](../../cloud/login.js#L15)。
  - 原实现：`button.disabled = false`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。

## elements（126 项）

- [x] **DOM-001** `header (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:11](../../static/index.html#L11)。
  - 原实现：`class="topbar" ¦ OP 家庭 AI 视频生产线 监控与安全控制中心 正在`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/App.tsx:155（等价页头/导航/页尾、主题与独立旧页入口）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-002** `section runtimeGuidance` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:25](../../static/index.html#L25)。
  - 原实现：`id="runtimeGuidance" class="runtime-guidance hidden" aria-live="polite" ¦ 当前项目需要补链<`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:43（运行提示、下一步、机器概况/当前任务与总览）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-003** `section nextAction` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:26](../../static/index.html#L26)。
  - 原实现：`id="nextAction" class="runtime-guidance needs-action hidden" aria-live="polite" ¦ 当前项目需要补链 -- <div id="gapQuickActions" class="gap-quick-acti`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:43（运行提示、下一步、机器概况/当前任务与总览）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-004** `section gapQuickBar` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:28](../../static/index.html#L28)。
  - 原实现：`id="gapQuickBar" class="gap-quick-bar hidden" aria-live="polite" ¦ 当前项目需要补链 --`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-005** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:34](../../static/index.html#L34)。
  - 原实现：`class="hero panel" ¦ 当前生产状态 正在读取生产线 请稍候，Dashboard 正在汇总全部环节状态。 远程总控 可确`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:43（运行提示、下一步、机器概况/当前任务与总览）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-006** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:43](../../static/index.html#L43)。
  - 原实现：`class="panel taskbox-panel" aria-label="任务箱总览" ¦ TASK BOX 正在读取任务箱 任务箱 </l`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:29（任务箱选择和历史区域）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-007** `select taskBoxSelect` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:46](../../static/index.html#L46)。
  - 原实现：`id="taskBoxSelect" aria-label="选择任务箱" ¦ 本次项目组合：-- 项目进度 0 / 0 </div`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:29（任务箱选择和历史区域）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-008** `details taskBoxHistory` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:57](../../static/index.html#L57)。
  - 原实现：`id="taskBoxHistory" class="taskbox-history hidden" ¦ 撤回历史 0 <section id="healthPanel" class="panel health-pan`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:29（任务箱选择和历史区域）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-009** `section healthPanel` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:63](../../static/index.html#L63)。
  - 原实现：`id="healthPanel" class="panel health-panel" aria-label="系统健康" aria-live="polite" ¦ HEALTH 系统健康 正在读取… <section class="metric`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:604（系统健康与资源指标）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-010** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:68](../../static/index.html#L68)。
  - 原实现：`class="metrics-grid" aria-label="系统资源" ¦ C CPU -- 处理器占用 <ar`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:604（系统健康与资源指标）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-011** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:69](../../static/index.html#L69)。
  - 原实现：`class="metric-card" ¦ C CPU -- 处理器占用 <div class=`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:604（系统健康与资源指标）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-012** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:70](../../static/index.html#L70)。
  - 原实现：`class="metric-card" ¦ M 内存 -- 正在读取 <d`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:604（系统健康与资源指标）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-013** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:71](../../static/index.html#L71)。
  - 原实现：`class="metric-card" ¦ G GPU -- 正在检测显卡 <div clas`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:604（系统健康与资源指标）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-014** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:72](../../static/index.html#L72)。
  - 原实现：`class="metric-card" ¦ D 成片磁盘 -- 正在读取 <div cl`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:604（系统健康与资源指标）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-015** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:73](../../static/index.html#L73)。
  - 原实现：`class="metric-card" ¦ N 网络 -- 正在检查网卡`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:604（系统健康与资源指标）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-016** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:76](../../static/index.html#L76)。
  - 原实现：`class="panel pipeline-panel" ¦ VIDEO PIPELINE 全流程状态 查看日期 <select id="pipeline`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期选择、五步卡片和明细）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-017** `select pipelineDateSelect` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:81](../../static/index.html#L81)。
  - 原实现：`id="pipelineDateSelect" aria-label="全流程查看日期" ¦ 工作台 · 检查中 语音客户端 · 检查中 <s`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期选择、五步卡片和明细）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-018** `article stageDownload` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:100](../../static/index.html#L100)。
  - 原实现：`id="stageDownload" class="stage-monitor" ¦ 下载 / 去字幕 等待 等待工作台状态 0 / 0`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期选择、五步卡片和明细）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-019** `article stageVoice` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:101](../../static/index.html#L101)。
  - 原实现：`id="stageVoice" class="stage-monitor" ¦ 批量语音 等待 等待语音任务 0 / 0 <str`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期选择、五步卡片和明细）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-020** `article stageStitch` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:102](../../static/index.html#L102)。
  - 原实现：`id="stageStitch" class="stage-monitor" ¦ AI 素材拼接 等待 等待拼接任务 0 / 0 <`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期选择、五步卡片和明细）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-021** `article stageCapcut` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:103](../../static/index.html#L103)。
  - 原实现：`id="stageCapcut" class="stage-monitor" ¦ CapCut 自动剪辑 等待 等待第五步任务 0 / 0 <article id="stageUpload" class="stage-monitor di`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期选择、五步卡片和明细）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-022** `article stageUpload` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:104](../../static/index.html#L104)。
  - 原实现：`id="stageUpload" class="stage-monitor disabled" ¦ 最终成片上传 未配置 上传服务尚未接入 0 / 0 <section id="downloadFailurePanel" class`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期选择、五步卡片和明细）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-023** `section downloadFailurePanel` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:106](../../static/index.html#L106)。
  - 原实现：`id="downloadFailurePanel" class="download-failure-panel hidden" aria-live="polite" ¦ 下载 / 去字幕失败任务 0 条 这些链接未进入后续语音、拼接与剪辑；补链或重试后再继续。`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（下载失败清单与空状态）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-024** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:119](../../static/index.html#L119)。
  - 原实现：`class="panel safety-panel" aria-label="生产安全" ¦ PRODUCTION SAFETY 生产安全 正在读取确定性检查… <div id="safetyGrid" class="safety`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-025** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:125](../../static/index.html#L125)。
  - 原实现：`class="safety-card neutral" ¦ 去字幕质检 正在读取… 自动安全恢复 正在读取… 成片质检 正在读取… </arti`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-026** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:126](../../static/index.html#L126)。
  - 原实现：`class="safety-card neutral" ¦ 自动安全恢复 正在读取… 成片质检 正在读取… 版本与配置 正在读取… </arti`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-027** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:127](../../static/index.html#L127)。
  - 原实现：`class="safety-card neutral" ¦ 成片质检 正在读取… 版本与配置 正在读取… 云端对账 正在读取… </articl`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-028** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:128](../../static/index.html#L128)。
  - 原实现：`class="safety-card neutral" ¦ 版本与配置 正在读取… 云端对账 正在读取… 磁盘预测 正在读取… </articl`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-029** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:129](../../static/index.html#L129)。
  - 原实现：`class="safety-card neutral" ¦ 云端对账 正在读取… 磁盘预测 正在读取… 登录状态 正在读取… </article`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-030** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:130](../../static/index.html#L130)。
  - 原实现：`class="safety-card neutral" ¦ 磁盘预测 正在读取… 登录状态 正在读取… 任务身份 正在读取… </article`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-031** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:131](../../static/index.html#L131)。
  - 原实现：`class="safety-card neutral" ¦ 登录状态 正在读取… 任务身份 正在读取… 故障证据 正在读取… </article`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-032** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:132](../../static/index.html#L132)。
  - 原实现：`class="safety-card neutral" ¦ 任务身份 正在读取… 故障证据 正在读取… 本区域全部来自本机确定性检查，正常查询消耗 0 模型 Token。 <`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-033** `article (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:133](../../static/index.html#L133)。
  - 原实现：`class="safety-card neutral" ¦ 故障证据 正在读取… 本区域全部来自本机确定性检查，正常查询消耗 0 模型 Token。`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:119（生产安全八类卡片与计数）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-034** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:138](../../static/index.html#L138)。
  - 原实现：`class="workspace-grid" ¦ STEP 5 TASKS 第五步任务与进度 <span id="t`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:324（第五步列表及项目筛选）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-035** `select step5ProjectFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:146](../../static/index.html#L146)。
  - 原实现：`id="step5ProjectFilter" aria-label="筛选第五步项目" ¦ 全部项目 总任务 0`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:324（第五步列表及项目筛选）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-036** `aside (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:163](../../static/index.html#L163)。
  - 原实现：`class="side-column" ¦ CURRENT 当前第五步任务 等待 <`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:268（上传进度、重扫及历史核验、项目缺口与任务操作）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-037** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:164](../../static/index.html#L164)。
  - 原实现：`class="panel current-card" ¦ CURRENT 当前第五步任务 等待 日期 -- <d`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:268（上传进度、重扫及历史核验、项目缺口与任务操作）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-038** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:169](../../static/index.html#L169)。
  - 原实现：`class="panel upload-card" ¦ ↥ UPLOAD SERVICE 正在读取百度网盘状态 等待工作台上传服务写入状态。 检查中 <di`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:268（上传进度、重扫及历史核验、项目缺口与任务操作）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-039** `button uploadRescanButton` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/index.html:183](../../static/index.html#L183)。
  - 原实现：`id="uploadRescanButton" class="primary wide" type="button" ¦ 重新对账、补传并清理 尚未手动检查上传缺口 核验历史云端文件 <div id="historicalCloudV`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **DOM-040** `button historicalCloudVerifyButton` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/index.html:185](../../static/index.html#L185)。
  - 原实现：`id="historicalCloudVerifyButton" class="wide" type="button" ¦ 核验历史云端文件 只核验历史上传记录，不补传、不删除文件 <div class="section-heading`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **DOM-041** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:188](../../static/index.html#L188)。
  - 原实现：`class="panel draft-manager-card" ¦ CAPCUT DRAFTS CapCut 草稿管理 未读取`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:268（上传进度、重扫及历史核验、项目缺口与任务操作）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-042** `button openDraftManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:194](../../static/index.html#L194)。
  - 原实现：`id="openDraftManagerButton" class="primary wide" type="button" ¦ 管理 CapCut 草稿 尚未手动清理 CapCut 草稿`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:336（三类入口和待删区，FileManagers承载实际管理视图）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-043** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:197](../../static/index.html#L197)。
  - 原实现：`class="panel audio-manager-card" ¦ AUDIO FILES 音频文件管理 未读取 <p clas`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:336（三类入口和待删区，FileManagers承载实际管理视图）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-044** `button openAudioManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:203](../../static/index.html#L203)。
  - 原实现：`id="openAudioManagerButton" class="primary wide" type="button" ¦ 管理音频文件 尚未手动清理音频`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:336（三类入口和待删区，FileManagers承载实际管理视图）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-045** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:206](../../static/index.html#L206)。
  - 原实现：`class="panel production-manager-card" ¦ PRODUCTION FILES 生产文件管理 未读取`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:336（三类入口和待删区，FileManagers承载实际管理视图）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-046** `button openProductionManagerButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:212](../../static/index.html#L212)。
  - 原实现：`id="openProductionManagerButton" class="primary wide" type="button" ¦ 管理生产文件 尚未手动清理生产文件 待删区：读取中… <button id="emptyPendingDeleteButton" clas`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:336（三类入口和待删区，FileManagers承载实际管理视图）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-047** `button emptyPendingDeleteButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:215](../../static/index.html#L215)。
  - 原实现：`id="emptyPendingDeleteButton" class="danger wide hidden" type="button" ¦ 立即清空待删区 QUEUE CONTROL 任务确认与撤回 <p class="queue-contro`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:336（三类入口和待删区，FileManagers承载实际管理视图）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-048** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:217](../../static/index.html#L217)。
  - 原实现：`class="panel queue-control-card" ¦ QUEUE CONTROL 任务确认与撤回 只影响尚未开始的队列记录；不会删除视频、音频或素材。 <div id="queueActionResult" class="act`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:6（安全继续及重置显示区；ContinueActions独立门禁和确认）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-049** `button continueCurrentButton` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/index.html:221](../../static/index.html#L221)。
  - 原实现：`id="continueCurrentButton" class="primary wide" type="button" ¦ 安全继续当前项目 由家里工作台先核对正式清单；已有有效产物会跳过，数量不一致时会安全暂停。 尚未执行安全继续对账`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:6（安全继续及重置显示区；ContinueActions独立门禁和确认）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-050** `section continueResult` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:223](../../static/index.html#L223)。
  - 原实现：`id="continueResult" class="reconcile-result neutral" ¦ 尚未执行安全继续对账 重置全部测试记录 仅把工作台、接收器、Dashboard 与 CapCut 的任务记录备份`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:6（安全继续及重置显示区；ContinueActions独立门禁和确认）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-051** `button resetTestRecordsButton` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/index.html:226](../../static/index.html#L226)。
  - 原实现：`id="resetTestRecordsButton" class="danger wide" type="button" ¦ 重置全部测试记录 仅把工作台、接收器、Dashboard 与 CapCut 的任务记录备份后归零；不会删除媒体、素材、配置或校准。 尚未重置测试记录 <details class="web-task`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:6（安全继续及重置显示区；ContinueActions独立门禁和确认）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-052** `details (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:229](../../static/index.html#L229)。
  - 原实现：`class="web-task-form" ¦ 新建项目任务 日期 项目<select id="createTemplate" name="templateId" requi`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:324（TaskOperations新建/补链表单；测试与任务浏览器验证）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-053** `form createTaskForm` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/index.html:230](../../static/index.html#L230)。
  - 原实现：`id="createTaskForm" ¦ 日期 项目 材料<select id="createM`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-054** `input createDate` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:231](../../static/index.html#L231)。
  - 原实现：`id="createDate" name="date" placeholder="例如 7.21" required ¦ 项目 材料 音频批次<input id="createAudio`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-055** `select createTemplate` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:232](../../static/index.html#L232)。
  - 原实现：`id="createTemplate" name="templateId" required ¦ 材料 音频批次 语音策略<select`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-056** `select createMaterial` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:233](../../static/index.html#L233)。
  - 原实现：`id="createMaterial" name="material" ¦ 音频批次 语音策略 按项目默认 <option value="r`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-057** `input createAudioBatch` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:234](../../static/index.html#L234)。
  - 原实现：`id="createAudioBatch" name="audioBatch" placeholder="默认使用日期" ¦ 语音策略 按项目默认 复用已有语音 新建语音 计划`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-058** `select createVoicePlan` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:235](../../static/index.html#L235)。
  - 原实现：`id="createVoicePlan" name="voicePlan" ¦ 按项目默认 复用已有语音 新建语音 计划视频数 </l`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-059** `input createExpectedCount` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:236](../../static/index.html#L236)。
  - 原实现：`id="createExpectedCount" name="expectedCount" type="number" min="1" ¦ 视频链接（每行一条） 提交并启动首项`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-060** `textarea createUrls` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:237](../../static/index.html#L237)。
  - 原实现：`id="createUrls" name="urls" rows="4" required ¦ 提交并启动首项 提交任务`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-061** `input createStartNow` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:238](../../static/index.html#L238)。
  - 原实现：`id="createStartNow" type="checkbox" ¦ 提交并启动首项 提交任务 正在读取接收器队列… </se`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-062** `button (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:239](../../static/index.html#L239)。
  - 原实现：`class="primary wide" type="submit" ¦ 提交任务 正在读取接收器队列… <div class="secti`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-063** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:244](../../static/index.html#L244)。
  - 原实现：`class="panel project-gaps-card" ¦ PROJECT STATUS 项目状态 正在读取项目状态… <section`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:444（项目状态/最近事件）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-064** `section (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:245](../../static/index.html#L245)。
  - 原实现：`class="panel events-card" ¦ RECENT EVENTS 最近事件 正在读取事件… <dialog`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/Dashboard.tsx:444（项目状态/最近事件）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **DOM-065** `dialog draftManagerDialog` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:249](../../static/index.html#L249)。
  - 原实现：`id="draftManagerDialog" class="draft-manager-dialog" ¦ CAPCUT DRAFTS 选择要移入待删区的草稿 ×</butt`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-066** `header (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:251](../../static/index.html#L251)。
  - 原实现：` ¦ CAPCUT DRAFTS 选择要移入待删区的草稿 × <p class="draft-manager-war`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-067** `button closeDraftManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:253](../../static/index.html#L253)。
  - 原实现：`id="closeDraftManagerButton" class="icon-button" type="button" aria-label="关闭草稿管理" ¦ × CapCut 或批处理客户端运行时禁止删除。人工及来源不明草稿不会默认勾选。 分类 <option v`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-068** `select draftCategoryFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:258](../../static/index.html#L258)。
  - 原实现：`id="draftCategoryFilter" ¦ 全部 正式自动草稿 内测草稿 人工或来源不明 </la`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-069** `select draftDateFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:266](../../static/index.html#L266)。
  - 原实现：`id="draftDateFilter" ¦ 全部日期 搜索 <button id="refreshDraftManagerB`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-070** `input draftSearchFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:270](../../static/index.html#L270)。
  - 原实现：`id="draftSearchFilter" type="search" placeholder="草稿名称或源视频" ¦ 刷新 全选当前筛选`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-071** `button refreshDraftManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:271](../../static/index.html#L271)。
  - 原实现：`id="refreshDraftManagerButton" type="button" ¦ 刷新 全选当前筛选 取消全选</butto`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-072** `button selectFilteredDraftsButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:275](../../static/index.html#L275)。
  - 原实现：`id="selectFilteredDraftsButton" type="button" ¦ 全选当前筛选 取消全选 已选择 0 个 <div id="draftManagerList" class="draft-manager-`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-073** `button clearDraftSelectionButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:276](../../static/index.html#L276)。
  - 原实现：`id="clearDraftSelectionButton" type="button" ¦ 取消全选 已选择 0 个 点击“管理 CapCut 草稿”后读取清单。`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-074** `section draftCleanupPreview` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:283](../../static/index.html#L283)。
  - 原实现：`id="draftCleanupPreview" class="draft-cleanup-preview hidden" ¦ 预览删除 确认移入待删区`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-075** `footer (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:284](../../static/index.html#L284)。
  - 原实现：` ¦ 预览删除 确认移入待删区 <`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-076** `button previewDraftCleanupButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:285](../../static/index.html#L285)。
  - 原实现：`id="previewDraftCleanupButton" class="primary" type="button" ¦ 预览删除 确认移入待删区 <dialog id="audioManagerDialog" class="draft-manager-dialog audio-manager-dialog`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-077** `button confirmDraftCleanupButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:286](../../static/index.html#L286)。
  - 原实现：`id="confirmDraftCleanupButton" class="danger hidden" type="button" ¦ 确认移入待删区 AUDIO F`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-078** `dialog audioManagerDialog` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:290](../../static/index.html#L290)。
  - 原实现：`id="audioManagerDialog" class="draft-manager-dialog audio-manager-dialog" ¦ AUDIO FILES 选择要移入待删区的音频 ×</button`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-079** `header (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:292](../../static/index.html#L292)。
  - 原实现：` ¦ AUDIO FILES 选择要移入待删区的音频 × <p class="draft-manager-warni`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-080** `button closeAudioManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:294](../../static/index.html#L294)。
  - 原实现：`id="closeAudioManagerButton" class="icon-button" type="button" aria-label="关闭音频管理" ¦ × 活动、等待恢复、拼接中或 CapCut 处理中任务引用的音频会被锁定。点击受保护行可查看具体原因。 日期 <optio`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-081** `select audioDateFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:298](../../static/index.html#L298)。
  - 原实现：`id="audioDateFilter" ¦ 全部日期 项目 全部项目 材料 全部材料 </la`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-082** `select audioProjectFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:299](../../static/index.html#L299)。
  - 原实现：`id="audioProjectFilter" ¦ 全部项目 材料 全部材料 语言 全部语言 </l`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-083** `select audioMaterialFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:300](../../static/index.html#L300)。
  - 原实现：`id="audioMaterialFilter" ¦ 全部材料 语言 全部语言 音频批次 全部批次 </la`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-084** `select audioLanguageFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:301](../../static/index.html#L301)。
  - 原实现：`id="audioLanguageFilter" ¦ 全部语言 音频批次 全部批次 任务状态 全`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-085** `select audioBatchFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:302](../../static/index.html#L302)。
  - 原实现：`id="audioBatchFilter" ¦ 全部批次 任务状态 全部状态 可手动删除 <option value="pro`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-086** `select audioStateFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:304](../../static/index.html#L304)。
  - 原实现：`id="audioStateFilter" ¦ 全部状态 可手动删除 任务正在使用 搜索<input i`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-087** `input audioSearchFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:310](../../static/index.html#L310)。
  - 原实现：`id="audioSearchFilter" type="search" placeholder="文件名、项目、材料或语言" ¦ 刷新 全选当前筛选`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-088** `button refreshAudioManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:311](../../static/index.html#L311)。
  - 原实现：`id="refreshAudioManagerButton" type="button" ¦ 刷新 全选当前筛选 取消全选</button`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-089** `button selectFilteredAudioButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:315](../../static/index.html#L315)。
  - 原实现：`id="selectFilteredAudioButton" type="button" ¦ 全选当前筛选 取消全选 已选择 0 个 <div id="audioManagerList" class="draft-manager-`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-090** `button clearAudioSelectionButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:316](../../static/index.html#L316)。
  - 原实现：`id="clearAudioSelectionButton" type="button" ¦ 取消全选 已选择 0 个 点击“管理音频文件”后读取清单。`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-091** `section audioCleanupPreview` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:323](../../static/index.html#L323)。
  - 原实现：`id="audioCleanupPreview" class="draft-cleanup-preview hidden" ¦ 预览删除 确认移入待删区`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-092** `footer (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:324](../../static/index.html#L324)。
  - 原实现：` ¦ 预览删除 确认移入待删区 <`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-093** `button previewAudioCleanupButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:325](../../static/index.html#L325)。
  - 原实现：`id="previewAudioCleanupButton" class="primary" type="button" ¦ 预览删除 确认移入待删区`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-094** `button confirmAudioCleanupButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:326](../../static/index.html#L326)。
  - 原实现：`id="confirmAudioCleanupButton" class="danger hidden" type="button" ¦ 确认移入待删区 AUDIO PROTECTED 任务正在使用，禁止删除 <div`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-095** `dialog audioProtectionDialog` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:330](../../static/index.html#L330)。
  - 原实现：`id="audioProtectionDialog" class="audio-protection-dialog" ¦ AUDIO PROTECTED 任务正在使用，禁止删除 所属任务 -- 当前状态 -- </di`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-096** `button closeAudioProtectionButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:339](../../static/index.html#L339)。
  - 原实现：`id="closeAudioProtectionButton" class="primary" type="button" ¦ 我知道了 PRODUCTION FILES<`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-097** `dialog productionManagerDialog` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:342](../../static/index.html#L342)。
  - 原实现：`id="productionManagerDialog" class="draft-manager-dialog production-manager-dialog" ¦ PRODUCTION FILES 选择要移入待删区的生产文件 <button id="closeProductionManagerButton" class="icon-button" type="button" aria-label="关闭生产文`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-098** `header (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:344](../../static/index.html#L344)。
  - 原实现：` ¦ PRODUCTION FILES 选择要移入待删区的生产文件 × <p class="draft`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-099** `button closeProductionManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:346](../../static/index.html#L346)。
  - 原实现：`id="closeProductionManagerButton" class="icon-button" type="button" aria-label="关闭生产文件管理" ¦ × 默认只勾选“云端已实时核验、没有活动引用”的安全生产文件。测试文件不会默认勾选；音频、公共素材、Logo、公共样品、草稿及百度同步目录永久排除。 <p cla`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-100** `select productionDateFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:353](../../static/index.html#L353)。
  - 原实现：`id="productionDateFilter" ¦ 全部日期 项目 全部项目 材料 全部材料 </s`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-101** `select productionProjectFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:354](../../static/index.html#L354)。
  - 原实现：`id="productionProjectFilter" ¦ 全部项目 材料 全部材料 文件类型 全部类型`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-102** `select productionMaterialFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:355](../../static/index.html#L355)。
  - 原实现：`id="productionMaterialFilter" ¦ 全部材料 文件类型 全部类型 任务状态 <opti`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-103** `select productionCategoryFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:356](../../static/index.html#L356)。
  - 原实现：`id="productionCategoryFilter" ¦ 全部类型 任务状态 全部状态 可清理 <option value="`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-104** `select productionStateFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:358](../../static/index.html#L358)。
  - 原实现：`id="productionStateFilter" ¦ 全部状态 可清理 受保护 搜索<input id="pr`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-105** `input productionSearchFilter` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:364](../../static/index.html#L364)。
  - 原实现：`id="productionSearchFilter" type="search" placeholder="文件名、项目、材料、语言或相对目录" ¦ 刷新 全选当前筛选</but`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-106** `button refreshProductionManagerButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:365](../../static/index.html#L365)。
  - 原实现：`id="refreshProductionManagerButton" type="button" ¦ 刷新 全选当前筛选 取消`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-107** `button selectFilteredProductionButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:369](../../static/index.html#L369)。
  - 原实现：`id="selectFilteredProductionButton" type="button" ¦ 全选当前筛选 取消全选 已选择 0 个 <div id="productionManagerList" class=`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-108** `button clearProductionSelectionButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:370](../../static/index.html#L370)。
  - 原实现：`id="clearProductionSelectionButton" type="button" ¦ 取消全选 已选择 0 个 点击“管理生产文件”后读取`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-109** `section productionCleanupPreview` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:377](../../static/index.html#L377)。
  - 原实现：`id="productionCleanupPreview" class="draft-cleanup-preview hidden" ¦ 预览清理 确认移入待删区 </f`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-110** `footer (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:378](../../static/index.html#L378)。
  - 原实现：` ¦ 预览清理 确认移入待删区 </di`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-111** `button previewProductionCleanupButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:379](../../static/index.html#L379)。
  - 原实现：`id="previewProductionCleanupButton" class="primary" type="button" ¦ 预览清理 确认移入待删区`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-112** `button confirmProductionCleanupButton` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/index.html:380](../../static/index.html#L380)。
  - 原实现：`id="confirmProductionCleanupButton" class="danger hidden" type="button" ¦ 确认移入待删区 FILE PROTECTED 当前文件禁止清理 <di`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-113** `dialog productionProtectionDialog` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:384](../../static/index.html#L384)。
  - 原实现：`id="productionProtectionDialog" class="audio-protection-dialog" ¦ FILE PROTECTED 当前文件禁止清理 文件 -- 所属任务 -- <`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-114** `button closeProductionProtectionButton` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:394](../../static/index.html#L394)。
  - 原实现：`id="closeProductionProtectionButton" class="primary" type="button" ¦ 我知道了 AI视频生产线 OPS · Tailscale安全控制 <span id="footerMa`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **DOM-115** `dialog replenishDialog` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:397](../../static/index.html#L397)。
  - 原实现：`id="replenishDialog" class="replenish-dialog" ¦ AI视频生产线 OPS · Tailscale安全控制 -- <`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **DOM-116** `footer (无 id)` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/index.html:400](../../static/index.html#L400)。
  - 原实现：` ¦ AI视频生产线 OPS · Tailscale安全控制 --`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/App.tsx:155（等价页头/导航/页尾、主题与独立旧页入口）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [ ] **DOM-117** `form loginForm` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`id="loginForm" ¦ 登录 用户名 密码 登录 <`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-118** `input username` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`name="username" autocomplete="username" maxlength="64" required ¦ 密码 登录 注册账号（需要邀请码） 用户名<i`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-119** `input password` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`name="password" type="password" autocomplete="current-password" maxlength="256" required ¦ 登录 注册账号（需要邀请码） 用户名 密码（至少12个字符）<input name="passw`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-120** `button (无 id)` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：` ¦ 登录 注册账号（需要邀请码） 用户名 密码（至少12个字符）<input name="password" type="passw`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-121** `details registration` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`id="registration" ¦ 注册账号（需要邀请码） 用户名 密码（至少12个字符）<input name="password" type="password" autocomplete="new-password" minlength="1`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-122** `form registerForm` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`id="registerForm" ¦ 用户名 密码（至少12个字符） 邀请码<input n`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-123** `input username` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`name="username" autocomplete="username" maxlength="64" required ¦ 密码（至少12个字符） 邀请码`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-124** `input password` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`name="password" type="password" autocomplete="new-password" minlength="12" maxlength="256" required ¦ 邀请码 注册`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-125** `input invite` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：`name="invite" type="password" autocomplete="off" maxlength="256" required ¦ 注册`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **DOM-126** `button (无 id)` — 云端；计划 **V2-4**；来源 [cloud/login.html:1](../../cloud/login.html#L1)。
  - 原实现：` ¦ 注册`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。

## events（78 项）

- [x] **EVENT-001** `input.addEventListener` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:233](../../static/app.js#L233)。
  - 原实现：`input.addEventListener("change", event => { const draftId = event.currentTarget.dataset.draftId; if (event.currentTarget.checked) state.selectedDraftIds.add(draftId); else state.selectedDraftIds.delete(draftId); resetDraftPreview(); updateDraftSelectionSummary(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-002** `input.addEventListener` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:369](../../static/app.js#L369)。
  - 原实现：`input.addEventListener("change", event => { const audioId = event.currentTarget.dataset.audioId; if (event.currentTarget.checked) state.selectedAudioIds.add(audioId); else state.selectedAudioIds.delete(audioId); resetAudioPreview(); updateAudioSelectionSummary(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-003** `row.addEventListener` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:378](../../static/app.js#L378)。
  - 原实现：`row.addEventListener("click", event => { const item = state.audioFiles.find(value => value.audioId === row.dataset.audioRowId); if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return; event.preventDefault(); showAudioProtection(item); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-004** `button.addEventListener` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:473](../../static/app.js#L473)。
  - 原实现：`button.addEventListener("click", () => { const select = $("productionCategoryFilter"); if (select) select.value = button.dataset.productionCategory ¦¦ ""; resetProductionPreview(); renderProductionManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-005** `input.addEventListener` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:561](../../static/app.js#L561)。
  - 原实现：`input.addEventListener("change", event => { const fileId = event.currentTarget.dataset.productionId; if (event.currentTarget.checked) state.selectedProductionIds.add(fileId); else state.selectedProductionIds.delete(fileId); resetProductionPreview(); updateProductionSelectionSummary(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-006** `row.addEventListener` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:570](../../static/app.js#L570)。
  - 原实现：`row.addEventListener("click", event => { const item = state.productionFiles.find(value => value.fileId === row.dataset.productionRowId); if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return; event.preventDefault(); showProductionProtection(item); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-007** `window.setTimeout` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1093](../../static/app.js#L1093)。
  - 原实现：`window.setTimeout(() => controller.abort(), timeoutMs)`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/home-cleanup.ts:105（原JSON正文、独立超时与错误提示；云端使用队列写入器）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-008** `$("closeReplenishDialog")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1131](../../static/app.js#L1131)。
  - 原实现：`$("closeReplenishDialog")?.addEventListener("click", () => dialog?.close())`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **EVENT-009** `$("replenishForm").addEventListener` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:1132](../../static/app.js#L1132)。
  - 原实现：`$("replenishForm").addEventListener("submit", async (event) => { event.preventDefault(); const button = event.currentTarget.querySelector("button"); button.disabled = true; try { const result = await postJson(ˋ/api/controls/tasks/${encodeURIComponent(taskId)}/replenishˋ, { urls: $("replenishUrls").value, startNow: $("replenishStartNow").checked, }); renderActionResult("queueActionResult", { state: "completed", message: result.`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **EVENT-010** `window.setTimeout` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1616](../../static/app.js#L1616)。
  - 原实现：`window.setTimeout(() => controller.abort(), timeoutMs)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-011** `window.setTimeout` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1630](../../static/app.js#L1630)。
  - 原实现：`window.setTimeout(resolve, 500 * (2 ** attempt))`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-012** `$("pipelineDateSelect").addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1714](../../static/app.js#L1714)。
  - 原实现：`$("pipelineDateSelect").addEventListener("change", event => { state.date = event.target.value; state.historyExplicit = true; refresh(); })`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:165（日期/任务箱/项目筛选回调保持原选择语义）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-013** `$("taskBoxSelect")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1719](../../static/app.js#L1719)。
  - 原实现：`$("taskBoxSelect")?.addEventListener("change", event => { state.batchId = event.target.value; state.date = ""; state.historyExplicit = Boolean(state.batchId); refresh(); })`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:29（日期/任务箱/项目筛选回调保持原选择语义）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-014** `$("step5ProjectFilter")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1725](../../static/app.js#L1725)。
  - 原实现：`$("step5ProjectFilter")?.addEventListener("change", event => { state.step5Filter = event.target.value; renderTasks(state.step5Items); })`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/TaskViews.tsx:324（日期/任务箱/项目筛选回调保持原选择语义）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-015** `$("openDraftManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1729](../../static/app.js#L1729)。
  - 原实现：`$("openDraftManagerButton")?.addEventListener("click", async () => { const dialog = $("draftManagerDialog"); if (dialog && !dialog.open) dialog.showModal(); await loadDraftManager(); })`；实现/测试证据：待补。 实现：FileManagers/useDashboard 家里清理与60秒待删区读取；PR #34，仅隔离。
- [x] **EVENT-016** `$("closeDraftManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1734](../../static/app.js#L1734)。
  - 原实现：`$("closeDraftManagerButton")?.addEventListener("click", () => $("draftManagerDialog")?.close())`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-017** `$("refreshDraftManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1735](../../static/app.js#L1735)。
  - 原实现：`$("refreshDraftManagerButton")?.addEventListener("click", loadDraftManager)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-018** `$(id)?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1737](../../static/app.js#L1737)。
  - 原实现：`$(id)?.addEventListener(id === "draftSearchFilter" ? "input" : "change", () => { resetDraftPreview(); renderDraftManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-019** `$("selectFilteredDraftsButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1742](../../static/app.js#L1742)。
  - 原实现：`$("selectFilteredDraftsButton")?.addEventListener("click", () => { filteredDrafts().filter(item => !item.protected).forEach(item => state.selectedDraftIds.add(item.draftId)); resetDraftPreview(); renderDraftManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-020** `$("clearDraftSelectionButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1747](../../static/app.js#L1747)。
  - 原实现：`$("clearDraftSelectionButton")?.addEventListener("click", () => { state.selectedDraftIds.clear(); resetDraftPreview(); renderDraftManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-021** `$("previewDraftCleanupButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1752](../../static/app.js#L1752)。
  - 原实现：`$("previewDraftCleanupButton")?.addEventListener("click", async event => { const button = event.currentTarget; const draftIds = [...state.selectedDraftIds]; if (!draftIds.length) { $("draftCleanupPreview").classList.remove("hidden"); $("draftCleanupPreview").innerHTML = "<strong>尚未选择草稿</strong>请先勾选要移入待删区的草稿。"; return; } button.disabled = true; button.textContent = "正在核对…"; try { const preview = await postJson("/api/controls/ca`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-022** `$("confirmDraftCleanupButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1783](../../static/app.js#L1783)。
  - 原实现：`$("confirmDraftCleanupButton")?.addEventListener("click", async event => { const button = event.currentTarget; const preview = state.draftPreview; if (!preview?.deletableCount) return; if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个草稿移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除视频、音频、成片或生产任务。ˋ)) return; if (preview.containsManualOrUnknown && !window.confirm("选择中包含人工或来源不明草稿。再次确认仍要将这些草稿移入待删区。")) return; button.disabled = true; button.textC`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-023** `$("openAudioManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1814](../../static/app.js#L1814)。
  - 原实现：`$("openAudioManagerButton")?.addEventListener("click", async () => { const dialog = $("audioManagerDialog"); if (dialog && !dialog.open) dialog.showModal(); await loadAudioManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-024** `$("closeAudioManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1819](../../static/app.js#L1819)。
  - 原实现：`$("closeAudioManagerButton")?.addEventListener("click", () => $("audioManagerDialog")?.close())`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-025** `$("closeAudioProtectionButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1820](../../static/app.js#L1820)。
  - 原实现：`$("closeAudioProtectionButton")?.addEventListener("click", () => $("audioProtectionDialog")?.close())`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-026** `$("refreshAudioManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1821](../../static/app.js#L1821)。
  - 原实现：`$("refreshAudioManagerButton")?.addEventListener("click", loadAudioManager)`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-027** `$(id)?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1826](../../static/app.js#L1826)。
  - 原实现：`$(id)?.addEventListener(id === "audioSearchFilter" ? "input" : "change", () => { resetAudioPreview(); renderAudioManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-028** `$("selectFilteredAudioButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1831](../../static/app.js#L1831)。
  - 原实现：`$("selectFilteredAudioButton")?.addEventListener("click", () => { filteredAudioFiles().filter(item => !item.protected).forEach(item => state.selectedAudioIds.add(item.audioId)); resetAudioPreview(); renderAudioManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-029** `$("clearAudioSelectionButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1836](../../static/app.js#L1836)。
  - 原实现：`$("clearAudioSelectionButton")?.addEventListener("click", () => { state.selectedAudioIds.clear(); resetAudioPreview(); renderAudioManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-030** `$("previewAudioCleanupButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1841](../../static/app.js#L1841)。
  - 原实现：`$("previewAudioCleanupButton")?.addEventListener("click", async event => { const button = event.currentTarget; const audioIds = [...state.selectedAudioIds]; if (!audioIds.length) { $("audioCleanupPreview").classList.remove("hidden"); $("audioCleanupPreview").innerHTML = "<strong>尚未选择音频</strong>请先勾选要移入待删区的音频文件。"; return; } button.disabled = true; button.textContent = "正在重新对账…"; try { const preview = await postJson("/api/control`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-031** `$("confirmAudioCleanupButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1876](../../static/app.js#L1876)。
  - 原实现：`$("confirmAudioCleanupButton")?.addEventListener("click", async event => { const button = event.currentTarget; const preview = state.audioPreview; if (!preview?.deletableCount) return; if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个音频文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除文件夹，也不会改变任务完成状态。ˋ)) return; button.disabled = true; button.textContent = "正在移入待删区…"; try { const audioIds = (preview.deletabl`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-032** `$("openProductionManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1908](../../static/app.js#L1908)。
  - 原实现：`$("openProductionManagerButton")?.addEventListener("click", async () => { const dialog = $("productionManagerDialog"); if (dialog && !dialog.open) dialog.showModal(); await loadProductionManager({ applyDefaults: true }); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-033** `$("closeProductionManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1913](../../static/app.js#L1913)。
  - 原实现：`$("closeProductionManagerButton")?.addEventListener("click", () => $("productionManagerDialog")?.close())`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-034** `$("closeProductionProtectionButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1914](../../static/app.js#L1914)。
  - 原实现：`$("closeProductionProtectionButton")?.addEventListener("click", () => $("productionProtectionDialog")?.close())`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-035** `$("refreshProductionManagerButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1915](../../static/app.js#L1915)。
  - 原实现：`$("refreshProductionManagerButton")?.addEventListener("click", () => loadProductionManager())`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-036** `$(id)?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1920](../../static/app.js#L1920)。
  - 原实现：`$(id)?.addEventListener(id === "productionSearchFilter" ? "input" : "change", () => { resetProductionPreview(); renderProductionManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-037** `$("selectFilteredProductionButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1925](../../static/app.js#L1925)。
  - 原实现：`$("selectFilteredProductionButton")?.addEventListener("click", () => { filteredProductionFiles() .filter(item => !item.protected) .forEach(item => state.selectedProductionIds.add(item.fileId)); resetProductionPreview(); renderProductionManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-038** `$("clearProductionSelectionButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1932](../../static/app.js#L1932)。
  - 原实现：`$("clearProductionSelectionButton")?.addEventListener("click", () => { state.selectedProductionIds.clear(); resetProductionPreview(); renderProductionManager(); })`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-039** `$("previewProductionCleanupButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1937](../../static/app.js#L1937)。
  - 原实现：`$("previewProductionCleanupButton")?.addEventListener("click", async event => { const button = event.currentTarget; const fileIds = [...state.selectedProductionIds]; if (!fileIds.length) { $("productionCleanupPreview").classList.remove("hidden"); $("productionCleanupPreview").innerHTML = "<strong>尚未选择生产文件</strong>请先勾选要移入待删区的文件。"; return; } button.disabled = true; button.textContent = "正在重新核验云端与引用…"; try { const preview = await`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-040** `$("confirmProductionCleanupButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1978](../../static/app.js#L1978)。
  - 原实现：`$("confirmProductionCleanupButton")?.addEventListener("click", async event => { const button = event.currentTarget; const preview = state.productionPreview; if (!preview?.deletableCount) return; if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个生产文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；项目状态、上传记录及云端文件不会改变。ˋ)) return; if (preview.containsTestFiles && !window.confirm("选择中包含 CapCut 测试或首帧测试文件。再次确认仍要将这些测试文件移入`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-041** `$("emptyPendingDeleteButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2035](../../static/app.js#L2035)。
  - 原实现：`$("emptyPendingDeleteButton")?.addEventListener("click", async (event) => { const button = event.currentTarget; const info = state.pendingDelete ¦¦ {}; if (!window.confirm(ˋ确认立即永久清除待删区的 ${Number(info.count ¦¦ 0)} 项（约 ${formatBytes(info.sizeBytes)}）吗？清除后无法恢复。ˋ)) return; if (!window.confirm("再次确认：这一步会永久删除，不进入回收站。")) return; button.disabled = true; try { const result = await postJson("/api/controls/pending-delete/empty", { confir`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **EVENT-042** `$("continueCurrentButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2051](../../static/app.js#L2051)。
  - 原实现：`$("continueCurrentButton")?.addEventListener("click", async (event) => { const button = event.currentTarget; if (button.dataset.allowed === "false") return; if (!window.confirm("确认让家里工作台安全继续当前项目吗？它会先核对任务清单，不会删除素材或重做有效成片。")) return; button.disabled = true; button.textContent = "正在发送继续指令…"; try { const clientRequestId = (window.crypto?.randomUUID?.() ¦¦ ˋdashboard-${Date.now()}-${Math.random()}ˋ); // Name the project this page s`；实现/测试证据：待补。 安全继续留独立2E，用户亲自确认后才可合并。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **EVENT-043** `window.setTimeout` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2080](../../static/app.js#L2080)。
  - 原实现：`window.setTimeout(refreshContinueStatus, 500)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **EVENT-044** `$("uploadRescanButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2083](../../static/app.js#L2083)。
  - 原实现：`$("uploadRescanButton")?.addEventListener("click", async (event) => { const button = event.currentTarget; if (!window.confirm("确认重新对账正式清单，补传遗漏成片，并对云端已实时核验的任务继续安全清理吗？不会重新剪辑等待中的任务，也不会清理配音、公共素材、Logo或公共样品。")) return; button.disabled = true; button.textContent = "正在检查上传缺口…"; try { const result = await postJson("/api/controls/upload/rescan", {}); renderActionResult("uploadActionResult", { state: window.opsCloudPostJson ? (result.sta`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **EVENT-045** `$("historicalCloudVerifyButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2107](../../static/app.js#L2107)。
  - 原实现：`$("historicalCloudVerifyButton")?.addEventListener("click", async (event) => { const button = event.currentTarget; if (!window.confirm("确认核验历史百度云文件吗？系统只会查询云端文件是否存在，并核对云端路径和文件大小；不会补传、不会删除本地或云端文件，也不会改变项目完成状态。")) return; button.disabled = true; button.textContent = "正在提交历史核验…"; try { const result = await postJson("/api/controls/upload/verify-history", {}); renderHistoricalCloudVerification(result); await refresh(); } catch (error`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **EVENT-046** `$("resetTestRecordsButton")?.addEventListener` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2124](../../static/app.js#L2124)。
  - 原实现：`$("resetTestRecordsButton")?.addEventListener("click", async (event) => { const button = event.currentTarget; if (!window.confirm("确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。")) return; if (!window.confirm("再次确认：Dashboard、工作台、接收器和 CapCut 的任务进度将从空状态重新开始。")) return; button.disabled = true; button.textContent = "正在备份并重置…"; try { const result = await postJson("/api/controls/testing/reset", { confirm: "RESET_TEST_RECORDS" }); state.da`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-047** `$("createTemplate").addEventListener` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2152](../../static/app.js#L2152)。
  - 原实现：`$("createTemplate").addEventListener("change", updateMaterialOptions)`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **EVENT-048** `$("createTaskForm").addEventListener` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2153](../../static/app.js#L2153)。
  - 原实现：`$("createTaskForm").addEventListener("submit", async (event) => { event.preventDefault(); const form = event.currentTarget; const button = form.querySelector("button[type='submit']"); button.disabled = true; try { const result = await postJson("/api/controls/tasks/create", { date: $("createDate").value.trim(), templateId: $("createTemplate").value, material: $("createMaterial").value, audioBatch: $("createAudioBatch").value.tr`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **EVENT-049** `window.setTimeout` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:2189](../../static/app.js#L2189)。
  - 原实现：`window.setTimeout(refreshLoop, document.hidden ? 20000 : 5000)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-050** `window.setTimeout` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:2194](../../static/app.js#L2194)。
  - 原实现：`window.setTimeout(refreshContinueLoop, state.continueInFlight ? (document.hidden ? 5000 : 1500) : 10000)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-051** `window.setInterval` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:2198](../../static/app.js#L2198)。
  - 原实现：`window.setInterval(updateDataFreshness, 1000)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-052** `document.addEventListener` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:2199](../../static/app.js#L2199)。
  - 原实现：`document.addEventListener("visibilitychange", updateDataFreshness)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-053** `window.setInterval` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2203](../../static/app.js#L2203)。
  - 原实现：`window.setInterval(refreshPendingDelete, 60000)`；实现/测试证据：待补。 实现：FileManagers/useDashboard 家里清理与60秒待删区读取；PR #34，仅隔离。
- [x] **EVENT-054** `(() => {
  const original = window.fetch.bind(window); 完整子功能复核：frontend-v2/src/data/client.ts:3（只读网络适配、202、缓存、401及取消；子功能均已迁移）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
  window.opsCloudNetwork=original;
  const samples = new Map();
  const inflight = new Map();
  let sourcePanel, dashboardSample;
  const refreshWatchers = new Map();
  const writeIds=['emptyPendingDeleteButton','continueCurrentButton','uploadRescanButton','historicalCloudVerifyButton','resetTestRecordsButton','previewDraftCleanupButton','confirmDraftCleanupButton','previewAudioCleanupButton','confirmAudioCleanupButton','previewProductionCleanupButton','confirmProductionCleanupButton'];
  document.addEventListener('submit', event => {
    if (!event.target.closest('[data-cloud-account]') && !window.opsCloudAcceptForm?.(event.target)) { event.preventDefault(); event.stopImmediatePropagation(); }
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
      const path=new URL(url,location.origin).pathname;
      if(path==='/api/dashboard'||path==='/api/dashboard/summary')dashboardSample=samples.get(url);
    }
  }
  function watchRefresh(key, response) {
    if (response.headers.get('X-Cache-Refresh-Pending')!=='true'||refreshWatchers.has(key)) return;
    const url=new URL(key,location.origin);const batch=url.searchParams.get('batchId');
    if(url.pathname!=='/api/dashboard'||!batch)return;
    const previous=response.headers.get('X-Cache-Version');const previousTag=response.headers.get('ETag');
    const watch=(async()=>{
      for(let attempt=0;attempt<60;attempt++){
        await wait(1000);
        if(document.visibilityState!=='visible')return;
        if(typeof state==='undefined'||state.batchId!==batch)return;
        const newer=await original(key,{headers:{'X-Ops-Page-Visible':'true'}});
        if(newer.status===401){location.assign('/login');return;}
        if(newer.status===200&&(newer.headers.get('X-Cache-Version')!==previous||newer.headers.get('ETag')!==previousTag)){
          if(!state.refreshBusy&&typeof refresh==='function'){state.fullDashboardLoaded=false;await refresh();}
          return;
        }
      }
    })().catch(()=>{}).finally(()=>refreshWatchers.delete(key));
    refreshWatchers.set(key,watch);
  }
  window.fetch = async (input, init = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/api/')) return original(input, init);
    const method = (init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (method !== 'GET') {if(window.opsCloudWriteFetch)return window.opsCloudWriteFetch(url.href,init);throw new Error('写命令尚未启用');}
    init={...init,headers:new Headers(init.headers || (input instanceof Request ? input.headers : undefined))};
    init.headers.set('X-Ops-Page-Visible',String(document.visibilityState==='visible'));
    const key = url.pathname + url.search;
    // Coalesce browser retries too; the cloud independently coalesces all devices.
    if (inflight.has(key)) return (await inflight.get(key)).clone();
    const work = (async () => {
      for (let attempt = 0; attempt < 120; attempt++) {
        const response = await original(input, init);
        if (response.status === 401) { location.assign('/login'); throw new Error('请重新登录'); }
        if (response.status !== 202) { observe(key, response); watchRefresh(key,response); return response; }
        // A pending envelope is never delivered to the old business renderer.
        await wait(500, init.signal || (input instanceof Request ? input.signal : undefined));
      }
      throw new Error('正在向家里取数，稍后自动刷新；已有数据显示保留');
    })();
    inflight.set(key, work);
    try { return (await work).clone(); } finally { inflight.delete(key); }
  };
  document.addEventListener('DOMContentLoaded', () => {
    // The home H4 timer measures browser reception. Cloud reception is not a
    // fresh home scan: derive displayed age from cloud cache/source ages.
    const paintCloudAge=()=>{
      if(!dashboardSample||typeof state==='undefined')return;
      const sample=dashboardSample;const since=(performance.now()-sample.received)/1000;
      const age=sample.age+since;const known=sample.sourceAge!==null&&Number.isFinite(sample.sourceAge)&&sample.sourceAge>=0;
      const effective=known?sample.sourceAge+age:null;
      state.freshnessReceivedAt=known?new Date(Date.now()-effective*1000):null;
      state.freshnessReceivedTick=performance.now()-(effective??age)*1000;
      state.freshnessStartedAt=state.freshnessReceivedTick;
      updateDataFreshness();
      const node=document.getElementById('dataFreshness');node.title='云端缓存：年龄包含家里扫描至取数的间隔及云端缓存时间，收到缓存不代表实时';
      if(!known){
        document.getElementById('lastUpdated').textContent='源扫描时间未知';
        document.getElementById('freshnessAge').textContent='（该版本最近取数 '+Math.floor(age)+' 秒前）';
        node.classList.add('warning');document.getElementById('freshnessWarning').hidden=false;
      }
    };
    recordDashboardReception=paintCloudAge;
    paintCloudAge();setInterval(paintCloudAge,1000);
    sourcePanel = document.createElement('details'); sourcePanel.open = true;
    sourcePanel.style.cssText = 'margin:12px;padding:12px;background:#fff5cf;color:#513f00;border-radius:8px';
    const summary = document.createElement('summary'); summary.textContent = '云端只读预览 · 家里代理部署前等待取数 · 写命令尚未启用';
    const explanation=document.createElement('p'); explanation.textContent='列表记录本页读到的各份数据；切换日期后旧条目会保留，请以当前所选看板为准。';
    sourcePanel.append(summary, explanation, document.createElement('ul')); document.body.prepend(sourcePanel);
    const forced=new WeakSet();
    for (const id of writeIds) {
      const button = document.getElementById(id); if (button) { forced.add(button); button.disabled = true; button.title = '当前云端为只读里程碑'; }
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
      const buttons=[...document.querySelectorAll('button[onclick], button[data-cloud-control], #createTaskForm button, #replenishForm button[type="submit"]'),...writeIds.map(id=>document.getElementById(id)).filter(Boolean)];
      for(const button of buttons) {
        const action=/^controlTask\(this, '(start|cancel)'\)$/.exec(button.getAttribute('onclick')||'');
        if(action){button.dataset.cloudControl=action[1];button.removeAttribute('onclick');}
        if(button.getAttribute('onclick')==='openReplenishment(this.dataset.taskId)'){button.dataset.cloudControl='replenish-open';button.removeAttribute('onclick');}
        const allowed=window.opsCloudCanWrite?.(button)===true;
        if(!allowed){if(!button.disabled){forced.add(button);button.disabled=true;}button.title='云端执行通道未就绪、数据过期或有待对账命令；清理需新版代理、Dashboard、有效预览和清理开关';}
        else if(forced.has(button)){forced.delete(button);button.disabled=false;button.title='';}
      }
    };
    window.addEventListener('ops-cloud-write-state',disableWrites);
    disableWrites(); new MutationObserver(disableWrites).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']});
    async function pollHealth() {
      try {
        const response=await original('/console/status',{headers:{'X-Ops-Page-Visible':String(document.visibilityState==='visible')}});
        if(response.status===401){location.assign('/login');return;}
        if(!response.ok)throw new Error();
        const health=await response.json();
        const text=health.heartbeatAgeSeconds===null?'等待家里代理部署/连接':!health.agentOnline?'家里离线，距心跳 '+Math.floor(health.heartbeatAgeSeconds)+' 秒':health.engineState==='healthy'?'家里在线':health.engineState==='busy'?'引擎忙，保留已有数据':'代理在线，旧引擎状态不可用/尚待确认';
        summary.textContent='云端缓存 · '+text+' · '+(health.executorAvailable?(health.commandsPaused?'命令下发已暂停':'命令通道已部署'):'等待 Claude 部署命令代理');
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
        const names={'/api/health':'递交健康','/api/dashboard':'完整看板','/api/dashboard/summary':'当前摘要','/api/task-boxes/current':'当前任务箱','/api/task-boxes/history':'历史任务箱','/api/controls/tasks':'任务队列','/api/controls/templates':'任务模板','/api/safety':'安全面板','/api/project-gaps':'项目缺口','/api/pipeline':'历史流水线','/api/controls/continue-current/status':'恢复状态','/api/control-commands/current':'命令状态','/api/subtitle-verification/current':'字幕核验'};
        const name=(names[parsed.pathname]||'页面数据')+(parsed.searchParams.get('date')?' '+parsed.searchParams.get('date'):'');
        const stamp=new Date(sample.scan);
        const effective=sample.sourceAge===null?null:sample.sourceAge+age;
        row.textContent=name+'：'+(Number.isNaN(stamp.getTime())||effective===null?'源扫描时间未知，该版本最近取数 '+age+' 秒前':'数据截至 '+stamp.toLocaleTimeString('zh-CN',{hour12:false})+'（'+Math.floor(effective)+' 秒前）；该版本最近取数 '+age+' 秒前');
        row.style.color=age>120||(effective!==null&&effective>120)?'#b42318':age>30||effective===null||effective>30?'#8a5c00':'#38533a'; list.append(row);
      }
    },1000);
  });
})` — 云端；计划 **V2-2F**；来源 [cloud/readonly.js:2](../../cloud/readonly.js#L2)。
  - 原实现：`(() => { const original = window.fetch.bind(window); window.opsCloudNetwork=original; const samples = new Map(); const inflight = new Map(); let sourcePanel, dashboardSample; const refreshWatchers = new Map(); const writeIds=['emptyPendingDeleteButton','continueCurrentButton','uploadRescanButton','historicalCloudVerifyButton','resetTestRecordsButton','previewDraftCleanupButton','confirmDraftCleanupButton','previewAudioCleanupB`；实现/测试证据：待补。
- [x] **EVENT-055** `document.addEventListener` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:10](../../cloud/readonly.js#L10)。
  - 原实现：`document.addEventListener('submit', event => { if (!event.target.closest('[data-cloud-account]') && !window.opsCloudAcceptForm?.(event.target)) { event.preventDefault(); event.stopImmediatePropagation(); } }, true)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 部分覆盖：读取已迁移，外层包装/写入拦截/账号事件尚未全部迁移，不记为完成。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-056** `setTimeout` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:16](../../cloud/readonly.js#L16)。
  - 原实现：`setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms)`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-057** `signal?.addEventListener` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:17](../../cloud/readonly.js#L17)。
  - 原实现：`signal?.addEventListener('abort', abort, {once: true})`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **EVENT-058** `document.addEventListener` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:71](../../cloud/readonly.js#L71)。
  - 原实现：`document.addEventListener('DOMContentLoaded', () => { // The home H4 timer measures browser reception. Cloud reception is not a // fresh home scan: derive displayed age from cloud cache/source ages. const paintCloudAge=()=>{ if(!dashboardSample¦¦typeof state==='undefined')return; const sample=dashboardSample;const since=(performance.now()-sample.received)/1000; const age=sample.age+since;const known=sample.sourceAge!==null&&Nu`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。 部分覆盖：读取已迁移，外层包装/写入拦截/账号事件尚未全部迁移，不记为完成。 完整子功能复核：frontend-v2/src/data/client.ts:3（只读网络适配、202、缓存、401及取消；子功能均已迁移）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-059** `setInterval` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:91](../../cloud/readonly.js#L91)。
  - 原实现：`setInterval(paintCloudAge,1000)`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/client.ts:3（只读网络适配、202、缓存、401及取消；子功能均已迁移）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-060** `window.addEventListener` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:130](../../cloud/readonly.js#L130)。
  - 原实现：`window.addEventListener('ops-cloud-write-state',disableWrites)`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-061** `new MutationObserver(disableWrites).observe` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:131](../../cloud/readonly.js#L131)。
  - 原实现：`new MutationObserver(disableWrites).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled']})`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/upload-writer.ts:37（显式双模式白名单和状态门禁，替代DOM拦截/MutationObserver）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-062** `setInterval` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:143](../../cloud/readonly.js#L143)。
  - 原实现：`setInterval(pollHealth,5000)`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-063** `setInterval` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:147](../../cloud/readonly.js#L147)。
  - 原实现：`setInterval(()=>{ if(typeof state!=='undefined'&&!state.refreshBusy&&typeof refresh==='function'){ state.fullDashboardLoaded=false;void refresh(); } },60000)`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-064** `setInterval` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:152](../../cloud/readonly.js#L152)。
  - 原实现：`setInterval(() => { const list=sourcePanel.querySelector('ul'); list.replaceChildren(); for (const [key,sample] of samples) { const age=Math.floor(sample.age+(performance.now()-sample.received)/1000); const row=document.createElement('li'); const parsed=new URL(key,location.origin); const names={'/api/health':'递交健康','/api/dashboard':'完整看板','/api/dashboard/summary':'当前摘要','/api/task-boxes/current':'当前任务箱','/api/task-boxes/histo`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-065** `(() => {
  const network=window.opsCloudNetwork||window.fetch.bind(window), key='ops-command-receipts-v1'; V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
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
})` — 云端；计划 **V2-1**；来源 [cloud/commands.js:3](../../cloud/commands.js#L3)。
  - 原实现：`(() => { const network=window.opsCloudNetwork¦¦window.fetch.bind(window), key='ops-command-receipts-v1'; const active=new Map();let health={},panel,list,specificResult;const eligibility=new Map(); const pending=new Set(['submitting','queued','leased','sent','unknown']); const labels={submitting:'收件结果待查询',queued:'云端排队',leased:'代理已领取，尚未发送',sent:'已发家里，等待 HTTP 回执',unknown:'结果不明，必须在家里对账',completed:'已收到家里 HTTP 回执（业务进度请看原状态）',not_sen`；实现/测试证据：待补。
- [x] **EVENT-066** `setTimeout` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:11](../../cloud/commands.js#L11)。
  - 原实现：`setTimeout(resolve,ms)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **EVENT-067** `document.addEventListener` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:124](../../cloud/commands.js#L124)。
  - 原实现：`document.addEventListener('DOMContentLoaded',()=>{ document.addEventListener('click',event=>{const button=event.target.closest('button[data-cloud-control]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();if(!button.disabled&&window.opsCloudCanWrite(button)){if(button.dataset.cloudControl==='replenish-open')openReplenishment(button.dataset.taskId);else void controlTask(button,button.dataset.cloudContr`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **EVENT-068** `document.addEventListener` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:125](../../cloud/commands.js#L125)。
  - 原实现：`document.addEventListener('click',event=>{const button=event.target.closest('button[data-cloud-control]');if(!button)return;event.preventDefault();event.stopImmediatePropagation();if(!button.disabled&&window.opsCloudCanWrite(button)){if(button.dataset.cloudControl==='replenish-open')openReplenishment(button.dataset.taskId);else void controlTask(button,button.dataset.cloudControl);}},true)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **EVENT-069** `setInterval` — 云端；计划 **V2-1**；来源 [cloud/commands.js:138](../../cloud/commands.js#L138)。
  - 原实现：`setInterval(poll,3000)`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **EVENT-070** `(() => {
 const endpoint='/api/controls/cloud-cleanup/',previews=new Map(); 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
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
})` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:3](../../cloud/cleanup.js#L3)。
  - 原实现：`(() => { const endpoint='/api/controls/cloud-cleanup/',previews=new Map(); const kinds={Draft:'drafts',Audio:'audio',Production:'production'}; const spec={drafts:{prefix:'draft',selection:'selectedDraftIds',confirm:'RECYCLE_SELECTED_CAPCUT_DRAFTS'},audio:{prefix:'audio',selection:'selectedAudioIds',confirm:'RECYCLE_SELECTED_AUDIO_FILES'},production:{prefix:'production',selection:'selectedProductionIds',confirm:'RECYCLE_SELECTE`；实现/测试证据：待补。
- [x] **EVENT-071** `document.addEventListener` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:43](../../cloud/cleanup.js#L43)。
  - 原实现：`document.addEventListener('click',event=>{ const button=event.target.closest('button');if(!button)return; const match=/^(preview¦confirm)(Draft¦Audio¦Production)CleanupButton$/.exec(button.id),pending=button.id==='emptyPendingDeleteButton'; if(!match&&!pending){if(/(Draft¦Audio¦Production)ManagerButton$/.test(button.id))void capability();return;} event.preventDefault();event.stopImmediatePropagation();if(button.disabled¦¦!wind`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **EVENT-072** `document.addEventListener` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:52](../../cloud/cleanup.js#L52)。
  - 原实现：`document.addEventListener('DOMContentLoaded',()=>{const button=document.createElement('button');button.type='button';button.textContent='检查清理通道';button.id='checkCleanupCapabilityButton';button.addEventListener('click',()=>void capability());document.getElementById('pendingDeleteStatus')?.after(button);setInterval(()=>{if(document.querySelector('#draftManagerDialog[open],#audioManagerDialog[open],#productionManagerDialog[open]'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **EVENT-073** `button.addEventListener` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:52](../../cloud/cleanup.js#L52)。
  - 原实现：`button.addEventListener('click',()=>void capability())`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **EVENT-074** `setInterval` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:52](../../cloud/cleanup.js#L52)。
  - 原实现：`setInterval(()=>{if(document.querySelector('#draftManagerDialog[open],#audioManagerDialog[open],#productionManagerDialog[open]'))void capability();},30000)`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **EVENT-075** `(() => {
  const api = async (path, method = 'GET') => { 完整子功能复核：frontend-v2/src/data/console-admin.ts:11（账号CSRF及原方法/状态码；读取目录仍用GET）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
    const headers = {};
    if (method !== 'GET') {
      const session = await fetch('/auth/session').then(r => r.json());
      headers['X-CSRF-Token'] = session.csrf;
    }
    const response = await fetch(path, {method, headers});
    if (!response.ok) throw new Error(`请求失败 (${response.status})`);
    return response.json();
  };
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const show = async (body, message) => {
    try {
      const result = await api('/console/backups');
      body.replaceChildren();
      body.append(element('p', `仅台账和配置恢复；视频、草稿不在备份中。已用及预留 ${(result.usedReservedBytes / 1048576).toFixed(1)} MiB / ${(result.quotaBytes / 1e9).toFixed(0)} GB。`));
      const phase = result.agentState?.phase || 'waiting_configuration';
      const phases = {waiting_configuration: '等待本机配置恢复密钥', creating: '正在生成', uploading: '正在上传', completed: '最近一次已上传', failed: '备份失败，请检查代理状态'};
      body.append(element('p', `家里备份：${phases[phase] || phase}。${result.recipientConfigured ? '云端已登记公钥。' : '云端尚未登记公钥。'}`));
      body.append(element('p', `实际保留日期：${result.retainedDates.join('、') || '尚无备份'}`));
      if (!result.items.length) body.append(element('p', '尚无已完成的备份包；未完成上传不会显示为可恢复备份。'));
      for (const item of result.items) {
        const row = element('div');
        row.style.cssText = 'padding:8px 0;border-bottom:1px solid #888';
        row.append(element('p', `${item.kind === 'home' ? '家里台账/配置' : '云端数据库'} · ${item.date} · ${(item.bytes / 1048576).toFixed(2)} MiB · ${item.packageId}`));
        for (const name of ['manifest.json', ...item.manifest.artifacts.map(p => p.name)]) {
          const link = element('a', `下载 ${name}`);
          link.href = `/console/backups/${item.packageId}/${name}`;
          link.download = name; link.style.marginRight = '16px'; row.append(link);
        }
        const verify = element('button', '校验云端文件');
        verify.type = 'button';
        verify.onclick = async () => {
          verify.disabled = true;
          try { const checked = await api(`/console/backups/${item.packageId}/verify`, 'POST'); message.textContent = checked.verified ? `校验通过：${item.packageId}` : `校验失败：${item.packageId}`; }
          catch (error) { message.textContent = error.message; }
          finally { verify.disabled = false; }
        };
        row.append(verify); body.append(row);
      }
      if (result.events.length) body.append(element('p', '保留/容量事件：' + result.events.map(e => `${new Date(e.at * 1000).toLocaleString()} ${e.code}`).join('；')));
    } catch (error) { message.textContent = error.message; }
  };
  document.addEventListener('DOMContentLoaded', () => {
    const panel = element('details'); panel.id = 'cloudBackupPanel';
    panel.style.cssText = 'margin:16px;padding:12px;border:1px solid #888;border-radius:8px;overflow-wrap:anywhere';
    panel.append(element('summary', '异地备份（台账与配置）'));
    const refresh = element('button', '刷新列表'), request = element('button', '请求一次备份');
    refresh.type = request.type = 'button';
    const message = element('p'), body = element('div'); message.setAttribute('role', 'status');
    refresh.onclick = () => show(body, message);
    request.onclick = async () => {
      request.disabled = true;
      try { await api('/console/backups/request', 'POST'); message.textContent = '请求已排队；代理配置就绪后执行。稍后刷新列表查看。'; }
      catch (error) { message.textContent = error.message; }
      finally { request.disabled = false; }
    };
    panel.append(refresh, request, message, body);
    panel.addEventListener('toggle', () => { if (panel.open) show(body, message); });
    document.body.append(panel);
  });
})` — 云端；计划 **V2-1**；来源 [cloud/backups.js:2](../../cloud/backups.js#L2)。
  - 原实现：`(() => { const api = async (path, method = 'GET') => { const headers = {}; if (method !== 'GET') { const session = await fetch('/auth/session').then(r => r.json()); headers['X-CSRF-Token'] = session.csrf; } const response = await fetch(path, {method, headers}); if (!response.ok) throw new Error(ˋ请求失败 (${response.status})ˋ); return response.json(); }; const element = (tag, text) => { const node = document.createElement(tag); if`；实现/测试证据：待补。
- [x] **EVENT-076** `document.addEventListener` — 云端；计划 **V2-1**；来源 [cloud/backups.js:50](../../cloud/backups.js#L50)。
  - 原实现：`document.addEventListener('DOMContentLoaded', () => { const panel = element('details'); panel.id = 'cloudBackupPanel'; panel.style.cssText = 'margin:16px;padding:12px;border:1px solid #888;border-radius:8px;overflow-wrap:anywhere'; panel.append(element('summary', '异地备份（台账与配置）')); const refresh = element('button', '刷新列表'), request = element('button', '请求一次备份'); refresh.type = request.type = 'button'; const message = element('p'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **EVENT-077** `panel.addEventListener` — 云端；计划 **V2-1**；来源 [cloud/backups.js:65](../../cloud/backups.js#L65)。
  - 原实现：`panel.addEventListener('toggle', () => { if (panel.open) show(body, message); })`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [ ] **EVENT-078** `document.getElementById(id).addEventListener` — 云端；计划 **V2-4**；来源 [cloud/login.js:5](../../cloud/login.js#L5)。
  - 原实现：`document.getElementById(id).addEventListener('submit', async event => { event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button'); button.disabled = true; try { const response = await fetch(route, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(form)))}); if (!response.ok) { message.textContent = '未成功，请核对填写内容或稍后重试。'`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。

## routes（73 项）

- [x] **PATH-001** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:141](../../static/app.js#L141)。
  - 原实现：`"/api/safety"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-002** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:250](../../static/app.js#L250)。
  - 原实现：`"/api/controls/capcut-drafts"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-003** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:394](../../static/app.js#L394)。
  - 原实现：`"/api/controls/audio-files"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-004** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:586](../../static/app.js#L586)。
  - 原实现：`"/api/controls/production-files"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-005** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1137](../../static/app.js#L1137)。
  - 原实现：`ˋ/api/controls/tasks/${encodeURIComponent(taskId)}/replenishˋ`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **PATH-006** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:1518](../../static/app.js#L1518)。
  - 原实现：`"/api/control-commands/current"`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-007** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1589](../../static/app.js#L1589)。
  - 原实现：`ˋ/api/controls/tasks/${encodeURIComponent(taskId)}/${action}ˋ`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **PATH-008** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1646](../../static/app.js#L1646)。
  - 原实现：`"/api/dashboard/summary"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-009** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1646](../../static/app.js#L1646)。
  - 原实现：`ˋ/api/dashboard${params.toString() ? ˋ?${params}ˋ : ""}ˋ`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-010** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-1**；来源 [static/app.js:1693](../../static/app.js#L1693)。
  - 原实现：`"/api/health"`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-011** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1763](../../static/app.js#L1763)。
  - 原实现：`"/api/controls/capcut-drafts/preview"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-012** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1793](../../static/app.js#L1793)。
  - 原实现：`"/api/controls/capcut-drafts/cleanup"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-013** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1852](../../static/app.js#L1852)。
  - 原实现：`"/api/controls/audio-files/preview"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-014** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1885](../../static/app.js#L1885)。
  - 原实现：`"/api/controls/audio-files/recycle"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-015** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1948](../../static/app.js#L1948)。
  - 原实现：`"/api/controls/production-files/preview"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-016** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:1992](../../static/app.js#L1992)。
  - 原实现：`"/api/controls/production-files/recycle"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-017** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2020](../../static/app.js#L2020)。
  - 原实现：`"/api/controls/pending-delete"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-018** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2C**；来源 [static/app.js:2042](../../static/app.js#L2042)。
  - 原实现：`"/api/controls/pending-delete/empty"`；实现/测试证据：待补。 家里模式实现/隔离证据：V2-2C_CLEANUP_PARITY.md、cleanup.test、cleanup-filter-parity、home-cleanup-browser-check；PR #34。云端写入口留2D，非生产验收。
- [x] **PATH-019** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2E**；来源 [static/app.js:2068](../../static/app.js#L2068)。
  - 原实现：`"/api/control-commands"`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-020** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2089](../../static/app.js#L2089)。
  - 原实现：`"/api/controls/upload/rescan"`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **PATH-021** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2A**；来源 [static/app.js:2113](../../static/app.js#L2113)。
  - 原实现：`"/api/controls/upload/verify-history"`；实现/测试：V2-2A_UPLOAD_PARITY.md、uploads.test.tsx、upload-browser-check.cjs；PR #31，仅隔离；云端通用动作仍按各条未勾选项继续。
- [x] **PATH-022** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2131](../../static/app.js#L2131)。
  - 原实现：`"/api/controls/testing/reset"`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/ResetAction.tsx:18（home双确认、精确正文、结果/失败及清空日期任务箱选择，cloud禁用）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-023** `接口/动态路径` — 两者（写操作按模式分流）；计划 **V2-2B**；来源 [static/app.js:2159](../../static/app.js#L2159)。
  - 原实现：`"/api/controls/tasks/create"`；实现/测试证据：待补。 V2-2B_TASK_PARITY.md + tasks.test + task-browser-check，PR #32，仅隔离验收。
- [x] **PATH-024** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:25](../../cloud/readonly.js#L25)。
  - 原实现：`'/api/dashboard'`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-025** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:25](../../cloud/readonly.js#L25)。
  - 原实现：`'/api/dashboard/summary'`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-026** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:31](../../cloud/readonly.js#L31)。
  - 原实现：`'/api/dashboard'`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-027** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:50](../../cloud/readonly.js#L50)。
  - 原实现：`'/api/'`；实现：V2 数据层/原显示规则/React 只读视图；证据：client.test、parity.test、readonly-browser-check；PR #30；仅隔离验收。
- [x] **PATH-028** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:106](../../cloud/readonly.js#L106)。
  - 原实现：`'/auth/session'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-029** `接口/动态路径` — 云端；计划 **V2-2F**；来源 [cloud/readonly.js:107](../../cloud/readonly.js#L107)。
  - 原实现：`'/auth/logout'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-030** `接口/动态路径` — 云端；计划 **V2-2F**；来源 [cloud/readonly.js:115](../../cloud/readonly.js#L115)。
  - 原实现：`'/auth/password'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/AccountActions.tsx:6（已登录当前账号、密码字段、原错误/禁用、退出；401仍跳/login）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-031** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:134](../../cloud/readonly.js#L134)。
  - 原实现：`'/console/status'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/useDashboard.ts:197（共享只读轮询与状态、完整看板定时刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-032** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/health'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-033** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/dashboard'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-034** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/dashboard/summary'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-035** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/task-boxes/current'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-036** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/task-boxes/history'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-037** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/controls/tasks'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-038** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/controls/templates'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-039** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/safety'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-040** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/project-gaps'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-041** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/pipeline'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-042** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/controls/continue-current/status'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-043** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/control-commands/current'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-044** `接口/动态路径` — 云端；计划 **V2-1**；来源 [cloud/readonly.js:157](../../cloud/readonly.js#L157)。
  - 原实现：`'/api/subtitle-verification/current'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:69（数据来源、名称、年龄和新鲜度颜色）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-045** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:13](../../cloud/commands.js#L13)。
  - 原实现：`'/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-046** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:24](../../cloud/commands.js#L24)。
  - 原实现：`'/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-047** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:37](../../cloud/commands.js#L37)。
  - 原实现：`'/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-048** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:39](../../cloud/commands.js#L39)。
  - 原实现：`'/api/control-commands/'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-049** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:39](../../cloud/commands.js#L39)。
  - 原实现：`'/api/control-commands/current'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-050** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:41](../../cloud/commands.js#L41)。
  - 原实现：`'/auth/session'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-051** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:48](../../cloud/commands.js#L48)。
  - 原实现：`'/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-052** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:54](../../cloud/commands.js#L54)。
  - 原实现：`'/console/commands/'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-053** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:54](../../cloud/commands.js#L54)。
  - 原实现：`'/console/commands/request/'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-054** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:68](../../cloud/commands.js#L68)。
  - 原实现：`'/api/controls/cloud-cleanup/preview'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-055** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:69](../../cloud/commands.js#L69)。
  - 原实现：`'/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-056** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:77](../../cloud/commands.js#L77)。
  - 原实现：`'/api/control-commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-057** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:87](../../cloud/commands.js#L87)。
  - 原实现：`'/cloud-cleanup/execute'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-058** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:108](../../cloud/commands.js#L108)。
  - 原实现：`'/console/commands/'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-059** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:108](../../cloud/commands.js#L108)。
  - 原实现：`'/console/commands/request/'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-060** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:114](../../cloud/commands.js#L114)。
  - 原实现：`'/console/commands/'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-061** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:128](../../cloud/commands.js#L128)。
  - 原实现：`'/console/submission-requests/'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-062** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:132](../../cloud/commands.js#L132)。
  - 原实现：`'/console/status'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-063** `接口/动态路径` — 云端；计划 **V2-2A**；来源 [cloud/commands.js:135](../../cloud/commands.js#L135)。
  - 原实现：`'/console/commands'`；实现/测试证据：待补。 V2-2E隔离证据：V2-2E_SAFE_CONTINUE_PARITY.md、safe-continue.test、safe-continue-browser-check；PR #36。必须用户亲自确认后才可合并，非生产验收。
- [x] **PATH-064** `接口/动态路径` — 云端；计划 **V2-2D**；来源 [cloud/cleanup.js:4](../../cloud/cleanup.js#L4)。
  - 原实现：`'/api/controls/cloud-cleanup/'`；实现/测试证据：待补。 云端实现/隔离证据：V2-2D_CLOUD_CLEANUP_PARITY.md、cloud-cleanup.test、poll-merge.test、cloud-cleanup-browser-check；PR #35。仅三类与待删区，非生产验收。
- [x] **PATH-065** `接口/动态路径` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:6](../../cloud/backups.js#L6)。
  - 原实现：`'/auth/session'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/data/console-admin.ts:11（账号CSRF及原方法/状态码；读取目录仍用GET）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-066** `接口/动态路径` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:20](../../cloud/backups.js#L20)。
  - 原实现：`'/console/backups'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:215（目录、加密下载链接、容量、日期/阶段、事件及空状态）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-067** `接口/动态路径` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:34](../../cloud/backups.js#L34)。
  - 原实现：`ˋ/console/backups/${item.packageId}/${name}ˋ`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/CloudViews.tsx:215（目录、加密下载链接、容量、日期/阶段、事件及空状态）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-068** `接口/动态路径` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:41](../../cloud/backups.js#L41)。
  - 原实现：`ˋ/console/backups/${item.packageId}/verifyˋ`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（逐包校验与失败提示、防重复）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [x] **PATH-069** `接口/动态路径` — 云端；计划 **V2-2F**；来源 [cloud/backups.js:60](../../cloud/backups.js#L60)。
  - 原实现：`'/console/backups/request'`；实现/测试证据：待补。 完整子功能复核：frontend-v2/src/components/views/BackupAction.tsx:15（请求一次备份、排队反馈；目录按需展开和刷新）；PR #37、V2-2F_ADMIN_PARITY.md；仅隔离范围。
- [ ] **PATH-070** `接口/动态路径` — 云端；计划 **V2-4**；来源 [cloud/login.js:3](../../cloud/login.js#L3)。
  - 原实现：`'/auth/options'`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **PATH-071** `接口/动态路径` — 云端；计划 **V2-4**；来源 [cloud/login.js:4](../../cloud/login.js#L4)。
  - 原实现：`'/auth/login'`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **PATH-072** `接口/动态路径` — 云端；计划 **V2-4**；来源 [cloud/login.js:4](../../cloud/login.js#L4)。
  - 原实现：`'/auth/register'`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。
- [ ] **PATH-073** `接口/动态路径` — 云端；计划 **V2-4**；来源 [cloud/login.js:12](../../cloud/login.js#L12)。
  - 原实现：`'/auth/login'`；实现/测试证据：待补。 用户2026-10-20明确延后：本轮沿用/login含邀请码注册及401跳转；V2-4随单独cloud PR迁移，不算遗漏。

## 原文件完整性

- `static/app.js` SHA256 `01a5fbb10dd53adbbb4f64d369d5c72004f650e550dbfff1a8cd997c4ecf3013`
- `static/index.html` SHA256 `8ea07e3c6f73453b5e48ce0339c5defca8d470790ae4ea705046d47929a2478a`
- `cloud/readonly.js` SHA256 `a73ebacd977ae1c28b2bb100d6cb46a6626fd7f039ab1b2b8df4486eb7fc2a21`
- `cloud/commands.js` SHA256 `f4ad6aa59252816b33766dbd48de913f3344a4fb22348bafc4d4a95e4cdf1ca7`
- `cloud/cleanup.js` SHA256 `7d62d1aed018727e87929eaf41a2cc4b94f1306b564c852271abdc77f1b6332d`
- `cloud/backups.js` SHA256 `190fd1ed3af0b38ca76fe0e08118af20c159f2c0ba4501c7a2f98f7cc45d01c3`
- `cloud/login.js` SHA256 `a4ac15bfd1cc76bbd5b065ebca9555ed3e70580d632f698419114a1605d5752c`
- `cloud/login.html` SHA256 `ff36a3e3ceea28f03adff166b8d3e022be5566830cf9a69a2af8df4be7b48b38`

机器可读逐项账本见 [inventory.json](inventory.json)。任何未勾选、未覆盖的分支都必须保留为待办，不能以通用占位面板记为完成。
