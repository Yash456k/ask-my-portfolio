import { useEffect, useMemo, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { getActivity } from '../api'
import { readCachedActivity } from '../activity'
import type { ActivitySnapshot } from '../activity'

type ActivityKind = 'codex' | 'github'
type CardPosition = 'active' | 'behind' | 'swapping-out' | 'swapping-in'
type ActivityRange = 'quarter' | 'year'

type HeatmapDay = {
  date: string
  count: number
  level: number
  isFuture: boolean
}

const DAY_MS = 86_400_000
const RANGE_WEEKS: Record<ActivityRange, number> = {
  quarter: 14,
  year: 53,
}

function dateAtNoon(value: string): Date {
  return new Date(`${value}T12:00:00`)
}

function isoDate(value: Date): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('en', {
    notation: 'compact',
    maximumFractionDigits: value >= 1_000_000_000 ? 2 : 1,
  }).format(value)
}

function formatTooltipValue(value: number, isTokenCount: boolean): string {
  if (!isTokenCount) return value.toLocaleString()
  const scaled = (divisor: number, suffix: string) => {
    const amount = value / divisor
    const maximumFractionDigits = amount >= 10 ? 1 : 2
    return `${new Intl.NumberFormat('en', { maximumFractionDigits }).format(amount)}${suffix}`
  }
  if (value >= 1_000_000_000) return scaled(1_000_000_000, ' billion')
  if (value >= 1_000_000) return scaled(1_000_000, ' million')
  if (value >= 1_000) return scaled(1_000, 'K')
  return value.toLocaleString()
}

function formatDate(value: string): string {
  return dateAtNoon(value).toLocaleDateString('en', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function quantile(sorted: number[], fraction: number): number {
  return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * fraction))] ?? 0
}

function buildCalendar(activity: ActivitySnapshot, kind: ActivityKind, range: ActivityRange): HeatmapDay[][] {
  const sourceDays = kind === 'codex'
    ? activity.codex.days.map((day) => ({ date: day.date, count: day.tokens }))
    : activity.github.days
  const counts = sourceDays.map((day) => day.count).filter(Boolean).sort((a, b) => a - b)
  // Keep ordinary days quiet and reserve the brightest shade for rare peaks.
  const bands = [0.5, 0.75, 0.95]
  const thresholds = bands.map((fraction) => quantile(counts, fraction))
  const byDate = new Map(sourceDays.map((day) => [day.date, day.count]))
  const lastDataDay = dateAtNoon(activity.period.end)
  const calendarEnd = new Date(lastDataDay)
  calendarEnd.setDate(calendarEnd.getDate() + (6 - calendarEnd.getDay()))
  const weekCount = RANGE_WEEKS[range]
  const calendarStart = new Date(calendarEnd.getTime() - ((weekCount * 7 - 1) * DAY_MS))

  return Array.from({ length: weekCount }, (_, weekIndex) =>
    Array.from({ length: 7 }, (_, dayIndex) => {
      const date = new Date(calendarStart.getTime() + ((weekIndex * 7 + dayIndex) * DAY_MS))
      const dateKey = isoDate(date)
      const count = byDate.get(dateKey) ?? 0
      const level = count === 0 ? 0 : 1 + thresholds.filter((threshold) => count > threshold).length
      return { date: dateKey, count, level, isFuture: date > lastDataDay }
    }),
  )
}

function monthMarkers(weeks: HeatmapDay[][]): Array<{ week: number; label: string }> {
  const markers: Array<{ week: number; label: string }> = []
  let previousMonth = ''
  weeks.forEach((week, index) => {
    const first = dateAtNoon(week[0].date)
    const middle = new Date(first.getTime() + 3 * DAY_MS)
    const month = `${middle.getFullYear()}-${middle.getMonth()}`
    if (month !== previousMonth) {
      markers.push({ week: index + 1, label: middle.toLocaleDateString('en', { month: 'short' }) })
      previousMonth = month
    }
  })
  // Omit a short leading month rather than colliding with the next label.
  return markers.filter((marker, index) => !markers[index + 1] || markers[index + 1].week - marker.week >= 4)
}

function CodexMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.7 14.3 9.7 21.3 12l-7 2.3-2.3 7-2.3-7-7-2.3 7-2.3L12 2.7Z" />
    </svg>
  )
}

function GitHubMark() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 5v11.2M16 7.8v11.1M8 8.1h5.2A2.8 2.8 0 0 0 16 5.3V3m-8 13.2A2.8 2.8 0 1 1 5.2 19 2.8 2.8 0 0 1 8 16.2Zm8 2.7a2.8 2.8 0 1 1-2.8 2.8 2.8 2.8 0 0 1 2.8-2.8Z" />
    </svg>
  )
}

type ActivityCardProps = {
  activity: ActivitySnapshot
  kind: ActivityKind
  position: CardPosition
  range: ActivityRange
  onSwapComplete: () => void
}

