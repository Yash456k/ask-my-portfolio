import { useEffect, useId, useState } from 'react'
import { isTheme, readTheme, saveTheme, THEMES, THEME_STORAGE_KEY } from '../lib/themes'
import type { ThemeId } from '../lib/themes'

export function ThemePicker() {
  const id = useId()
  const [theme, setTheme] = useState<ThemeId>(() => {
    const applied = document.documentElement.dataset.theme
    return isTheme(applied) ? applied : readTheme()
  })
  const [saved, setSaved] = useState<boolean | null>(null)

  useEffect(() => {
    function sync(event: StorageEvent) {
      if (event.key !== THEME_STORAGE_KEY && event.key !== null) return
      const next = isTheme(event.newValue) ? event.newValue : 'warm'
      setTheme(next)
    }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [])

  function choose(next: ThemeId) {
    setSaved(saveTheme(next))
    setTheme(next)
  }

  return (
    <div className="palette-picker">
      <button className="palette-trigger" type="button" popoverTarget={id} aria-label="Choose color theme" title="Choose color theme">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2m0 16v2M2 12h2m16 0h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" strokeLinecap="round" />
        </svg>
      </button>
      <div id={id} popover="auto" className="palette-popover" aria-label="Color themes">
        <div className="palette-heading">
          <div><span>A different atmosphere</span><h2>Make it yours.</h2></div>
          <button type="button" popoverTarget={id} popoverTargetAction="hide" aria-label="Close color themes">×</button>
        </div>
        <fieldset className="palette-options">
          <legend className="visually-hidden">Color theme</legend>
          {THEMES.map((option) => (
            <label className="palette-option" key={option.id}>
              <input type="radio" name={id} value={option.id} checked={theme === option.id} onChange={() => choose(option.id)} />
              <span className={`palette-preview palette-preview--${option.id}`} aria-hidden="true"><i /><i /><i /></span>
              <span className="palette-description"><strong>{option.name}{option.id === 'warm' && <small>Default</small>}</strong><span>{option.description}</span></span>
              <span className="palette-check" aria-hidden="true">✓</span>
            </label>
          ))}
        </fieldset>
        <p className="palette-note" aria-live="polite">{saved === false ? 'Applied for this visit.' : saved ? 'Saved for your next visit.' : 'Three palettes. Same portfolio.'}</p>
      </div>
    </div>
  )
}
