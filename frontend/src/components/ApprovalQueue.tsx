import type { Approval } from '../types'
import { fmtMoney } from '../format'

const KIND: Record<Approval['kind'], string> = {
  invoice: 'Vendor invoice',
  rent: 'Rent',
  purchase: 'Purchase',
}

export function ApprovalQueue({
  approvals,
  balance,
  signer,
  onSigner,
  onApprove,
  busyId,
  errors,
}: {
  approvals: Approval[]
  balance: number | null
  signer: string
  onSigner: (s: string) => void
  onApprove: (a: Approval) => void
  busyId: string | null
  errors: Record<string, string>
}) {
  const pending = approvals.filter((a) => a.status === 'pending')
  const done = approvals.filter((a) => a.status === 'approved').slice(-3).reverse()
  return (
    <section className="panel">
      <header className="panel__head">
        <h2>Needs your approval</h2>
        <span className="count">{pending.length}</span>
      </header>
      <label className="signer">
        <span>Approving as</span>
        <input value={signer} onChange={(e) => onSigner(e.target.value)} placeholder="Your name" />
      </label>
      {pending.length === 0 && <p className="empty">Nothing waiting. Agents prepare payments here; only you can send them.</p>}
      <ul className="approvals">
        {pending.map((a) => {
          const short = balance != null && a.amount > balance
          return (
            <li key={a.id} className="approval">
              <div className="approval__top">
                <span className="chip">{KIND[a.kind]}</span>
                <span className="muted">ticket #{a.ticket_id}</span>
              </div>
              <div className="approval__amount">{fmtMoney(a.amount)}</div>
              <div className="approval__payee">to {a.payee}</div>
              <p className="muted">{a.description}</p>
              <p className="approval__reason">“{a.reason}” — Boss</p>
              {short && <p className="approval__warn">Checking has {fmtMoney(balance!)}. This would overdraw it, so it can't be sent.</p>}
              {errors[a.id] && <p className="approval__warn">{errors[a.id]}</p>}
              <button
                className="btn btn--approve"
                disabled={!signer.trim() || short || busyId === a.id}
                onClick={() => onApprove(a)}
              >
                {busyId === a.id ? 'Sending…' : !signer.trim() ? 'Enter your name to approve' : `Approve ${fmtMoney(a.amount)}`}
              </button>
            </li>
          )
        })}
      </ul>
      {done.length > 0 && (
        <>
          <h3 className="subhead">Recently approved</h3>
          <ul className="approved">
            {done.map((a) => (
              <li key={a.id}>
                <span>
                  {KIND[a.kind]} · {a.payee}
                </span>
                <span>
                  {fmtMoney(a.amount)} <span className="muted">by {a.approved_by}</span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
