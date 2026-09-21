/* What continuous monitoring adds over the bank's queue.
 *
 * Each row here is a transaction the bank's threshold let through. The bank's own score sits next to
 * the agent's verdict, because the gap between them is the entire argument for running the agent
 * between alerts rather than only on them.
 */
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Monitoring } from '../api'
import { Link } from '../router'
import { PATTERN } from './CaseFile'

const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const SOURCE: Record<string, string> = {
  ring_monitor: 'Ring sweep', model_monitor: 'Score sweep', agent_monitor: 'Monitor',
}

export function Missed() {
  const [data, setData] = useState<Monitoring | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { api.monitoring().then(setData).catch((e: Error) => setError(e.message)) }, [])

  if (error) return <main className="page"><p className="error" role="alert">{error}</p></main>
  if (!data) return <main className="page"><p className="empty">Loading…</p></main>

  const lowScored = data.alerts.filter((a) => (a.bank_risk_score ?? 1) < 0.3).length

  return (
    <main className="page" aria-labelledby="missed-title">
      <header className="page-head">
        <h2 id="missed-title">What the queue missed</h2>
        <p className="prose">
          Between the alerts it was handed, the agent swept the graph for cards using a known ring&rsquo;s
          device and for transactions the bank&rsquo;s threshold let through. It raised{' '}
          <strong className="num">{data.raised}</strong> cases of its own, called fraud in{' '}
          <strong className="num">{data.confirmed_fraud}</strong> of them, worth{' '}
          <strong className="num">{usd(data.exposure_usd)}</strong> of exposure nobody had queued, and
          left the rest uncertain for a person to look at.
        </p>
      </header>

      <table className="missed-table">
        <thead>
          <tr>
            <th>Case</th><th>Found by</th><th>Card</th>
            <th className="col-num">Bank&rsquo;s score</th><th>Agent&rsquo;s verdict</th>
            <th>Pattern</th><th className="col-num">Exposure</th>
          </tr>
        </thead>
        <tbody>
          {data.alerts.map((a) => (
            <tr key={a.case_id}>
              <td><Link to={`/case/${a.case_id}`}>{a.case_id}</Link></td>
              <td>{SOURCE[a.source] ?? a.source}</td>
              <td className="num">{a.card_id}</td>
              <td className="col-num num">{a.bank_risk_score?.toFixed(2) ?? '—'}</td>
              <td><span className={`verdict-chip v-${a.verdict}`}>{a.verdict}</span></td>
              <td>{PATTERN[a.pattern ?? ''] ?? a.pattern}</td>
              <td className="col-num num">{a.exposure_usd ? usd(a.exposure_usd) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="hint">
        None of these were in the queue the bank handed over. {lowScored} of {data.raised} were scored
        below 0.30 by the bank and let through, and the graph still had enough to act on. The cases
        left uncertain are not failures: policy escalates those to an analyst rather than guessing.
      </p>
    </main>
  )
}
