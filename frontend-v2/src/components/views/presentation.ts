import { replenishmentQueueStatus } from "@/data/replenishment-status";
import {
  object as o,
  list,
  number as n,
  text as t,
  type Row,
} from '@/data/types'
import {
  currentProjectPipeline,
  formatBytes,
  formatDuration,
  categoryFor,
} from '@/data/legacy-formatters'

export function pipelineFor(data: Row) {
  const payload = o(data.pipeline)
  return (
    currentProjectPipeline(payload, o(data.currentProjectStatus)) ||
    Object.fromEntries(list(payload.items).map((row) => [t(row.key), row]))
  )
}
export function heroFor(data: Row) {
  const overview = o(data.overview),
    current = o(overview.current),
    stages = o(overview.pipeline)
  const active = ['download', 'voice', 'stitch', 'capcut', 'upload']
    .map((key) => o(stages[key]))
    .find((row) => row.state === 'running')
  if (active)
    return {
      title: `${active.name} · ${active.stateText}`,
      subtitle: t(active.current, `${active.program}正在运行`),
    }
  if (overview.current)
    return {
      title: t(current.state_text, '生产线等待中'),
      subtitle: `${t(current.date_label, '未定日期')} · ${t(current.project, '未分类')} · ${t(current.material, '未指定材料')} · ${t(current.language, '未指定语言')}`,
    }
  const gaps = list(o(data.projectGaps).items).filter((row) => row.gapActive)
  const queued = gaps.filter(row => replenishmentQueueStatus(row, o(data.receiverQueue).error ? [] : list(o(data.receiverQueue).items)).queued > 0).length
  return gaps.length
    ? {
        title: queued ? `没有正在运行的项目 · ${queued} 个项目补链已收到、排队中` : `没有正在运行的项目 · ${gaps.length} 个项目等待补链（共缺 ${gaps.reduce((sum, row) => sum + n(row.missingCount), 0)} 条）`,
        subtitle:
          gaps
            .slice(0, 4)
            .map(
              (row) =>
                `${t(row.date, '')} ${t(row.project, '未分类')}/${t(row.material)} 缺 ${n(row.missingCount)} 条`,
            )
            .join('；') + (queued ? '。已收到的补链等待执行，请勿重复补交。' : '。点上方“补链”按钮提交链接。'),
      }
    : {
        title: '暂时没有生产任务',
        subtitle: 'Dashboard 正常运行，正在等待工作台或客户端写入状态。',
      }
}
export function metricValues(metrics: Row) {
  const gpu = o(metrics.gpu),
    memory = metrics.memory,
    disk = o(metrics.disk),
    network = o(metrics.network)
  return [
    {
      key: 'cpu',
      label: 'CPU',
      value: metrics.cpu == null ? '--' : `${metrics.cpu}%`,
      note: '处理器占用',
      progress: metrics.cpu,
    },
    {
      key: 'memory',
      label: '内存',
      value: memory == null ? '--' : `${memory}%`,
      note:
        metrics.memory_used_gb == null
          ? '正在读取'
          : `${metrics.memory_used_gb} / ${metrics.memory_total_gb} GB`,
      progress: memory,
    },
    {
      key: 'gpu',
      label: 'GPU',
      value: gpu.available ? `${gpu.usage}%` : '未检测',
      note: gpu.available
        ? `${gpu.name} · ${gpu.temperature}°C`
        : t(gpu.name, '未检测到 NVIDIA GPU'),
      progress: gpu.usage,
    },
    {
      key: 'disk',
      label: '成片磁盘',
      value: disk.percent == null ? '--' : `${disk.percent}%`,
      note:
        disk.free_gb == null
          ? '目录暂不可用'
          : `${t(disk.label, '成片磁盘')} 剩余 ${disk.free_gb} GB`,
      progress: disk.percent,
    },
    {
      key: 'network',
      label: '网络',
      value: network.online ? '在线' : '离线',
      note: network.online
        ? `${Array.isArray(network.interfaces) ? network.interfaces.length : 0} 个活动网卡`
        : '未发现活动网络',
    },
  ]
}
export function uploadValues(upload: Row) {
  const configured = upload.state !== 'unconfigured',
    percent = Math.max(0, Math.min(100, n(upload.progress)))
  return {
    title: configured
      ? upload.state === 'running'
        ? '百度网盘上传中'
        : t(upload.stateText, '百度网盘上传服务')
      : '百度网盘未配置',
    message: configured
      ? `等待 ${upload.waiting || 0}，上传中 ${upload.uploading || 0}，云端已核验 ${upload.cloudVerified || 0}，失败 ${upload.failed || 0}。本条文件已清理 ${upload.taskFilesCleaned || 0}，等待共享引用释放 ${upload.waitingSharedRelease || 0}，全部清理完成 ${upload.localCleaned || 0}，阻止 ${upload.cleanupBlocked || 0}，历史保留 ${upload.legacyRetained || 0}，永久保护 ${upload.permanentKeep || 0}。`
      : '请先在TikHub工作台配置并授权百度网盘。',
    badge: configured
      ? upload.state === 'failed'
        ? '上传失败'
        : upload.state === 'completed'
          ? '上传完成'
          : upload.state === 'running'
            ? '上传中'
            : '等待成片'
      : '未配置',
    live: configured && n(upload.total) > 0,
    percent,
    label: `总进度 ${n(upload.completed)} / ${n(upload.total)} 条`,
    percentage: `${percent.toFixed(percent < 10 && percent > 0 ? 1 : 0)}%`,
    bytes: `${formatBytes(upload.bytesUploaded)} / ${formatBytes(upload.bytesTotal)}`,
    speed:
      n(upload.speedBytesPerSecond) > 0
        ? `${formatBytes(upload.speedBytesPerSecond)}/s`
        : '正在采样',
    remaining: `${n(upload.waiting) + n(upload.uploading)} 条 · ${formatBytes(upload.bytesRemaining)}`,
    eta:
      n(upload.bytesRemaining) <= 0
        ? '已完成'
        : formatDuration(upload.etaSeconds),
    file: t(upload.currentFileName, '').trim()
      ? `当前文件：${upload.currentFileName} · ${n(upload.currentFileProgress)}%（百度单文件分片完成后更新）`
      : n(upload.bytesRemaining) > 0
        ? '当前文件：等待上传服务领取下一条'
        : '全部文件已完成上传',
  }
}
export function currentValues(current: Row) {
  return {
    currentDate: t(current.date_label),
    currentProject: t(current.project),
    currentMaterial: t(current.material),
    currentLanguage: t(current.language),
    currentState: t(current.state_text || current.state, '等待'),
    currentError: t(current.error, ''),
    category: categoryFor(current.state),
  }
}
export const commandLabels: Record<string, string> = {
  submitting: '收件结果待查询',
  queued: '云端排队',
  leased: '代理已领取，尚未发送',
  sent: '已发家里，等待 HTTP 回执',
  unknown: '结果不明，必须在家里对账',
  completed: '已收到家里 HTTP 回执（业务进度请看原状态）',
  not_sent: '未发家里',
  cancelled: '已撤销发送前命令',
  expired: '发送前已过期',
  resolved_unknown: '已人工对账；原命令不再重试',
}
export const continueLabels: Record<string, string> = {
  submitting: '收件待查询',
  queued: '云端排队',
  leased: '代理已领取',
  sent: '已发家里，等待回执',
  unknown: '结果不明，请人工对账',
  idle: '尚未对账',
  requested: '命令已发送',
  persisted: '命令已保存',
  receiver_acknowledged: '家里接收器已收到',
  workbench_acknowledged: '家里工作台已领取',
  executing: '正在安全继续',
  accepted: '工作台已接收',
  running: '正在安全继续',
  recovering: '正在恢复当前项目',
  completed: '恢复已完成',
  blocked: '已阻止',
  failed: '执行失败',
  expired: '命令已过期',
  offline: '状态服务离线',
}
