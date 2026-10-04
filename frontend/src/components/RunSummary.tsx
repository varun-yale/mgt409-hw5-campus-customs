import type { CSSProperties } from 'react'
import type { AgentEvent, RunResult } from '../types'
import { AGENT_ORDER, agentMeta } from '../agents'
import { parseTool, saidLine } from '../format'
import { AgentAvatar } from './AgentAvatar'

/** After a run: one card per agent. Uses the run result when we have it,
 *  otherwise rebuilds a summary from the audit-trail events. */
export function RunSummary({ result, events }: { result: RunResult | null; events: AgentEvent[] }) {
  const runId = events[0]?.run_id ?? result?.run_id
  const model = events[0]?.run_model ?? result?.model

  if (result && result.run_id === runId) {
    const d = result.decision
    return (
      <div className="summary">
        <RunTag runId={result.run_id} model={result.model} />
        <div className="summary__card summary__card--boss" style={{ '--agent': agentMeta('boss').color } as CSSProperties}>
          <div className="summary__who">
            <AgentAvatar name="boss" size={38} />
            <div>
              <strong>Boss · final call</strong>
              <div className="muted">Routed to {result.plan.route_to.map((a) => agentMeta(a).label).join(', ')}</div>
            </div>
          </div>
          <p className="summary__main">{d.decision}</p>
          <p className="muted">{d.rationale}</p>
          {d.human_approval_required && (
            <p className="summary__flag">Needs approval: {d.approval_reason ?? 'see the approval queue'}</p>
          )}
          {d.open_questions.length > 0 && (
            <ul className="summary__list">
              {d.open_questions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          )}
        </div>
        <div className="summary__grid">
          {result.reports.map((r) => (
            <div key={r.agent} className="summary__card" style={{ '--agent': agentMeta(r.agent).color } as CSSProperties}>
              <div className="summary__who">
                <AgentAvatar name={r.agent} size={30} />
                <strong>{agentMeta(r.agent).label}</strong>
                {!r.confident && <span className="chip">not confident</span>}
                {r.needs_human_approval && <span className="chip chip--approval">needs approval</span>}
              </div>
              <p>{r.summary}</p>
              <p className="muted">→ {r.recommendation}</p>
              {r.blockers.length > 0 && (
                <ul className="summary__list summary__list--blockers">
                  {r.blockers.map((b, i) => (
                    <li key={i}>{b}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!events.length) return <p className="empty">The summary appears here after a run.</p>

  // Rebuild from the audit trail: what each agent did in the latest run.
  const byAgent = AGENT_ORDER.map((name) => {
    const mine = events.filter((e) => e.agent === name)
    const tools = [...new Set(mine.flatMap((e) => e.tools_called.map((c) => parseTool(c).name)))]
    const last = [...mine].reverse().find((e) => saidLine(e))
    const errors = mine.filter((e) => e.error).length
    return { name, steps: mine.length, tools, said: last ? saidLine(last) : null, errors }
  }).filter((a) => a.steps > 0)

  return (
    <div className="summary">
      <RunTag runId={runId} model={model} note="Rebuilt from the audit trail" />
      <div className="summary__grid">
        {byAgent.map((a) => (
          <div key={a.name} className="summary__card" style={{ '--agent': agentMeta(a.name).color } as CSSProperties}>
            <div className="summary__who">
              <AgentAvatar name={a.name} size={30} />
              <strong>{agentMeta(a.name).label}</strong>
              <span className="muted">
                {a.steps} step{a.steps > 1 ? 's' : ''}
              </span>
              {a.errors > 0 && <span className="chip chip--error">{a.errors} error{a.errors > 1 ? 's' : ''}</span>}
            </div>
            {a.said && <p>{a.said.length > 260 ? a.said.slice(0, 260) + '…' : a.said}</p>}
            {a.tools.length > 0 && (
              <div className="feed__tools">
                {a.tools.map((t) => (
                  <code key={t} className="tool">
                    {t}
                  </code>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function RunTag({ runId, model, note }: { runId?: string; model?: string | null; note?: string }) {
  return (
    <div className="runtag">
      {runId && <code>{runId}</code>}
      {model && <span className={`chip ${model === 'gpt-6-luna' ? 'chip--model' : 'chip--warn'}`}>{model}</span>}
      {note && <span className="muted">{note}</span>}
    </div>
  )
}
