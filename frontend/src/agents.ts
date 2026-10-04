import type { AgentName } from './types'

export interface AgentMeta {
  label: string
  role: string
  color: string
  glyph: string
}

export const AGENTS: Record<AgentName, AgentMeta> = {
  boss: { label: 'Boss', role: 'Routes tickets, makes the call', color: '#ff4fa3', glyph: '♛' },
  inventory: { label: 'Inventory', role: 'Stock, sizes, restocks', color: '#4cc9f0', glyph: '▦' },
  accounting: { label: 'Accounting', role: 'Invoices, cash, margins', color: '#ffc857', glyph: '$' },
  facilities: { label: 'Facilities', role: 'Lease and rent', color: '#7bd88f', glyph: '⌂' },
  customer_service: { label: 'Customer Service', role: 'What the customer hears', color: '#b794f6', glyph: '✉' },
}

export const AGENT_ORDER: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export function agentMeta(name: string): AgentMeta {
  return AGENTS[name as AgentName] ?? { label: name, role: '', color: '#a3a3b0', glyph: '?' }
}
