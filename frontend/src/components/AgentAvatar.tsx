import type { CSSProperties } from 'react'
import { agentMeta } from '../agents'

export type AvatarState = 'idle' | 'involved' | 'active'

/** A small CSS-drawn desk creature, one color and badge per agent. */
export function AgentAvatar({
  name,
  size = 44,
  state = 'involved',
}: {
  name: string
  size?: number
  state?: AvatarState
}) {
  const m = agentMeta(name)
  const style = { '--agent': m.color, '--size': `${size}px` } as CSSProperties
  return (
    <div className={`avatar avatar--${state}`} style={style} role="img" aria-label={m.label} title={m.label}>
      <div className="avatar__head">
        <span className="avatar__eye avatar__eye--l" />
        <span className="avatar__eye avatar__eye--r" />
        <span className="avatar__mouth" />
      </div>
      <span className="avatar__badge" aria-hidden>
        {m.glyph}
      </span>
    </div>
  )
}
