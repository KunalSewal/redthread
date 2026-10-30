/* The backend contract. Shapes follow redthread/api/app.py; the backend is the source of truth, so a
 * change here should come from a change there. Every call goes through `api`. */

export type Verdict = 'fraud' | 'legitimate' | 'uncertain'
export type Route = 'auto' | 'L1' | 'L2'

export interface CaseRow {
  case_id: string
  opened_at: string
  trigger_type: 'risk_score' | 'customer_report' | 'analyst_request'
  trigger_text: string
  card_id: string
  customer_id: string
  flagged_txn_id: string
  risk_score: number | null
  /** 'bank_queue' for the graded alerts; a monitor name for the ones the agent raised itself. */
  source: string
  status: string
  verdict?: Verdict
  fraud_probability?: number
  pattern?: string
  exposure_usd?: number
  sar?: boolean
  pending_approvals?: number
}

export interface ActionItem { action: string; route: Route; reason: string }
export interface Approval { decision: string; approver: string; role: string; note: string; at: string; in_graph?: boolean }
export interface CaseAction extends ActionItem { state: string; approval?: Approval | null }
export interface Evidence { claim: string; source: string; ref: string; entity_ids: string[] }
export interface CaseEvent { step: number; kind: string; detail: string; at: string; case_id?: string }

export interface GraphNode {
  id: string; kind: string; label: string; step: number
  role?: string; outcome?: string; pattern?: string; profile?: string; score?: number | null
}
export interface GraphEdge { source: string; target: string; kind: string; step: number }

/** One line of the belief ledger: what it rests on, which way it points, and what it was worth. */
export interface LedgerItem {
  basis: string
  direction: 'incriminating' | 'exculpatory'
  strength: 'weak' | 'moderate' | 'strong' | 'decisive'
  claim: string
  counted: boolean
  /** The likelihood ratio actually applied, after independence and correlation rules. */
  lr: number
  discounted?: boolean
  /** Not counted because the same fact already set the prior (the model score, or the denial). */
  as_prior?: boolean
  uninformative?: boolean
  entities?: string[]
}

export interface Belief {
  prior: number
  prior_reason: string
  posterior: number
  verdict: Verdict
  independent_evidence: number
  explanation: string
  ledger: LedgerItem[]
}

export interface Answer {
  case_id: string
  case: {
    status: string; verdict: Verdict; fraud_probability: number; pattern: string; pattern_description: string
    affected_txn_ids: string[]; first_suspicious_txn_id: string; connected_card_ids: string[]
    connected_device_profiles: string[]; exposure_usd: number; evidence: Evidence[]; similar_prior_cases: string[]
    summary: string; written_to_graph: boolean; graph_case_id: string
  }
  evidence_requests: { type: string; asked_after_step: number; assumed_response: string }[]
  next_best_actions: { initial: ActionItem[]; final: ActionItem[]; what_changed: string }
  sar: { file: boolean; reason: string; narrative: string; subjects: string[]; total_amount_usd: number; activity_dates: string[] }
  stop_reason: string
  tool_calls: number
  tokens: number
  latency_s: number
}

/** What the January detectors found: the charges the card had never made before. */
export interface ActivityShift {
  ref: string; card_id: string; baseline_txns: number; baseline_kinds: Record<string, number>
  recent_txns: number; flagged_in_run: boolean; run_total_usd: number; signature: string
  run: { tx_id: string; ts: string; amount: number; product: string; channel: string }[]
}
/** Other customers' cards that started the same thing in the same 30 days, against two earlier windows. */
export interface SchemePeers {
  ref: string; signature: string; strength: string; other_customers: number
  other_cards_now: number; other_cards_month_before: number; other_cards_two_months_before: number
  peers: { card_id: string; customer_id: string; n_txns: number; amount: number; first_ts: string; last_ts: string }[]
}

