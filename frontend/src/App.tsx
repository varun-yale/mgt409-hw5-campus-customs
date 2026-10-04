import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE, api, describeError, describeRunError, type RunFailure } from './api'
import type { AgentEvent, Approval, Cash, RunResult, Ticket } from './types'
import { AGENTS, AGENT_ORDER } from './agents'
import { ticketType } from './format'
import { AgentAvatar, type AvatarState } from './components/AgentAvatar'
import { TicketList } from './components/TicketList'
import { ActivityFeed } from './components/ActivityFeed'
import { RunSummary } from './components/RunSummary'
import { CashCard } from './components/CashCard'
import { ApprovalQueue } from './components/ApprovalQueue'

const RESULTS_KEY = 'cc-run-results'
const SIGNER_KEY = 'cc-signer'

function loadResults(): Record<number, RunResult> {
  try {
    return JSON.parse(localStorage.getItem(RESULTS_KEY) ?? '{}')
  } catch {
    return {}
  }
}

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  // ?ticket=101 opens that ticket directly (handy for board screenshots).
  const [selected, setSelected] = useState<number | null>(
    () => Number(new URLSearchParams(window.location.search).get('ticket')) || null,
  )
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [running, setRunning] = useState<{ ticketId: number; since: string } | null>(null)
  const [runError, setRunError] = useState<(RunFailure & { ticketId: number }) | null>(null)
  const [results, setResults] = useState<Record<number, RunResult>>(loadResults)
  const [offline, setOffline] = useState<string | null>(null)
  const [signer, setSigner] = useState(() => localStorage.getItem(SIGNER_KEY) ?? '')
  const [busyApproval, setBusyApproval] = useState<string | null>(null)
  const [approvalErrors, setApprovalErrors] = useState<Record<string, string>>({})
  const [now, setNow] = useState(Date.now())

  // Only the newest refresh may write state, so a slow older one can't
  // overwrite fresher data (e.g. a run's refresh landing after a reset).
  const refreshSeq = useRef(0)
  const refresh = useCallback(async () => {
    const seq = ++refreshSeq.current
    try {
      const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals()])
      if (seq !== refreshSeq.current) return
      setTickets(t.tickets)
      setCash(c)
      setApprovals(a.approvals)
      setOffline(null)
      setSelected((s) => s ?? t.tickets[0]?.id ?? null)
    } catch (e) {
      if (seq === refreshSeq.current) setOffline(describeError(e))
    }
  }, [])

  // Events for one ticket: either everything since a run started, or the latest run.
  const loadEvents = useCallback(async (ticketId: number, since?: string) => {
    const r = await api.events({ ticketId, limit: 500, since })
    const chron = [...r.events].reverse()
    if (since) return setEvents(chron)
    const latest = chron.at(-1)?.run_id
    setEvents(latest ? chron.filter((e) => e.run_id === latest) : [])
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    localStorage.setItem(SIGNER_KEY, signer)
  }, [signer])

  useEffect(() => {
    if (selected == null) return
    if (running?.ticketId === selected) return
    loadEvents(selected).catch(() => setEvents([]))
  }, [selected, running, loadEvents])

  // While the team works, poll the audit trail so steps appear as they happen.
  useEffect(() => {
    if (!running) return
    const tick = () => {
      setNow(Date.now())
      if (selected === running.ticketId) loadEvents(running.ticketId, running.since).catch(() => {})
    }
    tick()
    const id = setInterval(tick, 1200)
    return () => clearInterval(id)
  }, [running, selected, loadEvents])

  const saveResults = (next: Record<number, RunResult>) => {
    setResults(next)
    localStorage.setItem(RESULTS_KEY, JSON.stringify(next))
  }

  const runTeam = async (ticketId: number) => {
    const since = new Date().toISOString()
    const { [ticketId]: _old, ...rest } = results
    saveResults(rest)
    setRunError(null)
    setEvents([])
    setRunning({ ticketId, since })
    try {
      const res = await api.run(ticketId)
      saveResults({ ...rest, [ticketId]: res })
    } catch (e) {
      setRunError({ ticketId, ...describeRunError(e) })
    } finally {
      await refresh()
      setRunning(null)
    }
  }

  const approve = async (a: Approval) => {
    setBusyApproval(a.id)
    setApprovalErrors(({ [a.id]: _gone, ...others }) => others)
    try {
      await api.approve(a.id, signer.trim())
    } catch (e) {
      setApprovalErrors((m) => ({ ...m, [a.id]: describeError(e) }))
    } finally {
      setBusyApproval(null)
      await refresh()
    }
  }

  const reset = async () => {
    if (!window.confirm('Reset the working database to the original values? Prepared payments are cleared; the audit trail is kept.')) return
    try {
      await api.reset()
      saveResults({})
      setRunError(null)
      setApprovalErrors({})
      await refresh()
      if (selected != null) await loadEvents(selected)
    } catch (e) {
      setOffline(describeError(e))
    }
  }

  const ticket = tickets.find((t) => t.id === selected) ?? null
  const isRunningHere = running?.ticketId === selected
  const elapsed = running ? Math.max(0, Math.round((now - Date.parse(running.since)) / 1000)) : 0

  // Roster state: who has spoken in this run, and who spoke last.
  const roster = useMemo(() => {
    const seen = new Set(events.map((e) => e.agent))
    const last = events.at(-1)?.agent
    return AGENT_ORDER.map((name) => {
      let state: AvatarState = seen.has(name) ? 'involved' : 'idle'
      if (isRunningHere && (name === last || (!last && name === 'boss'))) state = 'active'
      const mine = events.filter((e) => e.agent === name)
      return { name, state, steps: mine.length, tools: mine.reduce((n, e) => n + e.tools_called.length, 0) }
    })
  }, [events, isRunningHere])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">CC</span>
          <div>
            <div className="brand__name">Campus Customs</div>
            <div className="brand__sub">Operations desk</div>
          </div>
        </div>
        <div className="topbar__right">
          {cash && <span className="pill">Shop date {cash.as_of}</span>}
          <span className={`pill ${offline ? 'pill--bad' : 'pill--ok'}`}>
            <span className="dot" /> {offline ? 'Backend offline' : `Connected · ${API_BASE.replace(/^https?:\/\//, '')}`}
          </span>
          <button className="btn btn--ghost" onClick={reset} disabled={!!running}>
            Reset shop
          </button>
        </div>
      </header>

      {offline && (
        <div className="banner banner--error">
          {offline}{' '}
          <button className="btn btn--ghost" onClick={refresh}>
            Retry
          </button>
        </div>
      )}

      <main className="layout">
        <aside className="col">
          <TicketList tickets={tickets} selected={selected} runningId={running?.ticketId ?? null} onSelect={setSelected} />
        </aside>

        <section className="col col--main">
          {ticket ? (
            <>
              <section className={`panel hero ${ticket.resolved ? 'hero--resolved' : ''}`}>
                <div className="hero__text">
                  <div className="hero__kicker">
                    #{ticket.id} · {ticketType(ticket.type)} · {ticket.requester}
                  </div>
                  <h1>{ticket.subject}</h1>
                  {ticket.notes && <p className="muted">“{ticket.notes}”</p>}
                </div>
                <div className="hero__action">
                  {ticket.resolved ? (
                    <span className="status status--resolved big">✓ Resolved</span>
                  ) : (
                    <button className="btn btn--primary" disabled={!!running} onClick={() => runTeam(ticket.id)}>
                      {isRunningHere ? 'Agents working…' : running ? 'Another ticket is running' : 'Run agent team'}
                    </button>
                  )}
                  {ticket.resolved && <span className="muted small">Reset the shop to run it again.</span>}
                </div>
              </section>

              <section className="panel">
                <header className="panel__head">
                  <h2>The team</h2>
                  <span className="muted">{isRunningHere ? 'live' : events.length ? 'latest run' : 'waiting'}</span>
                </header>
                <div className="roster">
                  {roster.map((a) => (
                    <div key={a.name} className={`roster__agent roster__agent--${a.state}`}>
                      <AgentAvatar name={a.name} size={52} state={a.state} />
                      <div className="roster__name" style={{ color: AGENTS[a.name].color }}>
                        {AGENTS[a.name].label}
                      </div>
                      <div className="roster__role">{AGENTS[a.name].role}</div>
                      <div className="roster__stats">
                        {a.steps ? `${a.steps} step${a.steps > 1 ? 's' : ''} · ${a.tools} tool call${a.tools === 1 ? '' : 's'}` : 'not called'}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {runError && runError.ticketId === ticket.id && (
                <div className="banner banner--error" role="alert">
                  <strong>{runError.title}.</strong> {runError.message}
                  {runError.runId && <code className="banner__code">{runError.runId}</code>}
                </div>
              )}

              <section className="panel">
                <header className="panel__head">
                  <h2>Activity</h2>
                  <span className="muted">what the agents are doing and which tools they use</span>
                </header>
                <ActivityFeed events={events} running={isRunningHere} elapsed={elapsed} />
              </section>

              <section className="panel">
                <header className="panel__head">
                  <h2>Run summary</h2>
                </header>
                {isRunningHere ? (
                  <p className="empty">The summary appears when the Boss makes the call.</p>
                ) : (
                  <RunSummary result={results[ticket.id] ?? null} events={events} />
                )}
              </section>
            </>
          ) : (
            <section className="panel">
              <p className="empty">{offline ? 'Waiting for the backend…' : 'Loading tickets…'}</p>
            </section>
          )}
        </section>

        <aside className="col">
          <CashCard cash={cash} />
          <ApprovalQueue
            approvals={approvals}
            balance={cash?.balance ?? null}
            signer={signer}
            onSigner={setSigner}
            onApprove={approve}
            busyId={busyApproval}
            errors={approvalErrors}
          />
        </aside>
      </main>
    </div>
  )
}
