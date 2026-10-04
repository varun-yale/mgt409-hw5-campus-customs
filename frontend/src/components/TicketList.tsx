import type { Ticket } from '../types'
import { ticketType } from '../format'

export function TicketList({
  tickets,
  selected,
  runningId,
  onSelect,
}: {
  tickets: Ticket[]
  selected: number | null
  runningId: number | null
  onSelect: (id: number) => void
}) {
  const open = tickets.filter((t) => !t.resolved).length
  return (
    <section className="panel">
      <header className="panel__head">
        <h2>Tickets</h2>
        <span className="muted">
          {open} open · {tickets.length - open} resolved
        </span>
      </header>
      <ul className="tickets">
        {tickets.map((t) => (
          <li key={t.id}>
            <button
              className={[
                'ticket',
                t.resolved ? 'ticket--resolved' : 'ticket--open',
                selected === t.id ? 'ticket--selected' : '',
              ].join(' ')}
              onClick={() => onSelect(t.id)}
              aria-pressed={selected === t.id}
            >
              <div className="ticket__top">
                <span className="ticket__id">#{t.id}</span>
                {runningId === t.id ? (
                  <span className="status status--running">
                    <span className="dot" /> Running
                  </span>
                ) : t.resolved ? (
                  <span className="status status--resolved">✓ Resolved</span>
                ) : (
                  <span className="status status--open">
                    <span className="dot" /> Open
                  </span>
                )}
              </div>
              <div className="ticket__subject">{t.subject}</div>
              <div className="ticket__meta">
                {ticketType(t.type)} · {t.requester}
              </div>
              {t.pending_approvals > 0 && (
                <div className="ticket__flag">
                  {t.pending_approvals} payment{t.pending_approvals > 1 ? 's' : ''} awaiting approval
                </div>
              )}
            </button>
          </li>
        ))}
      </ul>
    </section>
  )
}
