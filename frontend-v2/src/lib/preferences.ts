export type Theme = 'dark' | 'light'
export const views = ['overview', 'tasks', 'uploads', 'files', 'commands', 'health'] as const
export type View = typeof views[number]

// Only presentation preferences live here; no credentials or business state.
export function readPreference(key: string): string | null {
  try { return localStorage.getItem(`ops-v2:${key}`) } catch { return null }
}

export function writePreference(key: string, value: string) {
  try { localStorage.setItem(`ops-v2:${key}`, value) } catch { /* UI also works with storage disabled. */ }
}

export function currentView(): View {
  const candidate = window.location.hash.slice(1)
  return views.includes(candidate as View) ? candidate as View : 'overview'
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.style.colorScheme = theme
}

export function initialTheme(): Theme {
  return readPreference('theme') === 'light' ? 'light' : 'dark'
}
