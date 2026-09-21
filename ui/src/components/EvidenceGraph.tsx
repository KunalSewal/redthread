/* The case's neighbourhood in the graph, as it was known at a given step.
 *
 * The layout is solved once over the whole case and then revealed step by step, so rewinding the
 * thread makes the picture assemble and disassemble in place instead of rearranging itself. A graph
 * that reshuffles on every step is unreadable, and the point here is to watch one story build.
 *
 * Orange means fraud, never "selected": it marks the flagged transaction, the transactions found to
 * be part of it, the cards caught with it, and confirmed-fraud cases.
 */
import { useMemo, useState } from 'react'
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from 'd3-force'
import type { SimulationLinkDatum, SimulationNodeDatum } from 'd3-force'
import type { GraphEdge, GraphNode } from '../api'

type N = GraphNode & SimulationNodeDatum
type L = SimulationLinkDatum<N> & { kind: string; step: number }

const W = 520
const H = 460

function isFraudNode(n: GraphNode) {
  return n.role === 'flagged' || n.role === 'affected' || n.role === 'connected' || n.outcome === 'confirmed_fraud'
}

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const ns: N[] = nodes.map((n) => ({ ...n }))
  const ls: L[] = edges.map((e) => ({ source: e.source, target: e.target, kind: e.kind, step: e.step }))
  forceSimulation(ns)
    .force('link', forceLink<N, L>(ls).id((d) => d.id).distance((l) =>
      ((l.source as N).role === 'neighbor' || (l.target as N).role === 'neighbor' ? 70 : 55)))
    .force('charge', forceManyBody().strength(-260))
    .force('center', forceCenter(W / 2, H / 2))
    // Labelled nodes need room for their label, not just their shape, or the text collides.
    .force('collide', forceCollide<N>((d) => (d.kind === 'card' || d.kind === 'closed_case' ? 30 : 20)))
    .stop()
    .tick(300)
  for (const n of ns) {
    n.x = Math.max(20, Math.min(W - 20, n.x ?? 0))
    n.y = Math.max(20, Math.min(H - 20, n.y ?? 0))
  }
  return { ns, ls }
}

function Shape({ n }: { n: N }) {
  const fraud = isFraudNode(n)
  const stroke = fraud ? 'var(--thread)' : 'var(--graphite)'
  const fill = n.role === 'flagged' ? 'var(--thread)' : fraud ? 'var(--thread-wash)' : 'var(--sheet-raised)'
  const x = n.x ?? 0
  const y = n.y ?? 0
  switch (n.kind) {
    case 'device':
      return <path d={`M${x} ${y - 11} L${x + 11} ${y} L${x} ${y + 11} L${x - 11} ${y} Z`}
        fill="var(--ink)" stroke="var(--desk)" strokeWidth={1} />
    case 'card':
      return <rect x={x - 11} y={y - 7} width={22} height={14} rx={2} fill={fill} stroke={stroke} strokeWidth={1.5} />
    case 'closed_case':
      return <rect x={x - 7} y={y - 7} width={14} height={14} fill={fill} stroke={stroke} strokeWidth={1.5} />
    case 'customer':
      return <circle cx={x} cy={y} r={9} fill="var(--sheet-raised)" stroke="var(--graphite)" strokeWidth={1.5} />
    default:
      return <circle cx={x} cy={y} r={n.kind === 'txn' ? 6 : 7} fill={fill} stroke={stroke} strokeWidth={1.5} />
  }
}

/** Structural nodes are always labelled; a crowd of look-alike cards is labelled on demand instead. */
function labelled(n: GraphNode, crowd: boolean) {
  if (n.kind === 'txn') return n.role === 'flagged'
  if (n.kind === 'card' && (n.role === 'neighbor' || n.role === 'connected')) return !crowd
  return true
}

const KIND_NAME: Record<string, string> = {
  card: 'Card', txn: 'Transaction', device: 'Device', closed_case: 'Closed case',
  holder: 'Account holder', customer: 'Customer (issuer bucket)',
}

export function EvidenceGraph({ nodes, edges, step }: {
  nodes: GraphNode[]
  edges: GraphEdge[]
  /** Show only what the agent had found by this step. Infinity shows the finished case. */
  step?: number
}) {
  const { ns, ls } = useMemo(() => layout(nodes, edges), [nodes, edges])
  const [focus, setFocus] = useState<N | null>(null)
  const at = step ?? Infinity

  if (!nodes.length) return <p className="empty">The evidence graph appears once the case is investigated.</p>

  const visible = ns.filter((n) => n.step <= at)
  const shown = new Set(visible.map((n) => n.id))
  const links = ls.filter((l) => l.step <= at
    && shown.has((l.source as N).id) && shown.has((l.target as N).id))
  const byId = new Map(ns.map((n) => [n.id, n]))
  const crowd = visible.filter((n) => n.role === 'neighbor' || n.role === 'connected').length > 6
  const hidden = ns.length - visible.length

  return (
    <div className="graph">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Evidence graph: ${visible.length} entities known at step ${at === Infinity ? 'the end' : at}`}>
        {links.map((l, i) => {
          const s = l.source as N
          const t = l.target as N
          const thread = (isFraudNode(s) && isFraudNode(t))
            || (isFraudNode(s) && t.kind === 'device') || (isFraudNode(t) && s.kind === 'device')
          return <line key={i} x1={s.x} y1={s.y} x2={t.x} y2={t.y}
            stroke={thread ? 'var(--thread)' : 'var(--rule-strong)'} strokeWidth={thread ? 1.8 : 1} />
        })}
        {visible.map((n) => (
          <g key={n.id} tabIndex={0} className="graph-node"
            onMouseEnter={() => setFocus(byId.get(n.id) ?? null)}
            onMouseLeave={() => setFocus(null)}
            onFocus={() => setFocus(byId.get(n.id) ?? null)}
            aria-label={`${KIND_NAME[n.kind] ?? n.kind} ${n.id}`}>
            <Shape n={n} />
            {labelled(n, crowd) && (
              <text x={(n.x ?? 0) + 15} y={(n.y ?? 0) + 4} className="graph-label">{n.label}</text>
            )}
          </g>
        ))}
      </svg>
      <div className="graph-focus" aria-live="polite">
        {focus ? (
          <>
            <strong>{KIND_NAME[focus.kind] ?? focus.kind} {focus.id}</strong>
            {focus.profile && <span>{focus.profile}</span>}
            {focus.outcome && <span>{focus.outcome.replaceAll('_', ' ')}, {focus.pattern?.replaceAll('_', ' ')}</span>}
            {focus.score != null && <span className="num">model score {focus.score.toFixed(3)}</span>}
            {focus.role === 'neighbor' && <span>used the same device</span>}
          </>
        ) : (
          <span>
            {hidden > 0
              ? `${visible.length} of ${ns.length} entities found so far. Orange links run through the fraud.`
              : 'Orange links run through the fraud. Point at a node to see what it is.'}
          </span>
        )}
      </div>
    </div>
  )
}
