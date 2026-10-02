import { useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'

// A small outline drawing of what each project does. It plays once, holds, fades,
// and starts over; picking another project starts its drawing from the beginning.
const CYCLE_MS = 6500

const at = (seconds: number) => ({ '--d': `${seconds}s` }) as CSSProperties

function AskDemo() {
  return (
    <>
      <rect className="d-draw" pathLength={1} style={at(0)} x="372" y="6" width="150" height="26" rx="13" />
      <text className="d-fade demo-text" style={at(0.35)} x="447" y="23" textAnchor="middle">Who is Yash?</text>
      <circle className="d-draw" pathLength={1} style={at(0.9)} cx="46" cy="52" r="9" />
      <path className="d-draw" pathLength={1} style={at(1.05)} d="M46 47 L47.5 50.5 L51 52 L47.5 53.5 L46 57 L44.5 53.5 L41 52 L44.5 50.5 Z" />
      <rect className="d-draw" pathLength={1} style={at(1)} x="66" y="40" width="290" height="54" rx="12" />
      <path className="d-draw demo-soft" pathLength={1} style={at(1.4)} d="M84 56 H330" />
      <path className="d-draw demo-soft" pathLength={1} style={at(1.95)} d="M84 67 H306" />
      <path className="d-draw demo-soft" pathLength={1} style={at(2.5)} d="M84 78 H240" />
      <path className="d-draw demo-faint" pathLength={1} style={at(3)} d="M356 60 C366 60 366 52 378 52" />
      <path className="d-draw demo-faint" pathLength={1} style={at(3.15)} d="M356 72 C366 72 366 80 378 80" />
      <g className="d-pop" style={at(3.2)}>
        <rect x="378" y="43" width="112" height="18" rx="9" />
        <text className="demo-text demo-small" x="434" y="55.5" textAnchor="middle">About Yash · 0.97</text>
      </g>
      <g className="d-pop" style={at(3.4)}>
        <rect x="378" y="71" width="98" height="18" rx="9" />
        <text className="demo-text demo-small" x="427" y="83.5" textAnchor="middle">Projects · 0.64</text>
      </g>
    </>
  )
}

const SLOT_X = [118, 172, 226, 280, 334, 388, 442]
const TARGET = { x: 280, y: 18 }
const CURSOR = 'M0 0 L0 15 L4 11 L7.5 18 L10 17 L6.5 10 L12 10 Z'

function NskDemo() {
  return (
    <>
      {[18, 52].flatMap((y, row) => SLOT_X.map((x, column) => (
        <rect key={`${x}-${y}`} className="d-draw demo-soft" pathLength={1} style={at(0.04 * (row * 7 + column))} x={x} y={y} width="46" height="26" rx="6" />
      )))}
      <g className="d-pop" style={at(2.15)}>
        <rect className="demo-strong" x={TARGET.x} y={TARGET.y} width="46" height="26" rx="6" />
        <path className="demo-strong" d={`M${TARGET.x + 16} ${TARGET.y + 13} l5 5 l9 -10`} />
      </g>
      <text className="d-fade demo-text demo-small" style={at(2.4)} x={TARGET.x + 23} y="96" textAnchor="middle">500 at once · 1 booking</text>
      <g className="demo-cursor is-winner" style={{ ...at(0.7), '--fx': '-210px', '--fy': '30px' } as CSSProperties}>
        <path d={CURSOR} transform={`translate(${TARGET.x + 26} ${TARGET.y + 10})`} />
      </g>
      <g className="demo-cursor is-loser" style={{ ...at(0.75), '--fx': '230px', '--fy': '-14px' } as CSSProperties}>
        <path d={CURSOR} transform={`translate(${TARGET.x + 30} ${TARGET.y + 14})`} />
      </g>
      <g className="demo-cursor is-loser" style={{ ...at(0.8), '--fx': '40px', '--fy': '64px' } as CSSProperties}>
        <path d={CURSOR} transform={`translate(${TARGET.x + 20} ${TARGET.y + 16})`} />
      </g>
    </>
  )
}

function Card({ label, children }: { label: string, children?: ReactNode }) {
  return (
    <>
      <rect x="0" y="0" width="128" height="26" rx="6" />
      <circle cx="13" cy="13" r="5" />
      <text className="demo-text demo-small" x="24" y="16.5">{label}</text>
      <path className="demo-faint" d="M84 13 H116" />
      {children}
    </>
  )
}

function HiveDemo() {
  const columns = [['To do', 32], ['Doing', 226], ['Done', 420]] as const
  return (
    <>
      {columns.map(([name, x], index) => (
        <g key={name}>
          <rect className="d-draw demo-soft" pathLength={1} style={at(index * 0.12)} x={x} y="4" width="150" height="92" rx="9" />
          <text className="d-fade demo-text demo-small demo-muted" style={at(0.3 + index * 0.12)} x={x + 12} y="20">{name}</text>
        </g>
      ))}
      <g transform="translate(431 62)"><g className="d-pop" style={at(0.6)}><Card label="Hermes" /></g></g>
      <g transform="translate(43 62)">
        <g className="hive-card is-second" style={at(0.75)}><g className="d-pop" style={at(0.75)}><Card label="Codex" /></g></g>
      </g>
      <g transform="translate(43 28)">
        <g className="hive-card is-first" style={at(0.75)}>
          <g className="d-pop" style={at(0.6)}>
            <Card label="Claude">
              <path className="d-draw demo-strong" pathLength={1} style={at(4.35)} d="M100 13 l4 4 l8 -9" />
            </Card>
          </g>
        </g>
      </g>
    </>
  )
}

const DEMOS: Record<string, { title: string, draw: () => ReactNode }> = {
  'portfolio-rag': { title: 'A question answered with its sources', draw: AskDemo },
  nsk: { title: 'Three people race for one slot; one booking wins', draw: NskDemo },
  hivenote: { title: 'Agents claim tasks and move them to done', draw: HiveDemo },
}

export function ProjectDemo({ projectId }: { projectId: string }) {
  const [cycle, setCycle] = useState(0)
  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
    const timer = window.setInterval(() => setCycle((value) => value + 1), CYCLE_MS)
    return () => window.clearInterval(timer)
  }, [projectId])
  const demo = DEMOS[projectId]
  if (!demo) return null
  return (
    <svg key={`${projectId}-${cycle}`} className="project-demo" viewBox="0 0 600 100" role="img" aria-label={demo.title} style={{ '--cycle': `${CYCLE_MS}ms` } as CSSProperties}>
      {demo.draw()}
    </svg>
  )
}
