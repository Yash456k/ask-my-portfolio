export const THEME_STORAGE_KEY = 'portfolio:theme:v1'
export const THEMES = [
  { id: 'warm', name: 'Warm', description: 'The original. Paper and terracotta.', color: '#f5e8dc' },
  { id: 'midnight', name: 'Midnight', description: 'Warm embers after dark.', color: '#191613' },
  { id: 'forest', name: 'Forest', description: 'Soft sage and deep evergreens.', color: '#e7eee1' },
] as const
export type ThemeId = typeof THEMES[number]['id']

export function isTheme(value: unknown): value is ThemeId {
  return THEMES.some((theme) => theme.id === value)
}

export function readTheme(): ThemeId {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY)
    return isTheme(saved) ? saved : 'warm'
  } catch {
    return 'warm'
  }
}

export function applyTheme(theme: ThemeId) {
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEMES.find((item) => item.id === theme)!.color)
}

export function saveTheme(theme: ThemeId): boolean {
  applyTheme(theme)
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
    return true
  } catch {
    return false
  }
}
