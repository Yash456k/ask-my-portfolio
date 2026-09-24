// @vitest-environment jsdom
import { act, useState } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProjectRevolver } from './ProjectRevolver'
import type { ProjectItem } from './projectTypes'

const projects: ProjectItem[] = ['First', 'Second', 'Third'].map((title, index) => ({
  id: title, number: String(index + 1), date: 'Jan 2026', startedOn: '2026-01-15', title,
  eyebrow: '', role: '', summary: '', detail: '', highlights: [], metrics: [], tags: [],
  href: '/', repository: '', linkLabel: '', external: false,
}))

let container: HTMLDivElement
let root: Root
let aperture: HTMLElement
const onOpen = vi.fn()

function Harness() {
  const [active, setActive] = useState(1)
  return <ProjectRevolver projects={projects} activeIndex={active} onChange={setActive} onOpen={onOpen} onPositionChange={() => {}} />
}

function pointer(target: Element, type: string, x: number, y: number, pointerId = 1) {
  act(() => {
    target.dispatchEvent(new PointerEvent(type, {
      bubbles: true, pointerId, pointerType: 'touch', isPrimary: true,
      button: 0, buttons: type === 'pointerup' ? 0 : 1, clientX: x, clientY: y,
    }))
  })
}

function selectedTitle() {
  return container.querySelector('.reel-item[aria-pressed="true"] strong')!
}

function swipe(delta: number) {
  const title = selectedTitle()
  pointer(title, 'pointerdown', 100, 200)
  pointer(title, 'pointermove', 100, 200 + Math.sign(delta) * 10)
  // Touch implicitly captures the title. Moving capture to the aperture emits
  // lostpointercapture on that child, which bubbles through the aperture.
  pointer(title, 'lostpointercapture', 100, 200 + Math.sign(delta) * 10)
  pointer(aperture, 'pointermove', 100, 200 + delta)
  pointer(aperture, 'pointerup', 100, 200 + delta)
}

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
  onOpen.mockClear()
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  act(() => root.render(<Harness />))
  aperture = container.querySelector('.reel-aperture')!
  aperture.style.setProperty('--reel-spacing', '100px')
  const captured = new Set<number>()
  aperture.setPointerCapture = (id) => { captured.add(id) }
  aperture.releasePointerCapture = (id) => { captured.delete(id) }
  aperture.hasPointerCapture = (id) => captured.has(id)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
})

describe('project touch dragging', () => {
  it.each([[-70, 'Third'], [70, 'First']] as const)('continues after child capture transfers during a %ipx drag', (distance, expected) => {
    swipe(distance)
    expect(selectedTitle().textContent).toBe(expected)
    expect(onOpen).not.toHaveBeenCalled()
  })

  it.each([-24, 24])('advances on a short deliberate %ipx swipe', (distance) => {
    pointer(selectedTitle(), 'pointerdown', 100, 200)
    pointer(aperture, 'pointermove', 100, 200 + distance)
    pointer(aperture, 'pointerup', 100, 200 + distance)
    expect(selectedTitle().textContent).toBe(distance < 0 ? 'Third' : 'First')
  })

  it('allows repeated swipes to wrap through every project', () => {
    for (const expected of ['Third', 'First', 'Second', 'Third']) {
      swipe(-32)
      expect(selectedTitle().textContent).toBe(expected)
    }
  })

  it('retains the original selection on an actual cancellation or aperture capture loss', () => {
    for (const event of ['pointercancel', 'lostpointercapture']) {
      pointer(selectedTitle(), 'pointerdown', 100, 200)
      pointer(aperture, 'pointermove', 100, 130)
      pointer(aperture, event, 100, 130)
      pointer(aperture, 'pointerup', 100, 100)
      expect(selectedTitle().textContent).toBe('Second')
    }
  })

  it('rejects tiny movement, sideways intent and a pull returned to its origin', () => {
    for (const [x, y] of [[100, 206], [135, 205]]) {
      pointer(selectedTitle(), 'pointerdown', 100, 200)
      pointer(aperture, 'pointermove', x, y)
      pointer(aperture, 'pointerup', x, y)
      expect(selectedTitle().textContent).toBe('Second')
    }
    pointer(selectedTitle(), 'pointerdown', 100, 200)
    pointer(aperture, 'pointermove', 100, 140)
    pointer(aperture, 'pointermove', 100, 200)
    pointer(aperture, 'pointerup', 100, 200)
    expect(selectedTitle().textContent).toBe('Second')
  })
})
