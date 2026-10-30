import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ActionItem, CaseAction, ChallengeRecord } from '../api'

/** Next best actions before and after the evidence request, and the approvals the agent cannot give. */

export const ACTION_NAME: Record<string, string> = {
  ALLOW_TRANSACTION: 'Allow the transaction', DECLINE_TRANSACTION: 'Decline the transaction',
  MONITOR_CARD: 'Monitor the card', MONITOR_CONNECTED_CARDS: 'Monitor connected cards',
  WARN_CUSTOMER: 'Warn the customer', VERIFY_WITH_CUSTOMER: 'Verify with the customer',
  STEP_UP_AUTH: 'Require step-up authentication', BLOCK_CARD: 'Block and reissue the card',
  BLOCK_ALL_CARDS: "Block all the customer's cards", GENERATE_REPORT: 'Write an internal report',
  CREATE_CASE: 'Open a fraud case', FILE_REPORT: 'File a suspicious activity report',
  ESCALATE_TO_ANALYST: 'Escalate to an analyst', CLOSE_NO_FRAUD: 'Close as legitimate',
}
const ROUTE_NAME = { auto: 'Agent may act', L1: 'Team lead approves', L2: 'Fraud manager approves' }

function Plan({ title, items }: { title: string; items: ActionItem[] }) {
  return (
    <div className="plan">
      <h3>{title}</h3>
      <ol>
        {items.map((a) => (
          <li key={a.action}>
            <span className="action-name">{ACTION_NAME[a.action] ?? a.action}</span>
            <span className={`route route-${a.route}`}>{ROUTE_NAME[a.route]}</span>
            <p className="action-reason">{a.reason}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}

const KEY_STORE = 'redthread.approverKey'

/** The approver key, kept for this browser session only. The server resolves it to a name and role. */
export function useApproverKey() {
  const [key, setKey] = useState(() => {
    try { return sessionStorage.getItem(KEY_STORE) ?? '' } catch { return '' }
  })
  const [who, setWho] = useState<{ name: string; role: string } | null>(null)
  useEffect(() => {
    if (!key) { setWho(null); return }
    api.whoami(key).then(setWho).catch(() => setWho(null))
  }, [key])
  useEffect(() => {  // every approval row on the page signs in and out together
    const sync = (e: Event) => setKey((e as CustomEvent<string>).detail)
    window.addEventListener(KEY_STORE, sync)
    return () => window.removeEventListener(KEY_STORE, sync)
  }, [])
  const save = (k: string) => {
    try { if (k) sessionStorage.setItem(KEY_STORE, k); else sessionStorage.removeItem(KEY_STORE) } catch { /* ok */ }
    window.dispatchEvent(new CustomEvent(KEY_STORE, { detail: k }))
  }
  return { key, who, save }
}

function Approval({ caseId, a, onDone }: { caseId: string; a: CaseAction; onDone: () => void }) {
  const { key, who, save } = useApproverKey()
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  if (a.route === 'auto') return <span className="state state-done">Done by the agent (simulated)</span>
  if (a.approval) {
    return <span className={`state state-${a.approval.decision}`}>
      {a.approval.decision === 'approved' ? 'Approved' : 'Rejected'} by {a.approval.approver} ({a.approval.role})
      {a.approval.in_graph ? ', recorded in the case in the graph' : ''}
    </span>
  }
  const decide = (decision: string) => {
    setError('')
    api.approve(caseId, key, { action: a.action, decision, note: '' })
      .then(onDone).catch((e: Error) => setError(e.message))
  }
  if (!who) {
    return (
      <div className="approve">
        <label>
          <span>Approver key</span>
          <input type="password" value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Paste your approver key" autoComplete="off" />
        </label>
        <button className="btn-approve" onClick={() => save(draft.trim())} disabled={!draft.trim()}>Sign in</button>
        {key && <p className="error" role="alert">That approver key is not recognised.</p>}
      </div>
    )
  }
  return (
    <div className="approve">
      <span className="approver-id">Signed in as <strong>{who.name}</strong> ({who.role})</span>
      <button className="btn-approve" onClick={() => decide('approved')}>Approve</button>
      <button className="btn-quiet" onClick={() => decide('rejected')}>Reject</button>
      <button className="btn-quiet" onClick={() => { save(''); setDraft('') }}>Sign out</button>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  )
}

export function Actions({ caseId, initial, final, whatChanged, actions, onChange }: {
  caseId: string; initial: ActionItem[]; final: ActionItem[]; whatChanged: string; actions: CaseAction[]
  onChange: () => void
}) {
  const changed = whatChanged !== 'nothing'
  return (
    <div className="actions">
      <div className={`plans${changed ? '' : ' is-single'}`}>
        {changed && <Plan title="Before the evidence came back" items={initial} />}
        <Plan title={changed ? 'After' : 'Recommended'} items={final} />
      </div>
      {changed && <p className="what-changed">{whatChanged}</p>}
      <h3>Approvals</h3>
      <ul className="approvals">
        {actions.map((a) => (
          <li key={a.action}>
            <span className="action-name">{ACTION_NAME[a.action] ?? a.action}</span>
            <Approval caseId={caseId} a={a} onDone={onChange} />
          </li>
        ))}
      </ul>
    </div>
  )
}

/* Disagreeing with the agent takes evidence. The server weighs the reason and the IDs it cites in the
 * case's own ledger; a claim the evidence does not support waits for a second, different L2 approver
 * and does not become memory until then. */
export function Challenges({ caseId, verdict }: { caseId: string; verdict: string }) {
  const { key, who } = useApproverKey()
  const [records, setRecords] = useState<ChallengeRecord[]>([])
  const [position, setPosition] = useState(verdict === 'fraud' ? 'legitimate' : 'fraud')
  const [reason, setReason] = useState('')
  const [ids, setIds] = useState('')
  const [error, setError] = useState('')
  const load = () => { api.challenges(caseId).then(setRecords).catch(() => setRecords([])) }
  useEffect(load, [caseId])
  const raised = records.filter((r) => !r.action.endsWith('-review'))
  const settled = new Map(records.filter((r) => r.action.endsWith('-review')).map((r) => [r.action.replace('-review', ''), r]))
  const submit = () => {
    setError('')
    api.challenge(caseId, key, { position, reason, evidence_ids: ids.split(/[\s,]+/).filter(Boolean) })
      .then(() => { setReason(''); setIds(''); load() }).catch((e: Error) => setError(e.message))
  }
  return (
    <div className="challenges">
      <h3>Disagree with this verdict</h3>
      <p className="hint">State why, and cite the transactions, cards or cases it rests on. One person&rsquo;s claim
        can settle a close call; against clear evidence it needs a second L2 approver.</p>
      {raised.map((r) => {
        const n = Number(r.action.split('-')[1])
        const review = settled.get(r.action)
        return (
          <div key={r.action} className={`challenge c-${r.evaluation.status}`}>
            <p><strong>{r.by}</strong> ({r.role}) says <strong>{r.position}</strong>: {r.reason}</p>
            <p className="hint">{r.evaluation.status}: {r.evaluation.why}
              {r.evaluation.ids_not_in_case.length ? `. Not in this case: ${r.evaluation.ids_not_in_case.join(', ')}` : ''}</p>
            {review && <p className="hint">{review.decision} by {review.by}: {review.reason}</p>}
            {r.evaluation.status === 'contested' && !review && who?.role === 'L2' && who.name !== r.by && (
              <Settle caseId={caseId} n={n} apiKey={key} onDone={load} />
            )}
          </div>
        )
      })}
      {who ? (
        <div className="challenge-form">
          <label><span>The case is</span>
            <select value={position} onChange={(e) => setPosition(e.target.value)}>
              {['fraud', 'legitimate'].filter((p) => p !== verdict).map((p) => <option key={p}>{p}</option>)}
            </select>
          </label>
          <label><span>Because</span>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3}
              placeholder="What you know, in facts an auditor could check" />
          </label>
          <label><span>It rests on</span>
            <input value={ids} onChange={(e) => setIds(e.target.value)} placeholder="e.g. 3660258, C12975-K2" />
          </label>
          <button className="btn-quiet" onClick={submit} disabled={reason.trim().split(/\s+/).length < 5}>Submit for weighing</button>
          {error && <p className="error" role="alert">{error}</p>}
        </div>
      ) : <p className="hint">Sign in with an approver key above to raise a challenge.</p>}
    </div>
  )
}

function Settle({ caseId, n, apiKey, onDone }: { caseId: string; n: number; apiKey: string; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const decide = (decision: string) => {
    setError('')
    api.settle(caseId, n, apiKey, { decision, reason }).then(onDone).catch((e: Error) => setError(e.message))
  }
  return (
    <div className="challenge-form">
      <label><span>Your reason, as the second approver</span>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
      </label>
      <button className="btn-quiet" onClick={() => decide('upheld')} disabled={!reason.trim()}>Uphold</button>
      <button className="btn-quiet" onClick={() => decide('overruled')} disabled={!reason.trim()}>Overrule</button>
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  )
}
