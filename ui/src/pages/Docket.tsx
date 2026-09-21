/* The docket: what is in front of the team this morning.
 *
 * The bank's queue and the agent's own alerts are kept apart, because "we investigated the twenty we
 * were given" and "we found six nobody asked us to look at" are different claims.
 */
import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import type { CaseRow } from '../api'
import { Link } from '../router'
import { PATTERN } from './CaseFile'

const TRIGGER: Record<string, string> = {
  risk_score: 'Model alert', customer_report: 'Customer report', analyst_request: 'Analyst request',
}
const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

function Row({ r }: { r: CaseRow }) {
  return (
    <li className="docket-row">
      <Link to={`/case/${r.case_id}`} className="docket-hit">
        <span className="docket-id">{r.case_id}</span>
        <span className="docket-trigger">{TRIGGER[r.trigger_type] ?? r.trigger_type}</span>
        <span className="docket-card num">{r.card_id}</span>
        {r.verdict ? (
          <>
            <span className={`verdict-chip v-${r.verdict}`}>
              {r.verdict === 'uncertain' && <span className="chip-glyph" aria-hidden="true">?</span>}
              {r.verdict}
            </span>
            <span className="docket-p num">{r.fraud_probability?.toFixed(2)}</span>
            <span className="docket-pattern">{PATTERN[r.pattern ?? ''] ?? r.pattern}</span>
            <span className="docket-exposure num">{r.exposure_usd ? usd(r.exposure_usd) : ''}</span>
          </>
        ) : (
          <span className="verdict-chip v-new">not investigated</span>
        )}
        {!!r.pending_approvals && <span className="docket-pending">{r.pending_approvals} to approve</span>}
      </Link>
    </li>
  )
}

function Group({ title, note, rows }: { title: string; note: string; rows: CaseRow[] }) {
  const fraud = rows.filter((r) => r.verdict === 'fraud').length
  const exposure = rows.reduce((s, r) => s + (r.exposure_usd ?? 0), 0)
  return (
    <section className="docket-group" aria-labelledby={`g-${title}`}>
      <header className="docket-group-head">
        <h3 id={`g-${title}`}>{title}</h3>
        <p className="hint">{note}</p>
        <p className="docket-tally num">
          {rows.length} alerts &nbsp;·&nbsp; {fraud} fraud &nbsp;·&nbsp; {usd(exposure)} exposure
        </p>
      </header>
      <ul className="docket-list">{rows.map((r) => <Row key={r.case_id} r={r} />)}</ul>
    </section>
  )
}

export function Docket() {
  const [rows, setRows] = useState<CaseRow[]>([])
  const [error, setError] = useState('')
  useEffect(() => { api.cases().then(setRows).catch((e: Error) => setError(e.message)) }, [])

  const [queued, raised] = useMemo(() => [
    rows.filter((r) => r.source === 'bank_queue'),
    rows.filter((r) => r.source !== 'bank_queue'),
  ], [rows])

  if (error) {
    return (
      <main className="page">
        <p className="error" role="alert">
          Cannot reach the RedThread API: {error}. Start it with{' '}
          <code>uvicorn redthread.api.app:app --port 8000</code>.
        </p>
      </main>
    )
  }

  return (
    <main className="page" aria-labelledby="docket-title">
      <h2 id="docket-title" className="visually-hidden">Docket</h2>
      <Group title="The bank's queue" rows={queued}
        note="The twenty alerts the benchmark hands over." />
      {raised.length > 0 && (
        <Group title="Raised by the agent" rows={raised}
          note="Nobody asked for these. The monitors found them between alerts." />
      )}
    </main>
  )
}
