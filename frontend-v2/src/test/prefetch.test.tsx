import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { PrefetchCard, PrefetchOverview } from '@/components/views/PrefetchStatus'
import { prefetchText } from '@/data/prefetch'
afterEach(cleanup)
const view = { taskId:'task-6', batchId:'batch', sequence:6, productionDate:'11.2', project:'真黄颢', material:'碳岩板', state:'finished', completed:23,total:26,missingCount:3,acceptedPending:0,canReplenish:true }
describe('read-only cloud prefetch presentation', () => {
 it('shows a top hint without introducing any write button', () => {
  render(<PrefetchOverview data={{prefetchViews:[view]}} />)
  expect(screen.getByRole('region', {name:'提前下载缺链'})).toBeTruthy()
  expect(screen.getByText(/请在家里 Dashboard 补链/)).toBeTruthy()
  expect(screen.queryByRole('button')).toBeNull()
 })
 it('hides closed and interrupted gaps', () => {
  render(<PrefetchOverview data={{prefetchViews:[{...view,state:'interrupted',canReplenish:false}]}} />)
  expect(screen.queryByRole('region')).toBeNull()
 })
 it('renders progress and every card state independently of final counts', () => {
  expect(prefetchText(view)).toContain('已提前下载 23/26')
  expect(prefetchText({...view,state:'running'})).toContain('提前下载中')
  expect(prefetchText({...view,state:'interrupted'})).toContain('已中断，稍后续下')
  render(<PrefetchCard value={{...view,acceptedPending:3}} />)
  expect(screen.getByText(/已提前补链 3 条，轮到时下载/)).toBeTruthy()
 })
})
