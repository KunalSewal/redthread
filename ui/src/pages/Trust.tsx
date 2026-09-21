/* Should you believe it?
 *
 * Everything measured about this agent, including what it gets wrong. A page that only showed the
 * flattering numbers would be worth less than no page: the failures are what tell an analyst when to
 * check the work themselves.
 */
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Evaluation } from '../api'

const pct = (n: unknown) => (typeof n === 'number' ? `${(n * 100).toFixed(0)}%` : '—')

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="stat">
      <dt>{label}</dt>
      <dd className="num">{value}</dd>
      {note && <p className="stat-note">{note}</p>}
    </div>
  )
}

function Backtest({ b }: { b: Record<string, unknown> }) {
  const byTrigger = (b.accuracy_by_trigger ?? {}) as Record<string, number>
  const counts = (b.n_by_trigger ?? {}) as Record<string, number>
  return (
    <>
      <dl className="stats-grid">
        <Stat label="Verdict accuracy" value={pct(b.verdict_accuracy)} note={`on ${String(b.n)} replayed closed cases`} />
        <Stat label="Fraud caught" value={pct(b.fraud_recall)} />
        <Stat label="Cleared cases left alone" value={pct(b.cleared_accuracy)} />
        <Stat label="Calibration (Brier)" value={typeof b.brier === 'number' ? b.brier.toFixed(3) : '—'}
          note="lower is better; 0.25 is a coin flip" />
        <Stat label="Pattern accuracy" value={pct(b.pattern_accuracy_on_fraud)} />
        <Stat label="Agreement on filing" value={pct(b.sar_agreement)} />
      </dl>
      {Object.keys(byTrigger).length > 1 && (
        <div className="trigger-check">
          <h4>Is it reading the trigger instead of investigating?</h4>
          <p className="prose">
            Each replayed alert is given a customer report or a model score at random, independently of
            how the case actually ended. If the agent were leaning on the trigger rather than the
            evidence, these two numbers would pull apart.
          </p>
          <dl className="stats-grid">
            {Object.entries(byTrigger).map(([t, v]) => (
              <Stat key={t} label={t === 'customer_report' ? 'Arrived as a customer report' : 'Arrived as a model alert'}
                value={pct(v)} note={`${counts[t] ?? 0} cases`} />
            ))}
          </dl>
        </div>
      )}
    </>
  )
}

export function Trust() {
  const [data, setData] = useState<Evaluation | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { api.evaluation().then(setData).catch((e: Error) => setError(e.message)) }, [])

  if (error) return <main className="page"><p className="error" role="alert">{error}</p></main>
  if (!data) return <main className="page"><p className="empty">Loading…</p></main>

  const patterns = (data.patterns ?? {}) as Record<string, unknown>
  const perPattern = (patterns.per_pattern ?? patterns.by_pattern ?? {}) as Record<string, Record<string, unknown>>
  const lift = data.community_lift

  return (
    <main className="page" aria-labelledby="trust-title">
      <header className="page-head">
        <h2 id="trust-title">Should you believe it</h2>
        <p className="prose">
          The benchmark&rsquo;s answer key is hidden, so accuracy is measured by replaying closed cases the
          bank&rsquo;s analysts already decided, with point-in-time retrieval so the agent cannot see its own
          answer or anything that happened later.
        </p>
      </header>

      <section aria-labelledby="bt-title">
        <h3 id="bt-title">Replayed closed cases</h3>
        {data.backtest
          ? <Backtest b={data.backtest} />
          : <p className="empty">No backtest has been run yet.</p>}
      </section>

      {Object.keys(perPattern).length > 0 && (
        <section aria-labelledby="pat-title">
          <h3 id="pat-title">Naming the pattern, including where it fails</h3>
          <p className="prose">
            Patterns are named by a deterministic classifier, not the model, and it is measured
            against every confirmed-fraud case the bank&rsquo;s analysts labelled &mdash; thousands of them,
            rather than the handful in the replay above. It is strong on the four common patterns and
            genuinely bad at two: card testing is rare and easily confused with small legitimate
            purchases, and &ldquo;undocumented&rdquo; means a pattern nobody has written down yet.
          </p>
          <table className="digest-table">
            <thead><tr><th>Pattern</th><th className="col-num">Recall</th><th className="col-num">Cases</th></tr></thead>
            <tbody>
              {Object.entries(perPattern).map(([name, v]) => {
                const recall = Number((v as Record<string, unknown>).recall ?? v)
                return (
                  <tr key={name} className={recall < 0.5 ? 'is-poor' : undefined}>
                    <td>{name.replaceAll('_', ' ')}</td>
                    <td className="col-num num">{Number.isFinite(recall) ? recall.toFixed(3) : '—'}</td>
                    <td className="col-num num">{String((v as Record<string, unknown>).n ?? '')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <p className="hint">Rows in orange are where this agent is weakest. They are here on purpose.</p>
        </section>
      )}

      {lift && (
        <section aria-labelledby="lift-title">
          <h3 id="lift-title">What a bad neighbourhood is actually worth</h3>
          <p className="prose">
            A card&rsquo;s Louvain community can look damning: a third of its cards carrying confirmed fraud
            against a base rate of one in ten. Measured against{' '}
            <span className="num">{lift.n_fraud + lift.n_cleared}</span> closed cases, it is weak
            evidence, and the agent is told to treat it that way.
          </p>
          <table className="digest-table">
            <thead>
              <tr><th>Community lift</th><th className="col-num">If fraud</th><th className="col-num">If cleared</th><th className="col-num">Likelihood ratio</th></tr>
            </thead>
            <tbody>
              {Object.entries(lift.bands).map(([band, v]) => (
                <tr key={band}>
                  <td>{band}</td>
                  <td className="col-num num">{pct(v.p_fraud)}</td>
                  <td className="col-num num">{pct(v.p_cleared)}</td>
                  <td className="col-num num">{v.lr?.toFixed(2) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">
            A likelihood ratio near 1 means the finding barely moves belief. An earlier version of this
            measurement looked three times stronger, because it quietly dropped the cards that sit alone.
          </p>
        </section>
      )}
    </main>
  )
}
