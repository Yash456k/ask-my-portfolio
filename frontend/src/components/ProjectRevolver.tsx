import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent, PointerEvent } from 'react'
import { springStep, wrapIndex } from '../lib/revolver'
import type { ProjectItem } from './projectTypes'

type ProjectRevolverProps = {
  projects: readonly ProjectItem[]
  activeIndex: number
  onChange: (index: number) => void
  onOpen: () => void
  onPositionChange: (position: number) => void
}

export function ProjectRevolver({ projects, activeIndex, onChange, onOpen, onPositionChange }: ProjectRevolverProps) {
  const [position, setPosition] = useState(activeIndex)
  const physical = useRef({ position: activeIndex, velocity: 0, target: activeIndex })
  const frame = useRef<number | null>(null)
  const root = useRef<HTMLDivElement>(null)
  const gesture = useRef<{ pointerId: number; startX: number; startY: number; origin: number; target: number; spacing: number; dragged: boolean } | null>(null)
  const suppressClick = useRef(false)
  const selectedProject = projects[activeIndex] ?? projects[0]

  const animate = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      physical.current.position = physical.current.target
      physical.current.velocity = 0
      setPosition(physical.current.target)
      onPositionChange(physical.current.target)
      frame.current = null
      return
    }
    let previous = performance.now()
    const tick = (now: number) => {
      const state = physical.current
      const next = springStep(state.position, state.velocity, state.target, Math.min((now - previous) / 1000, .064))
      previous = now
      state.position = next.position
      state.velocity = next.velocity
      onPositionChange(state.position)
      if (Math.abs(state.position - state.target) < .0005 && Math.abs(state.velocity) < .005) {
        state.position = state.target
        state.velocity = 0
        setPosition(state.target)
        onPositionChange(state.target)
        frame.current = null
      } else {
        setPosition(state.position)
        frame.current = requestAnimationFrame(tick)
      }
    }
    frame.current = requestAnimationFrame(tick)
  }, [onPositionChange])

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
  }, [])

  const select = useCallback((target: number) => {
    physical.current.target = target
    onChange(wrapIndex(target, projects.length))
    animate()
  }, [animate, onChange, projects.length])

  const rotate = useCallback((direction: number) => {
    // Bound queued travel without throwing away input during an animation.
    const state = physical.current
    const target = state.target + direction
    select(Math.max(Math.round(state.position) - 3, Math.min(Math.round(state.position) + 3, target)))
  }, [select])

  useEffect(() => {
    const element = root.current
    if (!element) return
    let accumulated = 0
    let lastInput = 0
    let lastStep = 0
    const wheel = (event: WheelEvent) => {
      if (event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return
      event.preventDefault()
      const now = performance.now()
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 300 : 1)
      if (now - lastInput > 160 || Math.sign(accumulated) !== Math.sign(delta)) accumulated = 0
      lastInput = now
      accumulated += delta
      if (Math.abs(accumulated) >= 45 && now - lastStep > 130) {
        rotate(Math.sign(accumulated))
        accumulated = 0
        lastStep = now
      }
    }
    element.addEventListener('wheel', wheel, { passive: false })
    return () => element.removeEventListener('wheel', wheel)
  }, [rotate])

  const keyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
    event.preventDefault()
    rotate(event.key === 'ArrowDown' ? 1 : -1)
  }
  const pointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !event.isPrimary || gesture.current) return
    suppressClick.current = false
    const spacing = Number.parseFloat(getComputedStyle(event.currentTarget).getPropertyValue('--reel-spacing')) || 104
    gesture.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, origin: physical.current.position, target: physical.current.target, spacing, dragged: false }
  }
  const pointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const drag = gesture.current
    if (!drag || drag.pointerId !== event.pointerId) return
    const delta = event.clientY - drag.startY
    if (!drag.dragged) {
      const sideways = event.clientX - drag.startX
      if (Math.abs(sideways) > Math.abs(delta) && Math.abs(sideways) > 8) { gesture.current = null; return }
      if (Math.abs(delta) < 8) return
      drag.dragged = true
      suppressClick.current = true
      event.currentTarget.setPointerCapture(event.pointerId)
    }
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    physical.current.position = drag.origin - delta / drag.spacing
    physical.current.velocity = 0
    setPosition(physical.current.position)
    onPositionChange(physical.current.position)
  }
  const pointerEnd = (event: PointerEvent<HTMLDivElement>, cancelled = false) => {
    const drag = gesture.current
    if (!drag || drag.pointerId !== event.pointerId) return
    gesture.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (!drag.dragged) return
    if (cancelled) { select(drag.target); return }
    const delta = event.clientY - drag.startY
    // A short intentional swipe advances a project; longer pulls retain their travel.
    const steps = Math.abs(delta) < 20 ? 0 : Math.max(1, Math.round(Math.abs(delta) / drag.spacing))
    select(drag.target - Math.sign(delta) * steps)
  }
  const lostPointerCapture = (event: PointerEvent<HTMLDivElement>) => {
    // Touch starts with implicit capture on a child. Its capture-loss event bubbles
    // when the aperture takes over; only losing the aperture's own capture cancels.
    if (event.target === event.currentTarget) pointerEnd(event, true)
  }
  const openProject = () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current)
    frame.current = null
    physical.current.position = physical.current.target
    physical.current.velocity = 0
    setPosition(physical.current.target)
    onPositionChange(physical.current.target)
    onOpen()
  }
  const center = Math.round(position)

  return (
    <div className="smooth-reel-stage">
      <div ref={root} className="smooth-reel" role="group" aria-label="Project selector" aria-describedby="project-gesture" tabIndex={0} onKeyDown={keyboard}>
        <div className="reel-aperture" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={(event) => pointerEnd(event)} onPointerCancel={(event) => pointerEnd(event, true)} onLostPointerCapture={lostPointerCapture}>
          <div className="reel-seat" aria-hidden="true" />
          {[-2, -1, 0, 1, 2].map((slot) => {
            const absolute = center + slot
            const index = wrapIndex(absolute, projects.length)
            const project = projects[index]
            const offset = absolute - position
            const distance = Math.abs(offset)
            const opacity = distance <= 1 ? 1 - distance * .55 : Math.max(0, .45 * (2 - distance))
            return (
              <button type="button" className="reel-item" key={absolute}
                style={{ '--offset': offset, opacity, transform: `translateY(calc(-50% + ${offset} * var(--reel-spacing))) perspective(900px) rotateX(${-Math.sign(offset) * Math.min(distance, 2) * 18}deg) scale(${1 - Math.min(distance, 2) * .055})` } as CSSProperties}
                aria-hidden={Math.abs(slot) > 1} tabIndex={Math.abs(slot) > 1 ? -1 : 0}
                aria-pressed={index === activeIndex && Math.abs(slot) <= 1}
                aria-label={`${index === activeIndex ? 'Selected project' : 'Select project'}: ${project.title}`}
                onClick={(event) => { if (event.detail === 0 || !suppressClick.current) select(absolute) }}>
                <span className="reel-number">{project.number}</span>
                <span className="reel-item-copy"><strong>{project.title}</strong><small>{project.summary}</small></span>
              </button>
            )
          })}
        </div>
      </div>
      <p className="reel-summary">{selectedProject.summary}</p>
      <div className="reel-footer">
        <span className="reel-hint" id="project-gesture"><span className="gesture-cue is-vertical" aria-hidden="true" /><span className="desktop-reel-hint">Scroll or drag to explore</span><span className="mobile-reel-hint">Swipe up or down to explore</span></span>
        <button type="button" className="reel-open" onClick={openProject} aria-label={`View ${selectedProject.title}`}>View project <span aria-hidden="true">↗</span></button>
      </div>
      <span className="visually-hidden" aria-live="polite">Selected: {selectedProject.title}</span>
    </div>
  )
}
