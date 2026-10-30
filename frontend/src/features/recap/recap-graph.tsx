import { useMemo } from 'react'
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from 'd3-force'
import { schemeEvidence, type CaseDetail, type Replay } from '@/lib/api'
import { cn } from '@/lib/utils'

/* What the agent knew, as a graph, at each step of the investigation.
 *
 * The backend's case graph says at which step each entity became known. Two things the agent found are
 * not in it but are the heart of the January cases, so they are added here from the evidence the backend
 * already sent: the run of charges the card had never made (activity_shift) and the other cards that
 * started the same thing (scheme_peers). The case record the agent writes back to the graph is shown too,
 * at the step it was opened. Nothing here is computed beyond placing what the backend returned. */

export type Kind = 'card' | 'txn' | 'customer' | 'holder' | 'device' | 'closed_case' | 'scheme' | 'case'
export interface RecapNode {
  id: string
  kind: Kind
  label: string
  step: number
  role?: string
  outcome?: string
}
export interface RecapEdge { source: string; target: string; step: number }

export function buildRecapGraph(detail: CaseDetail, replay: Replay) {
  const nodes = new Map<string, RecapNode>()
  const edges: RecapEdge[] = []
  const add = (n: RecapNode) => {
    if (!nodes.has(n.id)) nodes.set(n.id, n)
  }
  const link = (source: string, target: string, step: number) => {
    if (nodes.has(source) && nodes.has(target)) edges.push({ source, target, step })
  }

  for (const n of detail.graph.nodes) add({ id: n.id, kind: n.kind as Kind, label: n.label, step: n.step, role: n.role, outcome: n.outcome })
  for (const e of detail.graph.edges) link(e.source, e.target, e.step)

  const card = detail.alert.card_id
  const stepOf = (tool: string) => replay.steps.find((s) => s.tool === tool)?.step
  const { shift, peers } = schemeEvidence(detail)

  const runStep = stepOf('activity_shift')
  if (shift && runStep != null && nodes.has(card)) {
    for (const t of shift.run) {
      if (!nodes.has(t.tx_id)) {
        add({ id: t.tx_id, kind: 'txn', label: `$${t.amount.toFixed(2)}`, step: runStep, role: 'affected' })
        link(card, t.tx_id, runStep)
      }
    }
  }

  const peerStep = stepOf('scheme_peers')
  if (peers && peerStep != null && peers.peers.length > 0 && nodes.has(card)) {
    const hub = `scheme:${card}`
    add({ id: hub, kind: 'scheme', label: `Same new pattern, ${peers.other_cards_now} cards`, step: peerStep })
    link(card, hub, peerStep)
    for (const p of peers.peers) {
      add({ id: p.card_id, kind: 'card', label: p.card_id, step: peerStep, role: 'peer' })
      link(hub, p.card_id, peerStep)
    }
  }

  const opened = replay.steps.find((s) => s.kind === 'case_opened')
  const caseId = detail.handover?.in_graph ?? detail.answer?.case.graph_case_id
  if (opened && caseId && nodes.has(card)) {
    add({ id: `case:${caseId}`, kind: 'case', label: caseId, step: opened.step })
    link(`case:${caseId}`, card, opened.step)
  }

  return { nodes: [...nodes.values()], edges }
}

const RADIUS: Record<Kind, number> = {
  card: 6, txn: 6.5, customer: 10, holder: 8, device: 11, closed_case: 6, scheme: 12, case: 13,
}

interface Placed extends RecapNode, SimulationNodeDatum { r: number }

