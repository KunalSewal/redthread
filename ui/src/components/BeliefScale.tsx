/* Where belief stands, on the scale the policy actually uses.
 *
 * Belief is known at three points and no others: the first assessment, and the prior and posterior
 * around the customer's reply. Between them we have no measurement, so the scale says so instead of
 * drawing a line through points that were never computed.
 */

const FRAUD_AT = 0.85
const LEGIT_AT = 0.15

const pct = (n: number) => `${(n * 100).toFixed(0)}%`

export function BeliefScale({ value, bankScore, previous, label }: {
  /** null until the agent has weighed anything. */
  value: number | null
  bankScore?: number | null
  /** Where belief stood before the customer replied, if it has moved. */
  previous?: number | null
  label?: string
}) {
  const band = value === null ? 'none' : value >= FRAUD_AT ? 'fraud' : value <= LEGIT_AT ? 'legitimate' : 'uncertain'

  return (
    <figure className="scale" aria-label={label ?? 'Fraud probability'}>
      <div className={`scale-track band-${band}`}>
        <span className="scale-zone zone-legit" style={{ width: pct(LEGIT_AT) }} />
        <span className="scale-zone zone-fraud" style={{ width: pct(1 - FRAUD_AT), left: pct(FRAUD_AT) }} />
        {bankScore != null && (
          <span className="scale-bank" style={{ left: pct(bankScore) }}>
            <span className="visually-hidden">The bank&rsquo;s legacy risk score, {bankScore.toFixed(2)}</span>
          </span>
        )}
        {previous != null && value != null && Math.abs(previous - value) > 0.005 && (
          <span className="scale-move" style={{
            left: pct(Math.min(previous, value)),
            width: pct(Math.abs(previous - value)),
          }} />
        )}
        {value === null ? (
          <span className="scale-unknown">no estimate yet</span>
        ) : (
          <span className={`scale-head band-${band}`} style={{ left: pct(value) }}>
            <span className="scale-value num">{value.toFixed(2)}</span>
          </span>
        )}
      </div>
      <figcaption className="scale-legend">
        <span className="scale-tick" style={{ left: 0 }}>legitimate</span>
        <span className="scale-tick" style={{ left: pct((LEGIT_AT + FRAUD_AT) / 2), transform: 'translateX(-50%)' }}>
          uncertain
        </span>
        <span className="scale-tick" style={{ right: 0 }}>fraud</span>
      </figcaption>
      {bankScore != null && (
        <p className="scale-note">
          The bank&rsquo;s legacy score put this at <strong className="num">{bankScore.toFixed(2)}</strong>.
        </p>
      )}
    </figure>
  )
}
