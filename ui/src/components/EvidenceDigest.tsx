/* What a single graph query actually returned.
 *
 * The agent reasons over digests, not raw rows, so this shows the same digest an analyst would need
 * to check its work. Each tool gets a renderer that answers the question that tool was asked;
 * anything without one falls back to a readable key/value list rather than a wall of JSON.
 */
import type { ReactNode } from 'react'

type Digest = Record<string, unknown>

const usd = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const num = (v: unknown) => (typeof v === 'number' ? v : Number(v))

/** Renders whatever a tool gave us: a count map, a list, or a scalar. */
function List({ value, limit = 4 }: { value: unknown; limit?: number }) {
  if (Array.isArray(value)) return <>{value.slice(0, limit).join(', ') || '—'}</>
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, limit)
      .map(([k, n]) => `${k} (${n})`)
    return <>{entries.join(', ') || '—'}</>
  }
  return <>{value == null || value === '' ? '—' : String(value)}</>
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function Txns({ rows, limit = 8 }: { rows: Digest[]; limit?: number }) {
  if (!rows?.length) return <p className="empty">No transactions in this window.</p>
  return (
    <table className="digest-table">
      <thead>
        <tr><th>When</th><th>Amount</th><th>Where</th><th>Model</th></tr>
      </thead>
      <tbody>
        {rows.slice(0, limit).map((r, i) => (
          <tr key={i} className={num(r.model_score) >= 0.5 ? 'is-hot' : undefined}>
            <td className="num">{String(r.ts ?? '').slice(0, 16)}</td>
            <td className="num">{usd(num(r.amount))}</td>
            <td>{String(r.channel ?? '')}{r.region ? `, region ${r.region}` : ''}</td>
            <td className="num">{r.model_score == null ? '—' : num(r.model_score).toFixed(3)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Passages({ d }: { d: Digest }) {
  const passages = (d.passages ?? []) as Digest[]
  if (!passages.length) return <p className="empty">Nothing retrieved.</p>
  return (
    <ul className="passages">
      {passages.map((p, i) => (
        <li key={i}>
          <h5>{String(p.section)}</h5>
          <p className="prose passage-text">{String(p.text ?? p.content ?? '')}</p>
          <span className={`authority authority-${p.authority}`}>
            {p.authority === 'regulator' ? 'External authority' : "The bank's own policy"} &middot; {String(p.source)}
          </span>
        </li>
      ))}
    </ul>
  )
}

const RENDERERS: Record<string, (d: Digest) => ReactNode> = {
  alert_context: (d) => {
    const f = (d.flagged_txn ?? {}) as Digest
    const holder = d.holder as Digest | undefined
    return (
      <dl className="facts">
        <Fact label="Flagged">{usd(num(f.amount))}, {String(f.channel)}, {String(f.ts).slice(0, 16)}</Fact>
        <Fact label="Model score"><span className="num">{num(f.model_score).toFixed(3)}</span></Fact>
        <Fact label="Device status">{String(f.device_status ?? 'unknown')}{f.proxy ? `, ${f.proxy}` : ''}</Fact>
        {holder && <Fact label="Account holder">{String(holder.holder_id)}, {String(holder.n_txns)} transactions</Fact>}
        <Fact label="Other cards in this issuer bucket">{(d.customer_cards as string[])?.length ?? 0}</Fact>
      </dl>
    )
  },
  card_activity: (d) => (
    <>
      <dl className="facts">
        <Fact label="Window">{(d.window as string[])?.join(' to ')}</Fact>
        <Fact label="Transactions"><span className="num">{String(d.n_txns)}</span></Fact>
        <Fact label="Card-testing sequences">
          <span className="num">{(d.card_testing_sequences as unknown[])?.length ?? 0}</span>
        </Fact>
      </dl>
      <Txns rows={(d.rows ?? []) as Digest[]} />
    </>
  ),
  holder_baseline: (d) => (
    <dl className="facts">
      <Fact label="Prior transactions"><span className="num">{String(d.prior_txns)}</span></Fact>
      <Fact label="Typical amount"><span className="num">{usd(num(d.amount_mean))}</span></Fact>
      <Fact label="Regions"><List value={d.regions} /></Fact>
      <Fact label="Channels"><List value={d.channels} /></Fact>
      <Fact label="New for this holder">{d.flagged_is_new_for_holder ? 'yes' : 'no'}</Fact>
      <Fact label="Recurring pattern">
        {(d.recurring_pattern as { recurring?: boolean; reason?: string })?.recurring
          ? 'yes'
          : (d.recurring_pattern as { reason?: string })?.reason ?? 'none found'}
      </Fact>
      <Fact label="Prior transactions in confirmed fraud">
        <span className="num">{String(d.holder_prior_txns_in_confirmed_fraud_cases ?? 0)}</span>
      </Fact>
    </dl>
  ),
  community: (d) => (
    <>
      <dl className="facts">
        <Fact label="Community"><span className="num">{String(d.community_id)}</span></Fact>
        <Fact label="Cards in it"><span className="num">{String(d.cards_in_community)}</span></Fact>
        <Fact label="With confirmed fraud">
          <span className="num">{String(d.cards_with_confirmed_fraud)}</span>
        </Fact>
        <Fact label="Against the base rate">
          <span className="num">{(num(d.fraud_rate_in_community) * 100).toFixed(0)}%</span> here against{' '}
          <span className="num">{(num(d.fraud_rate_all_cards) * 100).toFixed(0)}%</span> across all cards
          {d.lift_vs_base_rate ? <> &mdash; a lift of <span className="num">{String(d.lift_vs_base_rate)}</span></> : null}
        </Fact>
      </dl>
      <p className="digest-note">{String(d.definition)}</p>
    </>
  ),
  ring: (d) => (
    <>
      <dl className="facts">
        <Fact label="Ring"><span className="num">{String(d.ring_id)}</span></Fact>
        <Fact label="Members"><span className="num">{(d.members as unknown[])?.length ?? 0}</span></Fact>
      </dl>
      <p className="digest-note">{String(d.definition)}</p>
      <ul className="chiplist">
        {((d.members ?? []) as Digest[]).slice(0, 12).map((m, i) => (
          <li key={i} className={(m.confirmed_fraud_closed_cases as string[])?.length ? 'is-fraud' : undefined}>
            {String(m.card_id)}
          </li>
        ))}
      </ul>
    </>
  ),
  linked_cases: (d) => {
    const closed = (d.closed_cases ?? []) as Digest[]
    if (!closed.length) return <p className="empty">Nothing in the graph links this alert to another case.</p>
    return (
      <ul className="caselist">
        {closed.slice(0, 8).map((c, i) => (
          <li key={i}>
            <span className={`outcome outcome-${c.outcome}`}>{String(c.outcome).replaceAll('_', ' ')}</span>
            <strong>{String(c.case_id)}</strong>
            <span>{String(c.pattern ?? '').replaceAll('_', ' ')}</span>
            {c.via ? <span className="via">via {String(c.via)}</span> : null}
          </li>
        ))}
      </ul>
    )
  },
  policy: (d) => <Passages d={d} />,
}
RENDERERS.similar_cases = RENDERERS.linked_cases
RENDERERS.policy_rule = RENDERERS.policy
RENDERERS.regulatory_redflags = RENDERERS.policy

function Fallback({ d }: { d: Digest }) {
  const entries = Object.entries(d).filter(([k, v]) => k !== 'ref' && v != null)
  return (
    <dl className="facts">
      {entries.slice(0, 10).map(([k, v]) => (
        <Fact key={k} label={k.replaceAll('_', ' ')}>
          {Array.isArray(v) ? `${v.length} item${v.length === 1 ? '' : 's'}` : <List value={v} />}
        </Fact>
      ))}
    </dl>
  )
}

/** The tool a digest key came from: 'policy:{"question":…}' and 'policy_rule:R7' are both policy. */
export function digestTool(key: string): string {
  return key.split(':')[0]
}

export function EvidenceDigest({ name, digest }: { name: string; digest: Digest }) {
  const render = RENDERERS[digestTool(name)]
  return (
    <div className="digest">
      <header className="digest-head">
        <code>{String(digest.ref ?? name)}</code>
      </header>
      {render ? render(digest) : <Fallback d={digest} />}
    </div>
  )
}
