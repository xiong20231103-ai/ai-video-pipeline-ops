import { list, number as n, object as o, text as t, type Row } from '@/data/types'
import { prefetchText } from '@/data/prefetch'

export function PrefetchCard({ value }: { value: unknown }) {
  const view = o(value)
  if (!['running', 'interrupted', 'finished'].includes(t(view.state))) return null
  return <p className="prefetch-card-status">{prefetchText(view)}{view.canReplenish === true ? ' · 请在家里 Dashboard 补链' : ''}</p>
}

export function PrefetchOverview({ data }: { data: Row }) {
  const views = list(data.prefetchViews).filter(view => view.state === 'finished' && view.canReplenish === true && n(view.missingCount) > 0)
  if (!views.length) return null
  return <section aria-label="提前下载缺链" aria-live="polite" className="runtime-guidance needs-action">
    {views.map(view => <p key={`${t(view.batchId)}:${t(view.taskId)}`}>
      {t(view.productionDate)} 第 {n(view.sequence)} 项 {t(view.project)}/{t(view.material)} 提前下载缺 {n(view.missingCount)} 条 · 请在家里 Dashboard 补链
    </p>)}
  </section>
}
