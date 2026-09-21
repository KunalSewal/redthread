/* The thread: the investigation as a line you can walk back along.
 *
 * This is the one control that drives the whole case file. Moving the playhead rewinds the evidence
 * graph, the belief scale, the evidence digest and the action plan to the state the agent was in at
 * that step. Arrow keys move it; the list uses a roving tabindex so it is one tab stop.
 */
import { useEffect, useRef } from 'react'
import type { Event } from '../api'

/** How each kind of step reads in the margin, and how its node is drawn. */
const KIND: Record<string, { label: string; node: 'dot' | 'ring' | 'diamond' | 'bar' | 'ask' }> = {
  alert: { label: 'Alert', node: 'bar' },
  evidence: { label: 'Queried the graph', node: 'dot' },
  analysis: { label: 'Stopped looking', node: 'ring' },
  assessment: { label: 'Weighed the evidence', node: 'diamond' },
  recommendation: { label: 'First recommendation', node: 'bar' },
  evidence_request: { label: 'Asked for evidence', node: 'ask' },
  reply: { label: 'Customer replied', node: 'ask' },
  decision: { label: 'Revised recommendation', node: 'bar' },
  validation: { label: 'Checked itself', node: 'ring' },
  report: { label: 'Wrote the case', node: 'ring' },
  memory: { label: 'Stored as memory', node: 'ring' },
}

/** The query name, without the 'query:' prefix and its arguments: 'alert_context(tx=…)' → the name. */
export function toolName(detail: string): string | null {
  const m = /^query:([a-z_]+)/.exec(detail)
  return m ? m[1] : null
}

function Node({ shape, state }: { shape: string; state: 'past' | 'current' | 'future' }) {
  const cls = `thread-node is-${state} node-${shape}`
  if (shape === 'diamond') return <span className={cls} aria-hidden="true" />
  return <span className={cls} aria-hidden="true" />
}

export function Thread({ events, step, onStep, live }: {
  events: Event[]
  step: number
  onStep: (step: number) => void
  live: boolean
}) {
  const listRef = useRef<HTMLOListElement>(null)
  const steps = events.map((e) => Number(e.step))
  const index = Math.max(0, steps.indexOf(step))

  // Keep the playhead in view when it moves, and carry keyboard focus with it. Both have to happen
  // after the render that moved it, or focus lands on the step we just left.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLButtonElement>('[data-current="true"]')
    if (!el) return
    el.scrollIntoView({ block: 'nearest', behavior: live ? 'smooth' : 'auto' })
    // Only follow focus if the reader is already on the thread; otherwise this would steal it.
    if (listRef.current?.contains(document.activeElement)) el.focus()
  }, [step, live])

  const move = (delta: number) => {
    const next = Math.min(Math.max(index + delta, 0), events.length - 1)
    if (events[next]) onStep(Number(events[next].step))
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    const keys: Record<string, () => void> = {
      ArrowDown: () => move(1),
      ArrowRight: () => move(1),
      ArrowUp: () => move(-1),
      ArrowLeft: () => move(-1),
      Home: () => events[0] && onStep(Number(events[0].step)),
      End: () => events.at(-1) && onStep(Number(events.at(-1)!.step)),
    }
    const fn = keys[e.key]
    if (!fn) return
    e.preventDefault()
    fn()  // focus follows in the effect above, once the new step has rendered
  }

  if (!events.length) {
    return <p className="thread-empty">{live ? 'Waiting for the first step…' : 'This case has not been investigated yet.'}</p>
  }

  return (
    <ol className="thread" ref={listRef} onKeyDown={onKeyDown} aria-label="Investigation steps">
      {events.map((e, i) => {
        const kind = KIND[e.kind] ?? { label: e.kind, node: 'dot' as const }
        const state = i < index ? 'past' : i === index ? 'current' : 'future'
        const tool = toolName(e.detail)
        return (
          <li key={`${e.step}-${i}`} className={`thread-step is-${state}`}>
            <button
              type="button"
              data-current={i === index}
              tabIndex={i === index ? 0 : -1}
              aria-current={i === index ? 'step' : undefined}
              onClick={() => onStep(Number(e.step))}
              className="thread-hit"
            >
              <span className="thread-num num">{e.step}</span>
              <Node shape={kind.node} state={state} />
              <span className="thread-body">
                <span className="thread-kind">{tool ? <code>{tool}</code> : kind.label}</span>
                <span className="thread-detail">{tool ? kind.label : e.detail}</span>
              </span>
            </button>
          </li>
        )
      })}
      {live && (
        <li className="thread-step is-live" aria-live="polite">
          <span className="thread-num" />
          <span className="thread-node node-dot is-live" aria-hidden="true" />
          <span className="thread-body"><span className="thread-kind">Investigating…</span></span>
        </li>
      )}
    </ol>
  )
}
