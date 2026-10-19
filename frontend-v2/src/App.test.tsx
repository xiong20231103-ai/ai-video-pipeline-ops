import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { applyTheme, currentView, initialTheme, readPreference, writePreference } from './lib/preferences'

describe('V2-0 isolated presentation shell', () => {
  it('labels the preview without calling an interface or inventing production data', async () => {
    const fetchSpy = vi.spyOn(window, 'fetch').mockRejectedValue(new Error('No API allowed'))
    render(<App />)
    expect(await screen.findByRole('heading', { name: '你的控制台，即将就绪' })).toBeVisible()
    expect(screen.getByText('非真实生产')).toBeVisible()
    expect(screen.getByText('未连接生产接口 · 不展示任务数据 · 不提供业务操作')).toBeVisible()
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(screen.queryByRole('button', { name: /安全继续|执行清理/ })).not.toBeInTheDocument()
  })

  it('starts dark and persists an explicit light theme across remounts', async () => {
    const user = userEvent.setup()
    const first = render(<App />)
    await user.click(screen.getByRole('button', { name: '切换到浅色主题' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(document.documentElement).not.toHaveClass('dark')
    expect(initialTheme()).toBe('light')
    first.unmount()
    render(<App />)
    expect(screen.getByRole('button', { name: '切换到深色主题' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: '切换到深色主题' }))
    expect(document.documentElement).toHaveClass('dark')
  })

  it('restores and navigates same-page hash views without creating backend routes', async () => {
    window.location.hash = '#uploads'
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: '上传' })).toBeVisible()
    window.location.hash = '#files'
    fireEvent(window, new HashChangeEvent('hashchange'))
    expect(screen.getByRole('heading', { level: 1, name: '文件管理' })).toBeVisible()
    expect(screen.getByRole('link', { name: '文件管理' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: '任务与流程' })).toHaveAttribute('href', '#tasks')
    window.location.hash = '#unexpected'
    expect(currentView()).toBe('overview')
  })

  it('keeps collapsed navigation accessible and remembers its presentation state', async () => {
    const user = userEvent.setup()
    const first = render(<App />)
    await user.click(screen.getByRole('button', { name: '收起侧栏' }))
    expect(screen.getByRole('button', { name: '展开侧栏' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByRole('link', { name: '安全继续与命令' })).toBeInTheDocument()
    expect(readPreference('sidebar')).toBe('collapsed')
    first.unmount()
    render(<App />)
    expect(screen.getByRole('button', { name: '展开侧栏' })).toBeInTheDocument()
  })

  it('opens a named mobile drawer, closes on selection and returns focus on Escape', async () => {
    const user = userEvent.setup()
    render(<App />)
    const trigger = screen.getByRole('button', { name: '打开导航' })
    await user.click(trigger)
    const dialog = screen.getByRole('dialog', { name: '控制台导航' })
    expect(dialog).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(trigger).toHaveFocus()
    await user.click(trigger)
    await user.click(within(screen.getByRole('dialog')).getByRole('link', { name: '上传' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('still works when local storage is blocked and never persists business state', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Blocked') })
    expect(initialTheme()).toBe('dark')
    expect(() => writePreference('theme', 'light')).not.toThrow()
    applyTheme('light')
    expect(document.documentElement.style.colorScheme).toBe('light')
  })

  it('does not start the React Bits animation loop when reduced motion is requested', async () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList)
    const animation = vi.spyOn(window, 'requestAnimationFrame')
    render(<App />)
    expect(await screen.findByRole('heading', { name: '你的控制台，即将就绪' })).toBeVisible()
    expect(animation).not.toHaveBeenCalled()
  })
})
