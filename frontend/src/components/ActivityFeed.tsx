import type { CSSProperties } from 'react'
import type { AgentEvent } from '../types'
import { agentMeta } from '../agents'
import { actionLabel, delegatedBy, fmtTime, parseTool, saidLine } from '../format'
import { AgentAvatar } from './AgentAvatar'

export function ActivityFeed({
  events,
  running,
  elapsed,
}: {
  events: AgentEvent[]
  running: boolean
  elapsed: number
}) {
  if (!events.length && !running) {
    return <p className="empty">No agent activity for this ticket yet. Run the team to watch them work.</p>
  }
  return (
    <ol className="feed" aria-live="polite">
      {events.map((e, i) => {
        const m = agentMeta(e.agent)
        const asker = delegatedBy(e)
        const said = saidLine(e)
        return (
          <li key={`${e.timestamp}-${i}`} className="feed__item" style={{ '--agent': m.color } as CSSProperties}>
            <AgentAvatar name={e.agent} size={34} />
            <div className="feed__body">
              <div className="feed__line">
                <strong style={{ color: m.color }}>{m.label}</strong>
                <span className="muted">{actionLabel(e)}</span>
                {asker && (
                  <span className="chip chip--delegation">
                    {agentMeta(asker).label} → {m.label}
                  </span>
                )}
                {e.needs_human_approval && <span className="chip chip--approval">needs approval</span>}
                <time className="feed__time">{fmtTime(e.timestamp)}</time>
              </div>
              {said && <p className="feed__said">{said}</p>}
              {e.tools_called.length > 0 && (
                <div className="feed__tools">
                  {e.tools_called.map((call, j) => {
                    const t = parseTool(call)
                    return (
                      <code key={j} className="tool" title={t.args || undefined}>
                        {t.name}
                      </code>
                    )
                  })}
                </div>
              )}
              {e.error && <p className="feed__error">{e.error}</p>}
            </div>
          </li>
        )
      })}
      {running && (
        <li className="feed__item feed__item--working">
          <div className="typing" aria-hidden>
            <span />
            <span />
            <span />
          </div>
          <div className="feed__body">
            <span className="muted">Agents working… {elapsed}s</span>
          </div>
        </li>
      )}
    </ol>
  )
}
