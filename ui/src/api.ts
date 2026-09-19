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
export interface GraphNode { id: string; kind: string; label: string; role?: string; outcome?: string; pattern?: string; profile?: string; score?: number | null }
export interface GraphEdge { source: string; target: string; kind: string }

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
  assessment: { fraud_probability: number; verdict: Verdict; uncertainty: string; reasoning: string } | null
  actions: CaseAction[]
  graph: { nodes: GraphNode[]; edges: GraphEdge[] }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? `Request failed (${res.status})`)
  return res.json()
}

export const api = {
  cases: () => fetch('/api/cases').then(json<CaseRow[]>),
  case: (id: string) => fetch(`/api/cases/${id}`).then(json<CaseDetail>),
  investigate: (id: string) => fetch(`/api/cases/${id}/investigate`, { method: 'POST' }).then(json<{ started: string }>),
  approve: (id: string, body: { action: string; decision: string; approver: string; role: string; note: string }) =>
    fetch(`/api/cases/${id}/approvals`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then(json<unknown>),
}
