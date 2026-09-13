// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readTheme, saveTheme, THEME_STORAGE_KEY } from './themes'

beforeEach(() => {
  localStorage.clear()
  delete document.documentElement.dataset.theme
  document.head.innerHTML = '<meta name="theme-color" content="#f5e8dc">'
})
afterEach(() => { vi.restoreAllMocks() })

describe('saved portfolio themes', () => {
  it('keeps the original Warm palette for a new visitor', () => {
    expect(readTheme()).toBe('warm')
  })
  it('ignores stale or invalid stored presets', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'removed-preset')
    expect(readTheme()).toBe('warm')
  })
  it('restores the selected preset for the next visit', () => {
    expect(saveTheme('forest')).toBe(true)
    expect(readTheme()).toBe('forest')
    expect(document.documentElement.dataset.theme).toBe('forest')
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe('#e7eee1')
  })
  it('can return to the original preset after using dark mode', () => {
    saveTheme('midnight')
    saveTheme('warm')
    expect(readTheme()).toBe('warm')
    expect(document.documentElement.dataset.theme).toBe('warm')
  })
  it('renders the default when storage access is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('Blocked', 'SecurityError') })
    expect(readTheme()).toBe('warm')
  })
  it('still applies a choice when it cannot be saved', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError') })
    expect(saveTheme('midnight')).toBe(false)
    expect(document.documentElement.dataset.theme).toBe('midnight')
  })
})
