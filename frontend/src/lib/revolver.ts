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

const AXIS_START = Date.UTC(2024, 0, 1)
const AXIS_MIDDLE = Date.UTC(2026, 0, 1)

// The timeline stops are 2024, 2026 and Now, where Now is today. Work started after 2026
// spreads across the last half up to today, so a project drifts back as days pass.
export function projectDatePosition(isoDate: string, today: number = Date.now()) {
  const time = Date.parse(isoDate)
  if (Number.isNaN(time)) return 1
  if (time <= AXIS_START) return 0
  if (time <= AXIS_MIDDLE) return ((time - AXIS_START) / (AXIS_MIDDLE - AXIS_START)) * .5
  return .5 + .5 * Math.min(1, (time - AXIS_MIDDLE) / Math.max(1, today - AXIS_MIDDLE))
}

export function projectPointerPosition(position: number, dates: readonly string[], today: number = Date.now()) {
  const lower = Math.floor(position)
  const fraction = position - lower
  const from = projectDatePosition(dates[wrapIndex(lower, dates.length)], today)
  const to = projectDatePosition(dates[wrapIndex(lower + 1, dates.length)], today)
  return from + (to - from) * fraction
}

export function cardSwipeDirection(x: number, y: number, velocity: number, width: number): -1 | 1 | null {
  if (Math.abs(x) < 24 || Math.abs(x) < Math.abs(y) * 1.2) return null
  if (Math.abs(x) < Math.min(width * .22, 90) && Math.abs(velocity) < .5) return null
  return x < 0 ? 1 : -1
}
