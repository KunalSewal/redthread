import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { CaseDetail, CaseRow, Event } from './api'
import { Actions } from './components/Actions'
import { EvidenceGraph } from './components/EvidenceGraph'
import { ProbabilityScale } from './components/ProbabilityScale'
import { Thread } from './components/Thread'
import './app.css'

const TRIGGER = { risk_score: 'Model alert', customer_report: 'Customer report', analyst_request: 'Analyst request' }
const VERDICT = { fraud: 'Fraud', legitimate: 'Legitimate', uncertain: 'Uncertain' }
const PATTERN: Record<string, string> = {
  card_testing: 'Card testing', card_not_present_fraud: 'Card not present', card_not_present_new_device:
    'Card not present, new device', out_of_region_use: 'Out-of-region use', account_takeover: 'Account takeover',
  undocumented: 'New pattern', none: 'No fraud',
}
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

function Queue({ rows, selected, onSelect }: { rows: CaseRow[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <nav className="queue" aria-label="Alert queue">
      <header className="brand">
        <svg width="28" height="20" viewBox="0 0 28 20" aria-hidden="true">
          <path d="M1 16 C7 -2, 13 22, 27 4" stroke="var(--thread)" strokeWidth="2.2" fill="none" />
        </svg>
        <h1>RedThread</h1>
      </header>
      <p className="queue-count">{rows.filter((r) => r.status !== 'new').length} of {rows.length} alerts investigated</p>
      <ul>
        {rows.map((r) => (
          <li key={r.case_id}>
            <button className={`queue-row${r.case_id === selected ? ' is-selected' : ''}`} onClick={() => onSelect(r.case_id)}
              aria-current={r.case_id === selected}>
              <span className="queue-id">{r.case_id}</span>
              <span className="queue-trigger">{TRIGGER[r.trigger_type]}</span>
              {r.verdict ? (
                <span className={`queue-verdict v-${r.verdict}`}>
                  {VERDICT[r.verdict]} <span className="queue-p">{r.fraud_probability?.toFixed(2)}</span>
                </span>
              ) : <span className="queue-verdict v-new">Not investigated</span>}
              {!!r.pending_approvals && <span className="queue-pending">{r.pending_approvals} to approve</span>}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  )
}

function CaseFile({ id, onChanged }: { id: string; onChanged: () => void }) {
  const [detail, setDetail] = useState<CaseDetail | null>(null)
  const [liveEvents, setLiveEvents] = useState<Event[] | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => api.case(id).then(setDetail).catch((e: Error) => setError(e.message)), [id])
  useEffect(() => { setDetail(null); setLiveEvents(null); setError(''); load() }, [load])

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
          load(); onChanged()
          return
        }
        setLiveEvents((prev) => [...(prev ?? []), e])
      }
      source.onerror = () => { source.close(); setLiveEvents(null); load() }
    }).catch((e: Error) => { setError(e.message); setLiveEvents(null) })
  }

  if (!detail) return <main className="case"><p className="empty">{error || 'Opening the case file…'}</p></main>
  const { alert, answer } = detail
  const c = answer?.case
  const live = liveEvents !== null
  const events = live ? liveEvents : detail.events
  const initialP = detail.assessment?.fraud_probability ?? c?.fraud_probability ?? 0

  return (
    <>
      <main className="case" aria-labelledby="case-title">
        <header className="case-head">
          <div className="case-ids">
            <h2 id="case-title">{alert.case_id}</h2>
            <span>{TRIGGER[alert.trigger_type]}, {alert.opened_at}</span>
            <span>Card {alert.card_id}, transaction {alert.flagged_txn_id}</span>
          </div>
          <button className="btn-primary" onClick={investigate} disabled={live}>
            {live ? 'Investigating…' : answer ? 'Investigate again' : 'Investigate'}
          </button>
        </header>
        <blockquote className="trigger">{alert.trigger_text}</blockquote>
        {error && <p className="error" role="alert">{error}</p>}

        {c && !live && (
          <section className="verdict" aria-label="Verdict">
            <div className="verdict-line">
              <span className={`verdict-word v-${c.verdict}`}>{VERDICT[c.verdict]}</span>
              <span className="verdict-pattern">{PATTERN[c.pattern] ?? c.pattern}</span>
              <span className="verdict-exposure">{usd(c.exposure_usd)} exposure</span>
              {answer.sar.file && <span className="verdict-sar">Report filed</span>}
            </div>
            <ProbabilityScale initial={initialP} final={c.fraud_probability} bankScore={alert.risk_score} />
            <p className="summary">{c.summary}</p>
            {c.pattern_description && <p className="summary pattern-description">{c.pattern_description}</p>}
          </section>
        )}

        <section aria-labelledby="thread-title">
          <h3 id="thread-title">How the agent got here</h3>
          <Thread events={events} live={live} />
        </section>

        {c && !live && (
          <>
            <section aria-labelledby="evidence-title">
              <h3 id="evidence-title">Evidence</h3>
              <ul className="evidence">
                {c.evidence.map((e, i) => (
                  <li key={i}>
                    <p>{e.claim}</p>
                    <span className={`source source-${e.source}`}>{e.source}</span>
                    <code className="ref">{e.ref}</code>
                  </li>
                ))}
              </ul>
              {detail.assessment?.uncertainty && (
                <p className="uncertainty"><strong>Still uncertain:</strong> {detail.assessment.uncertainty}</p>
              )}
            </section>
            {answer.sar.file && (
              <section aria-labelledby="sar-title" className="sar">
                <h3 id="sar-title">Suspicious activity report</h3>
                <p className="sar-meta">{usd(answer.sar.total_amount_usd)}, {answer.sar.activity_dates.join(' to ')}.
                  Subjects: {answer.sar.subjects.join(', ')}</p>
                <p className="sar-narrative">{answer.sar.narrative}</p>
              </section>
            )}
            <p className="stats">{answer.tool_calls} graph and retrieval calls, {answer.tokens.toLocaleString()} tokens,
              {' '}{answer.latency_s}s. {answer.stop_reason}</p>
          </>
        )}
      </main>

      <aside className="side" aria-label="Graph and actions">
        <section aria-labelledby="graph-title">
          <h3 id="graph-title">In the graph</h3>
          <EvidenceGraph nodes={detail.graph.nodes} edges={detail.graph.edges} />
        </section>
        {answer && !live && (
          <section aria-labelledby="actions-title">
            <h3 id="actions-title">Next best actions</h3>
            <Actions caseId={id} initial={answer.next_best_actions.initial} final={answer.next_best_actions.final}
              whatChanged={answer.next_best_actions.what_changed} actions={detail.actions}
              onChange={() => { load(); onChanged() }} />
          </section>
        )}
      </aside>
    </>
  )
}

export default function App() {
  const [rows, setRows] = useState<CaseRow[]>([])
  const [selected, setSelected] = useState<string | null>(() => new URLSearchParams(location.search).get('case'))
  const [error, setError] = useState('')
  const refresh = useCallback(() => api.cases().then(setRows).catch((e: Error) => setError(e.message)), [])
  useEffect(() => { refresh() }, [refresh])
  useEffect(() => { if (!selected && rows.length) setSelected(rows[0].case_id) }, [rows, selected])
  const select = (id: string) => { setSelected(id); history.replaceState(null, '', `?case=${id}`) }

  return (
    <div className="shell">
      <Queue rows={rows} selected={selected} onSelect={select} />
      {error && <p className="error" role="alert">Cannot reach the RedThread API: {error}. Start it with uvicorn.</p>}
      {selected && <CaseFile key={selected} id={selected} onChanged={refresh} />}
    </div>
  )
}
