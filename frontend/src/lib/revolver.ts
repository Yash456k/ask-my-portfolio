export function wrapIndex(index: number, length: number) {
  return ((index % length) + length) % length
}

// Critically damped spring, solved analytically so motion is stable at any frame rate.
export function springStep(position: number, velocity: number, target: number, seconds: number) {
  const frequency = 13
  const displacement = position - target
  const impulse = velocity + frequency * displacement
  const decay = Math.exp(-frequency * seconds)
  return {
    position: target + (displacement + impulse * seconds) * decay,
    velocity: (velocity - frequency * impulse * seconds) * decay,
  }
}

const MONTH = 30.44 * 24 * 60 * 60 * 1000
const AXIS_START = Date.UTC(2022, 0, 1)
// Little happened before mid-2024, so those years share a small gap at the start of the rail.
const AXIS_KNEE = Date.UTC(2024, 6, 1)
const KNEE_AT = .07
const STRETCH = 6 * MONTH

// The rail runs from 2022 to today. Past the knee, recent months get more room than old ones:
// a date's distance from the right end grows with the logarithm of its age, so everything
// drifts left as days pass.
export function timelinePosition(isoDate: string, today: number = Date.now()) {
  const time = Date.parse(isoDate)
  if (Number.isNaN(time)) return 1
  if (time <= AXIS_START) return 0
  if (time <= AXIS_KNEE) return ((time - AXIS_START) / (AXIS_KNEE - AXIS_START)) * KNEE_AT
  const age = Math.max(0, today - time)
  return 1 - (1 - KNEE_AT) * Math.log1p(age / STRETCH) / Math.log1p((today - AXIS_KNEE) / STRETCH)
}

export function projectPointerPosition(position: number, dates: readonly string[], today: number = Date.now()) {
  const lower = Math.floor(position)
  const fraction = position - lower
  const from = timelinePosition(dates[wrapIndex(lower, dates.length)], today)
  const to = timelinePosition(dates[wrapIndex(lower + 1, dates.length)], today)
  return from + (to - from) * fraction
}

export function cardSwipeDirection(x: number, y: number, velocity: number, width: number): -1 | 1 | null {
  if (Math.abs(x) < 24 || Math.abs(x) < Math.abs(y) * 1.2) return null
  if (Math.abs(x) < Math.min(width * .22, 90) && Math.abs(velocity) < .5) return null
  return x < 0 ? 1 : -1
}
