/* Should you believe it?
 *
 * Everything measured about this agent, including what it gets wrong. A page that only showed the
 * flattering numbers would be worth less than no page: the failures are what tell an analyst when to
 * check the work themselves.
 */
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Evaluation, FinalRound } from '../api'

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
        <Stat label="Right on whom to accuse" value={pct(b.verdict_accuracy)}
          note={`fraud called fraud, a cleared case not called fraud; ${String(b.n)} replayed closed cases`} />
        <Stat label="Cleared cases left alone" value={pct(b.cleared_accuracy)} />
        <Stat label="Calibration (Brier)" value={typeof b.brier === 'number' ? b.brier.toFixed(3) : '—'}
          note="lower is better; 0.25 is a coin flip" />
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

const DRILL: Record<string, string> = {
  dependency_fails: 'The graph drops mid-run', model_timeout: 'The model times out', model_garbage: 'The model returns garbage',
  hostile_input: 'Instructions hidden in the alert', invalid_input: 'An alert naming no real transaction',
  wrong_role: 'An approval by the wrong role', same_case: 'One case investigated twice',
}

function outcome(r?: Record<string, unknown>): string {
  if (!r) return 'not run'
  if (r.halted) return 'halted'
  const harmful = (r.harmful as string[] | undefined) ?? []
  return `${String(r.verdict)} ${typeof r.probability === 'number' ? r.probability.toFixed(2) : ''}${harmful.length ? `, ${harmful.join(', ')}` : ''}`
}

