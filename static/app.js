function currentLocalDateLabel() {
  const value = new Date();
  return `${value.getMonth() + 1}.${value.getDate()}`;
}

const state = {
  date: "", batchId: "", overview: null, templates: [], templateSignature: "",
  gaps: {}, lastGoodDashboard: null, refreshBusy: false
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
  renderPipelineRows(pipeline);
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
    : `<li><span>工作台已记录 ${failed} 条失败；请打开工作台的“批次核对 / 缺口提醒”查看并补链。</span></li>`;
}

function renderPipelinePayload(payload = {}) {
  const pipeline = {};
  (payload.items || []).forEach(item => { pipeline[item.key] = item; });
  renderPipeline(pipeline);
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
    const current = item.current || item.todaySummary || item.source || "暂无当前任务";
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

function renderOverview(data) {
  state.overview = data;
  const machine = data.machine || {};
  const badge = $("machineBadge");
  badge.className = `status-badge ${machine.online ? "online" : "offline"}`;
  badge.innerHTML = `<span></span>${escapeHtml(machine.name || "--")} · ${machine.online ? "在线" : "离线"}`;
  $("lastUpdated").textContent = formatClock(data.updatedAt);
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
  $("uploadCardTitle").textContent = upload.configured
    ? (upload.state === "running" ? "百度网盘上传中" : upload.message || "百度网盘上传服务")
    : "百度网盘未配置";
  $("uploadCardMessage").textContent = upload.configured
    ? `等待 ${upload.waiting || 0}，上传中 ${upload.uploading || 0}，云端已核验 ${upload.cloudVerified || upload.completed || 0}，失败 ${upload.failed || 0}。核验后已清理 ${upload.localCleaned || 0}，待清理 ${upload.cleanupPending || 0}，阻止 ${upload.cleanupBlocked || 0}。`
    : "请先在TikHub工作台配置并授权百度网盘。";
  $("uploadCardBadge").textContent = upload.configured
    ? (upload.state === "failed" ? "上传失败" : upload.state === "completed" ? "上传完成" : upload.state === "running" ? "上传中" : "等待成片")
    : "未配置";
  const activeStage = ["download", "voice", "stitch", "capcut", "upload"]
    .map(key => pipeline[key]).find(item => item && item.state === "running");
  if (activeStage) {
    $("heroTitle").textContent = `${activeStage.name} · ${activeStage.stateText}`;
    $("heroSubtitle").textContent = activeStage.current || `${activeStage.program}正在运行`;
  } else if (current) {
    $("heroTitle").textContent = current.state_text || "生产线等待中";
    $("heroSubtitle").textContent = `${current.date_label || "未定日期"} · ${current.project || "未分类"} · ${current.material || "未指定材料"} · ${current.language || "未指定语言"}`;
  } else {
    $("heroTitle").textContent = "暂时没有生产任务";
    $("heroSubtitle").textContent = "Dashboard 正常运行，正在等待工作台或客户端写入状态。";
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
  if (!items.length) {
    rows.innerHTML = `<tr><td colspan="6" class="empty">这个生产日期暂时没有第五步任务</td></tr>`;
    cards.innerHTML = `<p class="empty">这个生产日期暂时没有第五步任务</p>`;
    return;
  }
  const groups = new Map();
  items.forEach(item => {
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
      <td>${escapeHtml(item.state_text || item.state)}</td>
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
        <p>${escapeHtml(item.state_text || item.state)}</p><small>${escapeHtml(item.output_name || "尚未生成")}</small>
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

function renderProjectGaps(items) {
  const node = $("projectGapList");
  if (!node) return;
  if (!items.length) { node.innerHTML = `<p class="empty">暂无项目级下载记录</p>`; return; }
  state.gaps = {};
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

async function postJson(url, payload) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "操作失败");
  return result;
}

function openReplenishment(taskId) {
  const item = state.gaps[String(taskId)];
  const panel = $("replenishPanel");
  if (!item || !panel) return;
  const expected = Number(item.expectedCount || 0);
  const completed = Number(item.completed || 0);
  const missing = Number(item.missingCount ?? Math.max(0, expected - completed));
  panel.classList.remove("hidden");
  panel.innerHTML = `<strong>补链：${escapeHtml(item.project)} / ${escapeHtml(item.material)}</strong>
    <p>原计划 ${expected} 条，已完成 ${completed} 条；请只粘贴 ${missing} 条新链接。</p>
    <form id="replenishForm"><label class="wide">新链接（每行一条）<textarea id="replenishUrls" rows="4" required></textarea></label>
    <label class="wide checkbox"><input id="replenishStartNow" type="checkbox" checked>补链后继续当前项目</label>
    <button class="primary wide" type="submit">提交补链</button></form>`;
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
      panel.classList.add("hidden"); panel.innerHTML = ""; await refresh();
    } catch (error) {
      renderActionResult("queueActionResult", {
        state: "failed",
        message: error.message || "补链失败",
        updatedAt: new Date().toISOString(),
      });
      button.disabled = false;
    }
  });
  panel.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderReceiverQueue(items) {
  const node = $("receiverQueue");
  if (!node) return;
  if (!items.length) {
    node.innerHTML = `<p class="empty">暂无可确认或撤回的队列任务</p>`;
    return;
  }
  node.innerHTML = items.map(item => {
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
}

function renderTaskBoxes(payload = {}) {
  const boxes = Array.isArray(payload.items) ? payload.items : [];
  const selected = payload.selected || boxes.find(item => item.batchId === state.batchId) || boxes[0];
  const select = $("taskBoxSelect");
  const signature = boxes.map(item => `${item.batchId}:${item.updatedAt}`).join("|");
  if (select.dataset.signature !== signature) {
    select.innerHTML = boxes.length ? boxes.map(item =>
      `<option value="${escapeHtml(item.batchId)}">${escapeHtml(item.productionDate || "未定日期")} · ${item.completedProjects}/${item.projectCount} 项 · ${escapeHtml(item.batchId.slice(-8))}</option>`
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
    $("taskBoxItems").innerHTML = `<p class="empty">等待公司投递器提交任务</p>`;
    setBar("taskBoxBar", 0);
    return;
  }
  state.batchId = selected.batchId;
  select.value = selected.batchId;
  const current = selected.current;
  const next = selected.next;
  const position = current ? `当前第 ${current.sequence} / ${selected.projectCount} 项` : "没有正在运行的项目";
  $("taskBoxTitle").textContent = `${selected.productionDate || "未定日期"}任务箱 · 已完成 ${selected.completedProjects} / ${selected.projectCount}`;
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

function renderSources(source = {}) {
  const panel = $("sourceWarningPanel");
  const errors = Array.isArray(source.errors) ? source.errors : [];
  const messages = [];
  if (source.stale) messages.push("Dashboard采集状态已经过期");
  if (source.receiverError) messages.push(`接收器状态读取失败：${source.receiverError}`);
  if (source.watchdog && source.watchdog.state === "failed") {
    messages.push(`Dashboard守护启动失败：${source.watchdog.message || "原因未知"}`);
  }
  errors.slice(0, 5).forEach(item => messages.push(`${item.name}：${item.error}`));
  panel.classList.toggle("hidden", !messages.length);
  panel.innerHTML = messages.length
    ? `<strong>状态源提醒</strong><ul>${messages.map(message => `<li>${escapeHtml(message)}</li>`).join("")}</ul>`
    : "";
}

function renderContinueResult(result = {}) {
  const node = $("continueResult");
  const stateName = String(result.state || "idle");
  const stateLabel = {
    idle: "尚未对账", requested: "已发送", running: "对账中",
    completed: "可以继续", blocked: "已阻止", failed: "执行失败"
  }[stateName] || stateName;
  const rows = Array.isArray(result.steps) ? result.steps : [];
  node.className = `reconcile-result ${stateName === "completed" ? "completed" : ["blocked", "failed"].includes(stateName) ? "failed" : "neutral"}`;
  node.innerHTML = `<div class="reconcile-head"><strong>${escapeHtml(stateLabel)}${result.stale ? " · 结果已过期" : ""}</strong><span>${escapeHtml(formatDateTime(result.finishedAt || result.requestedAt))}</span></div>
    <p>${escapeHtml(result.message || "尚未执行安全继续对账")}</p>
    ${rows.length ? `<div class="reconcile-steps">${rows.map(item => `<div><span>${item.step}. ${escapeHtml(item.name)}</span><b>${Number(item.actual || 0)} / ${Number(item.expected || 0)}</b></div>`).join("")}</div>` : ""}`;
}

function renderActionResult(id, result = {}) {
  const node = $(id);
  const stateName = String(result.state || "idle");
  node.className = `action-result ${stateName === "completed" ? "completed" : stateName === "failed" ? "failed" : "neutral"}`;
  node.textContent = `${result.message || "尚无操作记录"}${result.updatedAt ? ` · ${formatDateTime(result.updatedAt)}` : ""}`;
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

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

async function refresh() {
  if (state.refreshBusy) return;
  state.refreshBusy = true;
  try {
    const params = new URLSearchParams();
    if (state.date) params.set("date", state.date);
    if (state.batchId) params.set("batchId", state.batchId);
    const data = await getJson(`/api/dashboard${params.toString() ? `?${params}` : ""}`);
    state.lastGoodDashboard = data;
    state.date = data.selectedDate || state.date;
    renderOverview(data.overview || {});
    renderPipelinePayload(data.pipeline || {});
    renderTasks(data.tasks?.items || []);
    renderEvents(data.events?.items || []);
    renderProjectGaps(data.projectGaps?.items || []);
    renderReceiverQueue(data.receiverQueue?.items || []);
    renderTemplates(data.templates?.items || []);
    renderTaskBoxes(data.taskBoxes || {});
    renderServices(data.services || []);
    renderSources(data.sources || {});
    renderContinueResult(data.controls?.continue || {});
    renderActionResult("uploadActionResult", data.controls?.uploadRescan || {});
  } catch (error) {
    $("machineBadge").className = "status-badge offline";
    $("machineBadge").innerHTML = "<span></span>Dashboard 连接失败";
    $("heroTitle").textContent = "暂时无法读取新状态";
    $("heroSubtitle").textContent = state.lastGoodDashboard
      ? "正在显示上一次成功状态；页面会自动重试，不会清空已有信息。"
      : "页面会继续自动重试，不影响正在运行的生产任务。";
  } finally {
    state.refreshBusy = false;
  }
}

$("pipelineDateSelect").addEventListener("change", event => {
  state.date = event.target.value;
  refresh();
});
$("taskBoxSelect")?.addEventListener("change", event => {
  state.batchId = event.target.value;
  state.date = "";
  refresh();
});
$("continueCurrentButton")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!window.confirm("确认让家里工作台安全继续当前项目吗？它会先核对任务清单，不会删除素材或重做有效成片。")) return;
  button.disabled = true;
  button.textContent = "正在发送继续指令…";
  try {
    const result = await postJson("/api/controls/continue-current", {});
    renderContinueResult({
      state: "requested",
      commandId: result.commandId,
      message: result.message || "继续指令已发送，正在对账",
      requestedAt: new Date().toISOString(),
    });
    await refresh();
  } catch (error) {
    renderContinueResult({ state: "failed", message: error.message || "发送继续指令失败" });
  } finally {
    button.disabled = false;
    button.textContent = "安全继续当前项目";
  }
});
$("uploadRescanButton")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  if (!window.confirm("确认检查所有正式清单，并自动补传已完成但尚未上传的成片吗？不会重新剪辑等待中的任务。")) return;
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
    button.textContent = "检查并补传未上传成片";
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
  window.setTimeout(refreshLoop, document.hidden ? 15000 : 3000);
}

refreshLoop();
