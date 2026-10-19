export type Row = Record<string, unknown>
export const object = (value: unknown): Row =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Row)
    : {}
export const list = (value: unknown): Row[] =>
  Array.isArray(value)
    ? value.filter((x) => x && typeof x === 'object' && !Array.isArray(x))
    : []
export const text = (value: unknown, fallback = '--'): string =>
  value === null || value === undefined || value === ''
    ? fallback
    : String(value)
export const number = (value: unknown): number =>
  Number.isFinite(Number(value)) ? Number(value) : 0
export const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((x) => typeof x === 'string') : []
export type Mode = 'home' | 'cloud'
export type Sample = {
  age: number
  received: number
  scan: string | null
  sourceAge: number | null
  version: string | null
  etag: string | null
}
export type Snapshot = {
  mode: Mode | null
  dashboard: Row | null
  safety: Row
  status: Row
  commands: Row[]
  backups: Row | null
  pendingDelete: Row
  session: Row
  error: string
  healthFailures: number
  receivedAt: Date | null
  receivedTick: number | null
  sources: Record<string, Sample>
  loading: boolean
}
