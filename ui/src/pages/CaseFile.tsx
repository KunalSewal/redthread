/* One case, rewindable.
 *
 * The thread on the left is the control: every panel here reads the step it points at. That is why
 * there are no tabs — the same case file tells the whole story as you walk it, which is also what
 * makes it demonstrable in one continuous move.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { CaseDetail, Event } from '../api'
import { Actions } from '../components/Actions'
import { Boundary } from '../components/Boundary'
import { BeliefLedger } from '../components/BeliefLedger'
import { BeliefScale } from '../components/BeliefScale'
import { EvidenceDigest } from '../components/EvidenceDigest'
import { EvidenceGraph } from '../components/EvidenceGraph'
import { Thread, toolName } from '../components/Thread'
import { useRouter } from '../router'

const TRIGGER: Record<string, string> = {
  risk_score: 'Model alert', customer_report: 'Customer report', analyst_request: 'Analyst request',
}
const VERDICT: Record<string, string> = { fraud: 'Fraud', legitimate: 'Legitimate', uncertain: 'Uncertain' }
export const PATTERN: Record<string, string> = {
  card_testing: 'Card testing', card_not_present_fraud: 'Card not present',
  card_not_present_new_device: 'Card not present, new device', out_of_region_use: 'Out-of-region use',
  account_takeover: 'Account takeover', undocumented: 'New pattern', none: 'No fraud',
}
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

/** The step at which each landmark happened, so panels know what was true when. */
function landmarks(events: Event[]) {
  const at = (kind: string) => {
    const e = events.find((x) => x.kind === kind)
    return e ? Number(e.step) : null
  }
  return { assessed: at('assessment'), recommended: at('recommendation'), replied: at('reply'), decided: at('decision') }
}

/** The evidence digest produced at this step, if this step was a query. */
function digestAt(detail: CaseDetail, step: number): [string, Record<string, unknown>] | null {
  const event = detail.events.find((e) => Number(e.step) === step)
  if (!event || event.kind !== 'evidence') return null
  const hit = Object.entries(detail.evidence).find(([, v]) =>
    v && typeof v === 'object' && (v as { ref?: string }).ref === event.detail)
  if (hit) return hit as [string, Record<string, unknown>]
  const name = toolName(event.detail)
  return name ? [name, { ref: event.detail }] : null
}