type HoveredDay = {
  day: HeatmapDay
  left: number
  top: number
  alignment: 'start' | 'center' | 'end'
}

function ActivityCard({ activity, kind, position, range, onSwapComplete }: ActivityCardProps) {
  const weeks = useMemo(() => buildCalendar(activity, kind, range), [activity, kind, range])
  const months = useMemo(() => monthMarkers(weeks), [weeks])
  const summary = useMemo(() => {
    const activeDays = weeks.flat().filter((day) => day.count > 0)
    const total = activeDays.reduce((sum, day) => sum + day.count, 0)
    const averageDays = kind === 'codex'
      ? activeDays.filter((day) => day.count > 1_000_000)
      : activeDays
    const averageTotal = averageDays.reduce((sum, day) => sum + day.count, 0)
    const peak = activeDays.reduce<HeatmapDay | null>(
      (current, day) => !current || day.count > current.count ? day : current,
      null,
    )
    return {
      total,
      activeDays: activeDays.length,
      average: averageDays.length > 0 ? averageTotal / averageDays.length : 0,
      peak,
    }
  }, [kind, weeks])
  const [hovered, setHovered] = useState<HoveredDay | null>(null)
  const days = useMemo(() => weeks.flat(), [weeks])
  const lastDayIndex = days.reduce((last, day, index) => (day.isFuture ? last : index), 0)
  // One tab stop for the whole calendar; arrow keys move between days.
  const [focusedDay, setFocusedDay] = useState<string | null>(null)
  const focusIndex = Math.max(0, focusedDay ? days.findIndex((day) => day.date === focusedDay) : lastDayIndex)
  const isCodex = kind === 'codex'
  const displayTotal = isCodex && range === 'year'
    ? activity.codex.lifetimeTotal
    : summary.total
  const unit = isCodex
    ? range === 'year' ? 'lifetime tokens' : 'tokens in period'
    : 'contributions'
  const columnTemplate = range === 'quarter'
    ? `repeat(${weeks.length}, minmax(0, 18px))`
    : `repeat(${weeks.length}, minmax(0, 1fr))`

  const showTooltip = (element: HTMLButtonElement, day: HeatmapDay) => {
    const calendar = element.closest<HTMLElement>('.activity-calendar')
    if (!calendar) return
    const cellBounds = element.getBoundingClientRect()
    const calendarBounds = calendar.getBoundingClientRect()
    const left = cellBounds.left - calendarBounds.left + cellBounds.width / 2
    const edgeSpace = 82
    setHovered({
      day,
      left,
      top: cellBounds.top - calendarBounds.top,
      alignment: left < edgeSpace ? 'start' : left > calendarBounds.width - edgeSpace ? 'end' : 'center',
    })
  }

  const moveFocus = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = { ArrowLeft: -7, ArrowRight: 7, ArrowUp: -1, ArrowDown: 1 }[event.key]
    const next = event.key === 'Home' ? 0
      : event.key === 'End' ? lastDayIndex
        : step === undefined ? null : Math.min(lastDayIndex, Math.max(0, focusIndex + step))
    if (next === null) return
    event.preventDefault()
    setFocusedDay(days[next].date)
    event.currentTarget.querySelectorAll<HTMLButtonElement>('.activity-cell')[next]?.focus()
  }

  return (
    <article
      className={`activity-card activity-card--${kind} is-${position}`}
      aria-hidden={position === 'behind' || position === 'swapping-out'}
      inert={position === 'behind' || position === 'swapping-out'}
      onAnimationEnd={position === 'swapping-in' ? onSwapComplete : undefined}
    >
      <header className="activity-card-header">
        <div className="activity-card-identity">
          <span className="activity-card-mark">{isCodex ? <CodexMark /> : <GitHubMark />}</span>
          <div>
            <p>{isCodex ? 'Codex' : 'GitHub'} activity</p>
            <span>{range === 'quarter' ? 'Last 3 months' : 'Last 12 months'}</span>
          </div>
        </div>
        <span className="activity-live"><i /> Updated daily</span>
      </header>

      <div className="activity-metrics">
        <div className="activity-stat activity-total">
          <span>{unit}</span>
          <strong>{formatNumber(displayTotal)}</strong>
          <small>{range === 'quarter' ? 'last 3 months' : isCodex ? 'all time' : 'last 12 months'}</small>
        </div>
        <div className="activity-stat activity-average">
          <span>Daily avg</span>
          <strong>{formatNumber(summary.average)}</strong>
          {!isCodex && <small>per active day</small>}
        </div>
        {summary.peak && (
          <div className="activity-stat activity-peak">
            <span>Peak</span>
            <strong>{formatNumber(summary.peak.count)}</strong>
            <small>{formatDate(summary.peak.date)}</small>
          </div>
        )}
      </div>

      <div className={`activity-calendar is-${range}`} role="group" aria-label={`${isCodex ? 'Codex' : 'GitHub'} daily activity for the last ${range === 'quarter' ? '3 months' : 'year'}`}>
        <div className="activity-months" aria-hidden="true" style={{ gridTemplateColumns: columnTemplate }}>
          {months.map((month) => (
            <span key={`${month.week}-${month.label}`} style={{ gridColumnStart: month.week }}>{month.label}</span>
          ))}
        </div>
        <div className="activity-weekdays" aria-hidden="true"><span>Mon</span><span>Wed</span><span>Fri</span></div>
        <div className="activity-grid" style={{ gridTemplateColumns: columnTemplate }} onKeyDown={moveFocus}>
          {days.map((day, index) => (
            <button
              type="button"
              className={`activity-cell level-${day.level} ${day.isFuture ? 'is-future' : ''}`}
              key={day.date}
              disabled={day.isFuture}
              tabIndex={index === focusIndex ? 0 : -1}
              aria-label={`${formatDate(day.date)}: ${formatTooltipValue(day.count, isCodex)} ${isCodex ? 'tokens' : 'contributions'}`}
              onMouseEnter={(event) => showTooltip(event.currentTarget, day)}
              onMouseLeave={() => setHovered(null)}
              onFocus={(event) => {
                setFocusedDay(day.date)
                showTooltip(event.currentTarget, day)
              }}
              onBlur={() => setHovered(null)}
            />
          ))}
        </div>
        {hovered && (
          <output
            className={`activity-day-tooltip align-${hovered.alignment}`}
            style={{ left: hovered.left, top: hovered.top }}
          >
            <strong>{formatTooltipValue(hovered.day.count, isCodex)}</strong> {isCodex ? 'tokens' : 'contributions'}
            <span>{formatDate(hovered.day.date)}</span>
          </output>
        )}
      </div>

      <footer className="activity-card-footer">
        <span><strong>{summary.activeDays}</strong> active days</span>
        <span>Refreshed daily from official activity</span>
      </footer>
    </article>
  )
}

