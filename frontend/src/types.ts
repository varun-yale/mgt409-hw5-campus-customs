// Shapes returned by the FastAPI backend (backend/main.py).

export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  notes: string | null
  status: string
  resolved: boolean
  pending_approvals: number
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  pending_approvals: number
  pending_total: number
  balance_if_all_approved: number
}

export interface AgentEvent {
  run_id: string
  run_model: string | null
  timestamp: string
  agent: string
  ticket_id: number | null
  action: string
  tools_called: string[]
  tool_results_summary: string[]
  output_summary: string | null
  needs_human_approval: boolean
  error: string | null
}

export interface Payment {
  payment_id: number
  amount: number
  paid_at: string
  approved_by: string
  balance_before: number
  balance_after: number
}

export interface Approval {
  id: string
  ticket_id: number
  kind: 'invoice' | 'rent' | 'purchase'
  target: Record<string, unknown>
  amount: number
  payee: string
  description: string
  reason: string
  status: 'pending' | 'approved'
  prepared_by: string
  prepared_at: string
  run_id: string
  approved_by: string | null
  approved_at: string | null
  payment: Payment | null
}

export interface Fact {
  field: string
  value: string
  source_tool: string
}

export interface SpecialistReport {
  agent: AgentName
  ticket_id: number | null
  summary: string
  facts: Fact[]
  recommendation: string
  blockers: string[]
  needs_human_approval: boolean
  risk: string
  confident: boolean
}

export interface BossDecision {
  ticket_id: number
  decision: string
  rationale: string
  human_approval_required: boolean
  approval_reason: string | null
  proposed_payments: unknown[]
  open_questions: string[]
}

export interface RunResult {
  run_id: string
  model: string
  ticket_id: number
  plan: { route_to: AgentName[]; reason: string }
  reports: SpecialistReport[]
  decision: BossDecision
  prepared_approvals: Approval[]
  skipped_proposals: { reason: string }[]
  ticket_status: string
}
