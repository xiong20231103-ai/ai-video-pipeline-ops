// Pure presentation rules copied from static/app.js at 07f87bb. No DOM or network.
// Original line 1
export function currentLocalDateLabel() {
  const value = new Date();
  return `${value.getMonth() + 1}.${value.getDate()}`;
}

// Original line 25
export function formatClock(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString("zh-CN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit"
  });
}

// Original line 53
export function formatDateTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"
  });
}

// Original line 61
export function formatAge(seconds) {
  if (seconds == null) return "无状态时间";
  if (seconds < 10) return "刚刚";
  if (seconds < 60) return `${seconds}秒前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前`;
  return `${Math.floor(seconds / 86400)}天前`;
}

// Original line 70
export function formatBytes(value) {
  let size = Number(value || 0);
  if (!Number.isFinite(size) || size <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit += 1; }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
}

// Original line 79
export function formatDuration(value) {
  const seconds = Math.max(0, Math.round(Number(value || 0)));
  if (!seconds) return "正在测算";
  if (seconds < 60) return `约 ${seconds} 秒`;
  if (seconds < 3600) return `约 ${Math.ceil(seconds / 60)} 分钟`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.ceil((seconds % 3600) / 60);
  return `约 ${hours} 小时${minutes ? ` ${minutes} 分钟` : ""}`;
}

// Original line 152
export function draftCategoryLabel(value) {
  if (value === "formal") return "正式自动";
  if (value === "lab") return "内测";
  return "人工/不明";
}

// Original line 158
export function draftDateKey(value) {
  const date = new Date(value || "");
  if (Number.isNaN(date.getTime())) return "";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

// Original line 330
export function audioIdentity(item) {
  return [item.project, item.material, item.language].filter(Boolean).join(" / ") || "历史或未登记任务";
}

// Original line 522
export function productionIdentity(item) {
  return [item.project, item.material, item.language].filter(Boolean).join(" / ")
    || (item.category === "capcut_test" ? "隔离测试文件" : "历史或未登记任务");
}

// Original line 619
export function ageFromTime(value) {
  if (!value) return "无成功更新时间";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "时间未知";
  return formatAge(Math.max(0, Math.floor((Date.now() - timestamp) / 1000)));
}

// Original line 663
export function stageClass(value) {
  if (value === "completed") return "completed";
  if (value === "failed") return "failed";
  if (value === "running") return "active";
  if (value === "unconfigured") return "disabled";
  if (value === "offline") return "failed";
  return "idle";
}

// Original line 743
export function currentProjectPipeline(payload = {}, currentProjectStatus = {}) {
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

// Original line 846
export function categoryFor(raw) {
  if (["Completed", "completed"].includes(raw)) return "completed";
  if (["Failed", "failed", "validation_failed", "manual_review"].includes(raw)) return "failed";
  if (["Waiting", "waiting_capcut", "waiting_client", "stopped"].includes(raw)) return "waiting";
  return "running";
}

// Original line 853
export function step5FilterKey(item) {
  return JSON.stringify([item.project || "未分类", item.material || "--"]);
}

// Original line 1269
export function runtimeFacts(services = [], currentProjectStatus = {}) {
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

// Original line 1313
export function nextActionFor(currentProjectStatus = {}) {
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

// Original line 1392
export function describeSourceErrors(errors = []) {
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

export function safetyEntries(data) {
 const hasActiveProject=data?.productionContext?.hasActiveProject===true;
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
 return entries.map(([title,value,text,klass])=>({title,text:!value||value.error?value?.message||'状态源暂不可用，保留其他检查结果':text(value),tone:!value||value.error?'warning':klass(value)}));
}
