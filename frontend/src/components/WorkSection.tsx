import { type CSSProperties, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import projectsData from '../data/projects.json'
import { ProjectDetail } from './ProjectDetail'
import { ProjectRevolver } from './ProjectRevolver'
import type { ProjectItem } from './projectTypes'
import { ExperienceTimeline } from './ExperienceTimeline'
import { projectPointerPosition } from '../lib/revolver'

const projectItems = projectsData as readonly ProjectItem[]
const projectDates = projectItems.map((project) => project.startedOn)
const sweepDuration = 310
const titleDuration = 420

type WorkSectionProps = {
  onNavigate: (path: string) => void
}

export function WorkSection({ onNavigate }: WorkSectionProps) {
  const [activeProjectIndex, setActiveProjectIndex] = useState(1)
  const [projectView, setProjectView] = useState<'selector' | 'detail' | 'returning'>('selector')
  const projectOpen = projectView !== 'selector'
  const work = useRef<HTMLElement>(null)
  const updateProjectPointer = useCallback((position: number) => {
    work.current?.style.setProperty('--project-position', String(projectPointerPosition(position, projectDates)))
  }, [])
  const panel = useRef<HTMLElement>(null)
  const interacted = useRef(false)
  const titleOrigin = useRef<{ x: number; y: number; fontSize: number } | null>(null)
  const returnTitle = useRef({ transform: 'none', color: '#282b24' })
  const titleMotion = useRef<Animation | null>(null)
  const returnDuration = useRef(titleDuration)
  const selectedProject = projectItems[activeProjectIndex] ?? projectItems[0]

  const openProject = () => {
    titleOrigin.current = null
    const heading = panel.current?.querySelector<HTMLElement>('.reel-item[aria-pressed="true"] strong')
    const panelBounds = panel.current?.getBoundingClientRect()
    if (heading && panelBounds) {
      const bounds = heading.getBoundingClientRect()
      titleOrigin.current = { x: bounds.left - panelBounds.left, y: bounds.top - panelBounds.top, fontSize: Number.parseFloat(getComputedStyle(heading).fontSize) }
    }
    interacted.current = true
    setProjectView('detail')
  }

  const closeProject = () => {
    if (projectView !== 'detail') return
    const heading = panel.current?.querySelector<HTMLElement>('#project-focus-title')
    const slot = panel.current?.querySelector<HTMLElement>('.reel-item[aria-pressed="true"] strong')
    if (!heading || !slot || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setProjectView('selector')
      return
    }
    const titleStyle = getComputedStyle(heading)
    returnTitle.current = { transform: titleStyle.transform, color: titleStyle.color }
    const elapsed = titleMotion.current?.currentTime
    returnDuration.current = typeof elapsed === 'number' ? Math.min(titleDuration, Math.max(0, elapsed - sweepDuration)) : titleDuration
    panel.current?.style.setProperty('--return-reveal-delay', `${returnDuration.current}ms`)
    // Start a reversal at the current frame, including an interrupted opening.
    const snapshots = [...(panel.current?.querySelectorAll<HTMLElement>('.projects-intro,.reel-footer,.reel-summary,.reel-seat,.reel-item,.reel-item-copy,.reel-number,.reel-item small,.project-focus-header,.project-focus-copy > p,.project-focus-metrics,.project-focus-highlights,.project-focus-footer') ?? [])].map((element) => {
      const style = getComputedStyle(element)
      return { element, translate: style.translate, transform: style.transform, opacity: style.opacity }
    })
    for (const snapshot of snapshots) {
      snapshot.element.style.setProperty('--return-translate', snapshot.translate)
      snapshot.element.style.setProperty('--return-transform', snapshot.transform)
      snapshot.element.style.setProperty('--return-opacity', snapshot.opacity)
    }
    setProjectView('returning')
  }

  useLayoutEffect(() => {
    if (projectView === 'selector' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const heading = panel.current?.querySelector<HTMLElement>('#project-focus-title')
    const panelBounds = panel.current?.getBoundingClientRect()
    if (!heading || !panelBounds) return
    const bounds = heading.getBoundingClientRect()
    const returning = projectView === 'returning'
    const slot = panel.current?.querySelector<HTMLElement>('.reel-item[aria-pressed="true"] strong')
    const slotBounds = slot?.getBoundingClientRect()
    const origin = returning && slot && slotBounds
      ? { x: slotBounds.left - panelBounds.left, y: slotBounds.top - panelBounds.top, fontSize: Number.parseFloat(getComputedStyle(slot).fontSize) }
      : titleOrigin.current
    if (!origin) return
    const x = origin.x - (bounds.left - panelBounds.left)
    const y = origin.y - (bounds.top - panelBounds.top)
    const scale = origin.fontSize / Number.parseFloat(getComputedStyle(heading).fontSize)
    const slotFrame = { transform: `translate(${x}px, ${y}px) scale(${scale})`, color: '#293d24' }
    const detailFrame = { transform: 'translate(0, 0) scale(1)', color: '#282b24' }
    const motion = heading.animate(returning ? [returnTitle.current, slotFrame] : [slotFrame, detailFrame], {
      duration: returning ? returnDuration.current : titleDuration,
      delay: returning ? 0 : sweepDuration,
      endDelay: returning ? sweepDuration : 0,
      easing: 'cubic-bezier(.22,1,.36,1)', fill: 'both',
    })
    titleMotion.current = motion
    if (returning) motion.onfinish = () => setProjectView('selector')
    return () => { titleMotion.current = null; motion.onfinish = null; motion.cancel() }
  }, [projectView])

  useEffect(() => {
    if (!interacted.current) return
    const target = panel.current?.querySelector<HTMLButtonElement>(projectOpen ? '.project-focus-header button' : '.reel-open')
    target?.focus({ preventScroll: true })
    if (projectOpen && window.matchMedia('(max-width: 850px)').matches && (panel.current?.getBoundingClientRect().top ?? 0) < 24) {
      panel.current?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
    }
  }, [projectOpen])

  return (
    <section ref={work} style={{ '--project-position': projectPointerPosition(1, projectDates) } as CSSProperties} className="portfolio-section work-section tactile-work" id="work" aria-labelledby="work-title">
      <div className="split-work-layout">
        <section className="work-mobile-panel experience-panel" aria-labelledby="work-title">
          <header className="split-panel-intro career-intro">
            <h2 id="work-title">Experience</h2>

          </header>
          <ExperienceTimeline project={selectedProject} projectOpen={projectOpen} />
        </section>

        <section
          ref={panel}
          className={`work-mobile-panel projects-panel ${projectOpen ? 'is-project-detail' : ''}`}
          aria-labelledby={projectOpen ? 'project-focus-title' : 'projects-title'}
        >
          <div className={`project-view-stack ${projectOpen ? 'is-detail-open' : ''} ${projectView === 'returning' ? 'is-returning' : ''}`}>
            <div className="project-selector-view" aria-hidden={projectOpen} inert={projectOpen}>
              <header className="split-panel-intro projects-intro">
                <h2 id="projects-title">Projects</h2>
                <a
                  className="view-all-projects"
                  href="/projects"
                  onClick={(event) => { event.preventDefault(); onNavigate('/projects') }}
                >
                  All projects <span aria-hidden="true">↗</span>
                </a>
              </header>

              <ProjectRevolver
                projects={projectItems}
                activeIndex={activeProjectIndex}
                onChange={setActiveProjectIndex}
                onPositionChange={updateProjectPointer}
                onOpen={openProject}
              />
            </div>
            <div className="project-detail-view" aria-hidden={!projectOpen} inert={projectView !== 'detail'}>
              <ProjectDetail project={selectedProject} onBack={closeProject} />
            </div>
          </div>
        </section>
      </div>
    </section>
  )
}
