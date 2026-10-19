import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

Object.defineProperty(window, 'matchMedia', { configurable: true, value: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }) })
class TestIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(window, 'IntersectionObserver', { configurable: true, value: TestIntersectionObserver })
afterEach(() => { cleanup(); localStorage.clear(); window.location.hash = ''; document.documentElement.className = 'dark'; document.documentElement.dataset.theme = 'dark' })