/** Lay the whole investigation out once, so nothing jumps as steps are added. */
function useLayout(nodes: RecapNode[], edges: RecapEdge[], center: string) {
  return useMemo(() => {
    const placed: Placed[] = nodes.map((n, i) => {
      const angle = (i / Math.max(1, nodes.length)) * Math.PI * 2
      const r = n.id === center ? 18 : RADIUS[n.kind]
      return { ...n, r, x: n.id === center ? 0 : Math.cos(angle) * 160, y: n.id === center ? 0 : Math.sin(angle) * 160, fx: n.id === center ? 0 : undefined, fy: n.id === center ? 0 : undefined }
    })
    const links = edges.map((e) => ({ ...e }))
    const sim = forceSimulation(placed)
      .force(
        'link',
        forceLink<Placed, (typeof links)[number] & { source: string | Placed; target: string | Placed }>(links)
          .id((d) => d.id)
          .distance((l) => {
            const t = l.target as Placed
            return t.kind === 'closed_case' || t.role === 'peer' || t.role === 'neighbor' || t.role === 'history' ? 46 : 84
          })
          .strength(0.7),
      )
      .force('charge', forceManyBody<Placed>().strength((d) => (d.kind === 'scheme' || d.kind === 'device' ? -320 : -150)))
      .force('collide', forceCollide<Placed>().radius((d) => d.r + 9))
      .force('x', forceX(0).strength(0.04))
      .force('y', forceY(0).strength(0.04))
      .stop()
    for (let i = 0; i < 400; i++) sim.tick()

    const xs = placed.map((p) => p.x ?? 0)
    const ys = placed.map((p) => p.y ?? 0)
    const pad = 56
    const box = {
      x: Math.min(...xs) - pad,
      y: Math.min(...ys) - pad,
      w: Math.max(...xs) - Math.min(...xs) + pad * 2,
      h: Math.max(...ys) - Math.min(...ys) + pad * 2,
    }
    return { byId: new Map(placed.map((p) => [p.id, p])), box }
  }, [nodes, edges, center])
}

