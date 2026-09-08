import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent, PointerEvent } from 'react'
import { experienceItems } from '../data/experience'
import { cardSwipeDirection, wrapIndex } from '../lib/revolver'
import type { ProjectItem } from './projectTypes'

const chapters = [experienceItems[2], experienceItems[1], experienceItems[0]]
const labels = ['2024', '2026', 'Now']
const dragHintKey = 'portfolio:experience-drag-hint:v1'
type Props = { project: ProjectItem; projectOpen: boolean }
type Drag = { startX: number; startY: number; x: number; y: number; previousX: number; time: number; velocity: number; moved: boolean; width: number }

export function ExperienceTimeline({ project, projectOpen }: Props) {
  const [active, setActive] = useState(2)
  const [hint, setHint] = useState<'pending' | 'visible' | 'dismissed'>(() => {
    try { return localStorage.getItem(dragHintKey) === 'seen' ? 'dismissed' : 'pending' }
    catch { return 'pending' }
  })
  const stack = useRef<HTMLDivElement>(null)
  const dismissHint = useCallback(() => {
    setHint('dismissed')
    try { localStorage.setItem(dragHintKey, 'seen') } catch { /* Storage can be unavailable in private browsing. */ }
  }, [])

  useEffect(() => {
    if (hint === 'dismissed') return
    if (hint === 'visible') {
      const timer = window.setTimeout(dismissHint, 5600)
      return () => window.clearTimeout(timer)
    }
    const element = stack.current
    if (!element) return
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || entry.intersectionRatio < .6) return
      try { localStorage.setItem(dragHintKey, 'seen') } catch { /* Still show the hint once during this visit. */ }
      setHint('visible')
      observer.disconnect()
    }, { threshold: .6 })
    observer.observe(element)
    return () => observer.disconnect()
  }, [dismissHint, hint])
  const [drag, setDrag] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const [leaving, setLeaving] = useState<{ index: number; direction: number; distance: number } | null>(null)
  const gesture = useRef<Drag | null>(null)
  const peeling = useRef(false)
  const hoverTimer = useRef<number | null>(null)
  const peelTimer = useRef<number | null>(null)
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  useEffect(() => () => {
    if (hoverTimer.current !== null) window.clearTimeout(hoverTimer.current)
    if (peelTimer.current !== null) window.clearTimeout(peelTimer.current)
  }, [])
  const clearHover = () => { if (hoverTimer.current !== null) window.clearTimeout(hoverTimer.current); hoverTimer.current = null }
  const select = (index: number) => {
    if (peeling.current || gesture.current?.moved) return
    clearHover()
    if (index !== active) dismissHint()
    setActive(wrapIndex(index, chapters.length))
  }
  const keyboard = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = wrapIndex(index + 1, chapters.length)
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = wrapIndex(index - 1, chapters.length)
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = chapters.length - 1
    else return
    event.preventDefault()
    select(next)
    buttons.current[next]?.focus()
  }
  const pointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || peeling.current || !event.isPrimary) return
    clearHover()
    gesture.current = { startX: event.clientX, startY: event.clientY, x: 0, y: 0, previousX: event.clientX, time: event.timeStamp, velocity: 0, moved: false, width: event.currentTarget.clientWidth }
  }
  const pointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = gesture.current
    if (!current) return
    const x = event.clientX - current.startX
    const y = event.clientY - current.startY
    if (!current.moved) {
      if (Math.abs(y) > Math.abs(x) && Math.abs(y) > 10) { gesture.current = null; return }
      if (Math.abs(x) < 8) return
      current.moved = true
      dismissHint()
      event.currentTarget.setPointerCapture(event.pointerId)
      setDragging(true)
    }
    const now = event.timeStamp
    current.velocity = (event.clientX - current.previousX) / Math.max(1, now - current.time)
    current.previousX = event.clientX
    current.time = now
    current.x = x
    current.y = y
    setDrag({ x: Math.max(-current.width, Math.min(current.width, x)), y: Math.max(-28, Math.min(28, y * .15)) })
  }
  const finishDrag = (event: PointerEvent<HTMLDivElement>, cancelled = false) => {
    const current = gesture.current
    gesture.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    setDragging(false)
    if (!current?.moved) return
    const velocity = event.timeStamp - current.time < 100 ? current.velocity : 0
    const direction = cancelled ? null : cardSwipeDirection(current.x, current.y, velocity, current.width)
    setDrag({ x: 0, y: 0 })
    if (direction === null) return
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      peeling.current = true
      setLeaving({ index: active, direction: -direction, distance: current.width + 60 })
      peelTimer.current = window.setTimeout(() => { setLeaving(null); peeling.current = false; peelTimer.current = null }, 260)
    }
    setActive(wrapIndex(active + direction, chapters.length))
  }

  return (
    <div className="career-deck">
      <div className="career-timeline">
        <div className={`project-timeline-pointer ${projectOpen ? 'is-open' : ''}`} role="img" aria-label={`${projectOpen ? 'Open' : 'Selected'} project: ${project.title}, ${project.date}`} title={`${project.title} · ${project.date}`}>
          <span className="project-marker-label"><b>{project.number}</b><span>{project.date}</span></span>
        </div>
        <div className="career-dates" role="tablist" aria-label="Experience timeline">
          {chapters.map((chapter, index) => <button key={chapter.id} ref={(element) => { buttons.current[index] = element }} type="button" role="tab" id={`career-tab-${chapter.id}`} aria-controls={`career-${chapter.id}`} aria-selected={active === index} tabIndex={active === index ? 0 : -1} onClick={() => select(index)} onPointerEnter={(event) => { if (event.pointerType !== 'mouse') return; clearHover(); hoverTimer.current = window.setTimeout(() => select(index), 90) }} onPointerLeave={clearHover} onKeyDown={(event) => keyboard(event, index)}><span aria-hidden="true" />{labels[index]}</button>)}
        </div>
      </div>
      <div ref={stack} className={`career-stack ${dragging ? 'is-dragging' : ''} ${hint === 'visible' ? 'is-hinting' : ''}`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={(event) => finishDrag(event)} onPointerCancel={(event) => finishDrag(event, true)}>
        {chapters.map((chapter, index) => {
          const depth = wrapIndex(index - active, chapters.length)
          const isLeaving = leaving?.index === index
          const isDragged = depth === 0 && drag.x !== 0
          const style: CSSProperties = { '--depth': depth, zIndex: isLeaving ? 5 : chapters.length - depth } as CSSProperties
          if (isLeaving) { style.transform = `translate3d(${leaving.direction * leaving.distance}px,-30px,70px) rotateY(${leaving.direction * -20}deg) rotateZ(${leaving.direction * 9}deg)`; style.opacity = 0 }
          else if (isDragged) { style.transform = `translate3d(${drag.x}px,${drag.y - Math.abs(drag.x) * .035}px,${Math.min(Math.abs(drag.x) * .16, 50)}px) rotateY(${Math.max(-14, Math.min(14, -drag.x * .055))}deg) rotateZ(${drag.x * .018}deg)` }
          return <article className={`career-card ${depth === 0 ? 'is-current' : ''} ${isLeaving ? 'is-peeling' : ''}`} key={chapter.id} style={style} id={`career-${chapter.id}`} role="tabpanel" aria-labelledby={`career-tab-${chapter.id}`} aria-describedby="career-gesture" aria-hidden={depth !== 0} inert={depth !== 0} tabIndex={depth === 0 ? 0 : -1}>
            <div className="career-card-content">
              <div className="career-card-meta"><span>{chapter.organization}</span>{chapter.current && <span className="career-current">Current</span>}</div>
              <h3>{chapter.title}</h3><time>{chapter.period}</time>
              <p>{chapter.detail}</p>
              {index !== 2 && <div className="career-proof">{index === 1 ? '9.66 / 10 CGPA' : '100K+ analytics records · 1,000+ roles / day'}</div>}
            </div>
          </article>
        })}
        {hint === 'visible' && <div className="career-swipe-invitation" aria-hidden="true">
          <span className="swipe-invitation-icon"><span /></span>
          <span><strong>Drag this card</strong><small>Left or right to explore</small></span>
        </div>}
      </div>
      <div className="career-navigation"><span>{String(active + 1).padStart(2, '0')} <i>/ 03</i></span><span className="career-drag-hint" id="career-gesture"><span className="gesture-cue" aria-hidden="true" />Drag to explore</span></div>
    </div>
  )
}
