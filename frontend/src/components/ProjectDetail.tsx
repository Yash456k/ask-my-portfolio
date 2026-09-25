import type { ProjectItem } from './projectTypes'

type ProjectDetailProps = {
  project: ProjectItem
  onBack: () => void
}

export function ProjectDetail({ project, onBack }: ProjectDetailProps) {
  return (
    <article className="project-focus-view" aria-labelledby="project-focus-title">
      <header className="project-focus-header">
        <div>
          <span>{project.number}</span>
          <time>{project.date}</time>
        </div>
        <button type="button" onClick={onBack}>Back to revolver <span aria-hidden="true">↙</span></button>
      </header>

      <div className="project-focus-copy">
        <h2 id="project-focus-title">{project.title}</h2>
        <p>{project.description}</p>
      </div>

      <ul className="project-focus-metrics" aria-label={`${project.title} results`}>
        {project.hooks.map((hook) => <li key={hook}>{hook}</li>)}
      </ul>

      <ul className="project-focus-highlights" aria-label={`${project.title} highlights`}>
        {project.points.map((point) => <li key={point}>{point}</li>)}
      </ul>

      <footer className="project-focus-footer">
        <nav aria-label={`${project.title} links`}>
          <a href={project.href} target={project.external ? '_blank' : undefined} rel={project.external ? 'noreferrer' : undefined}>
            {project.linkLabel} <span aria-hidden="true">↗</span>
          </a>
          <a href={project.repository} target="_blank" rel="noreferrer">Source <span aria-hidden="true">↗</span></a>
        </nav>
      </footer>
    </article>
  )
}
