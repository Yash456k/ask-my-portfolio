import { describe, expect, it } from 'vitest'
import { parseActivitySnapshot } from './activity'

const snapshot = {
  generatedAt: '2026-07-16T05:55:09Z',
  period: { start: '2025-07-16', end: '2026-07-16' },
  codex: {
    total: 123,
    lifetimeTotal: 456,
    peakDailyTokens: 123,
    activeDays: 1,
    peak: { date: '2026-07-15', count: 123 },
    days: [{ date: '2026-07-15', tokens: 123, private: 'drop-me' }],
    apiKey: 'drop-me',
  },
  github: {
    username: 'Yash456k',
    total: 6,
    activeDays: 1,
    peak: { date: '2026-07-16', count: 6 },
    days: [{ date: '2026-07-16', count: 6 }],
  },
  accessToken: 'drop-me',
}

describe('parseActivitySnapshot', () => {
  it('accepts the public schema and strips undeclared data', () => {
    const parsed = parseActivitySnapshot(snapshot)

    expect(parsed).not.toBeNull()
    expect(JSON.stringify(parsed)).not.toContain('drop-me')
    expect(parsed?.codex.days[0]).toEqual({ date: '2026-07-15', tokens: 123 })
  })

  it('keeps Claude Code days when present and drops them when malformed', () => {
    const claude = { total: 9, lifetimeTotal: 12, activeDays: 1, since: '2026-07-01', peak: { date: '2026-07-15', count: 9 }, days: [{ date: '2026-07-15', tokens: 9 }] }
    expect(parseActivitySnapshot({ ...snapshot, claude })?.claude).toEqual(claude)
    const parsed = parseActivitySnapshot({ ...snapshot, claude: { ...claude, total: -1 } })
    expect(parsed).not.toBeNull()
    expect(parsed?.claude).toBeUndefined()
  })

  it('rejects malformed data', () => {
    expect(parseActivitySnapshot({ ...snapshot, generatedAt: 'not-a-date' })).toBeNull()
    expect(parseActivitySnapshot({ ...snapshot, github: { ...snapshot.github, total: -1 } })).toBeNull()
  })
})