export interface CaseDetail {
  alert: CaseRow
  answer: Answer | null
  events: CaseEvent[]
  /** Tool digests keyed by tool name, or 'tool:{args}' for follow-ups. */
  evidence: Record<string, Record<string, unknown>>
  assessment: { evidence: Evidence[]; uncertainty?: string; reasoning?: string } | null
  belief: Belief | null
  request: { type: string; question: string; asked_after_step: number } | null
  reply: { text: string; prior?: number; posterior?: number } | null
  report: { summary: string; what_changed: string; stop_reason: string; sar_narrative: string } | null
  actions: CaseAction[]
  handover: Handover | null
  graph: { nodes: GraphNode[]; edges: GraphEdge[]; steps: number }
}

/** The January detectors' digests, when this case ran them. */
export function schemeEvidence(d: CaseDetail) {
  const shift = d.evidence.activity_shift as unknown as ActivityShift | undefined
  const peers = d.evidence.scheme_peers as unknown as SchemePeers | undefined
  return { shift: shift?.run?.length ? shift : undefined, peers }
}

export interface Handover {
  status: string; verdict: string; probability: number; pattern: string; exposure_usd: number; summary: string
  open_question: string; in_graph: string | null; next_step: string
  done: { action: string; by: string; decision?: string; at?: string }[]
  waiting: { action: string; needs: string; why: string }[]
  contested_challenges: { challenge: string; by: string; position: string; why: string }[]
  last_activity: { step: number; kind: string; detail: string; at: string } | null
}

export interface ReplayStep {
  step: number; at?: string; kind: string; detail: string
  tool?: string; query?: string; parameters?: string; returned?: Record<string, unknown>
  evidence_held: string[]; probability: number | null
  moved?: { from: number | null; to: number; because: string }
}
export interface Replay {
  case_id: string; steps: ReplayStep[]
  quarantined: { kind: string; text: string; at?: string }[]
  final: { verdict: string; probability: number; pattern: string } | null
}

export interface ChallengeRecord {
  case_id: string; action: string; position: string; reason: string; evidence_ids?: string[]
  by: string; role: string; at: string; decision?: string; in_graph: boolean
  evaluation: { status: string; why: string; probability_before: number | null; probability_after: number | null
    strength: string; ids_in_case: string[]; ids_not_in_case: string[] }
}

export interface Counterfactual {
  posterior: number; verdict: Verdict; prior: number; independent_evidence: number; explanation: string
  actions: ActionItem[]
  ledger: { basis: string; counted: boolean; lr: number; discounted: boolean; claim: string }[]
}

export interface Overview {
  cases: number; alerts: number; by_verdict: Record<string, number>; by_pattern: Record<string, number>
  exposure_usd: number; sars: number; pending_approvals: number
  model: { n: number; auc_model: number; auc_bank_risk_score: number } | null
}

export interface MonitoringAlert {
  case_id: string; source: string; opened_at: string; card_id: string; flagged_txn_id: string
  bank_risk_score: number | null; trigger_text: string
  verdict?: Verdict; pattern?: string; exposure_usd?: number; sar?: boolean
}
export interface Monitoring {
  alerts: MonitoringAlert[]; raised: number; confirmed_fraud: number; exposure_usd: number; by_source: Record<string, number>
}

export interface RingMember {
  card_id: string; txns: number; max_model_score: number | null
  confirmed_fraud_closed_cases: string[]; agent_cases: string[]
}
export interface Ring {
  ring_id: number; cards: number; devices: string[]
  members?: RingMember[]
  device_profiles?: { device_id: string; profile: string; n_cards: number }[]
}
export interface Rings {
  rings: Ring[]
  communities: { community: number; cards: number; fraud_cards: number; fraud_share: number }[]
  communities_total: number
  communities_ranked: number
}

export interface PlanAction { kind: string; target: string; cuts_usd: number; touches: string[] }
export interface PlanSummary {
  actions: PlanAction[]; exposure_total_usd: number; exposure_cut_usd: number; exposure_left_usd: number
  customers_touched: string[]; expected_cut_usd: number; expected_legitimate_customers_touched: number
  penalty_usd_per_customer: number; net_expected_usd: number; method: string
}
export interface ContainmentPlan {
  ring: string; shared: string[]; cards: string[]; established?: string[]; found_in: string; transactions: number
  plan: PlanSummary; block_every_card: PlanSummary; monitor: string[]
  other_people_on_blocked_cards: Record<string, number>
}
export interface Containment { planned_as_of: string; penalty_usd_per_person: number; plans: ContainmentPlan[] }

