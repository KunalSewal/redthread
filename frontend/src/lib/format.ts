import type { Route, Verdict } from './api'

const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const usd2 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
const int = new Intl.NumberFormat('en-US')

export const money = (n: number | null | undefined, cents = false) =>
  n == null ? 'Not computed' : (cents ? usd2 : usd0).format(n)
export const count = (n: number | null | undefined) => (n == null ? 'Not computed' : int.format(n))
export const pct = (p: number | null | undefined, digits = 0) =>
  p == null ? 'Not computed' : `${(p * 100).toFixed(digits)}%`
export const prob = (p: number | null | undefined) => (p == null ? 'Not computed' : p.toFixed(2))

export function date(s: string | null | undefined) {
  if (!s) return ''
  const d = new Date(s.replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
export function dateTime(s: string | null | undefined) {
  if (!s) return ''
  const d = new Date(s.replace(' ', 'T'))
  return Number.isNaN(d.getTime())
    ? s
    : d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  fraud: 'Fraud',
  legitimate: 'Legitimate',
  uncertain: 'Uncertain',
}

const PATTERNS: Record<string, string> = {
  none: 'No fraud pattern',
  undocumented: 'Undocumented scheme',
  card_not_present_fraud: 'Card-not-present fraud',
  card_not_present_new_device: 'New device, card not present',
  card_testing: 'Card testing',
  account_takeover: 'Account takeover',
  out_of_region: 'Out-of-region use',
}
export const pattern = (p: string | null | undefined) =>
  !p ? 'Not classified' : (PATTERNS[p] ?? sentence(p.replaceAll('_', ' ')))

const TRIGGERS: Record<string, string> = {
  risk_score: 'Model score',
  customer_report: 'Customer report',
  analyst_request: 'Analyst request',
}
export const trigger = (t: string) => TRIGGERS[t] ?? sentence(t.replaceAll('_', ' '))

const SOURCES: Record<string, string> = {
  bank_queue: 'Bank queue',
  model_monitor: 'Raised by the agent: model sweep',
  ring_monitor: 'Raised by the agent: ring sweep',
}
export const source = (s: string) => SOURCES[s] ?? sentence(s.replaceAll('_', ' '))
export const isBankQueue = (s: string) => s === 'bank_queue'

const STATUSES: Record<string, string> = {
  escalated: 'Escalated',
  closed_fraud: 'Closed as fraud',
  closed_legitimate: 'Closed as legitimate',
  open: 'Open',
  new: 'Not investigated',
}
export const status = (s: string) => STATUSES[s] ?? sentence(s.replaceAll('_', ' '))

/** Policy action identifiers in plain words. The identifier itself stays visible where it matters. */
const ACTIONS: Record<string, string> = {
  ALLOW_TRANSACTION: 'Allow the transaction',
  DECLINE_TRANSACTION: 'Decline the transaction',
  BLOCK_CARD: 'Block the card',
  BLOCK_ALL_CARDS: "Block all the customer's cards",
  MONITOR_CARD: 'Monitor the card',
  MONITOR_CONNECTED_CARDS: 'Monitor connected cards',
  WARN_CUSTOMER: 'Warn the customer',
  VERIFY_WITH_CUSTOMER: 'Verify with the customer',
  STEP_UP_AUTH: 'Require step-up authentication',
  GENERATE_REPORT: 'Generate an internal report',
  FILE_REPORT: 'File a suspicious activity report',
  CREATE_CASE: 'Open a case',
  ESCALATE_TO_ANALYST: 'Escalate to an analyst',
  CLOSE_NO_FRAUD: 'Close as no fraud',
}
export const action = (a: string) => ACTIONS[a] ?? sentence(a.toLowerCase().replaceAll('_', ' '))

/** One analyst role; the policy's route becomes how much a decision asks of them. */
export function approvalLevel(route: Route) {
  if (route === 'auto') return { label: 'Done by the agent', needsReason: false }
  if (route === 'L1') return { label: 'Needs your approval', needsReason: false }
  return { label: 'Needs senior sign-off', needsReason: true }
}

const BASES: Record<string, string> = {
  holder_behaviour: 'Cardholder behaviour',
  device: 'Device',
  shared_origin: 'Shared origin',
  linked_cases: 'Linked cases',
  similar_cases: 'Similar past cases',
  community: 'Wider community',
  customer: 'Customer',
  model_score: 'Model score',
  scheme_peers: 'Other cards doing the same',
  activity_shift: 'New kind of activity',
  analyst_statement: 'Analyst statement',
  verification: 'Verification',
  cross_card_links: 'Links to other cards',
  amount_or_timing: 'Amount or timing',
  prior_cases: 'Past cases',
  flagged_transaction_model: 'Model score on the flagged charge',
  region: 'Region',
}
export const basis = (b: string) => BASES[b] ?? sentence(b.replaceAll('_', ' '))

export function sentence(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
