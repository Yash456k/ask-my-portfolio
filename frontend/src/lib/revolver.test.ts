import { describe, expect, it } from 'vitest'
import { cardSwipeDirection, timelinePosition, projectPointerPosition, springStep, wrapIndex } from './revolver'

describe('continuous project rotation', () => {
  it('wraps repeated travel in either direction', () => {
    expect(wrapIndex(-10, 3)).toBe(2)
    expect(wrapIndex(13, 3)).toBe(1)
  })
  it('settles on the same project at 30, 60 and 120 fps without overshooting', () => {
    for (const fps of [30, 60, 120]) {
      let state = { position: 0, velocity: 0 }
      for (let i = 0; i < fps; i++) {
        state = springStep(state.position, state.velocity, 3, 1 / fps)
        expect(state.position).toBeLessThanOrEqual(3)
      }
      expect(state.position).toBeCloseTo(3, 3)
    }
  })
  it('preserves momentum when input reverses and settles on the new target', () => {
    let state = springStep(0, 0, 2, .1)
    expect(state.velocity).toBeGreaterThan(0)
    for (let i = 0; i < 120; i++) state = springStep(state.position, state.velocity, -1, 1 / 60)
    expect(state.position).toBeCloseTo(-1, 4)
    expect(state.velocity).toBeCloseTo(0, 4)
  })
})


describe('project pointer and card gestures', () => {
  const today = Date.UTC(2026, 8, 24)
  const dates = ['2025-08-14', '2026-07-11', '2024-06-27']
  it('squeezes the early years and gives recent months more room', () => {
    expect(timelinePosition('2022-01-01', today)).toBe(0)
    expect(timelinePosition('2024-07-01', today)).toBeCloseTo(.07, 5)
    expect(timelinePosition('2026-09-24', today)).toBe(1)
    const month = (from: string, to: string) => timelinePosition(to, today) - timelinePosition(from, today)
    expect(month('2026-08-01', '2026-09-01')).toBeGreaterThan(2 * month('2025-01-01', '2025-02-01'))
    expect(month('2025-01-01', '2025-02-01')).toBeGreaterThan(4 * month('2023-01-01', '2023-02-01'))
  })
  it('lets recent work drift back as days pass', () => {
    const later = Date.UTC(2026, 11, 24)
    expect(timelinePosition('2026-07-11', later)).toBeLessThan(timelinePosition('2026-07-11', today))
    expect(timelinePosition('2023-06-01', later)).toBe(timelinePosition('2023-06-01', today))
  })
  it('tracks fractional barrel movement, including reverse and wraparound', () => {
    const [nsk, rag, chat] = dates.map((date) => timelinePosition(date, today))
    expect(projectPointerPosition(.5, dates, today)).toBeCloseTo((nsk + rag) / 2)
    expect(projectPointerPosition(1.5, dates, today)).toBeCloseTo((rag + chat) / 2)
    expect(projectPointerPosition(2.5, dates, today)).toBeCloseTo((chat + nsk) / 2)
    expect(projectPointerPosition(-.5, dates, today)).toBeCloseTo((chat + nsk) / 2)
  })
  it('commits deliberate horizontal pulls and quick flicks in both directions', () => {
    expect(cardSwipeDirection(-100, 8, -.1, 500)).toBe(1)
    expect(cardSwipeDirection(100, 8, .1, 500)).toBe(-1)
    expect(cardSwipeDirection(-30, 4, -.7, 500)).toBe(1)
  })
  it('rejects taps, short pulls and vertical page scrolling', () => {
    expect(cardSwipeDirection(10, 0, 1, 500)).toBeNull()
    expect(cardSwipeDirection(35, 0, .1, 500)).toBeNull()
    expect(cardSwipeDirection(90, 150, 1, 500)).toBeNull()
  })
})