export function RecapGraph({
  nodes,
  edges,
  center,
  step,
  verdictStep,
  verdict,
}: {
  nodes: RecapNode[]
  edges: RecapEdge[]
  center: string
  step: number
  /** The step at which the verdict was reached; fraud colour appears only from then on. */
  verdictStep: number | null
  verdict?: string
}) {
  const { byId, box } = useLayout(nodes, edges, center)
  const known = nodes.filter((n) => n.step <= step)
  const fraud = verdict === 'fraud' && verdictStep != null && step >= verdictStep
  const fresh = known.filter((n) => n.step === step)
  // Label the entities the story turns on; the crowd (other cards, past cases) is named on hover and in
  // the explanation beside the graph.
  const crowd = (n: RecapNode) => n.kind === 'closed_case' || ['peer', 'neighbor', 'history'].includes(n.role ?? '')
  const labelled = new Set([
    center,
    ...known.filter((n) => ['customer', 'device', 'scheme', 'case'].includes(n.kind)).map((n) => n.id),
    ...fresh.filter((n) => !crowd(n)).slice(0, 4).map((n) => n.id),
  ])

  if (known.length === 0) {
    return (
      <div className="grid h-full place-items-center text-center text-sm text-muted-foreground">
        <p className="max-w-[28ch]">Nothing is in the graph yet. The first lookup brings in the card and its transaction.</p>
      </div>
    )
  }

  return (
    <svg viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} className="h-full w-full" role="img" aria-label={`${known.length} entities known at step ${step}`}>
      <g>
        {edges
          .filter((e) => e.step <= step)
          .map((e, i) => {
            const a = byId.get(e.source)
            const b = byId.get(e.target)
            if (!a || !b) return null
            const isNew = e.step === step
            return (
              <line
                key={`${e.source}-${e.target}-${i}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className={cn('recap-in', isNew ? 'stroke-foreground/70' : 'stroke-border')}
                strokeWidth={isNew ? 1.6 : 1.1}
                strokeDasharray={b.kind === 'scheme' || a.kind === 'scheme' ? '4 3' : undefined}
              />
            )
          })}
      </g>
      <g>
        {known.map((n) => {
          const p = byId.get(n.id)!
          const isNew = n.step === step
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} className="recap-in">
              <title>{titleFor(n)}</title>
              {isNew && <circle r={p.r + 7} className="recap-halo fill-none stroke-foreground/30" strokeWidth={1.5} />}
              <Shape node={n} r={p.r} center={n.id === center} fraud={fraud} />
              {labelled.has(n.id) && (
                <text
                  y={n.kind === 'scheme' ? -(p.r + 8) : p.r + 13}
                  textAnchor="middle"
                  className={cn('fill-muted-foreground text-[10px]', (n.id === center || isNew) && 'fill-foreground font-medium')}
                >
                  {n.kind === 'txn' ? `${n.label}` : n.label}
                </text>
              )}
            </g>
          )
        })}
      </g>
    </svg>
  )
}

function Shape({ node, r, center, fraud }: { node: RecapNode; r: number; center: boolean; fraud: boolean }) {
  const hot = fraud && (center || node.role === 'affected' || node.role === 'flagged' || node.role === 'peer' || node.kind === 'scheme')
  const stroke = hot ? 'stroke-fraud' : center ? 'stroke-foreground' : 'stroke-muted-foreground/70'
  const fill = hot ? 'fill-fraud-soft' : 'fill-card'

  switch (node.kind) {
    case 'device':
      return <rect x={-r} y={-r * 0.75} width={r * 2} height={r * 1.5} rx={3} className={cn(fill, stroke)} strokeWidth={1.6} />
    case 'closed_case':
      return (
        <rect
          x={-r}
          y={-r}
          width={r * 2}
          height={r * 2}
          rx={1.5}
          className={node.outcome === 'confirmed_fraud' ? 'fill-fraud/70 stroke-fraud' : 'fill-cleared/60 stroke-cleared'}
          strokeWidth={1}
        />
      )
    case 'scheme':
      return <rect x={-r} y={-r} width={r * 2} height={r * 2} rx={2} transform="rotate(45)" className={cn(fill, stroke)} strokeWidth={1.8} />
    case 'case':
      return (
        <g>
          <rect x={-r} y={-r} width={r * 2} height={r * 2} rx={4} className="fill-foreground stroke-foreground" />
          <path d={`M${-r * 0.45} ${-r * 0.1} l${r * 0.3} ${r * 0.3} l${r * 0.6} ${-r * 0.6}`} className="fill-none stroke-background" strokeWidth={2} />
        </g>
      )
    case 'txn':
      return <circle r={r} className={cn(hot ? 'fill-fraud stroke-fraud' : 'fill-muted-foreground/50 stroke-muted-foreground/70')} strokeWidth={1} />
    default:
      return <circle r={r} className={cn(fill, stroke)} strokeWidth={center ? 2.5 : 1.4} />
  }
}

const KIND_NAME: Record<Kind, string> = {
  card: 'Card', txn: 'Transaction', customer: 'Customer', holder: 'Account holder', device: 'Device',
  closed_case: 'Past case', scheme: 'Shared pattern', case: 'Case record',
}

function titleFor(n: RecapNode) {
  const role =
    n.role === 'alert' ? ', the alert card' : n.role === 'flagged' ? ', the flagged charge' : n.role === 'affected' ? ', part of the run'
      : n.role === 'peer' ? ', started the same pattern' : n.role === 'neighbor' ? ', shares the device' : ''
  const outcome = n.outcome ? `, ${n.outcome.replace('_', ' ')}` : ''
  return `${KIND_NAME[n.kind]} ${n.id.replace(/^(scheme|case):/, '')}${role}${outcome}`
}

export function GraphLegend() {
  const items: [string, React.ReactNode][] = [
    ['Card', <circle key="c" cx="7" cy="7" r="5" className="fill-card stroke-muted-foreground" strokeWidth="1.4" />],
    ['Transaction', <circle key="t" cx="7" cy="7" r="4" className="fill-muted-foreground/50" />],
    ['Device', <rect key="d" x="1.5" y="3" width="11" height="8" rx="2" className="fill-card stroke-muted-foreground" strokeWidth="1.4" />],
    ['Past case', <rect key="p" x="2.5" y="2.5" width="9" height="9" rx="1" className="fill-muted-foreground/40" />],
    ['Shared pattern', <rect key="s" x="3" y="3" width="8" height="8" rx="1" transform="rotate(45 7 7)" className="fill-card stroke-muted-foreground" strokeWidth="1.4" />],
    ['Case record', <rect key="r" x="1.5" y="1.5" width="11" height="11" rx="2.5" className="fill-foreground" />],
  ]
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      {items.map(([label, icon]) => (
        <li key={label} className="flex items-center gap-1.5">
          <svg viewBox="0 0 14 14" className="size-3.5" aria-hidden="true">
            {icon}
          </svg>
          {label}
        </li>
      ))}
    </ul>
  )
}
