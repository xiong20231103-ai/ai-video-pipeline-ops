import { number as n, type Row } from '@/data/types'

export function prefetchText(view: Row): string {
  const progress = `${n(view.completed)}/${n(view.total)}`
  const label = view.state === 'running' ? `提前下载中 · ${progress}`
    : view.state === 'interrupted' ? `已中断，稍后续下 · ${progress}` : `已提前下载 ${progress}`
  return label + (n(view.acceptedPending) ? ` · 已提前补链 ${n(view.acceptedPending)} 条，轮到时下载` : '')
    + (n(view.missingCount) ? ` · 缺 ${n(view.missingCount)} 条` : '')
}