export function ActivityDeck() {
  const [activity, setActivity] = useState<ActivitySnapshot | null>(() => readCachedActivity())
  const [refreshFailed, setRefreshFailed] = useState(false)
  const [active, setActive] = useState<ActivityKind>('codex')
  const [range, setRange] = useState<ActivityRange>('year')
  const [swap, setSwap] = useState<{ from: ActivityKind; to: ActivityKind } | null>(null)
  const selected = swap?.to ?? active

  useEffect(() => {
    const controller = new AbortController()
    void getActivity(controller.signal)
      .then((snapshot) => {
        setActivity(snapshot)
        setRefreshFailed(false)
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setRefreshFailed(true)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!swap) return
    const fallback = window.setTimeout(() => {
      setActive(swap.to)
      setSwap(null)
    }, 460)
    return () => window.clearTimeout(fallback)
  }, [swap])

  const selectCard = (next: ActivityKind) => {
    if (next === selected || swap) return
    setSwap({ from: active, to: next })
  }

  const completeSwap = () => {
    if (!swap) return
    setActive(swap.to)
    setSwap(null)
  }

  const positionFor = (kind: ActivityKind): CardPosition => {
    if (swap) return kind === swap.from ? 'swapping-out' : 'swapping-in'
    return kind === active ? 'active' : 'behind'
  }

  if (!activity) {
    return (
      <aside className="activity-deck activity-deck--loading" aria-label="Coding activity" aria-live="polite">
        <div className="activity-loading-card">
          <span className="activity-card-mark"><CodexMark /></span>
          <p>{refreshFailed ? 'Activity is temporarily unavailable.' : 'Loading activity…'}</p>
        </div>
      </aside>
    )
  }

  return (
    <aside className="activity-deck" aria-label="Coding activity">
      <div className="activity-toolbar">
        <div className="activity-range-switch" aria-label="Choose activity period">
          <button type="button" aria-pressed={range === 'quarter'} onClick={() => setRange('quarter')}>3M</button>
          <button type="button" aria-pressed={range === 'year'} onClick={() => setRange('year')}>1Y</button>
        </div>
        <div className="activity-switch" aria-label="Choose activity source">
          <span className={`activity-switch-glider is-${selected}`} aria-hidden="true" />
          <button type="button" aria-pressed={selected === 'codex'} disabled={Boolean(swap)} onClick={() => selectCard('codex')}>
            Codex
          </button>
          <button type="button" aria-pressed={selected === 'github'} disabled={Boolean(swap)} onClick={() => selectCard('github')}>
            GitHub
          </button>
        </div>
      </div>

      <div className="activity-card-stack">
        <ActivityCard activity={activity} kind="codex" position={positionFor('codex')} range={range} onSwapComplete={completeSwap} />
        <ActivityCard activity={activity} kind="github" position={positionFor('github')} range={range} onSwapComplete={completeSwap} />
      </div>

      <p className="activity-caption">
        <span aria-hidden="true">↻</span> A living record of work, refreshed every day{refreshFailed ? ' · showing the latest saved update' : ''}.
      </p>
    </aside>
  )
}
