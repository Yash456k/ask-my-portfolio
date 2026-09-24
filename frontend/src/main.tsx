import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import './portfolio-refinement.css'
import './activity-focus.css'
import './themes.css'
// Theme selection is disabled for now, so every visitor sees Warm (the :root default),
// including anyone who saved another theme. Restore with the ThemePicker in LandingSection.
// import { applyTheme, isTheme, readTheme, THEME_STORAGE_KEY } from './lib/themes'
//
// applyTheme(readTheme())
// window.addEventListener('storage', (event) => {
//   if (event.key === THEME_STORAGE_KEY || event.key === null) {
//     applyTheme(isTheme(event.newValue) ? event.newValue : 'warm')
//   }
// })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
