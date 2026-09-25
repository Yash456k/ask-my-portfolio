import projectsData from '../data/projects.json'
import type { ProjectItem } from './projectTypes'

const projects = projectsData as readonly ProjectItem[]

type AllProjectsSectionProps = {
  onNavigate: (path: string) => void
}

export function AllProjectsSection({ onNavigate }: AllProjectsSectionProps) {
  return (
    <section className="portfolio-section all-projects-section" id="projects" aria-labelledby="all-projects-title">
      <header className="section-header all-projects-header">
        <p>Projects</p>
        <a className="route-header-home" href="/" onClick={(event) => { event.preventDefault(); onNavigate('/') }}>
          <span aria-hidden="true">←</span> Home
        </a>
      </header>

      <div className="all-projects-layout">
        <div className="all-projects-intro">
          <p className="section-kicker"><span /> Built and shipped</p>
          <h2 id="all-projects-title">Every project,<br /><em>in one place.</em></h2>
          <p>Production systems, useful experiments, and things that made it into people’s hands.</p>
          <a className="route-back-link" href="/" onClick={(event) => { event.preventDefault(); onNavigate('/') }}>
            <span aria-hidden="true">←</span> Back to portfolio
          </a>
        </div>

        <div className="all-projects-grid">
          {projects.map((project) => (
            <article key={project.id}>
              <header>
                <span>{project.number}</span>
                <time>{project.date}</time>
              </header>
              <p>{project.eyebrow}</p>
              <h3>{project.title}</h3>
              <strong>{project.oneLiner}</strong>
              <ul aria-label={`${project.title} metrics`}>
                {project.hooks.map((hook) => <li key={hook}>{hook}</li>)}
              </ul>
              <footer>
                <span>{project.tags.slice(0, 3).join(' · ')}</span>
                <a href={project.href} target={project.external ? '_blank' : undefined} rel={project.external ? 'noreferrer' : undefined}>
                  Open project <span aria-hidden="true">↗</span>
                </a>
              </footer>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