export function CaseFile({ id }: { id: string }) {
  const { query, navigate } = useRouter()
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [liveEvents, setLiveEvents] = useState<Event[] | null>(null)
  const [step, setStep] = useState<number | null>(null)
  const [error, setError] = useState('')
  const replay = query.get('replay') === '1'
  const timer = useRef<number | null>(null)

  const load = useCallback(() => api.case(id).then((d) => {
    setDetail(d)
    setStep(null)
  }).catch((e: Error) => setError(e.message)), [id])

  useEffect(() => { setDetail(null); setLiveEvents(null); setError(''); load() }, [load])

  // Presenter mode: push the stored trace through the same views at a readable pace. This is the
  // real trace, not a mock, so the demo can be recorded with the workspace suspended.
  useEffect(() => {
    if (!replay || !detail?.events.length) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) { setStep(Number(detail.events.at(-1)!.step)); return }
    let i = 0
    setStep(Number(detail.events[0].step))
    timer.current = window.setInterval(() => {
      i += 1
      if (i >= detail.events.length) {
        if (timer.current) window.clearInterval(timer.current)
        return
      }
      setStep(Number(detail.events[i].step))
    }, 400)
    return () => { if (timer.current) window.clearInterval(timer.current) }
  }, [replay, detail])

  const investigate = () => {
    setError('')
    setLiveEvents([])
    api.investigate(id).then(() => {
      const source = new EventSource(`/api/cases/${id}/stream`)
      source.onmessage = (m) => {
        const e = JSON.parse(m.data)
        if (e.kind === 'done' || e.kind === 'failed') {
          source.close()
          if (e.kind === 'failed') setError(`The investigation stopped: ${e.detail}`)
          setLiveEvents(null)
          load()
          return
        }
        setLiveEvents((prev) => [...(prev ?? []), e])
      }
      source.onerror = () => { source.close(); setLiveEvents(null); load() }
    }).catch((e: Error) => { setError(e.message); setLiveEvents(null) })
  }

  const live = liveEvents !== null
  const events = live ? (liveEvents ?? []) : (detail?.events ?? [])
  const marks = landmarks(events)  // a scan of a few dozen events; memoising it would cost more
  const lastStep = events.length ? Number(events.at(-1)!.step) : 0
  const current = live ? lastStep : (step ?? lastStep)
  const rewound = !live && step !== null && step < lastStep

  if (!detail) {
    return (
      <main className="case-shell">
        <p className="empty">{error || 'Opening the case file…'}</p>
      </main>
    )
  }

  const { alert, answer, belief } = detail
  const c = answer?.case
  const digest = digestAt(detail, current)

  // What belief was, as of this step: nothing before the assessment, the posterior after it, and the
  // revised one once the customer replied. Never interpolated between.
  const beliefNow = marks.assessed === null || current < marks.assessed
    ? null
    : (marks.replied !== null && current >= marks.replied && detail.reply?.posterior != null
      // after the reply, the case's final probability (floored like every other) is the one to show
      ? c?.fraud_probability ?? detail.reply.posterior
      : belief?.posterior ?? c?.fraud_probability ?? null)
  const previous = marks.replied !== null && current >= marks.replied ? belief?.posterior ?? null : null
  const showFinal = marks.decided === null || current >= marks.decided
  const plan = showFinal ? answer?.next_best_actions.final : answer?.next_best_actions.initial

  return (
    <main className="case-shell" aria-labelledby="case-title">
      <div className="case-sheet">
        <header className="case-head">
          <div>
            <h2 id="case-title">{alert.case_id}</h2>
            <p className="case-meta">
              {TRIGGER[alert.trigger_type]} &nbsp;·&nbsp; {alert.opened_at} &nbsp;·&nbsp; card {alert.card_id}
              {alert.source !== 'bank_queue' && <span className="tag tag-raised">the agent raised this itself</span>}
            </p>
          </div>
          <div className="case-tools">
            {!live && answer && (
              <button className="btn-quiet" onClick={() => navigate(`/case/${id}?replay=1`)}>Replay</button>
            )}
            <button className="btn-primary" onClick={investigate} disabled={live}>
              {live ? 'Investigating…' : answer ? 'Investigate again' : 'Investigate'}
            </button>
          </div>
        </header>

        <blockquote className="trigger prose">{alert.trigger_text}</blockquote>
        {error && <p className="error" role="alert">{error}</p>}

        {c && (
          <section className="verdict" aria-label="Conclusion">
            <div className="verdict-line">
              <span className={`verdict-word v-${c.verdict}`}>{VERDICT[c.verdict]}</span>
              <span>{PATTERN[c.pattern] ?? c.pattern}</span>
              {c.exposure_usd > 0 && <span className="num">{usd(c.exposure_usd)} exposure</span>}
              {answer?.sar.file && <span className="tag tag-sar">Report filed</span>}
            </div>
            <BeliefScale value={beliefNow} previous={previous} bankScore={alert.risk_score} />
            {rewound && <p className="rewound-note">Showing the case as it stood at step {current}.</p>}
            <p className="prose">{c.summary}</p>
          </section>
        )}

        <div className="case-columns">
          <section className="case-thread" aria-labelledby="thread-title">
            <h3 id="thread-title">How it got here</h3>
            <p className="hint">Use the arrow keys to walk the investigation back.</p>
            <Thread events={events} step={current} onStep={setStep} live={live} />
          </section>

          <div className="case-panels">
            <section aria-labelledby="graph-title">
              <h3 id="graph-title">In the graph</h3>
              <Boundary label="The evidence graph">
                <EvidenceGraph nodes={detail.graph.nodes} edges={detail.graph.edges} step={current} />
              </Boundary>
            </section>

            <section aria-labelledby="digest-title">
              <h3 id="digest-title">What this step found</h3>
              <Boundary label="This step's result">
                {digest
                  ? <EvidenceDigest name={digest[0]} digest={digest[1]} />
                  : <p className="empty">This step was reasoning, not a query.</p>}
              </Boundary>
            </section>
          </div>
        </div>

        {belief && (
          <section aria-labelledby="ledger-title">
            <h3 id="ledger-title">Why the probability is what it is</h3>
            <Boundary label="The belief ledger">
              <BeliefLedger belief={belief} caseId={id}
                baselineActions={(answer?.next_best_actions.final ?? []).map((a) => a.action)} />
            </Boundary>
          </section>
        )}

        {c && c.evidence.length > 0 && (
          <section aria-labelledby="evidence-title">
            <h3 id="evidence-title">Evidence on the record</h3>
            <ul className="evidence">
              {c.evidence.map((e, i) => (
                <li key={i}>
                  <p className="prose">{e.claim}</p>
                  <span className={`source source-${e.source}`}>{e.source}</span>
                  <code className="ref">{e.ref}</code>
                </li>
              ))}
            </ul>
          </section>
        )}

        {answer?.sar.file && (
          <section className="sar" aria-labelledby="sar-title">
            <h3 id="sar-title">Suspicious activity report</h3>
            <p className="sar-meta num">
              {usd(answer.sar.total_amount_usd)}, {answer.sar.activity_dates.join(' to ')}.
              Subjects: {answer.sar.subjects.join(', ')}
            </p>
            <p className="prose">{answer.sar.narrative}</p>
          </section>
        )}

        {answer && plan && (
          <section aria-labelledby="actions-title">
            <h3 id="actions-title">Next best actions</h3>
            <Actions caseId={id} initial={answer.next_best_actions.initial}
              final={showFinal ? answer.next_best_actions.final : answer.next_best_actions.initial}
              whatChanged={showFinal ? answer.next_best_actions.what_changed : 'nothing'}
              actions={detail.actions} onChange={load} />
          </section>
        )}

        {answer && (
          <p className="stats num">
            {answer.tool_calls} graph and retrieval calls &nbsp;·&nbsp; {answer.tokens.toLocaleString()} tokens
            &nbsp;·&nbsp; {answer.latency_s}s. <span className="stats-reason">{answer.stop_reason}</span>
          </p>
        )}
      </div>
    </main>
  )
}
