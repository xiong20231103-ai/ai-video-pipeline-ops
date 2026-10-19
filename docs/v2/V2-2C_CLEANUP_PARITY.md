# V2-2C 家里三类清理与四项审查修复

仅前端。三类现有接口为唯一清单/预览/执行来源；复用已部署 H2 待删区，不增加删除逻辑、五类目录或后端接口。云端仅 GET 清单，所有家里清理 POST 在云端模式拒绝。云端清理票据属于后续2D，本 PR 不启用。

## 原实现逐行对照

| app.js 行 | 原代码 | V2 对应位置与语义 |
|---|---|---|
| [152](../../static/app.js#L152) | `function draftCategoryLabel(value) {` | [FileManagers.tsx:391](../../frontend-v2/src/components/views/FileManagers.tsx#L391)：原草稿分类中文含义 |
| [153](../../static/app.js#L153) | `if (value === "formal") return "正式自动";` | [FileManagers.tsx:391](../../frontend-v2/src/components/views/FileManagers.tsx#L391)：原草稿分类中文含义 |
| [154](../../static/app.js#L154) | `if (value === "lab") return "内测";` | [FileManagers.tsx:391](../../frontend-v2/src/components/views/FileManagers.tsx#L391)：原草稿分类中文含义 |
| [155](../../static/app.js#L155) | `return "人工/不明";` | [FileManagers.tsx:391](../../frontend-v2/src/components/views/FileManagers.tsx#L391)：原草稿分类中文含义 |
| [156](../../static/app.js#L156) | `}` | [FileManagers.tsx:391](../../frontend-v2/src/components/views/FileManagers.tsx#L391)：原草稿分类中文含义 |
| [158](../../static/app.js#L158) | `function draftDateKey(value) {` | [home-cleanup.ts:32](../../frontend-v2/src/data/home-cleanup.ts#L32)：相同本地日期算法 |
| [159](../../static/app.js#L159) | `const date = new Date(value ¦¦ "");` | [home-cleanup.ts:32](../../frontend-v2/src/data/home-cleanup.ts#L32)：相同本地日期算法 |
| [160](../../static/app.js#L160) | `if (Number.isNaN(date.getTime())) return "";` | [home-cleanup.ts:32](../../frontend-v2/src/data/home-cleanup.ts#L32)：相同本地日期算法 |
| [161](../../static/app.js#L161) | `const month = String(date.getMonth() + 1).padStart(2, "0");` | [home-cleanup.ts:32](../../frontend-v2/src/data/home-cleanup.ts#L32)：相同本地日期算法 |
| [162](../../static/app.js#L162) | `const day = String(date.getDate()).padStart(2, "0");` | [home-cleanup.ts:32](../../frontend-v2/src/data/home-cleanup.ts#L32)：相同本地日期算法 |
| [163](../../static/app.js#L163) | `return ˋ${date.getFullYear()}-${month}-${day}ˋ;` | [home-cleanup.ts:32](../../frontend-v2/src/data/home-cleanup.ts#L32)：相同本地日期算法 |
| [164](../../static/app.js#L164) | `}` | [home-cleanup.ts:32](../../frontend-v2/src/data/home-cleanup.ts#L32)：相同本地日期算法 |
| [166](../../static/app.js#L166) | `function renderDraftDateFilter() {` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [167](../../static/app.js#L167) | `const select = $("draftDateFilter");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [168](../../static/app.js#L168) | `if (!select) return;` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [169](../../static/app.js#L169) | `const selected = select.value ¦¦ "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [170](../../static/app.js#L170) | `const counts = new Map();` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [171](../../static/app.js#L171) | `state.drafts.forEach(item => {` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [172](../../static/app.js#L172) | `const key = draftDateKey(item.updatedAt ¦¦ item.createdAt);` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [173](../../static/app.js#L173) | `if (key) counts.set(key, (counts.get(key) ¦¦ 0) + 1);` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [174](../../static/app.js#L174) | `});` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [175](../../static/app.js#L175) | `const dates = [...counts.keys()].sort((a, b) => b.localeCompare(a));` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [176](../../static/app.js#L176) | `select.innerHTML = [` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [177](../../static/app.js#L177) | `ˋ<option value="">全部日期（${state.drafts.length}）</option>ˋ,` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [178](../../static/app.js#L178) | `...dates.map(value =>` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [179](../../static/app.js#L179) | `ˋ<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>ˋ` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [180](../../static/app.js#L180) | `)` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [181](../../static/app.js#L181) | `].join("");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [182](../../static/app.js#L182) | `select.value = dates.includes(selected) ? selected : "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [183](../../static/app.js#L183) | `}` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [185](../../static/app.js#L185) | `function filteredDrafts() {` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [186](../../static/app.js#L186) | `const category = $("draftCategoryFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [187](../../static/app.js#L187) | `const date = $("draftDateFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [188](../../static/app.js#L188) | `const query = ($("draftSearchFilter")?.value ¦¦ "").trim().toLocaleLowerCase();` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [189](../../static/app.js#L189) | `return state.drafts.filter(item => {` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [190](../../static/app.js#L190) | `if (category && item.category !== category) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [191](../../static/app.js#L191) | `if (date && draftDateKey(item.updatedAt ¦¦ item.createdAt) !== date) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [192](../../static/app.js#L192) | `if (query && !ˋ${item.name ¦¦ ""} ${item.sourceLabel ¦¦ ""}ˋ.toLocaleLowerCase().includes(query)) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [193](../../static/app.js#L193) | `return true;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [194](../../static/app.js#L194) | `});` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [195](../../static/app.js#L195) | `}` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [197](../../static/app.js#L197) | `function resetDraftPreview() {` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [198](../../static/app.js#L198) | `state.draftPreview = null;` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [199](../../static/app.js#L199) | `$("draftCleanupPreview")?.classList.add("hidden");` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [200](../../static/app.js#L200) | `$("confirmDraftCleanupButton")?.classList.add("hidden");` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [201](../../static/app.js#L201) | `}` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [203](../../static/app.js#L203) | `function updateDraftSelectionSummary() {` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [204](../../static/app.js#L204) | `const selected = state.drafts.filter(item => state.selectedDraftIds.has(item.draftId));` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [205](../../static/app.js#L205) | `const size = selected.reduce((total, item) => total + Number(item.sizeBytes ¦¦ 0), 0);` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [206](../../static/app.js#L206) | `const node = $("draftSelectionSummary");` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [207](../../static/app.js#L207) | `if (node) node.textContent = ˋ已选择 ${selected.length} 个 · ${formatBytes(size)}ˋ;` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [208](../../static/app.js#L208) | `}` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [210](../../static/app.js#L210) | `function renderDraftManager() {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [211](../../static/app.js#L211) | `const node = $("draftManagerList");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [212](../../static/app.js#L212) | `if (!node) return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [213](../../static/app.js#L213) | `const items = filteredDrafts();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [214](../../static/app.js#L214) | `if (!items.length) {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [215](../../static/app.js#L215) | `node.innerHTML = ˋ<p class="empty">当前筛选条件下没有草稿</p>ˋ;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [216](../../static/app.js#L216) | `updateDraftSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [217](../../static/app.js#L217) | `return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [218](../../static/app.js#L218) | `}` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [219](../../static/app.js#L219) | `node.innerHTML = items.map(item => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [220](../../static/app.js#L220) | `const checked = state.selectedDraftIds.has(item.draftId) ? "checked" : "";` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [221](../../static/app.js#L221) | `const disabled = item.protected ? "disabled" : "";` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [222](../../static/app.js#L222) | `const detail = item.protected ? item.protectedReason : (item.inIndex ? "索引正常" : "目录未登记在首页索引");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [223](../../static/app.js#L223) | `return ˋ<label class="draft-manager-row ${item.protected ? "protected" : ""}" title="${escapeHtml(detail)}">` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [224](../../static/app.js#L224) | `<input type="checkbox" data-draft-id="${escapeHtml(item.draftId)}" ${checked} ${disabled}>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [225](../../static/app.js#L225) | `<strong>${escapeHtml(item.name ¦¦ "未命名草稿")}</strong>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [226](../../static/app.js#L226) | `<span class="draft-category ${escapeHtml(item.category)}">${escapeHtml(draftCategoryLabel(item.category))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [227](../../static/app.js#L227) | `<span>${escapeHtml(formatDateTime(item.updatedAt ¦¦ item.createdAt))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [228](../../static/app.js#L228) | `<span>${escapeHtml(formatBytes(item.sizeBytes))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [229](../../static/app.js#L229) | `<span class="draft-source">${escapeHtml(item.sourceLabel ¦¦ detail)}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [230](../../static/app.js#L230) | `</label>ˋ;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [231](../../static/app.js#L231) | `}).join("");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [232](../../static/app.js#L232) | `node.querySelectorAll("input[data-draft-id]").forEach(input => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [233](../../static/app.js#L233) | `input.addEventListener("change", event => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [234](../../static/app.js#L234) | `const draftId = event.currentTarget.dataset.draftId;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [235](../../static/app.js#L235) | `if (event.currentTarget.checked) state.selectedDraftIds.add(draftId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [236](../../static/app.js#L236) | `else state.selectedDraftIds.delete(draftId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [237](../../static/app.js#L237) | `resetDraftPreview();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [238](../../static/app.js#L238) | `updateDraftSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [239](../../static/app.js#L239) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [240](../../static/app.js#L240) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [241](../../static/app.js#L241) | `updateDraftSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [242](../../static/app.js#L242) | `}` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [244](../../static/app.js#L244) | `async function loadDraftManager() {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [245](../../static/app.js#L245) | `const button = $("openDraftManagerButton");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [246](../../static/app.js#L246) | `const refreshButton = $("refreshDraftManagerButton");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [247](../../static/app.js#L247) | `if (button) { button.disabled = true; button.textContent = "正在读取草稿…"; }` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [248](../../static/app.js#L248) | `if (refreshButton) refreshButton.disabled = true;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [249](../../static/app.js#L249) | `try {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [250](../../static/app.js#L250) | `const payload = await getJson("/api/controls/capcut-drafts", 1, 60000);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [251](../../static/app.js#L251) | `state.drafts = payload.items ¦¦ [];` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [252](../../static/app.js#L252) | `state.draftSnapshot = payload.snapshotToken ¦¦ "";` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [253](../../static/app.js#L253) | `renderDraftDateFilter();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [254](../../static/app.js#L254) | `state.selectedDraftIds = new Set(` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [255](../../static/app.js#L255) | `[...state.selectedDraftIds].filter(id => state.drafts.some(item => item.draftId === id && !item.protected))` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [256](../../static/app.js#L256) | `);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [257](../../static/app.js#L257) | `resetDraftPreview();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [258](../../static/app.js#L258) | `renderDraftManager();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [259](../../static/app.js#L259) | `const count = $("draftManagerCount");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [260](../../static/app.js#L260) | `if (count) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [261](../../static/app.js#L261) | `count.textContent = ˋ${payload.counts?.total ¦¦ 0} 个ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [262](../../static/app.js#L262) | `count.className = ˋtask-state ${(payload.runningProcesses ¦¦ []).length ? "failed" : "neutral"}ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [263](../../static/app.js#L263) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [264](../../static/app.js#L264) | `} catch (error) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [265](../../static/app.js#L265) | `$("draftManagerList").innerHTML = ˋ<p class="empty">${escapeHtml(error.message ¦¦ "读取草稿失败")}</p>ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [266](../../static/app.js#L266) | `} finally {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [267](../../static/app.js#L267) | `if (button) { button.disabled = false; button.textContent = "管理 CapCut 草稿"; }` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [268](../../static/app.js#L268) | `if (refreshButton) refreshButton.disabled = false;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [269](../../static/app.js#L269) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [272](../../static/app.js#L272) | `function populateAudioFilter(id, values, label) {` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [273](../../static/app.js#L273) | `const select = $(id);` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [274](../../static/app.js#L274) | `if (!select) return;` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [275](../../static/app.js#L275) | `const selected = select.value ¦¦ "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [276](../../static/app.js#L276) | `const counts = new Map();` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [277](../../static/app.js#L277) | `values.filter(Boolean).forEach(value => counts.set(value, (counts.get(value) ¦¦ 0) + 1));` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [278](../../static/app.js#L278) | `const options = [...counts.keys()].sort((a, b) => a.localeCompare(b, "zh-CN"));` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [279](../../static/app.js#L279) | `select.innerHTML = [` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [280](../../static/app.js#L280) | `ˋ<option value="">全部${escapeHtml(label)}（${state.audioFiles.length}）</option>ˋ,` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [281](../../static/app.js#L281) | `...options.map(value => ˋ<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>ˋ)` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [282](../../static/app.js#L282) | `].join("");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [283](../../static/app.js#L283) | `select.value = options.includes(selected) ? selected : "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [284](../../static/app.js#L284) | `}` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [286](../../static/app.js#L286) | `function renderAudioFilters() {` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [287](../../static/app.js#L287) | `populateAudioFilter("audioDateFilter", state.audioFiles.map(item => item.date ¦¦ draftDateKey(item.updatedAt)), "日期");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [288](../../static/app.js#L288) | `populateAudioFilter("audioProjectFilter", state.audioFiles.map(item => item.project), "项目");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [289](../../static/app.js#L289) | `populateAudioFilter("audioMaterialFilter", state.audioFiles.map(item => item.material), "材料");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [290](../../static/app.js#L290) | `populateAudioFilter("audioLanguageFilter", state.audioFiles.map(item => item.language), "语言");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [291](../../static/app.js#L291) | `populateAudioFilter("audioBatchFilter", state.audioFiles.map(item => item.audioBatch), "批次");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [292](../../static/app.js#L292) | `}` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [294](../../static/app.js#L294) | `function filteredAudioFiles() {` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [295](../../static/app.js#L295) | `const date = $("audioDateFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [296](../../static/app.js#L296) | `const project = $("audioProjectFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [297](../../static/app.js#L297) | `const material = $("audioMaterialFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [298](../../static/app.js#L298) | `const language = $("audioLanguageFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [299](../../static/app.js#L299) | `const batch = $("audioBatchFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [300](../../static/app.js#L300) | `const taskState = $("audioStateFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [301](../../static/app.js#L301) | `const query = ($("audioSearchFilter")?.value ¦¦ "").trim().toLocaleLowerCase();` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [302](../../static/app.js#L302) | `return state.audioFiles.filter(item => {` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [303](../../static/app.js#L303) | `const itemDate = item.date ¦¦ draftDateKey(item.updatedAt);` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [304](../../static/app.js#L304) | `if (date && itemDate !== date) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [305](../../static/app.js#L305) | `if (project && item.project !== project) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [306](../../static/app.js#L306) | `if (material && item.material !== material) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [307](../../static/app.js#L307) | `if (language && item.language !== language) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [308](../../static/app.js#L308) | `if (batch && item.audioBatch !== batch) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [309](../../static/app.js#L309) | `if (taskState === "deletable" && item.protected) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [310](../../static/app.js#L310) | `if (taskState === "protected" && !item.protected) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [311](../../static/app.js#L311) | `const haystack = ˋ${item.name ¦¦ ""} ${item.relativePath ¦¦ ""} ${item.project ¦¦ ""} ${item.material ¦¦ ""} ${item.language ¦¦ ""}ˋ.toLocaleLowerCase();` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [312](../../static/app.js#L312) | `if (query && !haystack.includes(query)) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [313](../../static/app.js#L313) | `return true;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [314](../../static/app.js#L314) | `});` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [315](../../static/app.js#L315) | `}` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [317](../../static/app.js#L317) | `function resetAudioPreview() {` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [318](../../static/app.js#L318) | `state.audioPreview = null;` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [319](../../static/app.js#L319) | `$("audioCleanupPreview")?.classList.add("hidden");` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [320](../../static/app.js#L320) | `$("confirmAudioCleanupButton")?.classList.add("hidden");` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [321](../../static/app.js#L321) | `}` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [323](../../static/app.js#L323) | `function updateAudioSelectionSummary() {` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [324](../../static/app.js#L324) | `const selected = state.audioFiles.filter(item => state.selectedAudioIds.has(item.audioId));` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [325](../../static/app.js#L325) | `const size = selected.reduce((total, item) => total + Number(item.sizeBytes ¦¦ 0), 0);` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [326](../../static/app.js#L326) | `const node = $("audioSelectionSummary");` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [327](../../static/app.js#L327) | `if (node) node.textContent = ˋ已选择 ${selected.length} 个 · ${formatBytes(size)}ˋ;` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [328](../../static/app.js#L328) | `}` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [330](../../static/app.js#L330) | `function audioIdentity(item) {` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [331](../../static/app.js#L331) | `return [item.project, item.material, item.language].filter(Boolean).join(" / ") ¦¦ "历史或未登记任务";` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [332](../../static/app.js#L332) | `}` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [334](../../static/app.js#L334) | `function showAudioProtection(item) {` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [335](../../static/app.js#L335) | `const identity = audioIdentity(item);` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [336](../../static/app.js#L336) | `const reason = item.protectedReason ¦¦ "任务正在使用，禁止删除";` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [337](../../static/app.js#L337) | `$("audioProtectionIdentity").textContent = identity;` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [338](../../static/app.js#L338) | `$("audioProtectionState").textContent = item.taskState ¦¦ "等待恢复";` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [339](../../static/app.js#L339) | `$("audioProtectionReason").textContent = reason;` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [340](../../static/app.js#L340) | `const dialog = $("audioProtectionDialog");` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [341](../../static/app.js#L341) | `if (dialog && !dialog.open) dialog.showModal();` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [342](../../static/app.js#L342) | `}` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [344](../../static/app.js#L344) | `function renderAudioManager() {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [345](../../static/app.js#L345) | `const node = $("audioManagerList");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [346](../../static/app.js#L346) | `if (!node) return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [347](../../static/app.js#L347) | `const items = filteredAudioFiles();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [348](../../static/app.js#L348) | `if (!items.length) {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [349](../../static/app.js#L349) | `node.innerHTML = ˋ<p class="empty">当前筛选条件下没有音频文件</p>ˋ;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [350](../../static/app.js#L350) | `updateAudioSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [351](../../static/app.js#L351) | `return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [352](../../static/app.js#L352) | `}` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [353](../../static/app.js#L353) | `node.innerHTML = items.map(item => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [354](../../static/app.js#L354) | `const checked = state.selectedAudioIds.has(item.audioId) ? "checked" : "";` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [355](../../static/app.js#L355) | `const disabled = item.protected ? "disabled" : "";` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [356](../../static/app.js#L356) | `const stateLabel = item.protected ? "任务正在使用，禁止删除" : "可手动删除";` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [357](../../static/app.js#L357) | `return ˋ<div class="draft-manager-row audio-manager-row ${item.protected ? "protected" : ""}"` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [358](../../static/app.js#L358) | `data-audio-row-id="${escapeHtml(item.audioId)}" title="${escapeHtml(item.protectedReason ¦¦ stateLabel)}">` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [359](../../static/app.js#L359) | `<input type="checkbox" data-audio-id="${escapeHtml(item.audioId)}" ${checked} ${disabled}>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [360](../../static/app.js#L360) | `<strong>${escapeHtml(item.name ¦¦ "未命名音频")}</strong>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [361](../../static/app.js#L361) | `<span class="audio-protection ${item.protected ? "protected" : "deletable"}">${escapeHtml(stateLabel)}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [362](../../static/app.js#L362) | `<span>${escapeHtml(item.date ¦¦ "--")} · ${escapeHtml(formatDateTime(item.updatedAt ¦¦ item.createdAt))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [363](../../static/app.js#L363) | `<span>${escapeHtml(formatBytes(item.sizeBytes))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [364](../../static/app.js#L364) | `<span class="audio-identity">${escapeHtml(audioIdentity(item))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [365](../../static/app.js#L365) | `<span class="draft-source">${escapeHtml(item.relativePath ¦¦ "")}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [366](../../static/app.js#L366) | `</div>ˋ;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [367](../../static/app.js#L367) | `}).join("");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [368](../../static/app.js#L368) | `node.querySelectorAll("input[data-audio-id]").forEach(input => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [369](../../static/app.js#L369) | `input.addEventListener("change", event => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [370](../../static/app.js#L370) | `const audioId = event.currentTarget.dataset.audioId;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [371](../../static/app.js#L371) | `if (event.currentTarget.checked) state.selectedAudioIds.add(audioId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [372](../../static/app.js#L372) | `else state.selectedAudioIds.delete(audioId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [373](../../static/app.js#L373) | `resetAudioPreview();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [374](../../static/app.js#L374) | `updateAudioSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [375](../../static/app.js#L375) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [376](../../static/app.js#L376) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [377](../../static/app.js#L377) | `node.querySelectorAll("[data-audio-row-id]").forEach(row => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [378](../../static/app.js#L378) | `row.addEventListener("click", event => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [379](../../static/app.js#L379) | `const item = state.audioFiles.find(value => value.audioId === row.dataset.audioRowId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [380](../../static/app.js#L380) | `if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [381](../../static/app.js#L381) | `event.preventDefault();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [382](../../static/app.js#L382) | `showAudioProtection(item);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [383](../../static/app.js#L383) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [384](../../static/app.js#L384) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [385](../../static/app.js#L385) | `updateAudioSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [386](../../static/app.js#L386) | `}` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [388](../../static/app.js#L388) | `async function loadAudioManager() {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [389](../../static/app.js#L389) | `const button = $("openAudioManagerButton");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [390](../../static/app.js#L390) | `const refreshButton = $("refreshAudioManagerButton");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [391](../../static/app.js#L391) | `if (button) { button.disabled = true; button.textContent = "正在读取音频…"; }` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [392](../../static/app.js#L392) | `if (refreshButton) refreshButton.disabled = true;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [393](../../static/app.js#L393) | `try {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [394](../../static/app.js#L394) | `const payload = await getJson("/api/controls/audio-files", 1, 60000);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [395](../../static/app.js#L395) | `state.audioFiles = payload.items ¦¦ [];` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [396](../../static/app.js#L396) | `state.audioSnapshot = payload.snapshotToken ¦¦ "";` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [397](../../static/app.js#L397) | `renderAudioFilters();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [398](../../static/app.js#L398) | `state.selectedAudioIds = new Set(` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [399](../../static/app.js#L399) | `[...state.selectedAudioIds].filter(id =>` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [400](../../static/app.js#L400) | `state.audioFiles.some(item => item.audioId === id && !item.protected)` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [401](../../static/app.js#L401) | `)` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [402](../../static/app.js#L402) | `);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [403](../../static/app.js#L403) | `resetAudioPreview();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [404](../../static/app.js#L404) | `renderAudioManager();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [405](../../static/app.js#L405) | `const count = $("audioManagerCount");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [406](../../static/app.js#L406) | `if (count) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [407](../../static/app.js#L407) | `const protectedCount = Number(payload.counts?.protected ¦¦ 0);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [408](../../static/app.js#L408) | `count.textContent = ˋ${payload.counts?.total ¦¦ 0} 个ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [409](../../static/app.js#L409) | `count.className = ˋtask-state ${protectedCount ? "failed" : "neutral"}ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [410](../../static/app.js#L410) | `count.title = protectedCount ? ˋ${protectedCount} 个正在被任务使用ˋ : "当前没有受保护音频";` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [411](../../static/app.js#L411) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [412](../../static/app.js#L412) | `} catch (error) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [413](../../static/app.js#L413) | `$("audioManagerList").innerHTML = ˋ<p class="empty">${escapeHtml(error.message ¦¦ "读取音频失败")}</p>ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [414](../../static/app.js#L414) | `} finally {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [415](../../static/app.js#L415) | `if (button) { button.disabled = false; button.textContent = "管理音频文件"; }` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [416](../../static/app.js#L416) | `if (refreshButton) refreshButton.disabled = false;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [417](../../static/app.js#L417) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [418](../../static/app.js#L418) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [420](../../static/app.js#L420) | `function populateProductionFilter(id, values, label) {` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [421](../../static/app.js#L421) | `const select = $(id);` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [422](../../static/app.js#L422) | `if (!select) return;` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [423](../../static/app.js#L423) | `const selected = select.value ¦¦ "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [424](../../static/app.js#L424) | `const counts = new Map();` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [425](../../static/app.js#L425) | `values.filter(Boolean).forEach(value => counts.set(value, (counts.get(value) ¦¦ 0) + 1));` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [426](../../static/app.js#L426) | `const options = [...counts.keys()].sort((a, b) => a.localeCompare(b, "zh-CN"));` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [427](../../static/app.js#L427) | `select.innerHTML = [` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [428](../../static/app.js#L428) | `ˋ<option value="">全部${escapeHtml(label)}（${state.productionFiles.length}）</option>ˋ,` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [429](../../static/app.js#L429) | `...options.map(value => ˋ<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>ˋ)` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [430](../../static/app.js#L430) | `].join("");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [431](../../static/app.js#L431) | `select.value = options.includes(selected) ? selected : "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [432](../../static/app.js#L432) | `}` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [434](../../static/app.js#L434) | `function renderProductionFilters() {` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [435](../../static/app.js#L435) | `populateProductionFilter(` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [436](../../static/app.js#L436) | `"productionDateFilter",` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [437](../../static/app.js#L437) | `state.productionFiles.map(item => item.date ¦¦ draftDateKey(item.updatedAt)),` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [438](../../static/app.js#L438) | `"日期"` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [439](../../static/app.js#L439) | `);` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [440](../../static/app.js#L440) | `populateProductionFilter("productionProjectFilter", state.productionFiles.map(item => item.project), "项目");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [441](../../static/app.js#L441) | `populateProductionFilter("productionMaterialFilter", state.productionFiles.map(item => item.material), "材料");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [442](../../static/app.js#L442) | `const select = $("productionCategoryFilter");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [443](../../static/app.js#L443) | `if (select) {` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [444](../../static/app.js#L444) | `const selected = select.value ¦¦ "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [445](../../static/app.js#L445) | `const categories = state.productionCounts?.categories ¦¦ {};` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [446](../../static/app.js#L446) | `select.innerHTML = [` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [447](../../static/app.js#L447) | `ˋ<option value="">全部类型（${state.productionFiles.length}）</option>ˋ,` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [448](../../static/app.js#L448) | `...Object.entries(categories).map(([key, value]) =>` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [449](../../static/app.js#L449) | `ˋ<option value="${escapeHtml(key)}">${escapeHtml(value.label ¦¦ key)}（${Number(value.total ¦¦ 0)}）</option>ˋ` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [450](../../static/app.js#L450) | `)` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [451](../../static/app.js#L451) | `].join("");` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [452](../../static/app.js#L452) | `select.value = Object.hasOwn(categories, selected) ? selected : "";` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [453](../../static/app.js#L453) | `}` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [454](../../static/app.js#L454) | `}` | [FileManagers.tsx:348](../../frontend-v2/src/components/views/FileManagers.tsx#L348)：筛选选项、排序、数量及重置无效筛选 |
| [456](../../static/app.js#L456) | `function renderProductionCategorySummary() {` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [457](../../static/app.js#L457) | `const node = $("productionCategorySummary");` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [458](../../static/app.js#L458) | `if (!node) return;` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [459](../../static/app.js#L459) | `const categories = state.productionCounts?.categories ¦¦ {};` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [460](../../static/app.js#L460) | `const rows = Object.entries(categories);` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [461](../../static/app.js#L461) | `if (!rows.length) {` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [462](../../static/app.js#L462) | `node.innerHTML = ˋ<p class="empty">没有发现已登记的生产文件</p>ˋ;` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [463](../../static/app.js#L463) | `return;` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [464](../../static/app.js#L464) | `}` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [465](../../static/app.js#L465) | `node.innerHTML = rows.map(([key, value]) =>` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [466](../../static/app.js#L466) | `ˋ<button type="button" class="production-category-card" data-production-category="${escapeHtml(key)}">` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [467](../../static/app.js#L467) | `<span>${escapeHtml(value.label ¦¦ key)}</span>` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [468](../../static/app.js#L468) | `<strong>${Number(value.total ¦¦ 0)} 个 · ${escapeHtml(formatBytes(value.sizeBytes))}</strong>` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [469](../../static/app.js#L469) | `<small>可清理 ${Number(value.deletable ¦¦ 0)} · 保护 ${Number(value.protected ¦¦ 0)}</small>` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [470](../../static/app.js#L470) | `</button>ˋ` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [471](../../static/app.js#L471) | `).join("");` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [472](../../static/app.js#L472) | `node.querySelectorAll("[data-production-category]").forEach(button => {` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [473](../../static/app.js#L473) | `button.addEventListener("click", () => {` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [474](../../static/app.js#L474) | `const select = $("productionCategoryFilter");` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [475](../../static/app.js#L475) | `if (select) select.value = button.dataset.productionCategory ¦¦ "";` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [476](../../static/app.js#L476) | `resetProductionPreview();` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [477](../../static/app.js#L477) | `renderProductionManager();` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [478](../../static/app.js#L478) | `});` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [479](../../static/app.js#L479) | `});` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [480](../../static/app.js#L480) | `}` | [FileManagers.tsx:327](../../frontend-v2/src/components/views/FileManagers.tsx#L327)：服务器分类数量/容量及点击筛选 |
| [482](../../static/app.js#L482) | `function filteredProductionFiles() {` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [483](../../static/app.js#L483) | `const date = $("productionDateFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [484](../../static/app.js#L484) | `const project = $("productionProjectFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [485](../../static/app.js#L485) | `const material = $("productionMaterialFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [486](../../static/app.js#L486) | `const category = $("productionCategoryFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [487](../../static/app.js#L487) | `const taskState = $("productionStateFilter")?.value ¦¦ "";` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [488](../../static/app.js#L488) | `const query = ($("productionSearchFilter")?.value ¦¦ "").trim().toLocaleLowerCase();` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [489](../../static/app.js#L489) | `return state.productionFiles.filter(item => {` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [490](../../static/app.js#L490) | `const itemDate = item.date ¦¦ draftDateKey(item.updatedAt);` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [491](../../static/app.js#L491) | `if (date && itemDate !== date) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [492](../../static/app.js#L492) | `if (project && item.project !== project) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [493](../../static/app.js#L493) | `if (material && item.material !== material) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [494](../../static/app.js#L494) | `if (category && item.category !== category) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [495](../../static/app.js#L495) | `if (taskState === "deletable" && item.protected) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [496](../../static/app.js#L496) | `if (taskState === "protected" && !item.protected) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [497](../../static/app.js#L497) | `const haystack = [` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [498](../../static/app.js#L498) | `item.name, item.relativePath, item.categoryLabel, item.project,` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [499](../../static/app.js#L499) | `item.material, item.language, item.taskState` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [500](../../static/app.js#L500) | `].join(" ").toLocaleLowerCase();` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [501](../../static/app.js#L501) | `if (query && !haystack.includes(query)) return false;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [502](../../static/app.js#L502) | `return true;` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [503](../../static/app.js#L503) | `});` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [504](../../static/app.js#L504) | `}` | [home-cleanup.ts:45](../../frontend-v2/src/data/home-cleanup.ts#L45)：逐字段保持旧筛选条件，30组直接运行旧函数比对 |
| [506](../../static/app.js#L506) | `function resetProductionPreview() {` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [507](../../static/app.js#L507) | `state.productionPreview = null;` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [508](../../static/app.js#L508) | `$("productionCleanupPreview")?.classList.add("hidden");` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [509](../../static/app.js#L509) | `$("confirmProductionCleanupButton")?.classList.add("hidden");` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [510](../../static/app.js#L510) | `}` | [FileManagers.tsx:63](../../frontend-v2/src/components/views/FileManagers.tsx#L63)：选择、筛选或清单变化后废弃预览 |
| [512](../../static/app.js#L512) | `function updateProductionSelectionSummary() {` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [513](../../static/app.js#L513) | `const selected = state.productionFiles.filter(item => state.selectedProductionIds.has(item.fileId));` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [514](../../static/app.js#L514) | `const size = selected.reduce((total, item) => total + Number(item.sizeBytes ¦¦ 0), 0);` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [515](../../static/app.js#L515) | `const testCount = selected.filter(item => item.category === "capcut_test").length;` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [516](../../static/app.js#L516) | `const node = $("productionSelectionSummary");` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [517](../../static/app.js#L517) | `if (node) {` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [518](../../static/app.js#L518) | `node.textContent = ˋ已选择 ${selected.length} 个 · ${formatBytes(size)}${testCount ? ˋ · 含测试 ${testCount}ˋ : ""}ˋ;` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [519](../../static/app.js#L519) | `}` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [520](../../static/app.js#L520) | `}` | [FileManagers.tsx:217](../../frontend-v2/src/components/views/FileManagers.tsx#L217)：选择数量、总大小、人工及测试提示 |
| [522](../../static/app.js#L522) | `function productionIdentity(item) {` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [523](../../static/app.js#L523) | `return [item.project, item.material, item.language].filter(Boolean).join(" / ")` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [524](../../static/app.js#L524) | `¦¦ (item.category === "capcut_test" ? "隔离测试文件" : "历史或未登记任务");` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [525](../../static/app.js#L525) | `}` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [527](../../static/app.js#L527) | `function showProductionProtection(item) {` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [528](../../static/app.js#L528) | `$("productionProtectionName").textContent = item.name ¦¦ "--";` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [529](../../static/app.js#L529) | `$("productionProtectionIdentity").textContent = productionIdentity(item);` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [530](../../static/app.js#L530) | `$("productionProtectionState").textContent = item.taskState ¦¦ "受保护";` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [531](../../static/app.js#L531) | `$("productionProtectionReason").textContent = item.protectedReason ¦¦ "当前文件禁止清理";` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [532](../../static/app.js#L532) | `const dialog = $("productionProtectionDialog");` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [533](../../static/app.js#L533) | `if (dialog && !dialog.open) dialog.showModal();` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [534](../../static/app.js#L534) | `}` | [FileManagers.tsx:47](../../frontend-v2/src/components/views/FileManagers.tsx#L47)：保留服务器身份和保护原因，保护详情弹层 |
| [536](../../static/app.js#L536) | `function renderProductionManager() {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [537](../../static/app.js#L537) | `const node = $("productionManagerList");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [538](../../static/app.js#L538) | `if (!node) return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [539](../../static/app.js#L539) | `const items = filteredProductionFiles();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [540](../../static/app.js#L540) | `if (!items.length) {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [541](../../static/app.js#L541) | `node.innerHTML = ˋ<p class="empty">当前筛选条件下没有生产文件</p>ˋ;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [542](../../static/app.js#L542) | `updateProductionSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [543](../../static/app.js#L543) | `return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [544](../../static/app.js#L544) | `}` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [545](../../static/app.js#L545) | `node.innerHTML = items.map(item => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [546](../../static/app.js#L546) | `const checked = state.selectedProductionIds.has(item.fileId) ? "checked" : "";` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [547](../../static/app.js#L547) | `const disabled = item.protected ? "disabled" : "";` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [548](../../static/app.js#L548) | `const stateLabel = item.protected ? "受保护" : (item.category === "capcut_test" ? "测试文件，可手动清理" : "云端已核验，可清理");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [549](../../static/app.js#L549) | `return ˋ<div class="draft-manager-row production-manager-row ${item.protected ? "protected" : ""}"` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [550](../../static/app.js#L550) | `data-production-row-id="${escapeHtml(item.fileId)}" title="${escapeHtml(item.protectedReason ¦¦ stateLabel)}">` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [551](../../static/app.js#L551) | `<input type="checkbox" data-production-id="${escapeHtml(item.fileId)}" ${checked} ${disabled}>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [552](../../static/app.js#L552) | `<strong>${escapeHtml(item.name ¦¦ "未命名文件")}</strong>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [553](../../static/app.js#L553) | `<span class="production-file-type">${escapeHtml(item.categoryLabel ¦¦ item.category ¦¦ "")}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [554](../../static/app.js#L554) | `<span class="audio-protection ${item.protected ? "protected" : "deletable"}">${escapeHtml(stateLabel)}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [555](../../static/app.js#L555) | `<span>${escapeHtml(item.date ¦¦ "--")} · ${escapeHtml(formatBytes(item.sizeBytes))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [556](../../static/app.js#L556) | `<span class="audio-identity">${escapeHtml(productionIdentity(item))}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [557](../../static/app.js#L557) | `<span class="draft-source">${escapeHtml(item.relativePath ¦¦ "")}</span>` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [558](../../static/app.js#L558) | `</div>ˋ;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [559](../../static/app.js#L559) | `}).join("");` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [560](../../static/app.js#L560) | `node.querySelectorAll("input[data-production-id]").forEach(input => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [561](../../static/app.js#L561) | `input.addEventListener("change", event => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [562](../../static/app.js#L562) | `const fileId = event.currentTarget.dataset.productionId;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [563](../../static/app.js#L563) | `if (event.currentTarget.checked) state.selectedProductionIds.add(fileId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [564](../../static/app.js#L564) | `else state.selectedProductionIds.delete(fileId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [565](../../static/app.js#L565) | `resetProductionPreview();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [566](../../static/app.js#L566) | `updateProductionSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [567](../../static/app.js#L567) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [568](../../static/app.js#L568) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [569](../../static/app.js#L569) | `node.querySelectorAll("[data-production-row-id]").forEach(row => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [570](../../static/app.js#L570) | `row.addEventListener("click", event => {` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [571](../../static/app.js#L571) | `const item = state.productionFiles.find(value => value.fileId === row.dataset.productionRowId);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [572](../../static/app.js#L572) | `if (!item?.protected ¦¦ event.target.matches("input:not(:disabled)")) return;` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [573](../../static/app.js#L573) | `event.preventDefault();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [574](../../static/app.js#L574) | `showProductionProtection(item);` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [575](../../static/app.js#L575) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [576](../../static/app.js#L576) | `});` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [577](../../static/app.js#L577) | `updateProductionSelectionSummary();` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [578](../../static/app.js#L578) | `}` | [FileManagers.tsx:293](../../frontend-v2/src/components/views/FileManagers.tsx#L293)：清单表、保护行禁选、预览和逐项结果 |
| [580](../../static/app.js#L580) | `async function loadProductionManager({ applyDefaults = false } = {}) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [581](../../static/app.js#L581) | `const button = $("openProductionManagerButton");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [582](../../static/app.js#L582) | `const refreshButton = $("refreshProductionManagerButton");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [583](../../static/app.js#L583) | `if (button) { button.disabled = true; button.textContent = "正在读取生产文件…"; }` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [584](../../static/app.js#L584) | `if (refreshButton) refreshButton.disabled = true;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [585](../../static/app.js#L585) | `try {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [586](../../static/app.js#L586) | `const payload = await getJson("/api/controls/production-files", 1, 60000);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [587](../../static/app.js#L587) | `state.productionFiles = payload.items ¦¦ [];` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [588](../../static/app.js#L588) | `state.productionCounts = payload.counts ¦¦ {};` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [589](../../static/app.js#L589) | `state.productionSnapshot = payload.snapshotToken ¦¦ "";` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [590](../../static/app.js#L590) | `renderProductionFilters();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [591](../../static/app.js#L591) | `if (applyDefaults) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [592](../../static/app.js#L592) | `state.selectedProductionIds = new Set(` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [593](../../static/app.js#L593) | `state.productionFiles.filter(item => item.defaultSelected && !item.protected).map(item => item.fileId)` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [594](../../static/app.js#L594) | `);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [595](../../static/app.js#L595) | `} else {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [596](../../static/app.js#L596) | `state.selectedProductionIds = new Set(` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [597](../../static/app.js#L597) | `[...state.selectedProductionIds].filter(id =>` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [598](../../static/app.js#L598) | `state.productionFiles.some(item => item.fileId === id && !item.protected)` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [599](../../static/app.js#L599) | `)` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [600](../../static/app.js#L600) | `);` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [601](../../static/app.js#L601) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [602](../../static/app.js#L602) | `resetProductionPreview();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [603](../../static/app.js#L603) | `renderProductionCategorySummary();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [604](../../static/app.js#L604) | `renderProductionManager();` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [605](../../static/app.js#L605) | `const count = $("productionManagerCount");` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [606](../../static/app.js#L606) | `if (count) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [607](../../static/app.js#L607) | `count.textContent = ˋ${Number(payload.counts?.total ¦¦ 0)} 个ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [608](../../static/app.js#L608) | `count.className = ˋtask-state ${Number(payload.counts?.protected ¦¦ 0) ? "failed" : "neutral"}ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [609](../../static/app.js#L609) | `count.title = ˋ可清理 ${Number(payload.counts?.deletable ¦¦ 0)} 个，受保护 ${Number(payload.counts?.protected ¦¦ 0)} 个ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [610](../../static/app.js#L610) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [611](../../static/app.js#L611) | `} catch (error) {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [612](../../static/app.js#L612) | `$("productionManagerList").innerHTML = ˋ<p class="empty">${escapeHtml(error.message ¦¦ "读取生产文件失败")}</p>ˋ;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [613](../../static/app.js#L613) | `} finally {` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [614](../../static/app.js#L614) | `if (button) { button.disabled = false; button.textContent = "管理生产文件"; }` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [615](../../static/app.js#L615) | `if (refreshButton) refreshButton.disabled = false;` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [616](../../static/app.js#L616) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [617](../../static/app.js#L617) | `}` | [FileManagers.tsx:66](../../frontend-v2/src/components/views/FileManagers.tsx#L66)：读取清单、保留有效筛选及选择、仅生产采用服务器默认选择 |
| [1730](../../static/app.js#L1730) | `const dialog = $("draftManagerDialog");` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1731](../../static/app.js#L1731) | `if (dialog && !dialog.open) dialog.showModal();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1732](../../static/app.js#L1732) | `await loadDraftManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1733](../../static/app.js#L1733) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1734](../../static/app.js#L1734) | `$("closeDraftManagerButton")?.addEventListener("click", () => $("draftManagerDialog")?.close());` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1735](../../static/app.js#L1735) | `$("refreshDraftManagerButton")?.addEventListener("click", loadDraftManager);` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1736](../../static/app.js#L1736) | `["draftCategoryFilter", "draftDateFilter", "draftSearchFilter"].forEach(id => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1737](../../static/app.js#L1737) | `$(id)?.addEventListener(id === "draftSearchFilter" ? "input" : "change", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1738](../../static/app.js#L1738) | `resetDraftPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1739](../../static/app.js#L1739) | `renderDraftManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1740](../../static/app.js#L1740) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1741](../../static/app.js#L1741) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1742](../../static/app.js#L1742) | `$("selectFilteredDraftsButton")?.addEventListener("click", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1743](../../static/app.js#L1743) | `filteredDrafts().filter(item => !item.protected).forEach(item => state.selectedDraftIds.add(item.draftId));` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1744](../../static/app.js#L1744) | `resetDraftPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1745](../../static/app.js#L1745) | `renderDraftManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1746](../../static/app.js#L1746) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1747](../../static/app.js#L1747) | `$("clearDraftSelectionButton")?.addEventListener("click", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1748](../../static/app.js#L1748) | `state.selectedDraftIds.clear();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1749](../../static/app.js#L1749) | `resetDraftPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1750](../../static/app.js#L1750) | `renderDraftManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1751](../../static/app.js#L1751) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1752](../../static/app.js#L1752) | `$("previewDraftCleanupButton")?.addEventListener("click", async event => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1753](../../static/app.js#L1753) | `const button = event.currentTarget;` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1754](../../static/app.js#L1754) | `const draftIds = [...state.selectedDraftIds];` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1755](../../static/app.js#L1755) | `if (!draftIds.length) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1756](../../static/app.js#L1756) | `$("draftCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1757](../../static/app.js#L1757) | `$("draftCleanupPreview").innerHTML = "<strong>尚未选择草稿</strong>请先勾选要移入待删区的草稿。";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1758](../../static/app.js#L1758) | `return;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1759](../../static/app.js#L1759) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1760](../../static/app.js#L1760) | `button.disabled = true;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1761](../../static/app.js#L1761) | `button.textContent = "正在核对…";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1762](../../static/app.js#L1762) | `try {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1763](../../static/app.js#L1763) | `const preview = await postJson("/api/controls/capcut-drafts/preview", { draftIds }, { timeoutMs: 60000 });` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1764](../../static/app.js#L1764) | `state.draftPreview = preview;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1765](../../static/app.js#L1765) | `state.draftSnapshot = preview.snapshotToken ¦¦ "";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1766](../../static/app.js#L1766) | `const blocked = (preview.blocked ¦¦ []).map(item =>` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1767](../../static/app.js#L1767) | `ˋ<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>ˋ` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1768](../../static/app.js#L1768) | `).join("");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1769](../../static/app.js#L1769) | `$("draftCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1770](../../static/app.js#L1770) | `$("draftCleanupPreview").innerHTML = ˋ<strong>${escapeHtml(preview.message)}</strong>` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1771](../../static/app.js#L1771) | `可删除空间约 ${escapeHtml(formatBytes(preview.sizeBytes))}。` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1772](../../static/app.js#L1772) | `${blocked ? ˋ<ul>${blocked}</ul>ˋ : ""}ˋ;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1773](../../static/app.js#L1773) | `$("confirmDraftCleanupButton").classList.toggle("hidden", !preview.deletableCount);` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1774](../../static/app.js#L1774) | `} catch (error) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1775](../../static/app.js#L1775) | `resetDraftPreview();` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1776](../../static/app.js#L1776) | `$("draftCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1777](../../static/app.js#L1777) | `$("draftCleanupPreview").innerHTML = ˋ<strong>删除预览失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1778](../../static/app.js#L1778) | `} finally {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1779](../../static/app.js#L1779) | `button.disabled = false;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1780](../../static/app.js#L1780) | `button.textContent = "预览删除";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1781](../../static/app.js#L1781) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1782](../../static/app.js#L1782) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1783](../../static/app.js#L1783) | `$("confirmDraftCleanupButton")?.addEventListener("click", async event => {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1784](../../static/app.js#L1784) | `const button = event.currentTarget;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1785](../../static/app.js#L1785) | `const preview = state.draftPreview;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1786](../../static/app.js#L1786) | `if (!preview?.deletableCount) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1787](../../static/app.js#L1787) | `if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个草稿移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除视频、音频、成片或生产任务。ˋ)) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1788](../../static/app.js#L1788) | `if (preview.containsManualOrUnknown && !window.confirm("选择中包含人工或来源不明草稿。再次确认仍要将这些草稿移入待删区。")) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1789](../../static/app.js#L1789) | `button.disabled = true;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1790](../../static/app.js#L1790) | `button.textContent = "正在移入待删区…";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1791](../../static/app.js#L1791) | `try {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1792](../../static/app.js#L1792) | `const draftIds = (preview.deletable ¦¦ []).map(item => item.draftId);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1793](../../static/app.js#L1793) | `const result = await postJson("/api/controls/capcut-drafts/cleanup", {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1794](../../static/app.js#L1794) | `draftIds,` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1795](../../static/app.js#L1795) | `snapshotToken: preview.snapshotToken,` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1796](../../static/app.js#L1796) | `includeUnknown: Boolean(preview.containsManualOrUnknown),` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1797](../../static/app.js#L1797) | `confirm: "RECYCLE_SELECTED_CAPCUT_DRAFTS",` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1798](../../static/app.js#L1798) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1799](../../static/app.js#L1799) | `renderActionResult("draftCleanupResult", result);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1800](../../static/app.js#L1800) | `state.selectedDraftIds.clear();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1801](../../static/app.js#L1801) | `await loadDraftManager();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1802](../../static/app.js#L1802) | `await refresh();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1803](../../static/app.js#L1803) | `} catch (error) {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1804](../../static/app.js#L1804) | `renderActionResult("draftCleanupResult", {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1805](../../static/app.js#L1805) | `state: "failed", message: error.message ¦¦ "草稿清理失败", updatedAt: new Date().toISOString()` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1806](../../static/app.js#L1806) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1807](../../static/app.js#L1807) | `$("draftCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1808](../../static/app.js#L1808) | `$("draftCleanupPreview").innerHTML = ˋ<strong>草稿清理失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1809](../../static/app.js#L1809) | `} finally {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1810](../../static/app.js#L1810) | `button.disabled = false;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1811](../../static/app.js#L1811) | `button.textContent = "确认移入待删区";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1812](../../static/app.js#L1812) | `}` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1813](../../static/app.js#L1813) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1814](../../static/app.js#L1814) | `$("openAudioManagerButton")?.addEventListener("click", async () => {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1815](../../static/app.js#L1815) | `const dialog = $("audioManagerDialog");` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1816](../../static/app.js#L1816) | `if (dialog && !dialog.open) dialog.showModal();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1817](../../static/app.js#L1817) | `await loadAudioManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1818](../../static/app.js#L1818) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1819](../../static/app.js#L1819) | `$("closeAudioManagerButton")?.addEventListener("click", () => $("audioManagerDialog")?.close());` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1820](../../static/app.js#L1820) | `$("closeAudioProtectionButton")?.addEventListener("click", () => $("audioProtectionDialog")?.close());` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1821](../../static/app.js#L1821) | `$("refreshAudioManagerButton")?.addEventListener("click", loadAudioManager);` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1822](../../static/app.js#L1822) | `[` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1823](../../static/app.js#L1823) | `"audioDateFilter", "audioProjectFilter", "audioMaterialFilter", "audioLanguageFilter",` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1824](../../static/app.js#L1824) | `"audioBatchFilter", "audioStateFilter", "audioSearchFilter"` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1825](../../static/app.js#L1825) | `].forEach(id => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1826](../../static/app.js#L1826) | `$(id)?.addEventListener(id === "audioSearchFilter" ? "input" : "change", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1827](../../static/app.js#L1827) | `resetAudioPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1828](../../static/app.js#L1828) | `renderAudioManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1829](../../static/app.js#L1829) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1830](../../static/app.js#L1830) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1831](../../static/app.js#L1831) | `$("selectFilteredAudioButton")?.addEventListener("click", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1832](../../static/app.js#L1832) | `filteredAudioFiles().filter(item => !item.protected).forEach(item => state.selectedAudioIds.add(item.audioId));` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1833](../../static/app.js#L1833) | `resetAudioPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1834](../../static/app.js#L1834) | `renderAudioManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1835](../../static/app.js#L1835) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1836](../../static/app.js#L1836) | `$("clearAudioSelectionButton")?.addEventListener("click", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1837](../../static/app.js#L1837) | `state.selectedAudioIds.clear();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1838](../../static/app.js#L1838) | `resetAudioPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1839](../../static/app.js#L1839) | `renderAudioManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1840](../../static/app.js#L1840) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1841](../../static/app.js#L1841) | `$("previewAudioCleanupButton")?.addEventListener("click", async event => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1842](../../static/app.js#L1842) | `const button = event.currentTarget;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1843](../../static/app.js#L1843) | `const audioIds = [...state.selectedAudioIds];` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1844](../../static/app.js#L1844) | `if (!audioIds.length) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1845](../../static/app.js#L1845) | `$("audioCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1846](../../static/app.js#L1846) | `$("audioCleanupPreview").innerHTML = "<strong>尚未选择音频</strong>请先勾选要移入待删区的音频文件。";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1847](../../static/app.js#L1847) | `return;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1848](../../static/app.js#L1848) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1849](../../static/app.js#L1849) | `button.disabled = true;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1850](../../static/app.js#L1850) | `button.textContent = "正在重新对账…";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1851](../../static/app.js#L1851) | `try {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1852](../../static/app.js#L1852) | `const preview = await postJson("/api/controls/audio-files/preview", { audioIds }, { timeoutMs: 60000 });` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1853](../../static/app.js#L1853) | `state.audioPreview = preview;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1854](../../static/app.js#L1854) | `state.audioSnapshot = preview.snapshotToken ¦¦ "";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1855](../../static/app.js#L1855) | `const blocked = (preview.blocked ¦¦ []).map(item =>` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1856](../../static/app.js#L1856) | `ˋ<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>ˋ` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1857](../../static/app.js#L1857) | `).join("");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1858](../../static/app.js#L1858) | `$("audioCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1859](../../static/app.js#L1859) | `$("audioCleanupPreview").innerHTML = ˋ<strong>${escapeHtml(preview.message)}</strong>` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1860](../../static/app.js#L1860) | `可删除空间约 ${escapeHtml(formatBytes(preview.sizeBytes))}。` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1861](../../static/app.js#L1861) | `${blocked ? ˋ<ul>${blocked}</ul>ˋ : ""}ˋ;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1862](../../static/app.js#L1862) | `$("confirmAudioCleanupButton").classList.toggle("hidden", !preview.deletableCount);` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1863](../../static/app.js#L1863) | `if (preview.blockedCount) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1864](../../static/app.js#L1864) | `window.alert(ˋ有 ${preview.blockedCount} 个音频被活动任务保护，已禁止删除。请查看页面中的具体原因。ˋ);` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1865](../../static/app.js#L1865) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1866](../../static/app.js#L1866) | `} catch (error) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1867](../../static/app.js#L1867) | `resetAudioPreview();` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1868](../../static/app.js#L1868) | `$("audioCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1869](../../static/app.js#L1869) | `$("audioCleanupPreview").innerHTML = ˋ<strong>音频删除预览失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1870](../../static/app.js#L1870) | `window.alert(error.message ¦¦ "音频状态已变化，请重新对账");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1871](../../static/app.js#L1871) | `} finally {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1872](../../static/app.js#L1872) | `button.disabled = false;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1873](../../static/app.js#L1873) | `button.textContent = "预览删除";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1874](../../static/app.js#L1874) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1875](../../static/app.js#L1875) | `});` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1876](../../static/app.js#L1876) | `$("confirmAudioCleanupButton")?.addEventListener("click", async event => {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1877](../../static/app.js#L1877) | `const button = event.currentTarget;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1878](../../static/app.js#L1878) | `const preview = state.audioPreview;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1879](../../static/app.js#L1879) | `if (!preview?.deletableCount) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1880](../../static/app.js#L1880) | `if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个音频文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；不会删除文件夹，也不会改变任务完成状态。ˋ)) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1881](../../static/app.js#L1881) | `button.disabled = true;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1882](../../static/app.js#L1882) | `button.textContent = "正在移入待删区…";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1883](../../static/app.js#L1883) | `try {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1884](../../static/app.js#L1884) | `const audioIds = (preview.deletable ¦¦ []).map(item => item.audioId);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1885](../../static/app.js#L1885) | `const result = await postJson("/api/controls/audio-files/recycle", {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1886](../../static/app.js#L1886) | `audioIds,` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1887](../../static/app.js#L1887) | `snapshotToken: preview.snapshotToken,` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1888](../../static/app.js#L1888) | `confirm: "RECYCLE_SELECTED_AUDIO_FILES",` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1889](../../static/app.js#L1889) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1890](../../static/app.js#L1890) | `renderActionResult("audioCleanupResult", result);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1891](../../static/app.js#L1891) | `state.selectedAudioIds.clear();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1892](../../static/app.js#L1892) | `await loadAudioManager();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1893](../../static/app.js#L1893) | `await refresh();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1894](../../static/app.js#L1894) | `window.alert(result.message ¦¦ "音频已移入待删区");` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1895](../../static/app.js#L1895) | `} catch (error) {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1896](../../static/app.js#L1896) | `const message = error.message ¦¦ "音频清理失败";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1897](../../static/app.js#L1897) | `renderActionResult("audioCleanupResult", {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1898](../../static/app.js#L1898) | `state: "failed", message, updatedAt: new Date().toISOString()` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1899](../../static/app.js#L1899) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1900](../../static/app.js#L1900) | `$("audioCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1901](../../static/app.js#L1901) | `$("audioCleanupPreview").innerHTML = ˋ<strong>音频清理已停止</strong>${escapeHtml(message)}ˋ;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1902](../../static/app.js#L1902) | `window.alert(message);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1903](../../static/app.js#L1903) | `} finally {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1904](../../static/app.js#L1904) | `button.disabled = false;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1905](../../static/app.js#L1905) | `button.textContent = "确认移入待删区";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1906](../../static/app.js#L1906) | `}` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1907](../../static/app.js#L1907) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1908](../../static/app.js#L1908) | `$("openProductionManagerButton")?.addEventListener("click", async () => {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1909](../../static/app.js#L1909) | `const dialog = $("productionManagerDialog");` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1910](../../static/app.js#L1910) | `if (dialog && !dialog.open) dialog.showModal();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1911](../../static/app.js#L1911) | `await loadProductionManager({ applyDefaults: true });` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1912](../../static/app.js#L1912) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1913](../../static/app.js#L1913) | `$("closeProductionManagerButton")?.addEventListener("click", () => $("productionManagerDialog")?.close());` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1914](../../static/app.js#L1914) | `$("closeProductionProtectionButton")?.addEventListener("click", () => $("productionProtectionDialog")?.close());` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1915](../../static/app.js#L1915) | `$("refreshProductionManagerButton")?.addEventListener("click", () => loadProductionManager());` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1916](../../static/app.js#L1916) | `[` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1917](../../static/app.js#L1917) | `"productionDateFilter", "productionProjectFilter", "productionMaterialFilter",` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1918](../../static/app.js#L1918) | `"productionCategoryFilter", "productionStateFilter", "productionSearchFilter"` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1919](../../static/app.js#L1919) | `].forEach(id => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1920](../../static/app.js#L1920) | `$(id)?.addEventListener(id === "productionSearchFilter" ? "input" : "change", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1921](../../static/app.js#L1921) | `resetProductionPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1922](../../static/app.js#L1922) | `renderProductionManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1923](../../static/app.js#L1923) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1924](../../static/app.js#L1924) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1925](../../static/app.js#L1925) | `$("selectFilteredProductionButton")?.addEventListener("click", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1926](../../static/app.js#L1926) | `filteredProductionFiles()` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1927](../../static/app.js#L1927) | `.filter(item => !item.protected)` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1928](../../static/app.js#L1928) | `.forEach(item => state.selectedProductionIds.add(item.fileId));` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1929](../../static/app.js#L1929) | `resetProductionPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1930](../../static/app.js#L1930) | `renderProductionManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1931](../../static/app.js#L1931) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1932](../../static/app.js#L1932) | `$("clearProductionSelectionButton")?.addEventListener("click", () => {` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1933](../../static/app.js#L1933) | `state.selectedProductionIds.clear();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1934](../../static/app.js#L1934) | `resetProductionPreview();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1935](../../static/app.js#L1935) | `renderProductionManager();` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1936](../../static/app.js#L1936) | `});` | [FileManagers.tsx:203](../../frontend-v2/src/components/views/FileManagers.tsx#L203)：打开/关闭、筛选、全选仅当前未保护行、清空及预览失效；同组件显式状态 |
| [1937](../../static/app.js#L1937) | `$("previewProductionCleanupButton")?.addEventListener("click", async event => {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1938](../../static/app.js#L1938) | `const button = event.currentTarget;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1939](../../static/app.js#L1939) | `const fileIds = [...state.selectedProductionIds];` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1940](../../static/app.js#L1940) | `if (!fileIds.length) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1941](../../static/app.js#L1941) | `$("productionCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1942](../../static/app.js#L1942) | `$("productionCleanupPreview").innerHTML = "<strong>尚未选择生产文件</strong>请先勾选要移入待删区的文件。";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1943](../../static/app.js#L1943) | `return;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1944](../../static/app.js#L1944) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1945](../../static/app.js#L1945) | `button.disabled = true;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1946](../../static/app.js#L1946) | `button.textContent = "正在重新核验云端与引用…";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1947](../../static/app.js#L1947) | `try {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1948](../../static/app.js#L1948) | `const preview = await postJson("/api/controls/production-files/preview", { fileIds }, { timeoutMs: 60000 });` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1949](../../static/app.js#L1949) | `state.productionPreview = preview;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1950](../../static/app.js#L1950) | `state.productionSnapshot = preview.snapshotToken ¦¦ "";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1951](../../static/app.js#L1951) | `const categories = (preview.categories ¦¦ []).map(item =>` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1952](../../static/app.js#L1952) | `ˋ<li>${escapeHtml(item.label)}：${Number(item.count ¦¦ 0)} 个 · ${escapeHtml(formatBytes(item.sizeBytes))}</li>ˋ` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1953](../../static/app.js#L1953) | `).join("");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1954](../../static/app.js#L1954) | `const blocked = (preview.blocked ¦¦ []).slice(0, 30).map(item =>` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1955](../../static/app.js#L1955) | `ˋ<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>ˋ` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1956](../../static/app.js#L1956) | `).join("");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1957](../../static/app.js#L1957) | `const blockedMore = Number(preview.blockedCount ¦¦ 0) > 30` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1958](../../static/app.js#L1958) | `? ˋ<p>另有 ${Number(preview.blockedCount ¦¦ 0) - 30} 个受保护文件，请返回清单查看。</p>ˋ` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1959](../../static/app.js#L1959) | `: "";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1960](../../static/app.js#L1960) | `$("productionCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1961](../../static/app.js#L1961) | `$("productionCleanupPreview").innerHTML = ˋ<strong>${escapeHtml(preview.message)}</strong>` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1962](../../static/app.js#L1962) | `预计释放 ${escapeHtml(formatBytes(preview.sizeBytes))}。` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1963](../../static/app.js#L1963) | `${categories ? ˋ<ul>${categories}</ul>ˋ : ""}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1964](../../static/app.js#L1964) | `${blocked ? ˋ<p>以下文件不会删除：</p><ul>${blocked}</ul>${blockedMore}ˋ : ""}ˋ;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1965](../../static/app.js#L1965) | `$("confirmProductionCleanupButton").classList.toggle("hidden", !preview.deletableCount);` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1966](../../static/app.js#L1966) | `if (preview.blockedCount) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1967](../../static/app.js#L1967) | `window.alert(ˋ有 ${preview.blockedCount} 个文件被活动任务、云端核验或身份规则保护，已自动排除。ˋ);` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1968](../../static/app.js#L1968) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1969](../../static/app.js#L1969) | `} catch (error) {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1970](../../static/app.js#L1970) | `resetProductionPreview();` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1971](../../static/app.js#L1971) | `$("productionCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1972](../../static/app.js#L1972) | `$("productionCleanupPreview").innerHTML = ˋ<strong>生产文件清理预览失败</strong>${escapeHtml(error.message ¦¦ "请刷新后重试")}ˋ;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1973](../../static/app.js#L1973) | `} finally {` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1974](../../static/app.js#L1974) | `button.disabled = false;` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1975](../../static/app.js#L1975) | `button.textContent = "预览清理";` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1976](../../static/app.js#L1976) | `}` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1977](../../static/app.js#L1977) | `});` | [home-cleanup.ts:138](../../frontend-v2/src/data/home-cleanup.ts#L138)：仅所选服务器ID、60秒超时、返回快照；UI makePreview显示阻止原因 |
| [1978](../../static/app.js#L1978) | `$("confirmProductionCleanupButton")?.addEventListener("click", async event => {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1979](../../static/app.js#L1979) | `const button = event.currentTarget;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1980](../../static/app.js#L1980) | `const preview = state.productionPreview;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1981](../../static/app.js#L1981) | `if (!preview?.deletableCount) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1982](../../static/app.js#L1982) | `if (!window.confirm(ˋ确认将 ${preview.deletableCount} 个生产文件（${formatBytes(preview.sizeBytes)}）移入待删区吗？保留 3 天后自动清除，期间可恢复；项目状态、上传记录及云端文件不会改变。ˋ)) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1983](../../static/app.js#L1983) | `if (preview.containsTestFiles && !window.confirm("选择中包含 CapCut 测试或首帧测试文件。再次确认仍要将这些测试文件移入待删区。")) return;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1984](../../static/app.js#L1984) | `button.disabled = true;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1985](../../static/app.js#L1985) | `button.textContent = "正在移入待删区…";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1986](../../static/app.js#L1986) | `try {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1987](../../static/app.js#L1987) | `const fileIds = (preview.deletable ¦¦ []).map(item => item.fileId);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1988](../../static/app.js#L1988) | `// Recycling a large, user-confirmed inventory can legitimately take` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1989](../../static/app.js#L1989) | `// several minutes (Windows shell recycling is one file operation at a` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1990](../../static/app.js#L1990) | `// time).  The old 10s watchdog aborted the fetch while the server kept` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1991](../../static/app.js#L1991) | `// working, which produced the misleading "signal is aborted" alert.` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1992](../../static/app.js#L1992) | `const result = await postJson("/api/controls/production-files/recycle", {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1993](../../static/app.js#L1993) | `fileIds,` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1994](../../static/app.js#L1994) | `snapshotToken: preview.snapshotToken,` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1995](../../static/app.js#L1995) | `confirm: "RECYCLE_SELECTED_PRODUCTION_FILES",` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1996](../../static/app.js#L1996) | `}, { timeoutMs: 15 * 60 * 1000 });` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1997](../../static/app.js#L1997) | `renderActionResult("productionCleanupResult", result);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1998](../../static/app.js#L1998) | `state.selectedProductionIds.clear();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [1999](../../static/app.js#L1999) | `await loadProductionManager();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2000](../../static/app.js#L2000) | `await refresh();` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2001](../../static/app.js#L2001) | `window.alert(result.message ¦¦ "生产文件清理已完成");` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2002](../../static/app.js#L2002) | `} catch (error) {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2003](../../static/app.js#L2003) | `const message = error.message ¦¦ "生产文件清理失败";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2004](../../static/app.js#L2004) | `renderActionResult("productionCleanupResult", {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2005](../../static/app.js#L2005) | `state: "failed", message, updatedAt: new Date().toISOString()` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2006](../../static/app.js#L2006) | `});` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2007](../../static/app.js#L2007) | `$("productionCleanupPreview").classList.remove("hidden");` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2008](../../static/app.js#L2008) | `$("productionCleanupPreview").innerHTML = ˋ<strong>生产文件清理已停止</strong>${escapeHtml(message)}ˋ;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2009](../../static/app.js#L2009) | `window.alert(message);` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2010](../../static/app.js#L2010) | `} finally {` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2011](../../static/app.js#L2011) | `button.disabled = false;` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2012](../../static/app.js#L2012) | `button.textContent = "确认移入待删区";` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2013](../../static/app.js#L2013) | `}` | [home-cleanup.ts:146](../../frontend-v2/src/data/home-cleanup.ts#L146)：仅预览可删ID及快照、原确认正文/二次确认/超时，UI execute显示部分失败并刷新 |
| [2015](../../static/app.js#L2015) | `async function refreshPendingDelete() {` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2016](../../static/app.js#L2016) | `const node = $("pendingDeleteStatus");` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2017](../../static/app.js#L2017) | `const button = $("emptyPendingDeleteButton");` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2018](../../static/app.js#L2018) | `if (!node ¦¦ !button) return;` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2019](../../static/app.js#L2019) | `try {` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2020](../../static/app.js#L2020) | `const result = await getJson("/api/controls/pending-delete");` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2021](../../static/app.js#L2021) | `state.pendingDelete = result;` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2022](../../static/app.js#L2022) | `const count = Number(result.count ¦¦ 0);` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2023](../../static/app.js#L2023) | `const review = Number(result.needsReview ¦¦ 0);` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2024](../../static/app.js#L2024) | `node.textContent = count` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2025](../../static/app.js#L2025) | `? ˋ待删区：${count} 项，约 ${formatBytes(result.sizeBytes)}；${result.note ¦¦ ""}。最早于 ${formatDateTime(result.nextPurgeAt)} 自动清除。ˋ` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2026](../../static/app.js#L2026) | `: "待删区：空";` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2027](../../static/app.js#L2027) | `if (review) node.textContent += ˋ 另有 ${review} 项核验失败，保留待人工检查。ˋ;` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2028](../../static/app.js#L2028) | `button.classList.toggle("hidden", !count);` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2029](../../static/app.js#L2029) | `button.textContent = ˋ立即清空待删区（${count} 项，约 ${formatBytes(result.sizeBytes)}）ˋ;` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2030](../../static/app.js#L2030) | `} catch (error) {` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2031](../../static/app.js#L2031) | `node.textContent = ˋ待删区：读取失败（${error.message ¦¦ "未知原因"}）ˋ;` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2032](../../static/app.js#L2032) | `button.classList.add("hidden");` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2033](../../static/app.js#L2033) | `}` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2034](../../static/app.js#L2034) | `}` | [FileManagers.tsx:55](../../frontend-v2/src/components/views/FileManagers.tsx#L55)：共享只读快照和刷新后容量、最早清除时间 |
| [2035](../../static/app.js#L2035) | `$("emptyPendingDeleteButton")?.addEventListener("click", async (event) => {` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2036](../../static/app.js#L2036) | `const button = event.currentTarget;` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2037](../../static/app.js#L2037) | `const info = state.pendingDelete ¦¦ {};` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2038](../../static/app.js#L2038) | `if (!window.confirm(ˋ确认立即永久清除待删区的 ${Number(info.count ¦¦ 0)} 项（约 ${formatBytes(info.sizeBytes)}）吗？清除后无法恢复。ˋ)) return;` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2039](../../static/app.js#L2039) | `if (!window.confirm("再次确认：这一步会永久删除，不进入回收站。")) return;` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2040](../../static/app.js#L2040) | `button.disabled = true;` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2041](../../static/app.js#L2041) | `try {` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2042](../../static/app.js#L2042) | `const result = await postJson("/api/controls/pending-delete/empty", { confirm: "EMPTY_PENDING_DELETE_NOW" }, { timeoutMs: 600000 });` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2043](../../static/app.js#L2043) | `window.alert(result.message ¦¦ "待删区已清空");` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2044](../../static/app.js#L2044) | `} catch (error) {` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2045](../../static/app.js#L2045) | `window.alert(error.message ¦¦ "清空待删区失败");` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2046](../../static/app.js#L2046) | `} finally {` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2047](../../static/app.js#L2047) | `button.disabled = false;` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2048](../../static/app.js#L2048) | `await refreshPendingDelete();` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2049](../../static/app.js#L2049) | `}` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |
| [2050](../../static/app.js#L2050) | `});` | [home-cleanup.ts:198](../../frontend-v2/src/data/home-cleanup.ts#L198)：原两次确认、相同确认正文与10分钟独立超时 |

## 四项审查修复

1. client.readOnce 将 deadline 放到每个 HTTP 交换（含正文）内。202 收件后取消该 deadline，等待500ms后重新请求，最多120轮；仍支持卸载取消与原重试。假时钟30秒/120轮/8秒单请求测试通过；真实Chromium连续202等待30秒后正常显示，未走health超时回退。
2. 测试主机名仅在 src/test/config.json 中；Vitest明确使用localhost。生产detect移除测试域名，构建size检查扫描全部JS，发现测试域名即失败。
3. scripts/refresh-inventory.cjs 以当前函数节点 getText 提取，拒绝行号/名称/枚举数变化；保留ID、勾选、证据和PR。368条函数摘录附起始行/列、结束行，单元测试逐条比对实际AST。原workspace生成脚本亦修正父节点爬升问题。
4. control-timeout.ts 与Claude PR #33完全一致：不足60秒用Math.round(ms/1000)秒，否则Math.round(ms/60000)分钟；上传home和三类清理共用，原恢复建议和CONTROL_REQUEST_TIMEOUT保留。

## 验证与边界

- 106项前端测试（含30组新旧筛选零差异、368条摘录验证、双模式读契约和清理负例）、typecheck/lint/摘录检查通过。
- 三类服务器ID、快照失效、取消确认、人工/测试二次确认、部分失败、跨视图防重复、长清理不被只读视图卸载误中止、云端零家里POST；待删区双确认与原10分钟超时。
- 未验证真实生产、完整批次影子、云端清理执行或默认入口切换。旧Dashboard与后台程序没有修改/重启。
- 无新增依赖；复用固定shadcn Sheet/Table/Button/Input（MIT）。回滚revert本PR与static/v2产物，旧入口不受影响。
