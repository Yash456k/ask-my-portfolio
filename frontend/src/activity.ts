export type ActivityPeriod = {
  start: string
  end: string
}

export type CountDay = {
  date: string
  count: number
}

export type TokenDay = {
  date: string
  tokens: number
}

export type ActivitySnapshot = {
  generatedAt: string
  period: ActivityPeriod
  codex: {
    total: number
    lifetimeTotal: number
    peakDailyTokens: number
    activeDays: number
    peak: CountDay | null
    days: TokenDay[]
  }
  github: {
    username: string
    total: number
    activeDays: number
    peak: CountDay | null
    days: CountDay[]
  }
  /** Claude Code tokens, from the laptop's session logs via HiveNote; absent until synced. */
  claude?: {
    total: number
    lifetimeTotal: number
    activeDays: number
    since: string
    peak: CountDay | null
    days: TokenDay[]
  }
}

const STORAGE_KEY = 'portfolio-activity:v1'
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/
const GITHUB_USERNAME = /^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$/

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isCount(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
}

function parseCountDay(value: unknown): CountDay | null {
  if (!isRecord(value) || typeof value.date !== 'string' || !ISO_DATE.test(value.date) || !isCount(value.count)) return null
  return { date: value.date, count: value.count }
}

function parseTokenDay(value: unknown): TokenDay | null {
  if (!isRecord(value) || typeof value.date !== 'string' || !ISO_DATE.test(value.date) || !isCount(value.tokens)) return null
  return { date: value.date, tokens: value.tokens }
}

function parseDays<T>(value: unknown, parser: (day: unknown) => T | null): T[] | null {
  if (!Array.isArray(value) || value.length > 370) return null
  const parsed = value.map(parser)
  return parsed.every((day): day is T => day !== null) ? parsed : null
}

function parseClaude(value: unknown): ActivitySnapshot['claude'] {
  if (!isRecord(value)) return undefined
  const days = parseDays(value.days, parseTokenDay)
  const peak = value.peak === null ? null : parseCountDay(value.peak)
  if (
    !days || (value.peak !== null && !peak)
    || !isCount(value.total) || !isCount(value.lifetimeTotal) || !isCount(value.activeDays) || value.activeDays > 370
    || typeof value.since !== 'string' || !ISO_DATE.test(value.since)
  ) return undefined
  return { total: value.total, lifetimeTotal: value.lifetimeTotal, activeDays: value.activeDays, since: value.since, peak, days }
}

export function parseActivitySnapshot(value: unknown): ActivitySnapshot | null {
  if (!isRecord(value) || !isRecord(value.period) || !isRecord(value.codex) || !isRecord(value.github)) return null
  const { period, codex, github } = value
  if (
    typeof value.generatedAt !== 'string'
    || !Number.isFinite(Date.parse(value.generatedAt))
    || typeof period.start !== 'string'
    || typeof period.end !== 'string'
    || !ISO_DATE.test(period.start)
    || !ISO_DATE.test(period.end)
  ) return null

  const codexDays = parseDays(codex.days, parseTokenDay)
  const githubDays = parseDays(github.days, parseCountDay)
  const codexPeak = codex.peak === null ? null : parseCountDay(codex.peak)
  const githubPeak = github.peak === null ? null : parseCountDay(github.peak)
  if (
    !codexDays
    || !githubDays
    || (codex.peak !== null && !codexPeak)
    || (github.peak !== null && !githubPeak)
    || !isCount(codex.total)
    || !isCount(codex.lifetimeTotal)
    || !isCount(codex.peakDailyTokens)
    || !isCount(codex.activeDays)
    || codex.activeDays > 370
    || typeof github.username !== 'string'
    || github.username.length > 39
    || !GITHUB_USERNAME.test(github.username)
    || !isCount(github.total)
    || !isCount(github.activeDays)
    || github.activeDays > 370
  ) return null

  return {
    generatedAt: value.generatedAt,
    period: { start: period.start, end: period.end },
    codex: {
      total: codex.total,
      lifetimeTotal: codex.lifetimeTotal,
      peakDailyTokens: codex.peakDailyTokens,
      activeDays: codex.activeDays,
      peak: codexPeak,
      days: codexDays,
    },
    github: {
      username: github.username,
      total: github.total,
      activeDays: github.activeDays,
      peak: githubPeak,
      days: githubDays,
    },
    ...(parseClaude(value.claude) ? { claude: parseClaude(value.claude) } : {}),
  }
}

export function readCachedActivity(): ActivitySnapshot | null {
  if (typeof window === 'undefined') return null
  try {
    const cached = window.localStorage.getItem(STORAGE_KEY)
    return cached ? parseActivitySnapshot(JSON.parse(cached)) : null
  } catch {
    return null
  }
}

export function writeCachedActivity(snapshot: ActivitySnapshot): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot))
  } catch {
    // HTTP caching still works when browser storage is blocked or full.
  }
}
