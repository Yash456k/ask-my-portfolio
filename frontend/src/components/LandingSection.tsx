import { ActivityDeck } from './ActivityDeck'
// Theme picker disabled for now; restore with the <ThemePicker /> line below.
// import { ThemePicker } from './ThemePicker'



type LandingSectionProps = {
  onNavigate: (path: string) => void
}

export function LandingSection({ onNavigate }: LandingSectionProps) {
  return (
    <section className="portfolio-section landing-section" id="home" aria-labelledby="landing-title">
      <div className="landing-orbit" aria-hidden="true">
        <span />
      </div>

      <header className="portfolio-nav">
        <a className="portfolio-wordmark" href="#home" aria-label="Yash Khambhatta, home">
          Yash Khambhatta
        </a>
        <nav aria-label="Portfolio">
          <a href="/projects" onClick={(event) => { event.preventDefault(); onNavigate('/projects') }}>Projects</a>
          <a href="/about" onClick={(event) => { event.preventDefault(); onNavigate('/about') }}>About</a>
          <a className="nav-contact" href="mailto:yash456k@gmail.com">Let&apos;s talk</a>
          {/* <ThemePicker /> */}
        </nav>
      </header>

      <div className="landing-hero">
        <div className="landing-copy">
          <h1 id="landing-title">
            I build stuff
            <em>I find interesting.</em>
          </h1>
          <p className="landing-summary">
            Yes, I use AI to build. I can also explain how everything works, ask me anything.
          </p>
          <div className="landing-actions">
            <a className="primary-link" href="#work">Explore selected work <span aria-hidden="true">↘</span></a>
            <a className="text-link" href="#playground">Or ask my portfolio</a>
          </div>
        </div>

        <div className="activity-focus"><ActivityDeck /></div>
      </div>

      <div className="landing-footer"><p className="landing-status"><span /> Full-stack engineer at AIVID Techvision</p>

        <a className="scroll-cue" href="#work" aria-label="Continue to experience and projects">
          <span>Scroll to explore</span>
          <b aria-hidden="true">↓</b>
        </a>
      </div>
    </section>
  )
}
