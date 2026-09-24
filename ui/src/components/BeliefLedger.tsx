/* How the probability was computed, line by line, and what happens without any of it.
 *
 * The agent does not assert a probability: it judges each finding, and the arithmetic is done in
 * code. That makes the whole thing reversible, so every line can be struck out and the posterior and
 * the recommendation recomputed exactly — no model call, no approximation.
 */
import { useEffect, useState } from 'react'
import type { Belief, LedgerItem } from '../api'

const BASIS: Record<string, string> = {
  flagged_transaction_model: 'the model score',
  holder_behaviour: "the holder's behaviour",
  device: 'the device',
  cross_card_links: 'links to other cards',
  prior_cases: 'prior cases',
  customer_statement: 'the customer',
  amount_or_timing: 'amount and timing',
  region: 'region',
}

interface Counterfactual {
  posterior: number
  verdict: string
  explanation: string
  actions: { action: string; route: string }[]
}

function Weight({ item }: { item: LedgerItem }) {
  if (item.as_prior) return <span className="lr-none">already the prior</span>
  if (!item.counted) return <span className="lr-none">corroborates</span>
  const up = item.lr > 1
  const shown = up ? item.lr : 1 / item.lr
  return (
    <span className={`lr num ${up ? 'lr-up' : 'lr-down'}`}>
      {up ? '×' : '÷'}{shown.toFixed(shown >= 10 ? 0 : 1)}
    </span>
  )
}

export function BeliefLedger({ belief, caseId, baselineActions }: {
  belief: Belief
  caseId: string
  baselineActions: string[]
}) {
  const [dropped, setDropped] = useState<Set<number>>(new Set())
  const [result, setResult] = useState<Counterfactual | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!dropped.size) { setResult(null); return }
    let cancelled = false
    setBusy(true)
    fetch(`/api/cases/${caseId}/counterfactual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dropped: [...dropped] }),
    })
      .then((r) => r.json())
      .then((r: Counterfactual) => { if (!cancelled) setResult(r) })
      .catch(() => { if (!cancelled) setResult(null) })
      .finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [dropped, caseId])

  const toggle = (i: number) => setDropped((prev) => {
    const next = new Set(prev)
    if (!next.delete(i)) next.add(i)
    return next
  })

  const now = result?.posterior ?? belief.posterior
  const actionsNow = result ? result.actions.map((a) => a.action) : baselineActions
  const changed = result && actionsNow.join() !== baselineActions.join()

  return (
    <div className="ledger">
      <p className="ledger-prior">
        Started at <strong className="num">{belief.prior.toFixed(2)}</strong> &mdash; {belief.prior_reason}.
        Then {belief.independent_evidence} independent {belief.independent_evidence === 1 ? 'line' : 'lines'} of
        evidence moved it.
      </p>

      <ul className="ledger-items">
        {belief.ledger.map((item, i) => {
          const off = dropped.has(i)
          return (
            <li key={i} className={`ledger-item dir-${item.direction}${off ? ' is-off' : ''}${item.counted ? '' : ' is-quiet'}`}>
              <label className="ledger-toggle">
                <input type="checkbox" checked={!off} onChange={() => toggle(i)}
                  aria-label={`Include: ${item.claim.slice(0, 80)}`} />
                <span className="ledger-basis">{BASIS[item.basis] ?? item.basis.replaceAll('_', ' ')}</span>
                <Weight item={item} />
              </label>
              <p className="ledger-claim">{item.claim}</p>
              {item.discounted && (
                <p className="ledger-note">
                  Halved: this rests on an entity a stronger finding already used, so it is not
                  independent of it.
                </p>
              )}
            </li>
          )
        })}
      </ul>

      <div className={`ledger-result${dropped.size ? ' is-counterfactual' : ''}`} aria-live="polite">
        {dropped.size === 0 ? (
          <p>Untick any line to see what the agent would have concluded without it.</p>
        ) : (
          <p>
            Without {dropped.size} {dropped.size === 1 ? 'line' : 'lines'}:{' '}
            <strong className="num">{belief.posterior.toFixed(2)}</strong> becomes{' '}
            <strong className="num">{busy ? '…' : now.toFixed(2)}</strong>
            {result && <> &mdash; {result.verdict}</>}
            {changed && <>, and the recommendation becomes <strong>{actionsNow.join(', ') || 'nothing'}</strong></>}
            {result && !changed && <>, and the recommendation does not change</>}.
          </p>
        )}
      </div>
    </div>
  )
}
