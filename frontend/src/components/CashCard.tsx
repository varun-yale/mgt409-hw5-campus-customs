import type { Cash } from '../types'
import { fmtMoney } from '../format'

export function CashCard({ cash }: { cash: Cash | null }) {
  if (!cash) return <section className="panel cash">Loading cash…</section>
  const after = cash.balance_if_all_approved
  return (
    <section className="panel cash">
      <header className="panel__head">
        <h2>Checking</h2>
        <span className="muted">as of {cash.as_of}</span>
      </header>
      {/* key on the balance so the number flashes when a payment lands */}
      <div key={cash.balance} className="cash__balance">
        {fmtMoney(cash.balance)}
      </div>
      <dl className="cash__rows">
        <div>
          <dt>Waiting for approval</dt>
          <dd>
            {cash.pending_approvals} · {fmtMoney(cash.pending_total)}
          </dd>
        </div>
        <div>
          <dt>If all approved</dt>
          <dd className={after < 0 ? 'neg' : ''}>{fmtMoney(after)}</dd>
        </div>
      </dl>
      {after < 0 && <p className="cash__warn">Not everything waiting can be paid. Checking can't go below $0.</p>}
    </section>
  )
}
