import { useEffect, useId, useState } from 'react'
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

// HiveNote's dashboard bee (hivenote/ui/app.js), redrawn in outline and centred on its body.
function Bee({ flip = false }: { flip?: boolean }) {
  const clip = `bee-${useId().replace(/:/g, '')}`
  return (
    <g transform={`scale(${flip ? -0.5 : 0.5} 0.5) translate(-32 -38)`}>
      <g className="bee-whole">
        <defs><clipPath id={clip}><ellipse cx="32" cy="38" rx="20" ry="17.5" /></clipPath></defs>
        <g transform="rotate(-22 25 21)"><ellipse className="bee-wing is-back" cx="25" cy="15" rx="8" ry="12" /></g>
        <path d="M12.8 37 L6.5 39 L12.8 41.2 Z" />
        <g clipPath={`url(#${clip})`}><path d="M20.75 18 V60 M28.75 18 V60" /></g>
        <ellipse cx="32" cy="38" rx="20" ry="17.5" />
        <g transform="rotate(16 36 21)"><ellipse className="bee-wing" cx="36" cy="14" rx="8.5" ry="12.5" /></g>
        <path d="M41 24 C42 18.5 44.5 15 47.5 13.5 M37 22.5 C37 17 38 13.5 40 11" />
        <circle cx="48" cy="13" r="2.2" /><circle cx="40.4" cy="10.5" r="2.2" />
        <circle className="bee-eye" cx="39.5" cy="35.5" r="2.2" /><circle className="bee-eye" cx="46" cy="35.5" r="2" />
        <path d="M40.6 40.8 q2.3 2.2 4.6 0" />
      </g>
    </g>
  )
}

const hex = (x: number, y: number, r = 15.5) => {
  const w = r * Math.sqrt(3) / 2
  return `M${x} ${y - r} L${x + w} ${y - r / 2} L${x + w} ${y + r / 2} L${x} ${y + r} L${x - w} ${y + r / 2} L${x - w} ${y - r / 2} Z`
}
// A loose comb of sixteen cells; each cell is a note. Every bee works its own corner.
const ROWS = [[22, [257.5, 286.5, 315.5, 344.5]], [47.5, [214, 243, 272, 301, 330, 359, 388]], [73, [228.5, 257.5, 286.5, 315.5, 344.5]]] as const
const CELLS = ROWS.flatMap(([y, xs]) => xs.map((x) => [x, y] as const))
const NOTE_A = [243, 47.5] as const, NOTE_B = [344.5, 22] as const, NOTE_C = [286.5, 73] as const, NOTE_D = [388, 47.5] as const
const writing = (x: number, y: number, start: number) => [[-6, 7, -4.5], [-7, 5, 0], [-5, 4, 4.5]].map(([a, b, dy], i) => (
  <path key={i} className="d-draw" pathLength={1} style={at(start + i * 0.3)} d={`M${x + a} ${y + dy} H${x + b}`} />
))

function HiveDemo() {
  return (
    <>
      {CELLS.map(([x, y], i) => <path key={`${x}-${y}`} className="d-draw demo-soft" pathLength={1} style={at(0.05 * i)} d={hex(x, y)} />)}
      {/* Claude writes a note; the cell glows when it is done. */}
      {writing(NOTE_A[0], NOTE_A[1], 2.0)}
      <path className="d-pop demo-strong" style={at(3.05)} d={hex(NOTE_A[0], NOTE_A[1])} />
      {/* Codex watches that note, then picks up the next one. */}
      <path className="hive-thread demo-faint" style={at(1.7)} d={`M${NOTE_B[0] - 4} ${NOTE_B[1] + 6} L${NOTE_A[0] + 6} ${NOTE_A[1] - 6}`} />
      {writing(NOTE_C[0], NOTE_C[1], 3.9)}
      {/* Hermes reads a note on its way past. */}
      <path className="hive-read demo-strong" style={at(2.15)} d={hex(NOTE_D[0], NOTE_D[1])} />
      <g className="hive-bee is-claude" style={at(0.6)}><Bee /><text className="demo-text demo-tiny" x="-13" y="4" textAnchor="end">Claude</text></g>
      <g className="hive-bee is-codex" style={at(0.6)}><Bee flip /><text className="demo-text demo-tiny" x="13" y="4">Codex</text></g>
      <g className="hive-bee is-hermes" style={at(0.6)}><Bee flip /><text className="demo-text demo-tiny" x="13" y="4">Hermes</text></g>
    </>
  )
}

const DEMOS: Record<string, { title: string, draw: () => ReactNode }> = {
  'portfolio-rag': { title: 'A question answered with its sources', draw: AskDemo },
  nsk: { title: 'Three people race for one slot; one booking wins', draw: NskDemo },
  hivenote: { title: 'Agents in a hive write notes, wait on each other and read what others left', draw: HiveDemo },
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
