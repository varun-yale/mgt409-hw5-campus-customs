import type { AgentEvent, Approval, Cash, RunResult, Ticket } from './types'

export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_BASE + path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, body?.detail ?? body)
  return body as T
}

export const api = {
  tickets: () => req<{ count: number; tickets: Ticket[] }>('/tickets'),
  cash: () => req<Cash>('/cash'),
  approvals: () => req<{ count: number; approvals: Approval[] }>('/approvals'),
  events: (opts: { ticketId?: number; limit?: number; since?: string }) => {
    const q = new URLSearchParams()
    if (opts.ticketId != null) q.set('ticket_id', String(opts.ticketId))
    if (opts.limit) q.set('limit', String(opts.limit))
    if (opts.since) q.set('since', opts.since)
    return req<{ count: number; events: AgentEvent[] }>(`/events?${q}`)
  },
  run: (ticketId: number) => req<RunResult>(`/tickets/${ticketId}/run`, { method: 'POST' }),
  approve: (id: string, approvedBy: string) =>
    req<{ approval: Approval; ticket_resolved: boolean }>(`/approvals/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  reset: () => req<{ matches_original: boolean }>('/reset', { method: 'POST' }),
}

/** One readable sentence for any error the backend (or the network) throws. */
export function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { message?: string } | string | null
    if (typeof d === 'string') return d
    if (d && typeof d === 'object' && d.message) return d.message
    return `The backend returned HTTP ${e.status}.`
  }
  if (e instanceof TypeError) {
    return `Can't reach the backend at ${API_BASE}. Is uvicorn running?`
  }
  return String(e)
}

export interface RunFailure {
  title: string
  message: string
  runId?: string
}

/** Turn a failed run into something the dashboard can show calmly. */
export function describeRunError(e: unknown): RunFailure {
  if (e instanceof ApiError && e.detail && typeof e.detail === 'object') {
    const d = e.detail as { error?: string; message?: string; run_id?: string; model?: string }
    if (d.error === 'portkey_quota_exhausted') {
      const status = d.message?.match(/status_code:\s*(\d+)/)?.[1] ?? '412'
      return {
        title: 'Portkey quota exhausted',
        message:
          `Portkey refused ${d.model ?? 'gpt-6-luna'} with HTTP ${status} (usage limit exceeded). ` +
          'The run stopped, the failure is recorded in the audit trail, and no other model was tried.',
        runId: d.run_id,
      }
    }
    if (d.error === 'run_incomplete') {
      return {
        title: "The run didn't finish",
        message: d.message ?? 'An agent failed before the Boss could decide.',
        runId: d.run_id,
      }
    }
  }
  return { title: "Couldn't run the team", message: describeError(e) }
}
