/* One card, or an organised group?
 *
 * Two different questions, two different algorithms. A ring is the tight core: cards joined by one
 * specific device that was new to each account in a suspicious transaction, found by connected
 * components. A community is the looser crowd a card moves with, found by Louvain over the whole
 * card-device graph. The ring is the evidence; the community is the neighbourhood.
 */
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Ring, Rings as RingsData } from '../api'
import { Link, useRouter } from '../router'

function RingDetail({ ring }: { ring: Ring }) {
  const members = ring.members ?? []
  const withFraud = members.filter((m) => m.confirmed_fraud_closed_cases.length)
  return (
    <div className="ring-detail">
      <h3>Ring {ring.ring_id}</h3>
      <p className="prose">
        <strong className="num">{ring.cards}</strong> cards joined by{' '}
        {ring.devices.length === 1 ? 'one device' : `${ring.devices.length} devices`}.{' '}
        <strong className="num">{withFraud.length}</strong> of them already carry a confirmed-fraud case.
      </p>
      {ring.device_profiles?.length ? (
        <ul className="device-list">
          {ring.device_profiles.map((d) => (
            <li key={d.device_id}>
              <strong>{d.device_id}</strong>
              <span className="device-profile">{d.profile}</span>
              <span className="num">{d.n_cards} cards all time</span>
            </li>
          ))}
        </ul>
      ) : null}
      <table className="digest-table">
        <thead>
          <tr><th>Card</th><th className="col-num">Transactions</th><th className="col-num">Top model score</th><th>Confirmed cases</th></tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.card_id} className={m.confirmed_fraud_closed_cases.length ? 'is-hot' : undefined}>
              <td className="num">{m.card_id}</td>
              <td className="col-num num">{m.txns}</td>
              <td className="col-num num">{m.max_model_score?.toFixed(3) ?? '—'}</td>
              <td>{m.confirmed_fraud_closed_cases.join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Rings({ ringId }: { ringId?: string }) {
  const { navigate } = useRouter()
  const [data, setData] = useState<RingsData | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { api.rings().then(setData).catch((e: Error) => setError(e.message)) }, [])

  if (error) return <main className="page"><p className="error" role="alert">{error}</p></main>
  if (!data) return <main className="page"><p className="empty">Loading…</p></main>

  const selected = ringId
    ? data.rings.find((r) => String(r.ring_id) === ringId)
    : data.rings.find((r) => r.members?.length)

  return (
    <main className="page rings-page" aria-labelledby="rings-title">
      <header className="page-head">
        <h2 id="rings-title">Rings and communities</h2>
        <p className="prose">
          Connected components over suspicious, new-to-account device use in the July&ndash;October
          history found <strong className="num">{data.rings.length}</strong> tight rings &mdash; built from
          that history alone, so no November or December alert leans on a ring that formed after it.
          Louvain over the whole
          card-device graph sorted <strong className="num">{data.communities_total?.toLocaleString()}</strong>{' '}
          communities, of which <strong className="num">{data.communities_ranked}</strong> hold five cards
          or more. The rings are what the agent cites as evidence; the communities are the wider
          neighbourhood, and on their own only weak evidence.
        </p>
      </header>

      <div className="rings-layout">
        <nav className="ring-list" aria-label="Rings">
          <h3>Rings</h3>
          <ul>
            {data.rings.map((r) => (
              <li key={r.ring_id}>
                <button
                  className={`ring-hit${selected?.ring_id === r.ring_id ? ' is-selected' : ''}`}
                  onClick={() => navigate(`/rings/${r.ring_id}`)}
                  aria-current={selected?.ring_id === r.ring_id}
                >
                  <span className="num">Ring {r.ring_id}</span>
                  <span className="ring-size num">{r.cards} cards</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <div className="ring-main">
          {selected ? <RingDetail ring={selected} /> : <p className="empty">Choose a ring.</p>}

          <section aria-labelledby="communities-title" className="communities">
            <h3 id="communities-title">Communities with the most known-bad cards</h3>
            <table className="digest-table">
              <thead>
                <tr><th>Community</th><th className="col-num">Cards</th><th className="col-num">With confirmed fraud</th><th className="col-num">Share</th></tr>
              </thead>
              <tbody>
                {data.communities.map((c) => (
                  <tr key={c.community}>
                    <td className="num">{c.community}</td>
                    <td className="col-num num">{c.cards}</td>
                    <td className="col-num num">{c.fraud_cards}</td>
                    <td className="col-num num">{(c.fraud_share * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="hint">
              About 10% of all cards carry a confirmed-fraud case, so these are well above the base
              rate &mdash; but see <Link to="/trust">what that is worth</Link> before treating it as proof.
            </p>
          </section>
        </div>
      </div>
    </main>
  )
}
