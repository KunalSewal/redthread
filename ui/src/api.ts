export type Verdict = 'fraud' | 'legitimate' | 'uncertain'

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

export interface ActionItem { action: string; route: 'auto' | 'L1' | 'L2'; reason: string }
export interface CaseAction extends ActionItem {
  state: string
  approval?: { decision: string; approver: string; role: string; note: string; at: string } | null
}
export interface Evidence { claim: string; source: string; ref: string; entity_ids: string[] }
export interface Event { step: number; kind: string; detail: string; at: string; case_id?: string }

export interface GraphNode {
  id: string; kind: string; label: string; step: number
  role?: string; outcome?: string; pattern?: string; profile?: string; score?: number | null
  ring?: number; cards_all_time?: number
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

export interface CaseDetail {
  alert: CaseRow
  answer: Answer | null
  events: Event[]
  /** Tool digests keyed by tool name (or 'tool:{args}' for follow-ups). The backend always sent
   *  these; the client used to drop them, which left the evidence panel with nothing to show. */
  evidence: Record<string, Record<string, unknown>>
  assessment: { evidence: Evidence[]; uncertainty?: string; reasoning?: string } | null
  belief: Belief | null
  signals: Record<string, unknown> | null
  final_signals: Record<string, unknown> | null
  request: { type: string; question: string; asked_after_step: number } | null
  reply: { text: string; prior?: number; posterior?: number } | null
  report: string | null
  actions: CaseAction[]
  graph: { nodes: GraphNode[]; edges: GraphEdge[]; steps: number }
}

export interface MonitoringAlert {
  case_id: string; source: string; opened_at: string; card_id: string; flagged_txn_id: string
  bank_risk_score: number | null; trigger_text: string
  verdict?: Verdict; pattern?: string; exposure_usd?: number; sar?: boolean
}

export interface Monitoring {
  alerts: MonitoringAlert[]
  raised: number
  confirmed_fraud: number
  exposure_usd: number
  by_source: Record<string, number>
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
export interface CommunityStat { community: number; cards: number; fraud_cards: number; fraud_share: number }
export interface Rings {
  rings: Ring[]
  communities: CommunityStat[]
  communities_total: number
  communities_ranked: number
}

export interface Evaluation {
  model: Record<string, unknown> | null
  patterns: Record<string, unknown> | null
  calibration: Record<string, unknown> | null
  community_lift: { n_fraud: number; n_cleared: number; bands: Record<string, { p_fraud: number; p_cleared: number; lr: number | null }> } | null
  backtest: Record<string, unknown> | null
  backtest_cases: Record<string, unknown>[] | null
}

export interface PolicyChunk { chunk_id: string; source: string; section: string; content: string }

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`)
  return res.json()
}

export const api = {
  cases: () => fetch('/api/cases').then(json<CaseRow[]>),
  case: (id: string) => fetch(`/api/cases/${id}`).then(json<CaseDetail>),
  monitoring: () => fetch('/api/monitoring').then(json<Monitoring>),
  rings: () => fetch('/api/rings').then(json<Rings>),
  evaluation: () => fetch('/api/evaluation').then(json<Evaluation>),
  policy: () => fetch('/api/policy').then(json<{ chunks: PolicyChunk[]; by_source: Record<string, number> }>),
  investigate: (id: string) => fetch(`/api/cases/${id}/investigate`, { method: 'POST' }).then(json<{ started: string }>),
  approve: (id: string, body: { action: string; decision: string; approver: string; role: string; note: string }) =>
    fetch(`/api/cases/${id}/approvals`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then(json<unknown>),
}
