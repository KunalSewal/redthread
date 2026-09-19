import type { Event } from '../api'

/** The investigation as it happened: every tool call, judgement and decision, in order. */

const KIND: Record<string, string> = {
  alert: 'Alert received',
  evidence: 'Queried the graph',
  analysis: 'Investigation complete',
  assessment: 'Assessed',
  recommendation: 'Recommended',
  evidence_request: 'Asked for evidence',
  reply: 'Reply received',
  decision: 'Decided',
  report: 'Wrote the case summary',
  memory: 'Saved to case memory',
  validation: 'Checked the assessment',
  tool_error: 'Query failed',
  memory_error: 'Could not save to memory',
}

const MAJOR = new Set(['alert', 'assessment', 'recommendation', 'evidence_request', 'reply', 'decision'])

function describe(e: Event) {
  if (e.kind === 'evidence') {
    const m = e.detail.match(/^query:(\w+)\((.*)\)$/)
    if (m) return <><code className="ref-name">{m[1]}</code> <span className="ref-args">{m[2]}</span></>
  }
  return e.detail
}

export function Thread({ events, live }: { events: Event[]; live: boolean }) {
  if (!events.length) {
    return <p className="empty">No investigation yet. Start one to watch each step as the agent takes it.</p>
  }
  return (
    <ol className={`thread${live ? ' is-live' : ''}`}>
      {events.map((e) => (
        <li key={e.step} className={`knot knot-${e.kind}${MAJOR.has(e.kind) ? ' is-major' : ''}`}>
          <span className="knot-time">{e.at.slice(11, 19)}</span>
          <div>
            <p className="knot-kind">{KIND[e.kind] ?? e.kind}</p>
            <p className="knot-detail">{describe(e)}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}