export interface Baseline {
  method: string; n: number; verdict_accuracy: number; fraud_caught: number | null
  cleared_left_alone: number | null; brier: number; wrongly_accused: number; missed_fraud: number; uncertain: number
}
export interface FinalRound {
  drills: Record<string, Record<string, unknown> & { passed: boolean; outcome?: string; stage?: string; reason?: string }> | null
  attacks: Record<string, { id: string; case: string; surface: string; goal: string
    clean: { verdict: string; harmful: string[] }
    defended?: Record<string, unknown>; undefended?: Record<string, unknown> }> | null
  ablation: { case: string; trigger: string; verdict: Record<string, string>; probability: Record<string, number> }[] | null
  detectors: { cases: number; summary: Record<string, { fired: number; confirmed_fraud_caught: number;
    of_confirmed: number; cleared_customers_acted_against: number; of_cleared: number }> } | null
  data_quality: { problem: string; what: string; affected_count: number; taints: string[] }[] | null
}
export interface Evaluation {
  baselines: Baseline[] | null
  backtest: { n: number; verdict_accuracy: number; fraud_recall: number; cleared_accuracy: number; brier: number } | null
  final_round?: FinalRound
}

export interface Analyst { name: string; role: string }

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit & { key?: string }): Promise<T> {
  const headers: Record<string, string> = {}
  if (init?.body) headers['Content-Type'] = 'application/json'
  if (init?.key) headers.Authorization = `Bearer ${init.key}`
  const res = await fetch(path, { ...init, headers })
  if (!res.ok) {
    const detail = (await res.json().catch(() => ({}))).detail
    throw new ApiError(res.status, typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
  return res.json()
}

const post = <T>(path: string, body: unknown, key?: string) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body), key })

export const api = {
  overview: () => request<Overview>('/api/overview'),
  cases: () => request<CaseRow[]>('/api/cases'),
  case: (id: string) => request<CaseDetail>(`/api/cases/${id}`),
  replay: (id: string) => request<Replay>(`/api/cases/${id}/replay`),
  challenges: (id: string) => request<ChallengeRecord[]>(`/api/cases/${id}/challenges`),
  monitoring: () => request<Monitoring>('/api/monitoring'),
  rings: () => request<Rings>('/api/rings'),
  ring: (id: number) => request<Ring>(`/api/rings/${id}`),
  containment: () => request<Containment>('/api/containment'),
  evaluation: () => request<Evaluation>('/api/evaluation'),
  whoami: (key: string) => request<Analyst>('/api/whoami', { key }),

  /** Who decides comes from the key; the body says only what is decided. */
  approve: (id: string, key: string, body: { action: string; decision: 'approved' | 'rejected'; note: string }) =>
    post<Approval>(`/api/cases/${id}/approvals`, body, key),
  challenge: (id: string, key: string, body: { position: string; reason: string; evidence_ids: string[] }) =>
    post<ChallengeRecord>(`/api/cases/${id}/challenges`, body, key),
  settle: (id: string, n: number, key: string, body: { decision: 'upheld' | 'overruled'; reason: string }) =>
    post<ChallengeRecord>(`/api/cases/${id}/challenges/${n}/review`, body, key),
  counterfactual: (id: string, dropped: number[]) => post<Counterfactual>(`/api/cases/${id}/counterfactual`, { dropped }),
  investigate: (id: string) => post<{ started: string }>(`/api/cases/${id}/investigate`, {}),
  /** Server-sent events of a running investigation; the caller closes it. */
  stream: (id: string) => new EventSource(`/api/cases/${id}/stream`),
}

/** The recorded snapshot answers reads only; the live backend answers everything. */
export const SNAPSHOT = import.meta.env.MODE === 'mock'
