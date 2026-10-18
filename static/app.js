function currentLocalDateLabel() {
  const value = new Date();
  return `${value.getMonth() + 1}.${value.getDate()}`;
}

const state = {
  date: "", batchId: "", overview: null, templates: [], templateSignature: "",
  gaps: {}, lastGoodDashboard: null, refreshBusy: false,
  step5Items: [], step5Filter: "",
  drafts: [], draftSnapshot: "", selectedDraftIds: new Set(), draftPreview: null,
  audioFiles: [], audioSnapshot: "", selectedAudioIds: new Set(), audioPreview: null,
  productionFiles: [], productionSnapshot: "", selectedProductionIds: new Set(),
  productionPreview: null, productionCounts: {},
  safety: null, safetyLoadedAt: 0,
  continueStatusBusy: false, continueCommandId: "", continueStatusFailures: 0,
  fullDashboardLoaded: false, historyExplicit: false, healthFailures: 0, continueInFlight: false,
  freshnessStartedAt: performance.now(), freshnessReceivedAt: null, freshnessReceivedTick: null,
  etags: {}, cachedJson: {}, runtime: null, lastContinueResult: null
};
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

function formatClock(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString("zh-CN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit"
  });
}

// Page freshness measures successful dashboard reception on this browser.
// It is independent of the home PC clock, health checks and saved local data.
function updateDataFreshness() {
  const received = state.freshnessReceivedAt !== null;
  const elapsed = Math.max(0, performance.now() - (state.freshnessReceivedTick ?? state.freshnessStartedAt));
  const level = elapsed > 120000 ? "stale" : elapsed > 30000 ? "warning" : "fresh";
  const node = $("dataFreshness");
  node.classList.toggle("warning", level === "warning");
  node.classList.toggle("stale", level === "stale");
  $("lastUpdated").textContent = received ? formatClock(state.freshnessReceivedAt) : "等待首次同步";
  $("freshnessAge").textContent = received ? `（${Math.floor(elapsed / 1000)} 秒前）` : "";
  $("freshnessWarning").hidden = level === "fresh";
}

function recordDashboardReception() {
  state.freshnessReceivedAt = new Date();
  state.freshnessReceivedTick = performance.now();
  updateDataFreshness();
}

function formatDateTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"
  });
}

function formatAge(seconds) {
  if (seconds == null) return "无状态时间";
  if (seconds < 10) return "刚刚";
  if (seconds < 60) return `${seconds}秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前`;
  return `${Math.floor(seconds / 86400)}天前`;
}

