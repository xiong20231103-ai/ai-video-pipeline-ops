import { object, list, text, type Row } from './types'

export const receiptKey = 'ops-command-receipts-v1'
export const pendingStates = new Set([
  'submitting',
  'queued',
  'leased',
  'sent',
  'unknown',
])
export function localReceipts(): Row[] {
  try {
    return list(JSON.parse(localStorage.getItem(receiptKey) || '[]'))
      .filter(
        (row) =>
          typeof row.requestId === 'string' &&
          typeof row.fingerprint === 'string' &&
          typeof row.path === 'string',
      )
      .slice(-100)
  } catch {
    return []
  }
}
export function saveReceipts(items: Row[]) {
  localStorage.setItem(receiptKey, JSON.stringify(items.slice(-100)))
}
export function mergeReceipts(local: Row[], remote: Row[]): Row[] {
  return [...local]
    .reverse()
    .concat(
      remote
        .filter(
          (row) => !local.some((x) => x.cloudCommandId === row.cloudCommandId),
        )
        .map((row) => ({ ...row, path: row.target, remote: true })),
    )
    .slice(0, 50)
}
export function captureReceipt(record: Row, answer: Row) {
  const next: Row = {
    ...record,
    state: answer.state,
    cloudCommandId: answer.cloudCommandId,
    updatedAt: Date.now(),
  }
  if (
    record.path === '/api/control-commands' &&
    object(answer.result).kind === 'http'
  ) {
    try {
      const result = object(answer.result)
      const body = object(
        JSON.parse(
          new TextDecoder().decode(
            Uint8Array.from(atob(text(result.bodyBase64, '')), (c) =>
              c.charCodeAt(0),
            ),
          ),
        ),
      )
      if (typeof body.commandId === 'string')
        next.homeCommandId = body.commandId
    } catch {
      /* A malformed body cannot create a different target or imply completion. */
    }
  }
  return next
}
