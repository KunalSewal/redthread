/* The regulator's view: one investigation, one step at a time.
 *
 * Built for someone who did not run the case and has five minutes to challenge it. Each step shows
 * the query that ran and its parameters, what came back, the evidence the agent held at that moment
 * (and nothing it collected later), and where the probability stood. Steps where the conclusion
 * moved say from what to what, and why.
 */
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Replay, ReplayStep } from '../api'
import { Link } from '../router'

const pct = (p: number | null | undefined) => (p == null ? 'not yet assessed' : `${Math.round(p * 100)}%`)

export function Audit({ id }: { id: string }) {
  const [data, setData] = useState<Replay | null>(null)
  const [error, setError] = useState('')
  const [at, setAt] = useState(0)
  useEffect(() => { api.replay(id).then((r) => { setData(r); setAt(0) }).catch((e: Error) => setError(e.message)) }, [id])

  if (error) return <main className="page"><p className="error" role="alert">{error}</p></main>
  if (!data) return <main className="page"><p className="empty">Loading…</p></main>
  const steps = data.steps
  const s: ReplayStep | undefined = steps[at]
  const moves = steps.filter((x) => x.moved)

  return (
    <main className="page audit" aria-labelledby="audit-title">
      <header className="page-head">
        <h2 id="audit-title">Audit view: {data.case_id}</h2>
        <p className="prose">
          {steps.length} recorded steps. The conclusion moved {moves.length === 1 ? 'once' : `${moves.length} times`}
          {data.final && <> and ended at <strong>{data.final.verdict}</strong>, {pct(data.final.probability)}</>}.
          {' '}<Link to={`/case/${id}`}>Open the case file</Link>.
        </p>
      </header>

      <div className="audit-controls">
        <button className="btn-quiet" onClick={() => setAt(Math.max(0, at - 1))} disabled={at === 0}>Previous step</button>
        <label className="audit-slider">
          <span>Step {s?.step} of {steps.length}</span>
          <input type="range" min={0} max={steps.length - 1} value={at}
                 onChange={(e) => setAt(Number(e.target.value))} aria-label="Step" />
        </label>
        <button className="btn-quiet" onClick={() => setAt(Math.min(steps.length - 1, at + 1))}
                disabled={at === steps.length - 1}>Next step</button>
        {moves.map((m) => (
          <button key={m.step} className="btn-quiet" onClick={() => setAt(steps.indexOf(m))}>
            Jump to step {m.step}: {pct(m.moved!.from)} to {pct(m.moved!.to)}
          </button>
        ))}
      </div>

      {s && (
        <div className="audit-grid">
          <section aria-label="This step" className="audit-step">
            <p className="audit-kind">{s.kind}{s.at ? <span className="num"> · {s.at}</span> : null}</p>
            <p className="prose">{s.detail}</p>
            {s.query && (
              <dl className="audit-dl">
                <dt>Query</dt><dd className="num">{s.query}</dd>
                <dt>Parameters</dt><dd className="num">{s.parameters}</dd>
              </dl>
            )}
            {s.returned && (
              <>
                <h3>What came back</h3>
                <dl className="audit-dl">
                  {Object.entries(s.returned).map(([k, v]) => (
                    <div key={k} className="audit-row"><dt>{k}</dt><dd className="num">{
                      typeof v === 'object' ? JSON.stringify(v).slice(0, 400) : String(v)}</dd></div>
                  ))}
                </dl>
              </>
            )}
            {s.moved && (
              <div className="audit-moved" role="note">
                <strong>Conclusion moved from {pct(s.moved.from)} to {pct(s.moved.to)}.</strong> {s.moved.because}
              </div>
            )}
            {s.belief && (
              <>
                <h3>How the probability was reached</h3>
                <p className="prose">Started at {pct(s.belief.prior)}: {s.belief.prior_reason}.</p>
                <table className="audit-ledger">
                  <thead><tr><th>Rests on</th><th>Points</th><th>Strength</th><th className="col-num">Odds ×</th><th>Finding</th></tr></thead>
                  <tbody>
                    {s.belief.counted.map((l, i) => (
                      <tr key={i}><td>{l.basis.replace(/_/g, ' ')}</td><td>{l.direction}</td><td>{l.strength}</td>
                        <td className="col-num num">{l.lr.toFixed(2)}</td><td>{l.claim}</td></tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>
          <aside aria-label="What the agent held at this step" className="audit-held">
            <h3>Held at this step</h3>
            <p className="audit-prob">Probability: <strong className="num">{pct(s.probability)}</strong></p>
            {s.evidence_held.length === 0
              ? <p className="empty">No evidence yet.</p>
              : <ol className="audit-refs">{s.evidence_held.map((r) => <li key={r} className="num">{r.replace(/^query:/, '')}</li>)}</ol>}
            {data.quarantined.length > 0 && (
              <>
                <h3>Set aside as instructions to the system</h3>
                <ul className="audit-refs">{data.quarantined.map((q, i) => <li key={i}>{q.text}</li>)}</ul>
              </>
            )}
          </aside>
        </div>
      )}
    </main>
  )
}