function formatBytes(value) {
  let size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

function formatDuration(value) {
  const seconds = Math.max(0, Math.round(Number(value || 0)));
  if (!seconds) return "正在测算";
  if (seconds < 60) return `约 ${seconds} 秒`;
  if (seconds < 3600) return `约 ${Math.ceil(seconds / 60)} 分钟`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.ceil((seconds % 3600) / 60);
  return `约 ${hours} 小时${minutes ? ` ${minutes} 分钟` : ""}`;
}

function renderSafety(data) {
  state.safety = data;
  const hasActiveProject = data?.productionContext?.hasActiveProject === true;
  const updated = $("safetyUpdatedAt");
  if (updated) updated.textContent = `最后检查 ${formatDateTime(data?.updatedAt)}`;
  const entries = [
    ["去字幕质检", data?.subtitleVerification,
      value => `干净 ${value.counts?.verified_clean || 0} · 少量残留已放行 ${value.counts?.warning || 0} · 完整残留 ${value.counts?.residual_detected || 0} · 待审计 ${value.counts?.audit_pending || 0}`,
      value => Number(value.counts?.residual_detected || 0) || Number(value.counts?.verification_failed || 0) ? "blocked" : Number(value.counts?.warning || 0) || Number(value.counts?.audit_pending || 0) ? "warning" : "good"],
    ["自动安全恢复", data?.autoRecovery,
      value => `${value.stateText || "空闲"} · 已尝试 ${value.attemptCount || 0}/1${value.commandState ? ` · 命令 ${value.commandState}` : ""}`,
      value => ["failed", "unavailable"].includes(value.state) ? "blocked" : ["observing", "waiting_stable", "starting", "command_persisted", "receiver_acknowledged", "workbench_acknowledged", "executing", "recovering"].includes(value.state) ? "warning" : "good"],
    ["成片质检", data?.quality,
      value => `${hasActiveProject ? "当前" : "历史审计"}：通过 ${value.passed || 0}/${value.total || 0} · 提醒 ${value.warning || 0} · 阻止 ${value.blocked || 0}`,
      value => Number(value.blocked || 0) ? "blocked" : Number(value.warning || 0) ? "warning" : "good"],
    ["版本与配置", data?.versions,
      value => `${value.items?.length || 0} 个组件 · ${Number(value.driftCount || 0) ? `检测到 ${value.driftCount} 项已变更，待确认基线` : "基线一致"}`,
      value => Number(value.driftCount || 0) ? "warning" : "good"],
    ["云端对账", data?.cloud,
      value => `实时核验 ${value.verified || 0}/${value.total || 0} · 阻止 ${value.blocked || 0}`,
      value => Number(value.blocked || 0) ? "warning" : "good"],
    ["磁盘预测", data?.disk,
      value => `剩余 ${value.remainingVideos || 0} 条 · 需要 ${formatBytes(value.requiredFreeBytes)} · 可用 ${formatBytes(value.freeBytes)}`,
      value => value.ready ? "good" : "blocked"],
    ["登录状态", data?.credentials,
      value => {
        const required = (value.items || []).filter(item => item.required !== false);
        const optionalOffline = (value.items || []).filter(item => item.required === false && !item.online).length;
        return `${required.length} 个当前必需服务 · ${value.ready ? "可用" : "需要处理"}${optionalOffline ? ` · ${optionalOffline} 个未到阶段` : ""}`;
      },
      value => value.ready ? "good" : "warning"],
    ["任务身份", data?.integrity,
      value => `活动 ${value.activeRecords || 0} · 硬错误 ${value.hardFailureCount || 0}`,
      value => value.safe ? "good" : "blocked"],
    ["故障证据", data?.evidence,
      value => value.incident ? `${value.incident.incidentId || "历史故障"} · 历史证据已保存，不代表当前仍异常` : "当前没有故障证据",
      value => value.incident ? "warning" : "good"],
  ];
  const grid = $("safetyGrid");
  if (!grid) return;
  grid.innerHTML = entries.map(([title, value, text, klass]) => {
    if (!value || value.error) {
      const reason = value?.message || "状态源暂不可用，保留其他检查结果";
      return `<article class="safety-card warning"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(reason)}</span></article>`;
    }
    return `<article class="safety-card ${klass(value)}"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(text(value))}</span></article>`;
  }).join("");
}

async function refreshSafety(force = false) {
  if (!force && Date.now() - state.safetyLoadedAt < 30000) return;
  try {
    const data = await getJson("/api/safety");
    state.safetyLoadedAt = Date.now();
    renderSafety(data);
  } catch (error) {
    renderSafety({
      updatedAt: new Date().toISOString(),
      quality: { error: true, message: "生产安全控制面暂不可用；不会影响生产任务" },
    });
  }
}

function draftCategoryLabel(value) {
  if (value === "formal") return "正式自动";
  if (value === "lab") return "内测";
  return "人工/不明";
}

function draftDateKey(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return "";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

function renderDraftDateFilter() {
  const select = $("draftDateFilter");
  if (!select) return;
  const selected = select.value || "";
  const counts = new Map();
  state.drafts.forEach(item => {
    const key = draftDateKey(item.updatedAt || item.createdAt);
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
  });
  const dates = [...counts.keys()].sort((a, b) => b.localeCompare(a));
  select.innerHTML = [
    `<option value="">全部日期（${state.drafts.length}）</option>`,
    ...dates.map(value =>
      `<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>`
    )
  ].join("");
  select.value = dates.includes(selected) ? selected : "";
}

function filteredDrafts() {
  const category = $("draftCategoryFilter")?.value || "";
  const date = $("draftDateFilter")?.value || "";
  const query = ($("draftSearchFilter")?.value || "").trim().toLocaleLowerCase();
  return state.drafts.filter(item => {
    if (category && item.category !== category) return false;
    if (date && draftDateKey(item.updatedAt || item.createdAt) !== date) return false;
    if (query && !`${item.name || ""} ${item.sourceLabel || ""}`.toLocaleLowerCase().includes(query)) return false;
    return true;
  });
}

function resetDraftPreview() {
  state.draftPreview = null;
  $("draftCleanupPreview")?.classList.add("hidden");
  $("confirmDraftCleanupButton")?.classList.add("hidden");
}

function updateDraftSelectionSummary() {
  const selected = state.drafts.filter(item => state.selectedDraftIds.has(item.draftId));
  const size = selected.reduce((total, item) => total + Number(item.sizeBytes || 0), 0);
  const node = $("draftSelectionSummary");
  if (node) node.textContent = `已选择 ${selected.length} 个 · ${formatBytes(size)}`;
}

function renderDraftManager() {
  const node = $("draftManagerList");
  if (!node) return;
  const items = filteredDrafts();
  if (!items.length) {
    node.innerHTML = `<p class="empty">当前筛选条件下没有草稿</p>`;
    updateDraftSelectionSummary();
    return;
  }
  node.innerHTML = items.map(item => {
    const checked = state.selectedDraftIds.has(item.draftId) ? "checked" : "";
    const disabled = item.protected ? "disabled" : "";
    const detail = item.protected ? item.protectedReason : (item.inIndex ? "索引正常" : "目录未登记在首页索引");
    return `<label class="draft-manager-row ${item.protected ? "protected" : ""}" title="${escapeHtml(detail)}">
      <input type="checkbox" data-draft-id="${escapeHtml(item.draftId)}" ${checked} ${disabled}>
      <strong>${escapeHtml(item.name || "未命名草稿")}</strong>
      <span class="draft-category ${escapeHtml(item.category)}">${escapeHtml(draftCategoryLabel(item.category))}</span>
      <span>${escapeHtml(formatDateTime(item.updatedAt || item.createdAt))}</span>
      <span>${escapeHtml(formatBytes(item.sizeBytes))}</span>
      <span class="draft-source">${escapeHtml(item.sourceLabel || detail)}</span>
    </label>`;
  }).join("");
  node.querySelectorAll("input[data-draft-id]").forEach(input => {
    input.addEventListener("change", event => {
      const draftId = event.currentTarget.dataset.draftId;
      if (event.currentTarget.checked) state.selectedDraftIds.add(draftId);
      else state.selectedDraftIds.delete(draftId);
      resetDraftPreview();
      updateDraftSelectionSummary();
    });
  });
  updateDraftSelectionSummary();
}

async function loadDraftManager() {
  const button = $("openDraftManagerButton");
  const refreshButton = $("refreshDraftManagerButton");
  if (button) { button.disabled = true; button.textContent = "正在读取草稿…"; }
  if (refreshButton) refreshButton.disabled = true;
  try {
    const payload = await getJson("/api/controls/capcut-drafts", 1, 60000);
    state.drafts = payload.items || [];
    state.draftSnapshot = payload.snapshotToken || "";
    renderDraftDateFilter();
    state.selectedDraftIds = new Set(
      [...state.selectedDraftIds].filter(id => state.drafts.some(item => item.draftId === id && !item.protected))
    );
    resetDraftPreview();
    renderDraftManager();
    const count = $("draftManagerCount");
    if (count) {
      count.textContent = `${payload.counts?.total || 0} 个`;
      count.className = `task-state ${(payload.runningProcesses || []).length ? "failed" : "neutral"}`;
    }
  } catch (error) {
    $("draftManagerList").innerHTML = `<p class="empty">${escapeHtml(error.message || "读取草稿失败")}</p>`;
  } finally {
    if (button) { button.disabled = false; button.textContent = "管理 CapCut 草稿"; }
    if (refreshButton) refreshButton.disabled = false;
  }
}

function populateAudioFilter(id, values, label) {
  const select = $(id);
  if (!select) return;
  const selected = select.value || "";
  const counts = new Map();
  values.filter(Boolean).forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
  const options = [...counts.keys()].sort((a, b) => a.localeCompare(b, "zh-CN"));
  select.innerHTML = [
    `<option value="">全部${escapeHtml(label)}（${state.audioFiles.length}）</option>`,
    ...options.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>`)
  ].join("");
  select.value = options.includes(selected) ? selected : "";
}

function renderAudioFilters() {
  populateAudioFilter("audioDateFilter", state.audioFiles.map(item => item.date || draftDateKey(item.updatedAt)), "日期");
  populateAudioFilter("audioProjectFilter", state.audioFiles.map(item => item.project), "项目");
  populateAudioFilter("audioMaterialFilter", state.audioFiles.map(item => item.material), "材料");
  populateAudioFilter("audioLanguageFilter", state.audioFiles.map(item => item.language), "语言");
  populateAudioFilter("audioBatchFilter", state.audioFiles.map(item => item.audioBatch), "批次");
}

function filteredAudioFiles() {
  const date = $("audioDateFilter")?.value || "";
  const project = $("audioProjectFilter")?.value || "";
  const material = $("audioMaterialFilter")?.value || "";
  const language = $("audioLanguageFilter")?.value || "";
  const batch = $("audioBatchFilter")?.value || "";
  const taskState = $("audioStateFilter")?.value || "";
  const query = ($("audioSearchFilter")?.value || "").trim().toLocaleLowerCase();
  return state.audioFiles.filter(item => {
    const itemDate = item.date || draftDateKey(item.updatedAt);
    if (date && itemDate !== date) return false;
    if (project && item.project !== project) return false;
    if (material && item.material !== material) return false;
    if (language && item.language !== language) return false;
    if (batch && item.audioBatch !== batch) return false;
    if (taskState === "deletable" && item.protected) return false;
    if (taskState === "protected" && !item.protected) return false;
    const haystack = `${item.name || ""} ${item.relativePath || ""} ${item.project || ""} ${item.material || ""} ${item.language || ""}`.toLocaleLowerCase();
    if (query && !haystack.includes(query)) return false;
    return true;
  });
}

function resetAudioPreview() {
  state.audioPreview = null;
  $("audioCleanupPreview")?.classList.add("hidden");
  $("confirmAudioCleanupButton")?.classList.add("hidden");
}

function updateAudioSelectionSummary() {
  const selected = state.audioFiles.filter(item => state.selectedAudioIds.has(item.audioId));
  const size = selected.reduce((total, item) => total + Number(item.sizeBytes || 0), 0);
  const node = $("audioSelectionSummary");
  if (node) node.textContent = `已选择 ${selected.length} 个 · ${formatBytes(size)}`;
}

function audioIdentity(item) {
  return [item.project, item.material, item.language].filter(Boolean).join(" / ") || "历史或未登记任务";
}

function showAudioProtection(item) {
  const identity = audioIdentity(item);
  const reason = item.protectedReason || "任务正在使用，禁止删除";
  $("audioProtectionIdentity").textContent = identity;
  $("audioProtectionState").textContent = item.taskState || "等待恢复";
  $("audioProtectionReason").textContent = reason;
  const dialog = $("audioProtectionDialog");
  if (dialog && !dialog.open) dialog.showModal();
}

function renderAudioManager() {
  const node = $("audioManagerList");
  if (!node) return;
  const items = filteredAudioFiles();
  if (!items.length) {
    node.innerHTML = `<p class="empty">当前筛选条件下没有音频文件</p>`;
    updateAudioSelectionSummary();
    return;
  }
  node.innerHTML = items.map(item => {
    const checked = state.selectedAudioIds.has(item.audioId) ? "checked" : "";
    const disabled = item.protected ? "disabled" : "";
    const stateLabel = item.protected ? "任务正在使用，禁止删除" : "可手动删除";
    return `<div class="draft-manager-row audio-manager-row ${item.protected ? "protected" : ""}"
        data-audio-row-id="${escapeHtml(item.audioId)}" title="${escapeHtml(item.protectedReason || stateLabel)}">
      <input type="checkbox" data-audio-id="${escapeHtml(item.audioId)}" ${checked} ${disabled}>
      <strong>${escapeHtml(item.name || "未命名音频")}</strong>
      <span class="audio-protection ${item.protected ? "protected" : "deletable"}">${escapeHtml(stateLabel)}</span>
      <span>${escapeHtml(item.date || "--")} · ${escapeHtml(formatDateTime(item.updatedAt || item.createdAt))}</span>
      <span>${escapeHtml(formatBytes(item.sizeBytes))}</span>
      <span class="audio-identity">${escapeHtml(audioIdentity(item))}</span>
      <span class="draft-source">${escapeHtml(item.relativePath || "")}</span>
    </div>`;
  }).join("");
  node.querySelectorAll("input[data-audio-id]").forEach(input => {
    input.addEventListener("change", event => {
      const audioId = event.currentTarget.dataset.audioId;
      if (event.currentTarget.checked) state.selectedAudioIds.add(audioId);
      else state.selectedAudioIds.delete(audioId);
      resetAudioPreview();
      updateAudioSelectionSummary();
    });
  });
  node.querySelectorAll("[data-audio-row-id]").forEach(row => {
    row.addEventListener("click", event => {
      const item = state.audioFiles.find(value => value.audioId === row.dataset.audioRowId);
      if (!item?.protected || event.target.matches("input:not(:disabled)")) return;
      event.preventDefault();
      showAudioProtection(item);
    });
  });
  updateAudioSelectionSummary();
}

async function loadAudioManager() {
  const button = $("openAudioManagerButton");
  const refreshButton = $("refreshAudioManagerButton");
  if (button) { button.disabled = true; button.textContent = "正在读取音频…"; }
  if (refreshButton) refreshButton.disabled = true;
  try {
    const payload = await getJson("/api/controls/audio-files", 1, 60000);
    state.audioFiles = payload.items || [];
    state.audioSnapshot = payload.snapshotToken || "";
    renderAudioFilters();
    state.selectedAudioIds = new Set(
      [...state.selectedAudioIds].filter(id =>
        state.audioFiles.some(item => item.audioId === id && !item.protected)
      )
    );
    resetAudioPreview();
    renderAudioManager();
    const count = $("audioManagerCount");
    if (count) {
      const protectedCount = Number(payload.counts?.protected || 0);
      count.textContent = `${payload.counts?.total || 0} 个`;
      count.className = `task-state ${protectedCount ? "failed" : "neutral"}`;
      count.title = protectedCount ? `${protectedCount} 个正在被任务使用` : "当前没有受保护音频";
    }
  } catch (error) {
    $("audioManagerList").innerHTML = `<p class="empty">${escapeHtml(error.message || "读取音频失败")}</p>`;
  } finally {
    if (button) { button.disabled = false; button.textContent = "管理音频文件"; }
    if (refreshButton) refreshButton.disabled = false;
  }
}

function populateProductionFilter(id, values, label) {
  const select = $(id);
  if (!select) return;
  const selected = select.value || "";
  const counts = new Map();
  values.filter(Boolean).forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
  const options = [...counts.keys()].sort((a, b) => a.localeCompare(b, "zh-CN"));
  select.innerHTML = [
    `<option value="">全部${escapeHtml(label)}（${state.productionFiles.length}）</option>`,
    ...options.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}（${counts.get(value)}）</option>`)
  ].join("");
  select.value = options.includes(selected) ? selected : "";
}

function renderProductionFilters() {
  populateProductionFilter(
    "productionDateFilter",
    state.productionFiles.map(item => item.date || draftDateKey(item.updatedAt)),
    "日期"
  );
  populateProductionFilter("productionProjectFilter", state.productionFiles.map(item => item.project), "项目");
  populateProductionFilter("productionMaterialFilter", state.productionFiles.map(item => item.material), "材料");
  const select = $("productionCategoryFilter");
  if (select) {
    const selected = select.value || "";
    const categories = state.productionCounts?.categories || {};
    select.innerHTML = [
      `<option value="">全部类型（${state.productionFiles.length}）</option>`,
      ...Object.entries(categories).map(([key, value]) =>
        `<option value="${escapeHtml(key)}">${escapeHtml(value.label || key)}（${Number(value.total || 0)}）</option>`
      )
    ].join("");
    select.value = Object.hasOwn(categories, selected) ? selected : "";
  }
}

function renderProductionCategorySummary() {
  const node = $("productionCategorySummary");
  if (!node) return;
  const categories = state.productionCounts?.categories || {};
  const rows = Object.entries(categories);
  if (!rows.length) {
    node.innerHTML = `<p class="empty">没有发现已登记的生产文件</p>`;
    return;
  }
  node.innerHTML = rows.map(([key, value]) =>
    `<button type="button" class="production-category-card" data-production-category="${escapeHtml(key)}">
      <span>${escapeHtml(value.label || key)}</span>
      <strong>${Number(value.total || 0)} 个 · ${escapeHtml(formatBytes(value.sizeBytes))}</strong>
      <small>可清理 ${Number(value.deletable || 0)} · 保护 ${Number(value.protected || 0)}</small>
    </button>`
  ).join("");
  node.querySelectorAll("[data-production-category]").forEach(button => {
    button.addEventListener("click", () => {
      const select = $("productionCategoryFilter");
      if (select) select.value = button.dataset.productionCategory || "";
      resetProductionPreview();
      renderProductionManager();
    });
  });
}

function filteredProductionFiles() {
  const date = $("productionDateFilter")?.value || "";
  const project = $("productionProjectFilter")?.value || "";
  const material = $("productionMaterialFilter")?.value || "";
  const category = $("productionCategoryFilter")?.value || "";
  const taskState = $("productionStateFilter")?.value || "";
  const query = ($("productionSearchFilter")?.value || "").trim().toLocaleLowerCase();
  return state.productionFiles.filter(item => {
    const itemDate = item.date || draftDateKey(item.updatedAt);
    if (date && itemDate !== date) return false;
    if (project && item.project !== project) return false;
    if (material && item.material !== material) return false;
    if (category && item.category !== category) return false;
    if (taskState === "deletable" && item.protected) return false;
    if (taskState === "protected" && !item.protected) return false;
    const haystack = [
      item.name, item.relativePath, item.categoryLabel, item.project,
      item.material, item.language, item.taskState
    ].join(" ").toLocaleLowerCase();
    if (query && !haystack.includes(query)) return false;
    return true;
  });
}

function resetProductionPreview() {
  state.productionPreview = null;
  $("productionCleanupPreview")?.classList.add("hidden");
  $("confirmProductionCleanupButton")?.classList.add("hidden");
}

function updateProductionSelectionSummary() {
  const selected = state.productionFiles.filter(item => state.selectedProductionIds.has(item.fileId));
  const size = selected.reduce((total, item) => total + Number(item.sizeBytes || 0), 0);
  const testCount = selected.filter(item => item.category === "capcut_test").length;
  const node = $("productionSelectionSummary");
  if (node) {
    node.textContent = `已选择 ${selected.length} 个 · ${formatBytes(size)}${testCount ? ` · 含测试 ${testCount}` : ""}`;
  }
}

function productionIdentity(item) {
  return [item.project, item.material, item.language].filter(Boolean).join(" / ")
    || (item.category === "capcut_test" ? "隔离测试文件" : "历史或未登记任务");
}

function showProductionProtection(item) {
  $("productionProtectionName").textContent = item.name || "--";
  $("productionProtectionIdentity").textContent = productionIdentity(item);
  $("productionProtectionState").textContent = item.taskState || "受保护";
  $("productionProtectionReason").textContent = item.protectedReason || "当前文件禁止清理";
  const dialog = $("productionProtectionDialog");
  if (dialog && !dialog.open) dialog.showModal();
}

function renderProductionManager() {
  const node = $("productionManagerList");
  if (!node) return;
  const items = filteredProductionFiles();
  if (!items.length) {
    node.innerHTML = `<p class="empty">当前筛选条件下没有生产文件</p>`;
    updateProductionSelectionSummary();
    return;
  }
  node.innerHTML = items.map(item => {
    const checked = state.selectedProductionIds.has(item.fileId) ? "checked" : "";
    const disabled = item.protected ? "disabled" : "";
    const stateLabel = item.protected ? "受保护" : (item.category === "capcut_test" ? "测试文件，可手动清理" : "云端已核验，可清理");
    return `<div class="draft-manager-row production-manager-row ${item.protected ? "protected" : ""}"
        data-production-row-id="${escapeHtml(item.fileId)}" title="${escapeHtml(item.protectedReason || stateLabel)}">
      <input type="checkbox" data-production-id="${escapeHtml(item.fileId)}" ${checked} ${disabled}>
      <strong>${escapeHtml(item.name || "未命名文件")}</strong>
      <span class="production-file-type">${escapeHtml(item.categoryLabel || item.category || "")}</span>
      <span class="audio-protection ${item.protected ? "protected" : "deletable"}">${escapeHtml(stateLabel)}</span>
      <span>${escapeHtml(item.date || "--")} · ${escapeHtml(formatBytes(item.sizeBytes))}</span>
      <span class="audio-identity">${escapeHtml(productionIdentity(item))}</span>
      <span class="draft-source">${escapeHtml(item.relativePath || "")}</span>
    </div>`;
  }).join("");
  node.querySelectorAll("input[data-production-id]").forEach(input => {
    input.addEventListener("change", event => {
      const fileId = event.currentTarget.dataset.productionId;
      if (event.currentTarget.checked) state.selectedProductionIds.add(fileId);
      else state.selectedProductionIds.delete(fileId);
      resetProductionPreview();
      updateProductionSelectionSummary();
    });
  });
  node.querySelectorAll("[data-production-row-id]").forEach(row => {
    row.addEventListener("click", event => {
      const item = state.productionFiles.find(value => value.fileId === row.dataset.productionRowId);
      if (!item?.protected || event.target.matches("input:not(:disabled)")) return;
      event.preventDefault();
      showProductionProtection(item);
    });
  });
  updateProductionSelectionSummary();
}

async function loadProductionManager({ applyDefaults = false } = {}) {
  const button = $("openProductionManagerButton");
  const refreshButton = $("refreshProductionManagerButton");
  if (button) { button.disabled = true; button.textContent = "正在读取生产文件…"; }
  if (refreshButton) refreshButton.disabled = true;
  try {
    const payload = await getJson("/api/controls/production-files", 1, 60000);
    state.productionFiles = payload.items || [];
    state.productionCounts = payload.counts || {};
    state.productionSnapshot = payload.snapshotToken || "";
    renderProductionFilters();
    if (applyDefaults) {
      state.selectedProductionIds = new Set(
        state.productionFiles.filter(item => item.defaultSelected && !item.protected).map(item => item.fileId)
      );
    } else {
      state.selectedProductionIds = new Set(
        [...state.selectedProductionIds].filter(id =>
          state.productionFiles.some(item => item.fileId === id && !item.protected)
        )
      );
    }
    resetProductionPreview();
    renderProductionCategorySummary();
    renderProductionManager();
    const count = $("productionManagerCount");
    if (count) {
      count.textContent = `${Number(payload.counts?.total || 0)} 个`;
      count.className = `task-state ${Number(payload.counts?.protected || 0) ? "failed" : "neutral"}`;
      count.title = `可清理 ${Number(payload.counts?.deletable || 0)} 个，受保护 ${Number(payload.counts?.protected || 0)} 个`;
    }
  } catch (error) {
    $("productionManagerList").innerHTML = `<p class="empty">${escapeHtml(error.message || "读取生产文件失败")}</p>`;
  } finally {
    if (button) { button.disabled = false; button.textContent = "管理生产文件"; }
    if (refreshButton) refreshButton.disabled = false;
  }
}

function ageFromTime(value) {
  if (!value) return "无成功更新时间";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "时间未知";
  return formatAge(Math.max(0, Math.floor((Date.now() - timestamp) / 1000)));
}

function setBar(id, value) {
  const safe = Number.isFinite(Number(value)) ? Math.min(100, Math.max(0, Number(value))) : 0;
  $(id).style.width = `${safe}%`;
}

function renderProcess(id, label, running) {
  const node = $(id);
  node.textContent = `${label} · ${running ? "运行中" : "未运行"}`;
  node.className = `process-pill ${running ? "running" : "stopped"}`;
}

function renderMetrics(metrics = {}) {
  const cpu = metrics.cpu;
  $("cpuValue").textContent = cpu == null ? "--" : `${cpu}%`;
  setBar("cpuBar", cpu);
  const memory = metrics.memory;
  $("memoryValue").textContent = memory == null ? "--" : `${memory}%`;
  $("memoryNote").textContent = metrics.memory_used_gb == null ? "正在读取" : `${metrics.memory_used_gb} / ${metrics.memory_total_gb} GB`;
  setBar("memoryBar", memory);
  const gpu = metrics.gpu || {};
  $("gpuValue").textContent = gpu.available ? `${gpu.usage}%` : "未检测";
  $("gpuNote").textContent = gpu.available ? `${gpu.name} · ${gpu.temperature}°C` : (gpu.name || "未检测到 NVIDIA GPU");
  setBar("gpuBar", gpu.usage);
  const disk = metrics.disk || {};
  $("diskValue").textContent = disk.percent == null ? "--" : `${disk.percent}%`;
  $("diskNote").textContent = disk.free_gb == null ? "目录暂不可用" : `${disk.label || "成片磁盘"} 剩余 ${disk.free_gb} GB`;
  setBar("diskBar", disk.percent);
  const network = metrics.network || {};
  $("networkValue").textContent = network.online ? "在线" : "离线";
  $("networkNote").textContent = network.online ? `${(network.interfaces || []).length} 个活动网卡` : "未发现活动网络";
  document.querySelector(".network-line").classList.toggle("online", Boolean(network.online));
  const processes = metrics.processes || {};
  renderProcess("workbenchProcess", "工作台", processes.workbench);
  renderProcess("voiceProcess", "语音客户端", processes.voice);
  renderProcess("capcutProcess", "CapCut客户端", processes.capcut);
}

function stageClass(value) {
  if (value === "completed") return "completed";
  if (value === "failed") return "failed";
  if (value === "running") return "active";
  if (value === "unconfigured") return "disabled";
  if (value === "offline") return "failed";
  return "idle";
}

function renderStage(name, data = {}) {
  const suffix = name[0].toUpperCase() + name.slice(1);
  const step = $(`pipe${suffix}`);
  const text = $(`pipe${suffix}Text`);
  if (step) step.className = `pipe-step ${stageClass(data.state)}`;
  if (text) text.textContent = `${data.stateText || "等待状态"} · ${Number(data.progress || 0)}%`;
  const card = $(`stage${suffix}`);
  if (!card) return;
  const klass = stageClass(data.state);
  card.className = `stage-monitor ${klass}`;
  card.querySelector(".stage-badge").textContent = data.stateText || "等待";
  card.querySelector(".stage-current").textContent = data.current || data.source || "暂无当前任务";
  card.querySelector(".stage-progress i").style.width = `${Math.max(0, Math.min(100, Number(data.progress || 0)))}%`;
  const today = data.todaySummary ? ` · 今日 ${data.todaySummary}` : "";
  const testHistory = Number(data.testHistoryCount || 0) ? ` · 测试历史 ${Number(data.testHistoryCount)} 条（不计生产）` : "";
  card.querySelector("small").textContent = `${Number(data.completed || 0)} 完成 / ${Number(data.failed || 0)} 失败 / ${Number(data.total || 0)} 总计${today}${testHistory}`;
}

function renderPipeline(pipeline = {}) {
  ["download", "voice", "stitch", "capcut", "upload"].forEach(name => renderStage(name, pipeline[name]));
  renderDownloadFailures(pipeline.download || {});
  renderUploadSummary(pipeline.upload || {});
  renderPipelineRows(pipeline);
}

function renderUploadSummary(upload = {}) {
  const configured = upload.state !== "unconfigured";
  $("uploadCardTitle").textContent = configured
    ? (upload.state === "running" ? "百度网盘上传中" : upload.stateText || "百度网盘上传服务")
    : "百度网盘未配置";
  $("uploadCardMessage").textContent = configured
    ? `等待 ${upload.waiting || 0}，上传中 ${upload.uploading || 0}，云端已核验 ${upload.cloudVerified || 0}，失败 ${upload.failed || 0}。本条文件已清理 ${upload.taskFilesCleaned || 0}，等待共享引用释放 ${upload.waitingSharedRelease || 0}，全部清理完成 ${upload.localCleaned || 0}，阻止 ${upload.cleanupBlocked || 0}，历史保留 ${upload.legacyRetained || 0}，永久保护 ${upload.permanentKeep || 0}。`
    : "请先在TikHub工作台配置并授权百度网盘。";
  $("uploadCardBadge").textContent = configured
    ? (upload.state === "failed" ? "上传失败" : upload.state === "completed" ? "上传完成" : upload.state === "running" ? "上传中" : "等待成片")
    : "未配置";
  const live = $("uploadLiveProgress");
  if (!live) return;
  live.classList.toggle("hidden", !configured || Number(upload.total || 0) <= 0);
  if (!configured || Number(upload.total || 0) <= 0) return;
  const percent = Math.max(0, Math.min(100, Number(upload.progress || 0)));
  $("uploadProgressLabel").textContent = `总进度 ${Number(upload.completed || 0)} / ${Number(upload.total || 0)} 条`;
  $("uploadProgressPercent").textContent = `${percent.toFixed(percent < 10 && percent > 0 ? 1 : 0)}%`;
  $("uploadProgressBar").style.width = `${percent}%`;
  $("uploadBytesText").textContent = `${formatBytes(upload.bytesUploaded)} / ${formatBytes(upload.bytesTotal)}`;
  $("uploadSpeedText").textContent = Number(upload.speedBytesPerSecond || 0) > 0
    ? `${formatBytes(upload.speedBytesPerSecond)}/s`
    : "正在采样";
  $("uploadRemainingText").textContent = `${Number(upload.waiting || 0) + Number(upload.uploading || 0)} 条 · ${formatBytes(upload.bytesRemaining)}`;
  $("uploadEtaText").textContent = Number(upload.bytesRemaining || 0) <= 0 ? "已完成" : formatDuration(upload.etaSeconds);
  const currentName = String(upload.currentFileName || "").trim();
  $("uploadCurrentFile").textContent = currentName
    ? `当前文件：${currentName} · ${Number(upload.currentFileProgress || 0)}%（百度单文件分片完成后更新）`
    : (Number(upload.bytesRemaining || 0) > 0 ? "当前文件：等待上传服务领取下一条" : "全部文件已完成上传");
}

function renderDownloadFailures(download = {}) {
  const panel = $("downloadFailurePanel");
  const list = $("downloadFailureList");
  const count = $("downloadFailureCount");
  if (!panel || !list || !count) return;
  const items = Array.isArray(download.failureItems) ? download.failureItems : [];
  const failed = Math.max(Number(download.failed || 0), items.length);
  panel.classList.toggle("hidden", failed <= 0);
  count.textContent = `${failed} 条`;
  const shown = items.slice(0, 8);
  list.innerHTML = shown.length
    ? shown.map(item => `<li><code>${escapeHtml(item.url || "未记录链接")}</code><span>${escapeHtml(item.reason || "下载或 AI 去字幕失败")}</span></li>`).join("")
    : `<li><span>已记录 ${failed} 条失败；请在本页任务箱展开对应材料，查看原因并直接补链。</span></li>`;
}

function currentProjectPipeline(payload = {}, currentProjectStatus = {}) {
  const identity = currentProjectStatus?.identity || {};
  const taskId = identity.canonicalTaskId || identity.taskId || "";
  const stages = Array.isArray(currentProjectStatus?.stages) ? currentProjectStatus.stages : [];
  if (!taskId || !stages.length) return null;

  const datePipeline = {};
  (payload.items || []).forEach(item => { datePipeline[item.key] = item; });
  const stateMap = {
    waiting: "idle",
    pending: "idle",
    unknown: "idle",
    blocked: "failed",
    failed: "failed",
    running: "running",
    completed: "completed",
  };
  const currentLabel = [identity.project, identity.material].filter(Boolean).join(" / ") || "当前项目";
  const pipeline = {};
  stages.forEach(stage => {
    const key = stage.step;
    const base = datePipeline[key] || {};
    const total = Number(stage.total || 0);
    const completed = Number(stage.completed || 0);
    const failed = Number(stage.failed || 0);
    const state = stateMap[String(stage.status || "unknown").toLowerCase()] || "idle";
    const stateText = stage.message || ({
      completed: "当前项目已完成",
      running: "当前项目处理中",
      failed: "当前项目被阻止",
      idle: stage.status === "unknown" ? "当前项目状态未知，等待对账" : "等待当前项目进入此阶段",
    }[state]);
    pipeline[key] = {
      ...base,
      ...stage,
      key,
      state,
      stateText,
      total,
      completed,
      failed,
      progress: total ? Math.round((completed + failed) * 100 / total) : 0,
      current: currentLabel,
      source: "当前项目任务级状态",
      todaySummary: "",
      taskScoped: true,
    };
  });
  return pipeline;
}

function renderPipelinePayload(payload = {}, currentProjectStatus = {}) {
  const pipeline = {};
  (payload.items || []).forEach(item => { pipeline[item.key] = item; });
  // The date ledger remains available for history, but it must never be used
  // as the live progress of a different active project.
  renderPipeline(currentProjectPipeline(payload, currentProjectStatus) || pipeline);
  renderPipelineDateOptions(payload.availableDates || [], payload.date);
}

function renderPipelineDateOptions(dates, selected) {
  const select = $("pipelineDateSelect");
  const values = Array.from(new Set([selected, ...dates].filter(Boolean)));
  const signature = values.join("|");
  if (select.dataset.signature !== signature) {
    select.innerHTML = values.map(value =>
      `<option value="${escapeHtml(value)}">生产日期 ${escapeHtml(value)}</option>`
    ).join("");
    select.dataset.signature = signature;
  }
  select.value = values.includes(selected) ? selected : (values[0] || "");
  state.date = select.value;
  $("taskDateLabel").textContent = state.date ? `生产日期 ${state.date}` : "跟随任务箱生产日期";
}

function renderPipelineRows(pipeline = {}) {
  const order = ["download", "voice", "stitch", "capcut", "upload"];
  const rows = $("pipelineRows");
  rows.innerHTML = order.map(key => {
    const item = pipeline[key] || {};
    const onlineText = item.state === "unconfigured"
      ? "尚未接入"
      : (item.programOnline ? "程序运行中" : "程序未运行");
    const onlineClass = item.programOnline ? "online" : "offline";
  const phase = item.phaseText || item.currentPhase || "";
  const current = [item.current || item.todaySummary || item.source || "暂无当前任务", phase]
    .filter(Boolean).join(" · ");
    const testHistory = Number(item.testHistoryCount || 0) ? `；测试历史 ${Number(item.testHistoryCount)} 条（不计生产）` : "";
    const liveText = item.state === "running"
      ? (item.isLive ? "实时更新" : "状态未刷新")
      : formatAge(item.ageSeconds);
    return `<tr>
      <td><span class="step-name"><i class="step-number">${escapeHtml(item.step || "")}</i>${escapeHtml(item.name || key)}</span></td>
      <td>${escapeHtml(item.program || "--")}<span class="program-state ${onlineClass}">${escapeHtml(onlineText)}</span></td>
      <td>${escapeHtml(current)}<span class="subtext">${escapeHtml((item.source || "") + testHistory)}</span></td>
      <td><div class="table-progress"><div class="bar"><i style="width:${Math.max(0, Math.min(100, Number(item.progress || 0)))}%"></i></div><small>${Number(item.progress || 0)}%</small></div></td>
      <td>${Number(item.completed || 0)} / ${Number(item.failed || 0)} / ${Number(item.total || 0)}</td>
      <td class="update-time">${escapeHtml(formatDateTime(item.updatedAt))}<small>${escapeHtml(liveText)}</small></td>
      <td><span class="task-state ${stageClass(item.state) === "active" ? "running" : stageClass(item.state)}">${escapeHtml(item.stateText || "等待")}</span></td>
    </tr>`;
  }).join("");
}

function categoryFor(raw) {
  if (["Completed", "completed"].includes(raw)) return "completed";
  if (["Failed", "failed", "validation_failed", "manual_review"].includes(raw)) return "failed";
  if (["Waiting", "waiting_capcut", "waiting_client", "stopped"].includes(raw)) return "waiting";
  return "running";
}

function step5FilterKey(item) {
  return JSON.stringify([item.project || "未分类", item.material || "--"]);
}

function renderOverview(data, projectGaps = []) {
  state.overview = data;
  const machine = data.machine || {};
  const badge = $("machineBadge");
  badge.className = `status-badge ${machine.online ? "online" : "offline"}`;
  badge.innerHTML = `<span></span>${escapeHtml(machine.name || "--")} · ${machine.online ? "在线" : "离线"}`;
  $("footerMachine").textContent = `${machine.name || "--"} · ${machine.status || "--"}`;
  const counts = data.counts || {};
  $("countTotal").textContent = counts.total || 0;
  $("countWaiting").textContent = counts.waiting || 0;
  $("countRunning").textContent = counts.running || 0;
  $("countCompleted").textContent = counts.completed || 0;
  $("countFailed").textContent = counts.failed || 0;
  const current = data.current;
  const pipeline = data.pipeline || {};
  const upload = data.upload || {};
  renderUploadSummary({
    ...upload,
    stateText: upload.message || upload.stateText,
  });
  const activeStage = ["download", "voice", "stitch", "capcut", "upload"]
    .map(key => pipeline[key]).find(item => item && item.state === "running");
  if (activeStage) {
    $("heroTitle").textContent = `${activeStage.name} · ${activeStage.stateText}`;
    $("heroSubtitle").textContent = activeStage.current || `${activeStage.program}正在运行`;
  } else if (current) {
    $("heroTitle").textContent = current.state_text || "生产线等待中";
    $("heroSubtitle").textContent = `${current.date_label || "未定日期"} · ${current.project || "未分类"} · ${current.material || "未指定材料"} · ${current.language || "未指定语言"}`;
  } else {
    // Nothing runs, but parked projects still wait for links: say so instead
    // of "no production task" (10.7 kept 3 parked projects on 2026-10-09).
    const parked = (Array.isArray(projectGaps) ? projectGaps : []).filter(item => item.gapActive);
    if (parked.length) {
      const missing = parked.reduce((total, item) => total + Number(item.missingCount || 0), 0);
      $("heroTitle").textContent = `没有正在运行的项目 · ${parked.length} 个项目等待补链（共缺 ${missing} 条）`;
      $("heroSubtitle").textContent = parked.slice(0, 4).map(item =>
        `${item.date || ""} ${item.project || "未分类"}/${item.material || "--"} 缺 ${Number(item.missingCount || 0)} 条`).join("；")
        + "。点上方“补链”按钮提交链接。";
    } else {
      $("heroTitle").textContent = "暂时没有生产任务";
      $("heroSubtitle").textContent = "Dashboard 正常运行，正在等待工作台或客户端写入状态。";
    }
  }
  if (current) {
    const category = categoryFor(current.state);
    $("currentDate").textContent = current.date_label || "--";
    $("currentProject").textContent = current.project || "--";
    $("currentMaterial").textContent = current.material || "--";
    $("currentLanguage").textContent = current.language || "--";
    $("currentState").textContent = current.state_text || current.state;
    $("currentState").className = `task-state ${category}`;
    $("currentError").textContent = current.error || "";
    $("currentError").classList.toggle("hidden", !current.error);
  }
  renderMetrics(data.metrics);
}

function renderTasks(items) {
  const rows = $("taskRows");
  const cards = $("taskCards");
  const select = $("step5ProjectFilter");
  const filters = new Map();
  items.forEach(item => {
    const project = item.project || "未分类";
    const material = item.material || "--";
    const key = step5FilterKey(item);
    if (!filters.has(key)) filters.set(key, { project, material });
  });
  if (!filters.has(state.step5Filter)) state.step5Filter = "";
  const filterSignature = Array.from(filters.keys()).join("|");
  if (select.dataset.signature !== filterSignature) {
    select.innerHTML = `<option value="">全部项目</option>${Array.from(filters.entries()).map(([key, filter]) =>
      `<option value="${escapeHtml(key)}">${escapeHtml(filter.project)} / ${escapeHtml(filter.material)}</option>`
    ).join("")}`;
    select.dataset.signature = filterSignature;
  }
  select.value = state.step5Filter;

  const visibleItems = state.step5Filter
    ? items.filter(item => step5FilterKey(item) === state.step5Filter)
    : items;
  const visibleCounts = visibleItems.reduce((counts, item) => {
    counts.total += 1;
    counts[item.category] = (counts[item.category] || 0) + 1;
    return counts;
  }, { total: 0, waiting: 0, running: 0, completed: 0, failed: 0 });
  $("countTotal").textContent = visibleCounts.total;
  $("countWaiting").textContent = visibleCounts.waiting;
  $("countRunning").textContent = visibleCounts.running;
  $("countCompleted").textContent = visibleCounts.completed;
  $("countFailed").textContent = visibleCounts.failed;

  if (!visibleItems.length) {
    rows.innerHTML = `<tr><td colspan="6" class="empty">这个生产日期暂时没有第五步任务</td></tr>`;
    cards.innerHTML = `<p class="empty">这个生产日期暂时没有第五步任务</p>`;
    return;
  }
  const groups = new Map();
  visibleItems.forEach(item => {
    const key = `${item.project || "未分类"} / ${item.material || "--"}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  rows.innerHTML = Array.from(groups.entries()).map(([label, group]) => {
    const done = group.filter(item => item.category === "completed").length;
    return `<tr class="task-group-row"><td colspan="6"><strong>${escapeHtml(label)}</strong><span>${done} / ${group.length} 完成</span></td></tr>${group.map(item => `
    <tr>
      <td><strong>${escapeHtml(item.project || "未分类")}</strong><span class="subtext">${escapeHtml(item.date_label || "")}</span></td>
      <td>${escapeHtml(item.material || "--")}<span class="subtext">${escapeHtml(item.language || "--")}</span></td>
      <td>${escapeHtml(item.number || "--")}${item.sequence ? `-${escapeHtml(item.sequence)}` : ""}</td>
      <td>${escapeHtml(item.phase_text || item.state_text || item.phase || item.state)}<span class="subtext">${item.heartbeat_at ? `心跳 ${escapeHtml(formatClock(item.heartbeat_at))}` : ""}</span></td>
      <td>${escapeHtml(item.output_name || "尚未生成")}<span class="subtext">${escapeHtml(item.video_name || "")}</span></td>
      <td><span class="task-state ${escapeHtml(item.category)}">${escapeHtml(item.category === "running" ? "处理中" : item.state_text)}</span></td>
    </tr>`).join("")}`;
  }).join("");
  cards.innerHTML = Array.from(groups.entries()).map(([label, group]) => {
    const done = group.filter(item => item.category === "completed").length;
    return `<details class="task-card-group" ${done < group.length ? "open" : ""}>
      <summary><strong>${escapeHtml(label)}</strong><span>${done} / ${group.length}</span></summary>
      ${group.map(item => `<article class="task-card-item">
        <div><b>${escapeHtml(item.language || "--")} · ${escapeHtml(item.number || "--")}${item.sequence ? `-${escapeHtml(item.sequence)}` : ""}</b><span class="task-state ${escapeHtml(item.category)}">${escapeHtml(item.category === "running" ? "处理中" : item.state_text)}</span></div>
        <p>${escapeHtml(item.phase_text || item.state_text || item.state)}</p><small>${escapeHtml(item.output_name || "尚未生成")}${item.heartbeat_at ? ` · 心跳 ${escapeHtml(formatClock(item.heartbeat_at))}` : ""}</small>
      </article>`).join("")}
    </details>`;
  }).join("");
}

function renderEvents(items) {
  const node = $("eventList");
  if (!items.length) { node.innerHTML = `<p class="empty">暂无事件</p>`; return; }
  node.innerHTML = items.slice(0, 20).map(item => {
    const severity = String(item.severity || "INFO").toLowerCase();
    return `<div class="event-item ${escapeHtml(severity)}"><i class="event-dot"></i><div><strong>${escapeHtml(item.message)}</strong><small>${escapeHtml(formatClock(item.created_at))}</small></div></div>`;
  }).join("");
}

function renderGapQuickBar(items = []) {
  const bar = $("gapQuickBar");
  const title = $("gapQuickTitle");
  const summary = $("gapQuickSummary");
  const actions = $("gapQuickActions");
  if (!bar || !title || !summary || !actions) return;
  const active = items.filter(item => Boolean(item.gapActive) && String(item.taskId || ""));
  if (!active.length) {
    bar.classList.add("hidden");
    actions.innerHTML = "";
    return;
  }
  const missingFor = item => Number(item.missingCount ?? Math.max(
    0,
    Number(item.expectedCount || 0) - Number(item.completed || 0),
  ));
  const totalMissing = active.reduce((total, item) => total + missingFor(item), 0);
  title.textContent = active.length === 1 ? "当前项目需要补链" : `${active.length} 个项目需要补链`;
  summary.textContent = `合计缺少 ${totalMissing} 条，点击项目直接补充`;
  actions.innerHTML = active.map(item => `
    <button type="button" data-task-id="${escapeHtml(String(item.taskId || ""))}" onclick="openReplenishment(this.dataset.taskId)">
      ${escapeHtml(item.project || "未分类")} / ${escapeHtml(item.material || "--")} · 缺 ${missingFor(item)} 条
    </button>`).join("");
  bar.classList.remove("hidden");
}

function renderProjectGaps(items) {
  const node = $("projectGapList");
  if (!node) return;
  state.gaps = {};
  if (!items.length) {
    renderGapQuickBar([]);
    node.innerHTML = `<p class="empty">暂无项目级下载记录</p>`;
    return;
  }
  node.innerHTML = items.map(item => {
    const expected = Number(item.expectedCount || 0);
    const completed = Number(item.completed || 0);
    const storedMissing = item.missingCount;
    const missing = Number(storedMissing !== undefined && storedMissing !== null && storedMissing !== ""
      ? storedMissing
      : Math.max(0, expected - completed));
    const notStarted = Boolean(item.notStarted);
    const blocked = Boolean(item.gapActive);
    const historicalFailed = Number(item.historicalFailed || 0);
    const current = item.currentTask ? ` · 当前 ${item.currentTask}` : "";
    const error = item.error ? ` · 错误 ${item.error}` : "";
    const videos = Object.values(item.videos || {});
    const taskId = String(item.taskId || "");
    if (taskId) state.gaps[taskId] = item;
    const taskRows = videos.length ? `<details class="project-task-details"><summary>查看 ${videos.length} 条任务状态</summary><ul>${videos.map(video =>
      `<li><span>${escapeHtml(video.url || "--")}</span><b>${escapeHtml(video.stage || "waiting")}</b><em>${escapeHtml(video.error || video.message || video.status || "等待")}</em></li>`
    ).join("")}</ul></details>` : "";
    return `<div class="project-gap ${blocked ? "blocked" : "ok"}">
      <div><strong>${escapeHtml(item.project || "未分类")} / ${escapeHtml(item.material || "--")}</strong><span>${escapeHtml(item.date || "--")}</span></div>
      <p>${notStarted ? `计划 ${expected} · 尚未开始` : `总数 ${expected} · 已完成 ${completed} · 剩余 ${missing} · 当前失败 ${Number(item.failed || 0)}`}</p>
      <small>${escapeHtml((item.stateText || item.status || "--") + current + error)}</small>
      ${historicalFailed ? `<small class="history-note">历史失败 ${historicalFailed} 条，已被有效补链覆盖</small>` : ""}
      ${blocked && taskId ? `<div class="queue-actions"><button class="start" data-task-id="${escapeHtml(taskId)}" onclick="openReplenishment(this.dataset.taskId)">按此缺口补链</button></div>` : ""}
      ${taskRows}
    </div>`;
  }).join("");
  renderGapQuickBar(items);
}

function renderTemplates(items) {
  const nextTemplates = Array.isArray(items) ? items : [];
  const signature = JSON.stringify(nextTemplates);
  const select = $("createTemplate");
  if (!select) return;
  if (signature === state.templateSignature && select.options.length > 1) return;
  state.templates = nextTemplates;
  state.templateSignature = signature;
  const previous = select.value;
  select.innerHTML = `<option value="">请选择项目</option>${state.templates.map(item =>
    `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label || `${item.project} / ${item.material}`)}</option>`
  ).join("")}`;
  if (previous && state.templates.some(item => String(item.id) === previous)) select.value = previous;
  updateMaterialOptions();
}

function updateMaterialOptions() {
  const template = state.templates.find(item => String(item.id) === String($("createTemplate")?.value || ""));
  const select = $("createMaterial");
  const count = $("createExpectedCount");
  if (!select) return;
  const materials = template?.materials?.length ? template.materials : (template?.material ? [template.material] : []);
  select.innerHTML = materials.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("");
  if (count && template?.expectedCount) count.value = template.expectedCount;
}

// Mutating control actions have different runtimes.  Keep the short default
// for ordinary UI commands, but let long, explicitly confirmed maintenance
// jobs wait for their real response instead of aborting the browser request.
async function postJson(url, payload, options = {}) {
  const timeoutMs = Number.isFinite(Number(options.timeoutMs))
    ? Math.max(1000, Number(options.timeoutMs))
    : 10000;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "操作失败");
    return result;
  } catch (error) {
    if (error?.name === "AbortError") {
      const timeoutError = new Error(`操作仍在后台处理（已等待 ${Math.ceil(timeoutMs / 60000)} 分钟），请刷新状态后再继续`);
      timeoutError.code = "CONTROL_REQUEST_TIMEOUT";
      timeoutError.cause = error;
      throw timeoutError;
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

function openReplenishment(taskId) {
  const item = state.gaps[String(taskId)];
  const panel = $("replenishPanel");
  const dialog = $("replenishDialog");
  if (!item || !panel) return;
  const expected = Number(item.expectedCount || 0);
  const completed = Number(item.completed || 0);
  const missing = Number(item.missingCount ?? Math.max(0, expected - completed));
  panel.innerHTML = `<header><div><strong>补链：${escapeHtml(item.project)} / ${escapeHtml(item.material)}</strong>
    <p>原计划 ${expected} 条，已完成 ${completed} 条；请只粘贴 ${missing} 条新链接。</p></div>
    <button id="closeReplenishDialog" type="button" aria-label="关闭补链窗口">×</button></header>
    <form id="replenishForm"><label class="wide">新链接（每行一条）<textarea id="replenishUrls" rows="4" required></textarea></label>
    <label class="wide checkbox"><input id="replenishStartNow" type="checkbox" checked>补链后继续当前项目</label>
    <button class="primary wide" type="submit">提交补链</button></form>`;
  $("closeReplenishDialog")?.addEventListener("click", () => dialog?.close());
  $("replenishForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button");
    button.disabled = true;
    try {
      const result = await postJson(`/api/controls/tasks/${encodeURIComponent(taskId)}/replenish`, {
        urls: $("replenishUrls").value,
        startNow: $("replenishStartNow").checked,
      });
      renderActionResult("queueActionResult", {
        state: "completed",
        message: result.message || "补链任务已提交",
        updatedAt: new Date().toISOString(),
      });
      if (dialog?.open) dialog.close();
      panel.innerHTML = "";
      await refresh();
    } catch (error) {
      renderActionResult("queueActionResult", {
        state: "failed",
        message: error.message || "补链失败",
        updatedAt: new Date().toISOString(),
      });
      button.disabled = false;
    }
  });
  if (dialog && !dialog.open) dialog.showModal();
  $("replenishUrls")?.focus();
}

function renderReceiverQueue(items) {
  const node = $("receiverQueue");
  if (!node) return;
  if (!items.length) {
    node.innerHTML = `<p class="empty">暂无可确认或撤回的队列任务</p>`;
    return;
  }
  // 223 items imported in July-September stayed "imported_waiting_start" and
  // made this list 25,000 px long.  Keep what can need a decision in view.
  const recentMs = 3 * 24 * 3600 * 1000;
  const isRecent = item => String(item.status || "") === "pending_confirmation" ||
    Date.now() - Date.parse(item.importedAt || item.createdAt || "") < recentMs;
  const recent = items.filter(isRecent);
  const older = items.filter(item => !isRecent(item));
  const render = list => list.map(item => {
    const taskId = String(item.taskId || "");
    const status = String(item.status || "");
    const canStart = status === "pending_confirmation" && !["auto_start_first", "auto_start_sequential"].includes(String(item.startMode || ""));
    const canCancel = status === "pending_confirmation" || status === "imported_waiting_start";
    const sequence = item.batchId ? `第 ${item.batchSequence || 1} / ${item.batchSize || 1} 项` : "单条任务";
    const actions = [
      canStart ? `<button class="start" data-task-id="${escapeHtml(taskId)}" onclick="controlTask(this, 'start')">启动首项</button>` : "",
      canCancel ? `<button class="cancel" data-task-id="${escapeHtml(taskId)}" onclick="controlTask(this, 'cancel')">撤回</button>` : "",
    ].join("");
    return `<article class="receiver-queue-item">
      <div><strong>${escapeHtml(item.project || "未分类")} / ${escapeHtml(item.material || "--")}</strong><span class="task-state neutral">${escapeHtml(status)}</span></div>
      <small>${escapeHtml(item.date || "--")} · ${escapeHtml(sequence)} · ${Number((item.urls || []).length)} 条链接</small>
      ${actions ? `<div class="queue-actions">${actions}</div>` : ""}
    </article>`;
  }).join("");
  const wasOpen = Boolean(node.querySelector("details.receiver-queue-older")?.open);
  node.innerHTML = (recent.length ? render(recent) : `<p class="empty">最近 3 天没有需要确认或撤回的任务</p>`)
    + (older.length ? `<details class="receiver-queue-older"${wasOpen ? " open" : ""}>
        <summary>更早导入的 ${older.length} 条任务（超过 3 天，通常无需操作）</summary>${render(older)}</details>` : "");
}

function renderTaskBoxes(payload = {}) {
  const boxes = Array.isArray(payload.items) ? payload.items : [];
  const history = Array.isArray(payload.history) ? payload.history : [];
  const historyPanel = $("taskBoxHistory");
  historyPanel.classList.toggle("hidden", !history.length);
  $("taskBoxHistoryCount").textContent = String(history.length);
  $("taskBoxHistoryItems").innerHTML = history.map(item => `<article class="taskbox-history-item">
    <strong>${escapeHtml(item.project || "未分类")} / ${escapeHtml(item.material || "--")}</strong>
    <span>${escapeHtml(item.productionDate || "--")} · ${escapeHtml(item.status || "cancelled")} · ${escapeHtml(item.reason || "已撤回")}</span>
  </article>`).join("");
  const selected = payload.selected || boxes.find(item => item.batchId === state.batchId) || boxes[0];
  const select = $("taskBoxSelect");
  // Rebuild only when the options themselves change; an update time alone
  // re-rendered the list (and closed it) while it was being used.
  const signature = boxes.map(item =>
    `${item.batchId}:${item.productionDate}:${item.completedProjects}/${item.projectCount}:${item.state}`
  ).join("|");
  if (select.dataset.signature !== signature) {
    select.innerHTML = boxes.length ? boxes.map(item =>
      `<option value="${escapeHtml(item.batchId)}">${escapeHtml(item.productionDate || "未定日期")} · ${item.completedProjects}/${item.projectCount} 项${item.state === "stale" ? " · 历史未完成" : ""} · ${escapeHtml(item.batchId.slice(-8))}</option>`
    ).join("") : `<option value="">暂无任务箱</option>`;
    select.dataset.signature = signature;
  }
  if (!selected) {
    state.batchId = "";
    $("taskBoxTitle").textContent = "暂无任务箱";
    $("taskBoxProjectProgress").textContent = "0 / 0";
    $("taskBoxVideoProgress").textContent = "0 / 0";
    $("taskBoxCurrent").textContent = "--";
    $("taskBoxNext").textContent = "--";
    $("taskBoxScope").textContent = "本次项目组合：当前无生产任务";
    $("taskBoxItems").innerHTML = `<p class="empty">等待公司投递器提交任务</p>`;
    setBar("taskBoxBar", 0);
    return;
  }
  state.batchId = selected.batchId;
  select.value = selected.batchId;
  const current = selected.current;
  const next = selected.next;
  const selectedProjects = Array.isArray(selected.selectedProjects) ? selected.selectedProjects.filter(Boolean) : [];
  const deferredProjects = Array.isArray(selected.unselectedProjects) ? selected.unselectedProjects.filter(Boolean) : [];
  $("taskBoxScope").textContent = selectedProjects.length
    ? `本次项目组合：${selectedProjects.join("、")}${deferredProjects.length ? `；未选择：${deferredProjects.join("、")}` : ""}`
    : "本次项目组合：按现有任务合同运行";
  const position = current ? `当前第 ${current.sequence} / ${selected.projectCount} 项` : "没有正在运行的项目";
  $("taskBoxTitle").textContent = `${selected.productionDate || "未定日期"}任务箱 · 已完成 ${selected.completedProjects} / ${selected.projectCount}`
    + (selected.state === "stale" ? " · 历史未完成（超过 14 天）" : "");
  $("taskBoxProjectProgress").textContent = `${selected.completedProjects} / ${selected.projectCount}`;
  $("taskBoxVideoProgress").textContent = `${selected.completedVideos} / ${selected.totalVideos}`;
  $("taskBoxCurrent").textContent = current ? `${current.sequence}/${selected.projectCount} ${current.project}/${current.material}` : position;
  $("taskBoxNext").textContent = next ? `${next.sequence}/${selected.projectCount} ${next.project}/${next.material}` : "--";
  setBar("taskBoxBar", selected.projectCount ? selected.completedProjects * 100 / selected.projectCount : 0);
  $("batchStatusTitle").textContent = `${selected.projectCount}个项目实时状态`;
  $("taskBoxItems").innerHTML = (selected.items || []).map(item => `
    <article class="taskbox-item ${escapeHtml(item.status)} ${current && current.taskId === item.taskId ? "current" : ""}">
      <div><span class="taskbox-sequence">${item.sequence}</span><strong>${escapeHtml(item.project)} / ${escapeHtml(item.material || "--")}</strong><span class="task-state ${item.status === "blocked" ? "failed" : item.status === "planned" ? "neutral" : escapeHtml(item.status)}">${escapeHtml(item.currentStep)}</span></div>
      <p>${escapeHtml(item.stateText)}</p>
      <small>成片 ${item.finalCompleted} / ${item.expected}${item.historicalFailed ? ` · 历史失败 ${item.historicalFailed}` : ""}</small>
    </article>`).join("");
}

function renderServices(items = []) {
  const node = $("serviceHealthGrid");
  node.innerHTML = items.map(item => `<div class="service-health ${item.online ? "online" : "offline"}">
    <i></i><strong>${escapeHtml(item.name)}</strong><span>${escapeHtml(item.stateText || (item.online ? "运行中" : "未运行"))} · ${escapeHtml(ageFromTime(item.updatedAt))}</span>
  </div>`).join("");
}

// Combine the process scan with the current project so the page states the
// real situation: a "running" project whose workbench is gone has stopped,
// and CapCut/Fish need the PC left alone while they drive the UI.
function runtimeFacts(services = [], currentProjectStatus = {}) {
  const items = Array.isArray(services) ? services : [];
  const online = key => Boolean(items.find(item => item.key === key)?.online);
  const stages = Array.isArray(currentProjectStatus?.stages) ? currentProjectStatus.stages : [];
  const download = stages.find(item => item.step === "download") || {};
  const identity = currentProjectStatus?.identity || {};
  const facts = {
    known: items.length > 0,
    workbench: online("workbench"),
    voice: online("voice"),
    capcut: online("capcut"),
    downloading: String(download.status || "").toLowerCase() === "running",
    projectRunning: String(currentProjectStatus?.state || "").toLowerCase() === "running",
    projectLabel: [identity.project, identity.material].filter(Boolean).join(" / ")
  };
  facts.offline = facts.known && !facts.workbench && facts.projectRunning;
  facts.busy = facts.known && facts.workbench && (facts.capcut || facts.voice || facts.downloading);
  return facts;
}

function renderRuntimeGuidance(services = [], currentProjectStatus = {}) {
  const facts = runtimeFacts(services, currentProjectStatus);
  state.runtime = facts;
  const node = $("runtimeGuidance");
  let tone = "";
  let html = "";
  if (facts.offline) {
    tone = "offline";
    html = `<strong>工作台已离线，生产实际已停止</strong>当前项目${facts.projectLabel ? `（${escapeHtml(facts.projectLabel)}）` : ""}显示为运行中，但工作台没有在运行。点击“安全继续当前项目”会自动启动工作台，并从断点继续。`;
  } else if (facts.workbench && facts.capcut) {
    tone = "hands-off";
    html = "<strong>CapCut 正在自动剪辑：请勿操作这台电脑</strong>剪映需要独占前台，移动鼠标、敲键盘或切换窗口都会让它失败。即使出现失败，客户端也会先自动重试，无需马上点击安全继续。";
  } else if (facts.workbench && facts.voice) {
    tone = "hands-off";
    html = "<strong>正在生成语音：请勿切换或关闭 Fish Audio 页面</strong>Fish 页面需要保持在文本转语音页，并保持窗口最大化。";
  }
  node.className = `runtime-guidance ${tone}${tone ? "" : " hidden"}`;
  node.innerHTML = html;
  if (state.lastContinueResult) renderContinueResult(state.lastContinueResult);
}

// One line on what is stuck and what to do.  The workbench already writes a
// readable reason into each current-project error; this names the step and
// adds the matching action.  Download gaps keep their own 补链 bar.
function nextActionFor(currentProjectStatus = {}) {
  const errors = Array.isArray(currentProjectStatus?.errors) ? currentProjectStatus.errors : [];
  if (!errors.length) return null;
  const identity = currentProjectStatus?.identity || {};
  const label = [identity.project, identity.material].filter(Boolean).join(" / ");
  const where = label ? `${label}：` : "";
  const first = errors[0] || {};
  const reasons = items => items.map(item => String(item.message || "").trim()).filter(Boolean);
  const capcut = errors.filter(item => item.component === "capcut");
  const upload = errors.filter(item => item.component === "upload");
  const resume = "点“安全继续当前项目”。";
  if (String(first.errorCode || "") === "VOICE_LOGIN_REQUIRED") {
    return {title: `${where}Fish Audio 登录已失效`, reasons: reasons([first]),
      action: "请先在浏览器重新登录 Fish Audio，再点“安全继续当前项目”。"};
  }
  if (first.component === "voice") {
    return {title: `${where}第 3 步配音没有完成`, reasons: reasons([first]),
      action: "点“安全继续当前项目”：只补做缺少的语音，不会重新下载。"};
  }
  if (first.component === "stitch") {
    return {title: `${where}第 4 步拼接被卡住`, reasons: reasons([first]), action: resume};
  }
  if (capcut.length) {
    return {title: `${where}第 5 步剪映有 ${capcut.length} 条失败`, reasons: reasons(capcut),
      action: "点“安全继续当前项目”从失败处继续；剪映运行时请不要操作这台电脑。"};
  }
  if (upload.length) {
    return {title: `${where}百度网盘上传有 ${upload.length} 条失败`, reasons: reasons(upload),
      action: "请在下方上传面板查看原因。"};
  }
  return {title: `${where}当前项目被卡住`, reasons: reasons([first]), action: resume};
}

function renderNextAction(currentProjectStatus = {}) {
  const node = $("nextAction");
  if (!node) return;
  const facts = state.runtime || {};
  // While a client is working (or the workbench is offline) the banner above
  // already says what to do; a "click Safe Continue" line would contradict it.
  const next = facts.busy || facts.offline ? null : nextActionFor(currentProjectStatus);
  node.classList.toggle("hidden", !next);
  if (!next) {
    node.innerHTML = "";
    return;
  }
  const shown = next.reasons.slice(0, 3);
  const more = next.reasons.length > shown.length ? `（另有 ${next.reasons.length - shown.length} 条）` : "";
  node.innerHTML = `<strong>${escapeHtml(next.title)}</strong>`
    + (shown.length ? `<span class="next-action-reason">原因：${shown.map(escapeHtml).join("；")}${more}</span>` : "")
    + `<span class="next-action-do">${escapeHtml(next.action)}</span>`;
}

function renderHealth(health = {}) {
  const body = $("healthBody");
  if (!body) return;
  // No data (older backend or a failed read) must never read as "healthy".
  $("healthPanel").classList.toggle("hidden", !health.updatedAt);
  if (!health.updatedAt) return;
  const commands = Array.isArray(health.openCommands) ? health.openCommands : [];
  const errors = Array.isArray(health.recentErrors) ? health.recentErrors : [];
  const stuck = commands.filter(item => Number(item.ageSeconds || 0) > 600 || item.state === "reconciliation_required");
  $("healthTitle").textContent = stuck.length
    ? `系统健康 · ${stuck.length} 条安全继续命令未结束`
    : errors.length ? `系统健康 · 最近 24 小时 ${errors.length} 类报错` : "系统健康 · 正常";
  $("healthPanel").classList.toggle("needs-action", stuck.length > 0);
  const commandRows = commands.length
    ? commands.map(item => `<li><b>${escapeHtml(item.step || "--")} · ${escapeHtml(item.state)}</b>
        <span>${escapeHtml(item.taskId || item.commandId)}</span>
        <em>已持续 ${escapeHtml(formatAge(item.ageSeconds).replace("前", ""))}</em></li>`).join("")
    : `<li class="ok">没有未结束的安全继续命令</li>`;
  const errorRows = errors.length
    ? errors.map(item => `<li><b>${escapeHtml(String(item.lastAt || "").slice(5, 16).replace("T", " "))}</b>
        <span>${escapeHtml(item.message)}</span>${Number(item.count) > 1 ? `<em>${Number(item.count)} 次</em>` : ""}</li>`).join("")
    : `<li class="ok">${health.logAvailable === false ? "未找到工作台日志文件" : "最近 24 小时工作台日志没有报错"}</li>`;
  body.innerHTML = `<div><h3>安全继续命令</h3><ul>${commandRows}</ul></div>
    <div><h3>工作台最近报错</h3><ul>${errorRows}</ul></div>`;
}

// Turn known source failures into what they mean for the operator.
function describeSourceErrors(errors = []) {
  const groups = new Map();
  errors.forEach(item => {
    const name = String(item.name || "");
    const key = name === "第四步到第五步.json" ? "handoff"
      : name === "last_batch_handoff.json" ? "voice" : `other:${name}:${item.error || ""}`;
    groups.set(key, [...(groups.get(key) || []), item]);
  });
  return [...groups.entries()].map(([key, items]) => {
    if (key === "handoff") return `${items.length} 个日期的剪映交接记录（第四步到第五步.json）无法读取，这些日期的第 5 步历史暂时不完整`;
    if (key === "voice") return "语音交接记录（last_batch_handoff.json）无法读取；下一批配音开始后会重新生成";
    return `${items[0].name}：${items[0].error}`;
  });
}

function renderSources(source = {}) {
  const panel = $("sourceWarningPanel");
  const errors = Array.isArray(source.errors) ? source.errors : [];
  const messages = [];
  if (source.stale) messages.push("Dashboard采集状态已经过期");
  if (source.receiverError) messages.push(`接收器状态读取失败：${source.receiverError}`);
  if (source.watchdog && source.watchdog.state === "failed") {
    messages.push(`Dashboard守护启动失败：${source.watchdog.message || "原因未知"}`);
  }
  describeSourceErrors(errors).slice(0, 5).forEach(message => messages.push(message));
  panel.classList.toggle("hidden", !messages.length);
  panel.innerHTML = messages.length
    ? `<strong>状态源提醒</strong><ul>${messages.map(message => `<li>${escapeHtml(message)}</li>`).join("")}</ul>`
    : "";
}

function renderContinueResult(result = {}) {
  state.lastContinueResult = result;
  const node = $("continueResult");
  const stateName = String(result.state || "idle");
  state.continueCommandId = String(result.commandId || state.continueCommandId || "");
  // A continue command is durable on the receiver.  Keep the button locked for
  // every non-terminal recovery phase, including the v3 accepted/recovering
  // states, so a refresh can never make a second click look safe.
  const inFlightStates = ["requested", "accepted", "running", "recovering", "persisted", "receiver_acknowledged", "workbench_acknowledged", "executing"];
  const commandInFlight = !result.stale && inFlightStates.includes(stateName)
    && result.continueCanRetry !== true;
  const stateLabel = {
    idle: "尚未对账", requested: "命令已发送", persisted: "命令已保存",
    receiver_acknowledged: "家里接收器已收到", workbench_acknowledged: "家里工作台已领取",
    executing: "正在安全继续", accepted: "工作台已接收",
    running: "正在安全继续", recovering: "正在恢复当前项目",
    completed: "恢复已完成", blocked: "已阻止", failed: "执行失败", expired: "命令已过期"
  }[stateName] || stateName;
  state.continueInFlight = commandInFlight;
  const rows = Array.isArray(result.steps) ? result.steps : [];
  const launchError = inFlightStates.includes(stateName)
    ? String(result.workbenchLaunchError || "")
    : "";
  const launchCode = String(result.workbenchLaunchCode || "");
  const launchLog = String(result.workbenchLaunchLog || "");
  const launchState = result.workbenchReady
    ? "工作台已确认就绪"
    : result.workbenchAlreadyRunning
      ? "正在复用已运行的工作台"
      : result.workbenchStartPending
        ? "工作台正在启动"
        : result.workbenchStarted
          ? "工作台已启动，等待接收指令"
          : "";
  node.className = `reconcile-result ${stateName === "completed" ? "completed" : ["blocked", "failed"].includes(stateName) ? "failed" : "neutral"}`;
  const commandDetail = result.commandId
    ? `<small>命令编号：${escapeHtml(result.commandId)}${commandInFlight ? " · 请勿重复点击" : ""}</small>`
    : "";
  const bridgeState = String(result.bridgeState || "");
  const bridgeMessage = String(result.bridgeMessage || "");
  const bridgeDetail = bridgeState
    ? `<p><small>Fish桥接：${escapeHtml(bridgeState)}${result.bridgePort ? ` · 端口 ${Number(result.bridgePort)}` : ""}${result.bridgePid ? ` · PID ${Number(result.bridgePid)}` : ""}${bridgeMessage ? ` · ${escapeHtml(bridgeMessage)}` : ""}</small></p>`
    : "";
  node.innerHTML = `<div class="reconcile-head"><strong>${escapeHtml(stateLabel)}${result.stale ? " · 结果已过期" : ""}</strong><span>${escapeHtml(formatDateTime(result.finishedAt || result.requestedAt))}</span></div>
    <p>${escapeHtml(result.message || "尚未执行安全继续对账")}</p>
    ${commandDetail}
    ${bridgeDetail}
    ${rows.length ? `<div class="reconcile-steps">${rows.map(item => `<div><span>${item.step}. ${escapeHtml(item.name)}</span><b>${Number(item.actual || 0)} / ${Number(item.expected || 0)}</b></div>`).join("")}</div>` : ""}`;
  if (launchState || launchError) {
    const detail = document.createElement("p");
    detail.className = launchError ? "failed" : "";
    detail.textContent = launchError
      ? `工作台启动失败${launchCode ? `（${launchCode}）` : ""}：${launchError}${launchLog ? `；日志：${launchLog}` : ""}`
      : `${launchState}${result.workbenchPid ? `（PID ${Number(result.workbenchPid)}）` : ""}`;
    node.appendChild(detail);
  }
  const button = $("continueCurrentButton");
  const allowed = result.allowed !== false;
  // The workbench is already working on the project (download, Fish or
  // CapCut). A click then starts nothing, and touching the PC can break
  // CapCut, so the button explains instead of inviting a click. An offline
  // workbench never sets runtimeBusy: that is exactly when Safe Continue helps.
  const runtimeBusy = !commandInFlight && Boolean(state.runtime?.busy);
  const clickable = allowed && !runtimeBusy && (result.continueCanRetry === true || !commandInFlight);
  button.dataset.allowed = clickable ? "true" : "false";
  button.dataset.commandState = stateName;
  button.disabled = !clickable;
  button.textContent = runtimeBusy
    ? "流水线正在运行，无需点击"
    : ["requested", "persisted"].includes(stateName)
    ? "命令已保存，等待接收器…"
    : stateName === "receiver_acknowledged"
      ? "接收器已收到，等待工作台…"
    : ["accepted", "workbench_acknowledged"].includes(stateName)
      ? "工作台已接收，正在核对…"
      : ["running", "recovering", "executing"].includes(stateName)
      ? "正在安全继续，请勿重复点击…"
      : "安全继续当前项目";
  button.title = runtimeBusy
    ? "工作台正在自动处理当前项目（下载/语音/CapCut），点击不会启动任何新步骤；运行结束或出现阻断后按钮会恢复"
    : commandInFlight
    ? (result.continueLockReason || result.message || "继续命令正在执行，请等待状态更新")
    : allowed ? "" : (result.message || "接收器状态未对账");
}

// The continue command has its own durable lifecycle. Poll it independently
// from the large dashboard payload so a transient error in any unrelated
// dashboard panel cannot leave the action button showing an obsolete
// "recovering" state after the receiver has already finished or blocked it.
async function refreshContinueStatus() {
  if (state.continueStatusBusy) return;
  state.continueStatusBusy = true;
  try {
    const result = await getJson("/api/control-commands/current");
    state.continueStatusFailures = 0;
    renderContinueResult(result || {});
  } catch (error) {
    state.continueStatusFailures += 1;
    // Never leave a stale "recovering" label on screen while the control
    // service is offline.  The action remains disabled (we cannot prove that
    // a retry is safe), but the user sees the real reason instead of assuming
    // that production is still running.  A healthy response restores the
    // authoritative command state automatically.
    if (state.continueStatusFailures >= 2) {
      const button = $("continueCurrentButton");
      const node = $("continueResult");
      if (button) {
        button.disabled = true;
        button.dataset.allowed = "false";
        button.textContent = "状态服务离线，正在重连…";
        button.title = "Dashboard或任务接收器暂时不可用，恢复连接后会自动重新对账";
      }
      if (node) {
        node.className = "reconcile-result failed";
        node.innerHTML = `<div class="reconcile-head"><strong>状态服务离线</strong></div><p>${escapeHtml(error?.message || "无法读取安全继续状态；正在自动重连")}</p>`;
      }
    }
  } finally {
    state.continueStatusBusy = false;
  }
}

function renderActionResult(id, result = {}) {
  const node = $(id);
  const stateName = String(result.state || "idle");
  node.className = `action-result ${stateName === "completed" ? "completed" : stateName === "failed" ? "failed" : "neutral"}`;
  node.textContent = `${result.message || "尚无操作记录"}${result.updatedAt ? ` · ${formatDateTime(result.updatedAt)}` : ""}`;
}

function renderHistoricalCloudVerification(result = {}) {
  const stateName = String(result.state || "idle");
  const total = Number(result.total ?? result.eligible ?? 0);
  const processed = Number(result.processed || 0);
  const verified = Number(result.verified || 0);
  const failed = Number(result.failed || 0);
  const summary = total
    ? ` · ${processed}/${total}，通过 ${verified}，失败 ${failed}`
    : "";
  renderActionResult("historicalCloudVerificationResult", {
    ...result,
    message: `${result.message || "尚未核验历史百度云文件"}${summary}`,
  });
  const button = $("historicalCloudVerifyButton");
  if (!button) return;
  const running = ["requested", "running"].includes(stateName);
  button.disabled = running;
  button.textContent = running
    ? `正在核验历史云端文件 ${processed}/${total || "…"}`
    : "核验历史云端文件";
}

async function controlTask(button, action) {
  const taskId = String(button.dataset.taskId || "");
  if (!taskId) return;
  const isStart = action === "start";
  const question = isStart
    ? "确认启动这个批次的首项吗？工作台会继续按原有顺序处理。"
    : "确认撤回这个尚未开始的任务吗？不会删除任何视频、音频或素材。";
  if (!window.confirm(question)) return;
  button.disabled = true;
  button.textContent = isStart ? "正在启动…" : "正在撤回…";
  try {
    const response = await fetch(`/api/controls/tasks/${encodeURIComponent(taskId)}/${action}`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "操作失败");
    renderActionResult("queueActionResult", {
      state: "completed",
      message: result.message || (isStart ? "启动命令已发送" : "撤回命令已发送"),
      updatedAt: new Date().toISOString(),
    });
    await refresh();
  } catch (error) {
    renderActionResult("queueActionResult", {
      state: "failed",
      message: error.message || "操作失败",
      updatedAt: new Date().toISOString(),
    });
    button.disabled = false;
    button.textContent = isStart ? "启动首项" : "撤回";
  }
}

// The 5-second status refresh keeps an 8 s limit; the file managers scan
// thousands of files (production files: 2,752 in about 12 s on 2026-10-11)
// and pass a longer one.
async function getJson(url, retries = 1, timeoutMs = 8000) {
  let lastError;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const headers = {};
      if (state.etags[url]) headers["If-None-Match"] = state.etags[url];
      const response = await fetch(url, { cache: "no-cache", headers, signal: controller.signal });
      if (response.status === 304 && state.cachedJson[url]) return state.cachedJson[url];
      if (!response.ok) throw new Error(`${response.status}`);
      const result = await response.json();
      const etag = response.headers.get("ETag");
      if (etag) state.etags[url] = etag;
      state.cachedJson[url] = result;
      return result;
    } catch (error) {
      lastError = error;
      if (attempt < retries) await new Promise(resolve => window.setTimeout(resolve, 500 * (2 ** attempt)));
    } finally {
      window.clearTimeout(timer);
    }
  }
  throw lastError || new Error("请求失败");
}

async function refresh() {
  if (state.refreshBusy) return;
  state.refreshBusy = true;
  try {
    const useSummary = state.fullDashboardLoaded && !state.historyExplicit && !state.batchId;
    const params = new URLSearchParams();
    if (state.date) params.set("date", state.date);
    if (state.batchId) params.set("batchId", state.batchId);
    const url = useSummary ? "/api/dashboard/summary" : `/api/dashboard${params.toString() ? `?${params}` : ""}`;
    const data = await getJson(url, 2);
    recordDashboardReception();
    state.lastGoodDashboard = data;
    state.healthFailures = 0;
    if (useSummary) {
      renderPipelinePayload(data.pipeline || {}, data.currentProjectStatus || {});
      // The authoritative summary may legitimately have no active task after
      // a batch completes or the workbench is stopped.  Clear the current
      // panel explicitly instead of leaving a stale historical box visible.
      renderTaskBoxes(data.currentTaskBox
        ? {items: [data.currentTaskBox], selected: data.currentTaskBox, history: []}
        : {items: [], selected: null, history: []});
      renderServices(data.services || []);
      renderRuntimeGuidance(data.services || [], data.currentProjectStatus || {});
      renderNextAction(data.currentProjectStatus || {});
      renderHealth(data.health || {});
      renderContinueResult(data.controls?.continue || {});
      try { window.localStorage.setItem("dashboardLastTrustedSummary", JSON.stringify(data)); } catch (_) {}
      return;
    }
    state.fullDashboardLoaded = true;
    state.date = data.selectedDate || state.date;
    renderOverview(data.overview || {}, data.projectGaps?.items || []);
    renderPipelinePayload(data.pipeline || {}, data.currentProjectStatus || {});
    state.step5Items = data.tasks?.items || [];
    renderTasks(state.step5Items);
    renderEvents(data.events?.items || []);
    renderProjectGaps(data.projectGaps?.items || []);
    renderReceiverQueue(data.receiverQueue?.items || []);
    renderTemplates(data.templates?.items || []);
    renderTaskBoxes(data.taskBoxes || {});
    renderServices(data.services || []);
    renderRuntimeGuidance(data.services || [], data.currentProjectStatus || {});
    renderNextAction(data.currentProjectStatus || {});
    renderHealth(data.health || {});
    renderSources(data.sources || {});
    renderContinueResult(data.controls?.continue || {});
    renderActionResult("uploadActionResult", data.controls?.uploadRescan || {});
    renderHistoricalCloudVerification(data.controls?.historicalCloudVerification || {});
    renderActionResult("draftCleanupResult", data.controls?.capcutDraftCleanup || {});
    renderActionResult("audioCleanupResult", data.controls?.audioCleanup || {});
    renderActionResult("productionCleanupResult", data.controls?.productionFileCleanup || {});
    renderActionResult("resetRecordsResult", data.controls?.resetRecords || {});
    await refreshSafety();
  } catch (error) {
    try {
      await getJson("/api/health", 0);
      state.healthFailures = 0;
      $("machineBadge").className = "status-badge warning";
      $("machineBadge").innerHTML = "<span></span>明细同步较慢";
      $("heroSubtitle").textContent = "家里服务在线，正在显示最后可信状态并继续同步明细。";
    } catch (_) {
      state.healthFailures += 1;
      if (state.healthFailures >= 3) {
        $("machineBadge").className = "status-badge offline";
        $("machineBadge").innerHTML = "<span></span>家里服务离线";
        $("heroTitle").textContent = "暂时无法读取新状态";
      }
      $("heroSubtitle").textContent = state.lastGoodDashboard
        ? "正在显示上一次可信状态；不会清空已有信息。"
        : "页面会继续自动重试，不影响正在运行的生产任务。";
    }
  } finally {
    state.refreshBusy = false;
  }
}

$("pipelineDateSelect").addEventListener("change", event => {
  state.date = event.target.value;
  state.historyExplicit = true;
  refresh();
});
$("taskBoxSelect")?.addEventListener("change", event => {
  state.batchId = event.target.value;
  state.date = "";
  state.historyExplicit = Boolean(state.batchId);
  refresh();
});
$("step5ProjectFilter")?.addEventListener("change", event => {
  state.step5Filter = event.target.value;
  renderTasks(state.step5Items);
});
$("openDraftManagerButton")?.addEventListener("click", async () => {
  const dialog = $("draftManagerDialog");
  if (dialog && !dialog.open) dialog.showModal();
  await loadDraftManager();
});
$("closeDraftManagerButton")?.addEventListener("click", () => $("draftManagerDialog")?.close());
$("refreshDraftManagerButton")?.addEventListener("click", loadDraftManager);
["draftCategoryFilter", "draftDateFilter", "draftSearchFilter"].forEach(id => {
  $(id)?.addEventListener(id === "draftSearchFilter" ? "input" : "change", () => {
    resetDraftPreview();
    renderDraftManager();
  });
});
$("selectFilteredDraftsButton")?.addEventListener("click", () => {
  filteredDrafts().filter(item => !item.protected).forEach(item => state.selectedDraftIds.add(item.draftId));
  resetDraftPreview();
  renderDraftManager();
});
$("clearDraftSelectionButton")?.addEventListener("click", () => {
  state.selectedDraftIds.clear();
  resetDraftPreview();
  renderDraftManager();
});
$("previewDraftCleanupButton")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  const draftIds = [...state.selectedDraftIds];
  if (!draftIds.length) {
    $("draftCleanupPreview").classList.remove("hidden");
    $("draftCleanupPreview").innerHTML = "<strong>尚未选择草稿</strong>请先勾选要移入回收站的草稿。";
    return;
  }
  button.disabled = true;
  button.textContent = "正在核对…";
  try {
    const preview = await postJson("/api/controls/capcut-drafts/preview", { draftIds }, { timeoutMs: 60000 });
    state.draftPreview = preview;
    state.draftSnapshot = preview.snapshotToken || "";
    const blocked = (preview.blocked || []).map(item =>
      `<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>`
    ).join("");
    $("draftCleanupPreview").classList.remove("hidden");
    $("draftCleanupPreview").innerHTML = `<strong>${escapeHtml(preview.message)}</strong>
      可删除空间约 ${escapeHtml(formatBytes(preview.sizeBytes))}。
      ${blocked ? `<ul>${blocked}</ul>` : ""}`;
    $("confirmDraftCleanupButton").classList.toggle("hidden", !preview.deletableCount);
  } catch (error) {
    resetDraftPreview();
    $("draftCleanupPreview").classList.remove("hidden");
    $("draftCleanupPreview").innerHTML = `<strong>删除预览失败</strong>${escapeHtml(error.message || "请刷新后重试")}`;
  } finally {
    button.disabled = false;
    button.textContent = "预览删除";
  }
});
$("confirmDraftCleanupButton")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  const preview = state.draftPreview;
  if (!preview?.deletableCount) return;
  if (!window.confirm(`确认将 ${preview.deletableCount} 个草稿移入 Windows 回收站吗？不会删除视频、音频、成片或生产任务。`)) return;
  if (preview.containsManualOrUnknown && !window.confirm("选择中包含人工或来源不明草稿。再次确认仍要将这些草稿移入回收站。")) return;
  button.disabled = true;
  button.textContent = "正在移入回收站…";
  try {
    const draftIds = (preview.deletable || []).map(item => item.draftId);
    const result = await postJson("/api/controls/capcut-drafts/cleanup", {
      draftIds,
      snapshotToken: preview.snapshotToken,
      includeUnknown: Boolean(preview.containsManualOrUnknown),
      confirm: "RECYCLE_SELECTED_CAPCUT_DRAFTS",
    });
    renderActionResult("draftCleanupResult", result);
    state.selectedDraftIds.clear();
    await loadDraftManager();
    await refresh();
  } catch (error) {
    renderActionResult("draftCleanupResult", {
      state: "failed", message: error.message || "草稿清理失败", updatedAt: new Date().toISOString()
    });
    $("draftCleanupPreview").classList.remove("hidden");
    $("draftCleanupPreview").innerHTML = `<strong>草稿清理失败</strong>${escapeHtml(error.message || "请刷新后重试")}`;
  } finally {
    button.disabled = false;
    button.textContent = "确认移入回收站";
  }
});
$("openAudioManagerButton")?.addEventListener("click", async () => {
  const dialog = $("audioManagerDialog");
  if (dialog && !dialog.open) dialog.showModal();
  await loadAudioManager();
});
$("closeAudioManagerButton")?.addEventListener("click", () => $("audioManagerDialog")?.close());
$("closeAudioProtectionButton")?.addEventListener("click", () => $("audioProtectionDialog")?.close());
$("refreshAudioManagerButton")?.addEventListener("click", loadAudioManager);
[
  "audioDateFilter", "audioProjectFilter", "audioMaterialFilter", "audioLanguageFilter",
  "audioBatchFilter", "audioStateFilter", "audioSearchFilter"
].forEach(id => {
  $(id)?.addEventListener(id === "audioSearchFilter" ? "input" : "change", () => {
    resetAudioPreview();
    renderAudioManager();
  });
});
$("selectFilteredAudioButton")?.addEventListener("click", () => {
  filteredAudioFiles().filter(item => !item.protected).forEach(item => state.selectedAudioIds.add(item.audioId));
  resetAudioPreview();
  renderAudioManager();
});
$("clearAudioSelectionButton")?.addEventListener("click", () => {
  state.selectedAudioIds.clear();
  resetAudioPreview();
  renderAudioManager();
});
$("previewAudioCleanupButton")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  const audioIds = [...state.selectedAudioIds];
  if (!audioIds.length) {
    $("audioCleanupPreview").classList.remove("hidden");
    $("audioCleanupPreview").innerHTML = "<strong>尚未选择音频</strong>请先勾选要移入回收站的音频文件。";
    return;
  }
  button.disabled = true;
  button.textContent = "正在重新对账…";
  try {
    const preview = await postJson("/api/controls/audio-files/preview", { audioIds }, { timeoutMs: 60000 });
    state.audioPreview = preview;
    state.audioSnapshot = preview.snapshotToken || "";
    const blocked = (preview.blocked || []).map(item =>
      `<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>`
    ).join("");
    $("audioCleanupPreview").classList.remove("hidden");
    $("audioCleanupPreview").innerHTML = `<strong>${escapeHtml(preview.message)}</strong>
      可删除空间约 ${escapeHtml(formatBytes(preview.sizeBytes))}。
      ${blocked ? `<ul>${blocked}</ul>` : ""}`;
    $("confirmAudioCleanupButton").classList.toggle("hidden", !preview.deletableCount);
    if (preview.blockedCount) {
      window.alert(`有 ${preview.blockedCount} 个音频被活动任务保护，已禁止删除。请查看页面中的具体原因。`);
    }
  } catch (error) {
    resetAudioPreview();
    $("audioCleanupPreview").classList.remove("hidden");
    $("audioCleanupPreview").innerHTML = `<strong>音频删除预览失败</strong>${escapeHtml(error.message || "请刷新后重试")}`;
    window.alert(error.message || "音频状态已变化，请重新对账");
  } finally {
    button.disabled = false;
    button.textContent = "预览删除";
  }
});
$("confirmAudioCleanupButton")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  const preview = state.audioPreview;
  if (!preview?.deletableCount) return;
  if (!window.confirm(`确认将 ${preview.deletableCount} 个音频文件（${formatBytes(preview.sizeBytes)}）移入 Windows 回收站吗？不会删除文件夹，也不会改变任务完成状态。`)) return;
  button.disabled = true;
  button.textContent = "正在移入回收站…";
  try {
    const audioIds = (preview.deletable || []).map(item => item.audioId);
    const result = await postJson("/api/controls/audio-files/recycle", {
      audioIds,
      snapshotToken: preview.snapshotToken,
      confirm: "RECYCLE_SELECTED_AUDIO_FILES",
    });
    renderActionResult("audioCleanupResult", result);
    state.selectedAudioIds.clear();
    await loadAudioManager();
    await refresh();
    window.alert(result.message || "音频已移入 Windows 回收站");
  } catch (error) {
    const message = error.message || "音频清理失败";
    renderActionResult("audioCleanupResult", {
      state: "failed", message, updatedAt: new Date().toISOString()
    });
    $("audioCleanupPreview").classList.remove("hidden");
    $("audioCleanupPreview").innerHTML = `<strong>音频清理已停止</strong>${escapeHtml(message)}`;
    window.alert(message);
  } finally {
    button.disabled = false;
    button.textContent = "确认移入回收站";
  }
});
$("openProductionManagerButton")?.addEventListener("click", async () => {
  const dialog = $("productionManagerDialog");
  if (dialog && !dialog.open) dialog.showModal();
  await loadProductionManager({ applyDefaults: true });
});
$("closeProductionManagerButton")?.addEventListener("click", () => $("productionManagerDialog")?.close());
$("closeProductionProtectionButton")?.addEventListener("click", () => $("productionProtectionDialog")?.close());
$("refreshProductionManagerButton")?.addEventListener("click", () => loadProductionManager());
[
  "productionDateFilter", "productionProjectFilter", "productionMaterialFilter",
  "productionCategoryFilter", "productionStateFilter", "productionSearchFilter"
].forEach(id => {
  $(id)?.addEventListener(id === "productionSearchFilter" ? "input" : "change", () => {
    resetProductionPreview();
    renderProductionManager();
  });
});
$("selectFilteredProductionButton")?.addEventListener("click", () => {
  filteredProductionFiles()
    .filter(item => !item.protected)
    .forEach(item => state.selectedProductionIds.add(item.fileId));
  resetProductionPreview();
  renderProductionManager();
});
$("clearProductionSelectionButton")?.addEventListener("click", () => {
  state.selectedProductionIds.clear();
  resetProductionPreview();
  renderProductionManager();
});
$("previewProductionCleanupButton")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  const fileIds = [...state.selectedProductionIds];
  if (!fileIds.length) {
    $("productionCleanupPreview").classList.remove("hidden");
    $("productionCleanupPreview").innerHTML = "<strong>尚未选择生产文件</strong>请先勾选要移入回收站的文件。";
    return;
  }
  button.disabled = true;
  button.textContent = "正在重新核验云端与引用…";
  try {
    const preview = await postJson("/api/controls/production-files/preview", { fileIds }, { timeoutMs: 60000 });
    state.productionPreview = preview;
    state.productionSnapshot = preview.snapshotToken || "";
    const categories = (preview.categories || []).map(item =>
      `<li>${escapeHtml(item.label)}：${Number(item.count || 0)} 个 · ${escapeHtml(formatBytes(item.sizeBytes))}</li>`
    ).join("");
    const blocked = (preview.blocked || []).slice(0, 30).map(item =>
      `<li>${escapeHtml(item.name)}：${escapeHtml(item.reason)}</li>`
    ).join("");
    const blockedMore = Number(preview.blockedCount || 0) > 30
      ? `<p>另有 ${Number(preview.blockedCount || 0) - 30} 个受保护文件，请返回清单查看。</p>`
      : "";
    $("productionCleanupPreview").classList.remove("hidden");
    $("productionCleanupPreview").innerHTML = `<strong>${escapeHtml(preview.message)}</strong>
      预计释放 ${escapeHtml(formatBytes(preview.sizeBytes))}。
      ${categories ? `<ul>${categories}</ul>` : ""}
      ${blocked ? `<p>以下文件不会删除：</p><ul>${blocked}</ul>${blockedMore}` : ""}`;
    $("confirmProductionCleanupButton").classList.toggle("hidden", !preview.deletableCount);
    if (preview.blockedCount) {
      window.alert(`有 ${preview.blockedCount} 个文件被活动任务、云端核验或身份规则保护，已自动排除。`);
    }
  } catch (error) {
    resetProductionPreview();
    $("productionCleanupPreview").classList.remove("hidden");
    $("productionCleanupPreview").innerHTML = `<strong>生产文件清理预览失败</strong>${escapeHtml(error.message || "请刷新后重试")}`;
  } finally {
    button.disabled = false;
    button.textContent = "预览清理";
  }
});
$("confirmProductionCleanupButton")?.addEventListener("click", async event => {
  const button = event.currentTarget;
  const preview = state.productionPreview;
  if (!preview?.deletableCount) return;
  if (!window.confirm(`确认将 ${preview.deletableCount} 个生产文件（${formatBytes(preview.sizeBytes)}）移入 Windows 回收站吗？项目状态、上传记录及云端文件不会改变。`)) return;
  if (preview.containsTestFiles && !window.confirm("选择中包含 CapCut 测试或首帧测试文件。再次确认仍要将这些测试文件移入回收站。")) return;
  button.disabled = true;
  button.textContent = "正在移入回收站…";
  try {
    const fileIds = (preview.deletable || []).map(item => item.fileId);
    // Recycling a large, user-confirmed inventory can legitimately take
    // several minutes (Windows shell recycling is one file operation at a
    // time).  The old 10s watchdog aborted the fetch while the server kept
    // working, which produced the misleading "signal is aborted" alert.
    const result = await postJson("/api/controls/production-files/recycle", {
      fileIds,
      snapshotToken: preview.snapshotToken,
      confirm: "RECYCLE_SELECTED_PRODUCTION_FILES",
    }, { timeoutMs: 15 * 60 * 1000 });
    renderActionResult("productionCleanupResult", result);
    state.selectedProductionIds.clear();
    await loadProductionManager();
    await refresh();
    window.alert(result.message || "生产文件清理已完成");
  } catch (error) {
    const message = error.message || "生产文件清理失败";
    renderActionResult("productionCleanupResult", {
      state: "failed", message, updatedAt: new Date().toISOString()
    });
    $("productionCleanupPreview").classList.remove("hidden");
    $("productionCleanupPreview").innerHTML = `<strong>生产文件清理已停止</strong>${escapeHtml(message)}`;
    window.alert(message);
  } finally {
    button.disabled = false;
    button.textContent = "确认移入回收站";
  }
});
$("continueCurrentButton")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (button.dataset.allowed === "false") return;
  if (!window.confirm("确认让家里工作台安全继续当前项目吗？它会先核对任务清单，不会删除素材或重做有效成片。")) return;
  button.disabled = true;
  button.textContent = "正在发送继续指令…";
  try {
    const clientRequestId = (window.crypto?.randomUUID?.() || `dashboard-${Date.now()}-${Math.random()}`);
    // Name the project this page showed when the user confirmed, so a stale
    // page cannot continue a project that has changed since (409 instead).
    const box = state.lastGoodDashboard?.currentTaskBox || {};
    const expectedTarget = Object.fromEntries(Object.entries({
      batchId: box.batchId,
      taskId: box.current?.taskId,
      attemptId: box.current?.attemptId,
    }).filter(([, value]) => typeof value === "string" && value));
    const payload = Object.keys(expectedTarget).length ? { clientRequestId, expectedTarget } : { clientRequestId };
    const result = await postJson("/api/control-commands", payload);
    renderContinueResult({
      ...result,
      state: result.state || "persisted",
      commandId: result.commandId,
      message: result.message || "命令已保存，等待家里接收器确认",
      requestedAt: new Date().toISOString(),
    });
    await refresh();
  } catch (error) {
    renderContinueResult({ state: "failed", message: error.message || "发送继续指令失败" });
  } finally {
    window.setTimeout(refreshContinueStatus, 500);
  }
});
$("uploadRescanButton")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!window.confirm("确认重新对账正式清单，补传遗漏成片，并对云端已实时核验的任务继续安全清理吗？不会重新剪辑等待中的任务，也不会清理配音、公共素材、Logo或公共样品。")) return;
  button.disabled = true;
  button.textContent = "正在检查上传缺口…";
  try {
    const result = await postJson("/api/controls/upload/rescan", {});
    renderActionResult("uploadActionResult", {
      state: "completed",
      message: result.message || "上传检查已完成",
      updatedAt: new Date().toISOString(),
    });
    await refresh();
  } catch (error) {
    renderActionResult("uploadActionResult", {
      state: "failed",
      message: error.message || "上传检查失败",
      updatedAt: new Date().toISOString(),
    });
  } finally {
    button.disabled = false;
    button.textContent = "重新对账、补传并清理";
  }
});
$("historicalCloudVerifyButton")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!window.confirm("确认核验历史百度云文件吗？系统只会查询云端文件是否存在，并核对云端路径和文件大小；不会补传、不会删除本地或云端文件，也不会改变项目完成状态。")) return;
  button.disabled = true;
  button.textContent = "正在提交历史核验…";
  try {
    const result = await postJson("/api/controls/upload/verify-history", {});
    renderHistoricalCloudVerification(result);
    await refresh();
  } catch (error) {
    renderHistoricalCloudVerification({
      state: "failed",
      message: error.message || "历史百度云核验提交失败",
      updatedAt: new Date().toISOString(),
    });
  }
});
$("resetTestRecordsButton")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!window.confirm("确认把今天的测试任务记录备份后全部归零吗？视频、音频、素材、配置和校准都会保留。")) return;
  if (!window.confirm("再次确认：Dashboard、工作台、接收器和 CapCut 的任务进度将从空状态重新开始。")) return;
  button.disabled = true;
  button.textContent = "正在备份并重置…";
  try {
    const result = await postJson("/api/controls/testing/reset", { confirm: "RESET_TEST_RECORDS" });
    state.date = "";
    state.batchId = "";
    renderActionResult("resetRecordsResult", {
      state: "completed",
      message: result.message || "测试记录已重置",
      updatedAt: result.resetAt || new Date().toISOString(),
    });
    await refresh();
  } catch (error) {
    renderActionResult("resetRecordsResult", {
      state: "failed",
      message: error.message || "测试记录重置失败",
      updatedAt: new Date().toISOString(),
    });
  } finally {
    button.disabled = false;
    button.textContent = "重置全部测试记录";
  }
});
$("createDate").value = currentLocalDateLabel();
$("createTemplate").addEventListener("change", updateMaterialOptions);
$("createTaskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  button.disabled = true;
  try {
    const result = await postJson("/api/controls/tasks/create", {
      date: $("createDate").value.trim(),
      templateId: $("createTemplate").value,
      material: $("createMaterial").value,
      audioBatch: $("createAudioBatch").value.trim(),
      voicePlan: $("createVoicePlan").value,
      expectedCount: $("createExpectedCount").value,
      urls: $("createUrls").value,
      startNow: $("createStartNow").checked,
    });
    event.currentTarget.reset();
    $("createDate").value = currentLocalDateLabel();
    renderActionResult("queueActionResult", {
      state: "completed",
      message: result.message || "任务已提交",
      updatedAt: new Date().toISOString(),
    });
    await refresh();
  } catch (error) {
    renderActionResult("queueActionResult", {
      state: "failed",
      message: error.message || "提交失败",
      updatedAt: new Date().toISOString(),
    });
  }
  finally { button.disabled = false; }
});

async function refreshLoop() {
  await refresh();
  window.setTimeout(refreshLoop, document.hidden ? 20000 : 5000);
}

async function refreshContinueLoop() {
  if (state.continueInFlight) await refreshContinueStatus();
  window.setTimeout(refreshContinueLoop, state.continueInFlight ? (document.hidden ? 5000 : 1500) : 10000);
}

updateDataFreshness();
window.setInterval(updateDataFreshness, 1000);
document.addEventListener("visibilitychange", updateDataFreshness);
refreshLoop();
refreshContinueLoop();
