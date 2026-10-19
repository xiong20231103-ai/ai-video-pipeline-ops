import type { ReactNode } from 'react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { number } from '@/data/types'
import {
  Table as ShadcnTable,
  TableBody,
  TableHeader,
  TableHead,
  TableRow,
} from '@/components/ui/table'

export function Panel({
  title,
  children,
  actions,
  className = '',
}: {
  title: string
  children: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <Card className={`data-panel ${className}`} data-panel={title}>
      <header className="data-panel-heading">
        <h2>{title}</h2>
        {actions}
      </header>
      {children}
    </Card>
  )
}
export function Status({
  children,
  state = '',
}: {
  children: ReactNode
  state?: string
}) {
  const tone = /fail|block|offline|unknown|error/.test(state)
    ? 'danger'
    : /complet|online|healthy|good/.test(state)
      ? 'success'
      : /running|waiting|pending|warning|queued|sent|leased/.test(state)
        ? 'warning'
        : 'neutral'
  return (
    <Badge variant="outline" className={`data-status tone-${tone}`}>
      {children}
    </Badge>
  )
}
export function Progress({ value }: { value: unknown }) {
  const amount = Math.max(0, Math.min(100, number(value)))
  return (
    <div
      className="data-progress"
      role="progressbar"
      aria-valuenow={amount}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${amount}%` }} />
    </div>
  )
}
export function Empty({ children = '暂无数据' }: { children?: ReactNode }) {
  return <p className="data-empty">{children}</p>
}
export function DisabledWrite({ children }: { children: ReactNode }) {
  return (
    <Button
      data-v2-write=""
      variant="outline"
      size="sm"
      disabled
      title="V2 只读预览，操作请用旧页面"
    >
      {children}
    </Button>
  )
}
export function Field({
  name,
  value,
  legacy,
}: {
  name: string
  value: ReactNode
  legacy?: string
}) {
  return (
    <div className="data-field">
      <dt>{name}</dt>
      <dd data-legacy={legacy}>{value}</dd>
    </div>
  )
}
export function Table({
  headings,
  children,
  empty = false,
}: {
  headings: string[]
  children: ReactNode
  empty?: boolean
}) {
  return (
    <div className="data-table-scroll">
      <ShadcnTable className="data-table">
        <TableHeader>
          <TableRow>
            {headings.map((x) => (
              <TableHead key={x}>{x}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {empty ? (
            <tr>
              <td colSpan={headings.length}>
                <Empty />
              </td>
            </tr>
          ) : (
            children
          )}
        </TableBody>
      </ShadcnTable>
    </div>
  )
}
