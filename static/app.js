function currentLocalDateLabel() {
  const value = new Date();
  return `${value.getMonth() + 1}.${value.getDate()}`;
}

const state = { date: "", pipelineDate: currentLocalDateLabel(), overview: null, templates: [], templateSignature: "", gaps: {} };
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
  $("diskNote").textContent = disk.free_gb == null ? "目录暂不可用" : `${disk.path} 剩余 ${disk.free_gb} GB`;
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
  card.querySelector("small").textContent = `${Number(data.completed || 0)} 完成 / ${Number(data.failed || 0)} 失败 / ${Number(data.total || 0)} 总计${today}`;
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
  const today = currentLocalDateLabel();
  const values = dates.includes(today) ? dates : [today, ...dates];
  const signature = values.join("|");
  if (select.dataset.signature !== signature) {
    select.innerHTML = values.map(value =>
      `<option value="${escapeHtml(value)}">${value === today ? `今天（${escapeHtml(value)}）` : escapeHtml(value)}</option>`
    ).join("");
    select.dataset.signature = signature;
  }
  select.value = values.includes(selected) ? selected : today;
  state.pipelineDate = select.value;
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
    const liveText = item.state === "running"
      ? (item.isLive ? "实时更新" : "状态未刷新")
      : formatAge(item.ageSeconds);
    return `<tr>
      <td><span class="step-name"><i class="step-number">${escapeHtml(item.step || "")}</i>${escapeHtml(item.name || key)}</span></td>
      <td>${escapeHtml(item.program || "--")}<span class="program-state ${onlineClass}">${escapeHtml(onlineText)}</span></td>
      <td>${escapeHtml(current)}<span class="subtext">${escapeHtml(item.source || "")}</span></td>
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
    ? `完成 ${upload.completed || 0} / ${upload.total || 0}，失败 ${upload.failed || 0}。云端存在且大小一致后清理本地：已清理 ${upload.localCleaned || 0}，待核验 ${upload.cleanupPending || 0}，保留/阻止 ${upload.cleanupBlocked || 0}。`
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
  renderDateOptions(data.dates || []);
}

function renderDateOptions(dates) {
  const select = $("dateSelect");
  const current = select.value;
  const values = ["", ...dates];
  const signature = values.join("|");
  if (select.dataset.signature === signature) return;
  select.innerHTML = values.map(value => `<option value="${escapeHtml(value)}">${value ? escapeHtml(value) : "全部日期"}</option>`).join("");
  select.value = values.includes(current) ? current : "";
  select.dataset.signature = signature;
}

function renderTasks(items) {
  const rows = $("taskRows");
  if (!items.length) {
    rows.innerHTML = `<tr><td colspan="6" class="empty">这个日期暂时没有任务</td></tr>`;
    return;
  }
  rows.innerHTML = items.map(item => `
    <tr>
      <td><strong>${escapeHtml(item.project || "未分类")}</strong><span class="subtext">${escapeHtml(item.date_label || "")}</span></td>
      <td>${escapeHtml(item.material || "--")}<span class="subtext">${escapeHtml(item.language || "--")}</span></td>
      <td>${escapeHtml(item.number || "--")}${item.sequence ? `-${escapeHtml(item.sequence)}` : ""}</td>
      <td>${escapeHtml(item.state_text || item.state)}</td>
      <td>${escapeHtml(item.output_name || "尚未生成")}<span class="subtext">${escapeHtml(item.video_name || "")}</span></td>
      <td><span class="task-state ${escapeHtml(item.category)}">${escapeHtml(item.category === "running" ? "处理中" : item.state_text)}</span></td>
    </tr>`).join("");
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
    const activelyRunning = String(item.status || "").toLowerCase() === "running";
    const blocked = !activelyRunning && (missing > 0 || item.status === "blocked_missing_links" || Number(item.failed || 0) > 0);
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
      <p>总数 ${expected} · 已完成 ${completed} · 剩余 ${missing} · 失败 ${Number(item.failed || 0)}</p>
      <small>${escapeHtml((item.stateText || item.status || "--") + current + error)}</small>
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
      await postJson(`/api/controls/tasks/${encodeURIComponent(taskId)}/replenish`, {
        urls: $("replenishUrls").value,
        startNow: $("replenishStartNow").checked,
      });
      panel.classList.add("hidden"); panel.innerHTML = ""; await refresh();
    } catch (error) { window.alert(error.message || "补链失败"); button.disabled = false; }
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
    await refresh();
  } catch (error) {
    window.alert(error.message || "操作失败");
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
  try {
    const query = state.date ? `?date=${encodeURIComponent(state.date)}` : "";
    const pipelineQuery = state.pipelineDate ? `?date=${encodeURIComponent(state.pipelineDate)}` : "";
    const [overview, pipeline, tasks, events, projectGaps, receiverQueue, templates] = await Promise.all([
      getJson("/api/overview"), getJson(`/api/pipeline${pipelineQuery}`),
      getJson(`/api/tasks${query}`), getJson("/api/events?limit=30"), getJson("/api/project-gaps"),
      getJson("/api/controls/tasks").catch(() => ({ items: [] })),
      getJson("/api/controls/templates").catch(() => ({ items: [] }))
    ]);
    renderOverview(overview); renderPipelinePayload(pipeline);
    renderTasks(tasks.items || []); renderEvents(events.items || []); renderProjectGaps(projectGaps.items || []);
    renderReceiverQueue(receiverQueue.items || []);
    renderTemplates(templates.items || []);
  } catch (error) {
    // Do not leave an old "gap" card visible when another dashboard request
    // momentarily fails. The card is operationally significant, so stale data
    // is worse than showing the empty state until the next two-second refresh.
    renderProjectGaps([]);
    renderReceiverQueue([]);
    $("machineBadge").className = "status-badge offline";
    $("machineBadge").innerHTML = "<span></span>Dashboard 连接失败";
    $("heroTitle").textContent = "暂时无法读取状态";
    $("heroSubtitle").textContent = "页面会继续自动重试，不影响正在运行的生产任务。";
  }
}

$("dateSelect").addEventListener("change", event => { state.date = event.target.value; refresh(); });
$("pipelineDateSelect").addEventListener("change", event => {
  state.pipelineDate = event.target.value;
  refresh();
});
$("createDate").value = currentLocalDateLabel();
$("createTemplate").addEventListener("change", updateMaterialOptions);
$("createTaskForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type='submit']");
  button.disabled = true;
  try {
    await postJson("/api/controls/tasks/create", {
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
    await refresh();
  } catch (error) { window.alert(error.message || "提交失败"); }
  finally { button.disabled = false; }
});
refresh();
setInterval(refresh, 2000);
