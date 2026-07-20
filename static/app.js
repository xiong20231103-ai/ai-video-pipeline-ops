const state = { date: "", overview: null };
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
  card.querySelector("small").textContent = `${Number(data.completed || 0)} 完成 / ${Number(data.failed || 0)} 失败 / ${Number(data.total || 0)} 总计`;
}

function renderPipeline(pipeline = {}) {
  renderStage("download", pipeline.download);
  renderStage("voice", pipeline.voice);
  renderStage("stitch", pipeline.stitch);
  renderStage("capcut", pipeline.capcut);
  const upload = pipeline.upload || {};
  const uploadNode = $("pipeUpload");
  uploadNode.className = `pipe-step ${stageClass(upload.state)}`;
  $("pipeUploadText").textContent = upload.stateText || "未配置";
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
  if (current) {
    const category = categoryFor(current.state);
    $("heroTitle").textContent = current.state_text || "生产线等待中";
    $("heroSubtitle").textContent = `${current.date_label || "未定日期"} · ${current.project || "未分类"} · ${current.material || "未指定材料"} · ${current.language || "未指定语言"}`;
    $("currentDate").textContent = current.date_label || "--";
    $("currentProject").textContent = current.project || "--";
    $("currentMaterial").textContent = current.material || "--";
    $("currentLanguage").textContent = current.language || "--";
    $("currentState").textContent = current.state_text || current.state;
    $("currentState").className = `task-state ${category}`;
    $("currentError").textContent = current.error || "";
    $("currentError").classList.toggle("hidden", !current.error);
  } else {
    $("heroTitle").textContent = "暂时没有生产任务";
    $("heroSubtitle").textContent = "Dashboard 正常运行，正在等待工作台或客户端写入状态。";
  }
  renderMetrics(data.metrics);
  renderPipeline(data.pipeline);
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

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

async function refresh() {
  try {
    const query = state.date ? `?date=${encodeURIComponent(state.date)}` : "";
    const [overview, tasks, events] = await Promise.all([
      getJson("/api/overview"), getJson(`/api/tasks${query}`), getJson("/api/events?limit=30")
    ]);
    renderOverview(overview); renderTasks(tasks.items || []); renderEvents(events.items || []);
  } catch (error) {
    $("machineBadge").className = "status-badge offline";
    $("machineBadge").innerHTML = "<span></span>Dashboard 连接失败";
    $("heroTitle").textContent = "暂时无法读取状态";
    $("heroSubtitle").textContent = "页面会继续自动重试，不影响正在运行的生产任务。";
  }
}

$("dateSelect").addEventListener("change", event => { state.date = event.target.value; refresh(); });
refresh();
setInterval(refresh, 2000);
