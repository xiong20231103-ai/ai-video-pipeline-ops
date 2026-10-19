import { safeContinueFor } from './safe-continue'
import { useEffect, useRef, useState } from 'react'
import { ReadClient } from './client'
import { list, object, type Snapshot } from './types'
import {
  localReceipts,
  mergeReceipts,
  pendingStates,
  captureReceipt,
  saveReceipts,
  mergePolledReceipts,
} from './receipts'

const empty = (): Snapshot => ({
  mode: null,
  dashboard: null,
  safety: {},
  status: {},
  commands: [],
  backups: null,
  pendingDelete: {},
  session: {},
  error: '',
  healthFailures: 0,
  receivedAt: null,
  receivedTick: null,
  sources: {},
  loading: true,
})
export function useDashboard(date: string, batchId: string) {
  const [snapshot, setSnapshot] = useState(empty)
  const [revision, setRevision] = useState(0)
  const latest = useRef(snapshot)
  const client = useRef<ReadClient | null>(null)
  const selection = useRef({
    date,
    batchId,
    propDate: date,
    propBatch: batchId,
  })
  useEffect(() => {
    latest.current = snapshot
  }, [snapshot])
  useEffect(() => {
    const reader = new ReadClient()
    client.current = reader
    if (selection.current.propDate !== date) selection.current.date = date
    if (selection.current.propBatch !== batchId) {
      selection.current.batchId = batchId
      selection.current.date = ''
    }
    selection.current.propDate = date
    selection.current.propBatch = batchId
    let cancelled = false,
      refreshBusy = false,
      fullLoaded = false,
      lastFull = 0,
      lastSafety = 0,
      lastPending = 0,
      continueFailures = 0,
      continueWasRunning = false
    const timers = new Set<ReturnType<typeof setTimeout>>()
    const update = (value: Partial<Snapshot>) => {
      if (!cancelled) setSnapshot((old) => ({ ...old, ...value }))
    }
    const schedule = (work: () => Promise<void>, delay: number) => {
      if (!cancelled) {
        const id = setTimeout(() => {
          timers.delete(id)
          void work()
        }, delay)
        timers.add(id)
      }
    }
    reader.onSource = () =>
      update({ sources: Object.fromEntries(reader.samples) })
    reader.onRefresh = () => {
      fullLoaded = false
      void refresh()
    }
    async function auxiliary() {
      if (cancelled) return
      if (Date.now() - lastSafety >= 30000) {
        lastSafety = Date.now()
        try {
          update({ safety: await reader.read('/api/safety') })
        } catch {
          update({
            safety: {
              quality: {
                error: true,
                message: '生产安全控制面暂不可用；不会影响生产任务',
              },
            },
          })
        }
      }
      if (Date.now() - lastPending >= 60000) {
        lastPending = Date.now()
        try {
          update({
            pendingDelete: await reader.read('/api/controls/pending-delete'),
          })
        } catch {
          /* Retain last successful state; never invent an empty inventory. */
        }
      }
    }
    async function refresh() {
      if (cancelled || refreshBusy) return
      refreshBusy = true
      try {
        const active = selection.current
        const full =
          !fullLoaded ||
          Boolean(active.propDate || active.batchId) ||
          (reader.mode === 'cloud' && Date.now() - lastFull >= 60000)
        const params = new URLSearchParams()
        if (active.date) params.set('date', active.date)
        if (active.batchId) params.set('batchId', active.batchId)
        const data = await reader.read(
          full
            ? `/api/dashboard${params.size ? '?' + params : ''}`
            : '/api/dashboard/summary',
          2,
        )
        if (cancelled) return
        if (object(data.controls).continue) {
          data.controls = {
            ...object(data.controls),
            continue: safeContinueFor(reader).observe(
              object(object(data.controls).continue),
              latest.current.status,
            ),
          }
        }
        if (full) {
          fullLoaded = true
          lastFull = Date.now()
          active.date = String(data.selectedDate || active.date)
          const box = oBox(data.taskBoxes)
          active.batchId = String(box.batchId || '')
        }
        setSnapshot((old) => ({
          ...old,
          dashboard: full
            ? data
            : {
                ...old.dashboard,
                pipeline: data.pipeline,
                currentProjectStatus: data.currentProjectStatus,
                currentTaskBox: data.currentTaskBox || null,
                services: data.services,
                health: data.health,
                controls: {
                  ...object(old.dashboard?.controls),
                  continue: object(data.controls).continue,
                },
                taskBoxes: data.currentTaskBox
                  ? {
                      items: [data.currentTaskBox],
                      selected: data.currentTaskBox,
                      history: [],
                    }
                  : { items: [], selected: null, history: [] },
              },
          receivedAt: new Date(),
          receivedTick: performance.now(),
          error: '',
          loading: false,
          healthFailures: 0,
          sources: Object.fromEntries(reader.samples),
        }))
        void auxiliary()
      } catch (error) {
        if (cancelled) return
        try {
          await reader.read('/api/health', 0)
          update({
            healthFailures: 0,
            loading: false,
            error: '家里服务在线，正在显示最后可信状态并继续同步明细。',
          })
        } catch {
          if (!cancelled)
            setSnapshot((old) => ({
              ...old,
              loading: false,
              healthFailures: old.healthFailures + 1,
              error: `${old.healthFailures >= 2 ? '暂时无法读取新状态。' : ''}${old.dashboard ? '正在显示上一次可信状态；不会清空已有信息。' : '页面会继续自动重试，不影响正在运行的生产任务。'}${error instanceof Error ? ' ' + error.message : ''}`,
            }))
        }
      } finally {
        refreshBusy = false
        schedule(refresh, document.hidden ? 20000 : 5000)
      }
    }
    async function cloudPoll() {
      if (cancelled) return
      try {
        const [status, commands] = await Promise.all([
          reader.read('/console/status', 0),
          reader.read('/console/commands', 0),
        ])
        const before = localReceipts()
        const local = [...before]
        for (let i = 0; i < local.length; i++) {
          if (!pendingStates.has(String(local[i].state))) continue
          const row = local[i]
          const target = row.cloudCommandId
            ? `/console/commands/${encodeURIComponent(String(row.cloudCommandId))}`
            : `/console/commands/request/${encodeURIComponent(String(row.requestId))}`
          try {
            local[i] = captureReceipt(row, await reader.read(target, 0))
          } catch {
            /* Lost receive acknowledgements remain query-only, never resend. */
          }
        }
        try {
          saveReceipts(mergePolledReceipts(before, local))
        } catch {
          /* Read-only display can continue with blocked storage. */
        }
        update({
          status,
          commands: mergeReceipts(localReceipts(), list(commands.items)),
        })
      } catch {
        update({ status: {} })
      } finally {
        schedule(cloudPoll, 3000)
      }
    }
    async function continuePoll() {
      if (cancelled) return
      const result = object(object(latest.current.dashboard?.controls).continue)
      const running =
        result.state === 'offline'
          ? continueWasRunning
          : [
              'submitting',
              'queued',
              'leased',
              'sent',
              'unknown',
              'requested',
              'accepted',
              'running',
              'recovering',
              'persisted',
              'receiver_acknowledged',
              'workbench_acknowledged',
              'executing',
            ].includes(String(result.state)) &&
            !result.stale &&
            result.continueCanRetry !== true
      continueWasRunning = running
      const controller = safeContinueFor(reader)
      const target = controller.target()
      const hasOriginal =
        reader.mode === 'cloud' && target !== '/api/control-commands/current'
      if ((running || hasOriginal || controller.needsPoll()) && target) {
        try {
          const value = controller.observe(
            await reader.read(target),
            latest.current.status,
            true,
          )
          continueFailures = 0
          if (!cancelled)
            setSnapshot((old) => ({
              ...old,
              dashboard: {
                ...old.dashboard,
                controls: {
                  ...object(old.dashboard?.controls),
                  continue: value,
                },
              },
            }))
        } catch {
          controller.failed()
          continueFailures++
          if (continueFailures >= 2 && !cancelled)
            setSnapshot((old) => ({
              ...old,
              dashboard: {
                ...old.dashboard,
                controls: {
                  ...object(old.dashboard?.controls),
                  continue: {
                    allowed: false,
                    state: 'offline',
                    message: '无法读取安全继续状态；正在自动重连',
                  },
                },
              },
            }))
        }
      }
      schedule(continuePoll, running ? (document.hidden ? 5000 : 1500) : 10000)
    }
    async function start() {
      try {
        const mode = await reader.detect()
        if (cancelled) return
        update({ mode })
        void refresh()
        void continuePoll()
        if (mode === 'cloud') {
          void cloudPoll()
          void reader
            .read('/auth/session', 0)
            .then((session) => update({ session }))
            .catch(() => undefined)
        }
      } catch (error) {
        update({
          error: error instanceof Error ? error.message : '无法确认运行模式',
          loading: false,
          mode: null,
        })
        schedule(start, 5000)
      }
    }
    void start()
    return () => {
      cancelled = true
      for (const timer of timers) clearTimeout(timer)
      reader.stop()
    }
  }, [date, batchId, revision])
  return {
    snapshot,
    reader: client,
    refresh: () => setRevision((old) => old + 1),
    acceptContinueResult: (result: Record<string, unknown>) =>
      setSnapshot((old) => ({
        ...old,
        dashboard: {
          ...old.dashboard,
          controls: {
            ...object(old.dashboard?.controls),
            continue: client.current
              ? safeContinueFor(client.current).observe(result, old.status)
              : result,
          },
        },
      })),
  }
}

function oBox(value: unknown) {
  const payload = object(value)
  return object(payload.selected || list(payload.items)[0])
}
