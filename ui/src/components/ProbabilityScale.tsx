/** Fraud probability on the policy's own scale: where the estimate started, where evidence moved it,
 * and the thresholds that decide what the bank may do. */

const THRESHOLDS = [
  { at: 0.15, label: 'Close as legitimate' },
  { at: 0.3, label: 'Open a case' },
  { at: 0.7, label: 'Block on one signal' },
  { at: 0.85, label: 'Decisive' },
]

interface Props {
  initial: number
  final: number
  bankScore: number | null
}

export function ProbabilityScale({ initial, final, bankScore }: Props) {
  const W = 640, H = 92, pad = 16, top = 30, bar = 10
  const x = (p: number) => pad + p * (W - 2 * pad)
  const moved = Math.abs(final - initial) >= 0.01
  const tone = final >= 0.85 ? 'var(--thread)' : final <= 0.15 ? 'var(--cleared)' : 'var(--unresolved)'
  return (
    <figure className="scale">
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Fraud probability ${moved ? `moved from ${initial.toFixed(2)} to ` : ''}${final.toFixed(2)}`}>
        <rect x={x(0)} y={top} width={x(0.15) - x(0)} height={bar} fill="var(--cleared-soft)" />
        <rect x={x(0.15)} y={top} width={x(0.85) - x(0.15)} height={bar} fill="var(--wash)" />
        <rect x={x(0.85)} y={top} width={x(1) - x(0.85)} height={bar} fill="var(--thread-soft)" />
        {THRESHOLDS.map((t) => (
          <g key={t.at}>
            <line x1={x(t.at)} x2={x(t.at)} y1={top - 4} y2={top + bar + 4} stroke="var(--graphite)" strokeWidth={1} />
            <text x={x(t.at)} y={top + bar + 18} textAnchor="middle" className="scale-tick">{t.at.toFixed(2)}</text>
          </g>
        ))}
        {bankScore !== null && (
          <g>
            <path d={`M${x(bankScore)} ${top - 2} l-4 -7 h8 z`} fill="var(--graphite)" />
            <text x={x(bankScore)} y={top - 13} textAnchor="middle" className="scale-note">bank score {bankScore.toFixed(2)}</text>
          </g>
        )}
        {moved && (
          <>
            <line x1={x(initial)} x2={x(final)} y1={top + bar / 2} y2={top + bar / 2} stroke={tone} strokeWidth={2} />
            <circle cx={x(initial)} cy={top + bar / 2} r={6} fill="var(--sheet)" stroke={tone} strokeWidth={2} />
          </>
        )}
        <circle cx={x(final)} cy={top + bar / 2} r={7} fill={tone} />
      </svg>
      <figcaption>
        <span className="scale-value" style={{ color: tone }}>{final.toFixed(2)}</span>
        {moved ? <span>after the evidence request, up from {initial.toFixed(2)}</span>
          : <span>no further evidence needed</span>}
        <span className="scale-legend">{THRESHOLDS.map((t) => `${t.at.toFixed(2)} ${t.label.toLowerCase()}`).join(', ')}</span>
      </figcaption>
    </figure>
  )
}