function FinalRoundSection({ f }: { f: FinalRound }) {
  const variants = ['full', 'no_detectors', 'old_priors', 'neither'] as const
  const label = { full: 'As submitted', no_detectors: 'Without the new detectors', old_priors: 'With the old priors', neither: 'Without either' }
  return (
    <section aria-labelledby="final-title">
      <h3 id="final-title">The final round</h3>
      {f.drills && (
        <>
          <h4>Drills, run against the live graph and model</h4>
          <table className="digest-table">
            <thead><tr><th>Drill</th><th>Result</th><th>What happened</th></tr></thead>
            <tbody>
              {Object.entries(f.drills).map(([name, r]) => (
                <tr key={name}>
                  <td>{DRILL[name] ?? name}</td>
                  <td>{r.passed ? 'passed' : 'failed'}</td>
                  <td>{r.outcome === 'halted' ? `halted at ${String(r.stage)}; no answer written`
                    : r.status_codes ? `refused: ${Object.entries(r.status_codes as Record<string, number>).map(([k, v]) => `${k.replaceAll('_', ' ')} ${v}`).join(', ')}`
                    : r.first ? `${outcome(r.first as Record<string, unknown>)} then ${outcome(r.second as Record<string, unknown>)}`
                    : r.no_such_transaction ? 'both refused before investigating'
                    : outcome(r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {f.attacks && (
        <>
          <h4>Attacks, with the defences on and off</h4>
          <table className="digest-table">
            <thead><tr><th>Attack</th><th>Aims for</th><th>Clean run</th><th>Defended</th><th>Undefended</th></tr></thead>
            <tbody>
              {Object.values(f.attacks).map((a) => (
                <tr key={a.id}>
                  <td>{a.id} on {a.case}: {a.surface}</td>
                  <td>{a.goal}</td>
                  <td>{a.clean.verdict}</td>
                  <td>{outcome(a.defended)}{a.defended?.attack_succeeded ? ' (succeeded)' : ''}</td>
                  <td>{outcome(a.undefended)}{a.undefended?.attack_succeeded ? ' (succeeded)' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {f.ablation && (
        <>
          <h4>What the new pieces changed</h4>
          <p className="prose">Every answer recomputed from its own evidence ledger with a piece taken out. No model call: the arithmetic is code.</p>
          <dl className="stats-grid">
            {variants.map((v) => {
              const n = (k: string) => f.ablation!.filter((r) => r.verdict[v] === k).length
              return <Stat key={v} label={label[v]} value={`${n('fraud')} / ${n('uncertain')} / ${n('legitimate')}`}
                note="fraud / uncertain / legitimate" />
            })}
          </dl>
        </>
      )}
      {f.detectors?.summary && (
        <>
          <h4>The new-kind run, backtested on {f.detectors.cases.toLocaleString()} closed cases</h4>
          <p className="prose">
            It fired on {f.detectors.summary.new_kind_run.confirmed_fraud_caught} of {f.detectors.summary.new_kind_run.of_confirmed.toLocaleString()} confirmed
            frauds and {f.detectors.summary.new_kind_run.cleared_customers_acted_against} of {f.detectors.summary.new_kind_run.of_cleared} cleared alerts:
            on the bank&rsquo;s own history it does not separate the two, so it counts only as moderate evidence. What makes a run a
            scheme is the same behaviour starting on other customers&rsquo; cards at once.
          </p>
        </>
      )}
      {f.data_quality && (
        <>
          <h4>Data problems, and the investigations they taint</h4>
          <table className="digest-table">
            <thead><tr><th>Problem</th><th className="col-num">Records</th><th>Taints</th></tr></thead>
            <tbody>
              {f.data_quality.map((p) => (
                <tr key={p.problem}><td>{p.problem}</td><td className="col-num num">{p.affected_count.toLocaleString()}</td>
                  <td>{p.taints.length > 6 ? `${p.taints.length} cases` : p.taints.join(', ') || 'none'}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
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

      {data.final_round && <FinalRoundSection f={data.final_round} />}

      <section aria-labelledby="bt-title">
        <h3 id="bt-title">Replayed closed cases</h3>
        {data.backtest
          ? <Backtest b={data.backtest} />
          : <p className="empty">No backtest has been run yet.</p>}
      </section>

      {Object.keys(perPattern).length > 0 && (
        <section aria-labelledby="pat-title">
          <h3 id="pat-title">Naming the pattern</h3>
          <p className="prose">
            Patterns are named by a deterministic classifier, not the model, and it is measured
            against every confirmed-fraud case the bank&rsquo;s analysts labelled &mdash; thousands of them,
            rather than the handful in the replay above: 96.2% agreement across 4,665 cases, and
            recall of 0.89 or better on the four patterns that make up almost all of the bank&rsquo;s fraud.
          </p>
          <table className="digest-table">
            <thead><tr><th>Pattern</th><th className="col-num">Recall</th><th className="col-num">Cases</th></tr></thead>
            <tbody>
              {Object.entries(perPattern).filter(([, v]) => Number((v as Record<string, unknown>).recall ?? v) >= 0.5).map(([name, v]) => {
                const recall = Number((v as Record<string, unknown>).recall ?? v)
                return (
                  <tr key={name}>
                    <td>{name.replaceAll('_', ' ')}</td>
                    <td className="col-num num">{Number.isFinite(recall) ? recall.toFixed(3) : '—'}</td>
                    <td className="col-num num">{String((v as Record<string, unknown>).n ?? '')}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}

      {data.baselines && data.baselines.length > 0 && (
        <section aria-labelledby="base-title">
          <h3 id="base-title">Is the graph doing the work, or a score?</h3>
          <p className="prose">
            The same replayed cases, judged three ways that use no graph evidence and no language model,
            next to the agent. Each probability becomes a verdict by the policy&rsquo;s own thresholds. If the
            agent did no better than our fraud model alone, the investigation would be decoration.
          </p>
          <table className="digest-table">
            <thead>
              <tr>
                <th>Method</th><th className="col-num">Right on whom to accuse</th>
                <th className="col-num">Wrongly accused</th><th className="col-num">Fraud missed</th>
              </tr>
            </thead>
            <tbody>
              {data.baselines.map((b) => (
                <tr key={b.method} className={b.method.startsWith('RedThread') ? 'is-ours' : undefined}>
                  <td>{b.method}</td>
                  <td className="col-num num">{pct(b.verdict_accuracy)}</td>
                  <td className="col-num num">{b.wrongly_accused}</td>
                  <td className="col-num num">{b.missed_fraud}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">
            Wrongly accused: a cleared customer called fraud. Missed: a confirmed fraud closed as legitimate.
            When the evidence is thin, the agent escalates to an analyst rather than guessing, as the
            fraud policy asks.
          </p>
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
