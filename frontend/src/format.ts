import type { AgentEvent } from './types'
import { agentMeta } from './agents'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })

export const fmtMoney = (n: number) => money.format(n)

export const fmtTime = (iso: string) =>
  new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })

const TICKET_TYPES: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price override',
}

export const ticketType = (t: string) => TICKET_TYPES[t] ?? t

/** "campus-customs_check_stock({...})" -> { name: "check_stock", args: "{...}" } */
export function parseTool(call: string): { name: string; args: string } {
  const bare = call.replace(/^campus-customs_/, '')
  const i = bare.indexOf('(')
  if (i < 0) return { name: bare, args: '' }
  return { name: bare.slice(0, i), args: bare.slice(i + 1, -1) }
}

/** What an event's action means, in words. */
export function actionLabel(e: AgentEvent): string {
  if (e.action.startsWith('delegated_by_')) {
    return `Answered ${agentMeta(e.action.slice('delegated_by_'.length)).label}`
  }
  switch (e.action) {
    case 'route_ticket':
      return 'Routed the ticket'
    case 'specialist_report':
      return 'Filed a report'
    case 'final_decision':
      return 'Made the call'
    case 'prepared_payment':
      return 'Prepared a payment'
    case 'load_tickets':
      return 'Read the desk'
    default:
      return e.action.replace(/_/g, ' ')
  }
}

/** Who asked, when an event is an answer to a colleague's question. */
export const delegatedBy = (e: AgentEvent) =>
  e.action.startsWith('delegated_by_') ? e.action.slice('delegated_by_'.length) : null

function grab(text: string, key: string): string | null {
  // Audit summaries are truncated JSON, so fall back to pulling one field out.
  const m = text.match(new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`))
  return m ? m[1].replace(/\\"/g, '"').replace(/\\n/g, ' ') : null
}

/** The one line an agent "said" in this step. */
export function saidLine(e: AgentEvent): string | null {
  const text = e.output_summary
  if (!text) return null
  try {
    const o = JSON.parse(text)
    if (o.route_to) return `Routing to ${o.route_to.map((a: string) => agentMeta(a).label).join(', ')}. ${o.reason ?? ''}`
    if (o.kind && o.amount != null) return `${fmtMoney(o.amount)} to ${o.payee}: ${o.description}`
    return o.decision ?? o.summary ?? o.recommendation ?? text
  } catch {
    const route = text.match(/"route_to"\s*:\s*\[([^\]]*)\]/)
    if (route) {
      const who = route[1].replace(/"/g, '').split(',').map((a) => agentMeta(a.trim()).label)
      return `Routing to ${who.join(', ')}. ${grab(text, 'reason') ?? ''}`
    }
    return grab(text, 'decision') ?? grab(text, 'summary') ?? text
  }
}
