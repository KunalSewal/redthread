import { useState } from 'react'
import { api } from '../api'
import type { ActionItem, CaseAction } from '../api'

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

function Approval({ caseId, a, onDone }: { caseId: string; a: CaseAction; onDone: () => void }) {
  const [role, setRole] = useState<'L1' | 'L2'>(a.route === 'L2' ? 'L2' : 'L1')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  if (a.route === 'auto') return <span className="state state-done">Done by the agent (simulated)</span>
  if (a.approval) {
    return <span className={`state state-${a.approval.decision}`}>
      {a.approval.decision === 'approved' ? 'Approved' : 'Rejected'} by {a.approval.approver} ({a.approval.role})
    </span>
  }
  const decide = (decision: string) => {
    setError('')
    api.approve(caseId, { action: a.action, decision, approver: name || 'Analyst', role, note: '' })
      .then(onDone).catch((e: Error) => setError(e.message))
  }
  return (
    <div className="approve">
      <label>
        <span>Your role</span>
        <select value={role} onChange={(e) => setRole(e.target.value as 'L1' | 'L2')}>
          <option value="L1">Team lead (L1)</option>
          <option value="L2">Fraud manager (L2)</option>
        </select>
      </label>
      <label>
        <span>Name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
      </label>
      <button className="btn-approve" onClick={() => decide('approved')}>Approve</button>
      <button className="btn-quiet" onClick={() => decide('rejected')}>Reject</button>
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
