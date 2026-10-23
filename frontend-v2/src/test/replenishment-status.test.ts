import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { describe, expect, it } from 'vitest'
import { replenishmentQueueStatus as status } from '@/data/replenishment-status'
import type { Row } from '@/data/types'
const source = readFileSync(resolve(process.cwd(), '../static/app.js'), 'utf8').split('function currentLocalDateLabel')[0]
const legacy = runInNewContext(source + ';replenishmentQueueStatus') as typeof status
const gap: Row = { taskId: 'parent', project: 'fixture', material: 'board', date: '10.22', missingCount: 5, completed: 0 }
const child: Row = { taskId: 'child', replenishForTaskId: 'parent', canonicalTaskId: 'parent', project: 'fixture', material: 'board', date: '10.22', urls: ['https://example.test/a', 'https://example.test/b'], status: 'pending_confirmation', startMode: 'auto_start_first' }
describe('durable replenishment admission presentation', () => {
  const cases: [string, Row[], number][] = [
    ['none', [], 0], ['partial', [child], 2], ['duplicate receipt', [child, child], 2],
    ['cancelled', [{...child, status:'cancelled'}], 0], ['merged', [{...child, status:'merged_into_parent'}], 0],
    ['imported is not proof of waiting', [{...child, status:'imported_waiting_start'}], 0],
    ['different date', [{...child, date:'10.21'}], 0], ['different parent', [{...child, canonicalTaskId:'other'}], 0],
    ['different material', [{...child, material:'other'}], 0], ['empty urls', [{...child, urls:[]}], 0],
  ]
  for (const [name, queue, expected] of cases) it(name, () => {
    expect(status(gap, queue).queued).toBe(expected)
    expect(JSON.stringify(legacy(gap, queue))).toBe(JSON.stringify(status(gap, queue)))
    expect(gap.completed).toBe(0)
  })
  it('partial admission retains uncovered deficit', () => expect(status(gap,[child]).message).toContain('另有 3 条尚未补交'))
  it('full admission does not claim valid outputs', () => {
    const result = status({...gap,missingCount:2},[child])
    expect(result.message).toContain('素材仍缺 2 条')
    expect(result.message).toContain('请勿重复补交')
  })
  it('manual admission is not automatic', () => expect(status(gap,[{...child,startMode:'pending_confirmation'}]).message).toContain('等待确认启动'))
})
