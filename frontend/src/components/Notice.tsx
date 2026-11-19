import type { ReactNode } from 'react'

/** A pressed-in message panel: errors (danger), warnings (warn), No Travel (violet). */
export function Notice({
  tone,
  icon,
  title,
  children,
  role,
}: {
  tone: 'danger' | 'warn' | 'violet'
  icon: ReactNode
  title?: string
  children: ReactNode
  role?: 'alert' | 'status'
}) {
  const styles = {
    danger: 'bg-danger-soft text-danger',
    warn: 'bg-warn-soft text-warn',
    violet: 'bg-violet-soft text-risk-no-travel',
  }[tone]
  return (
    <div role={role} className={`flex gap-3 rounded-[20px] p-3.5 text-[13.5px] ${styles}`} style={{ boxShadow: 'var(--clay-pressed)' }}>
      <span className="mt-0.5 shrink-0" aria-hidden>
        {icon}
      </span>
      <div className="min-w-0 space-y-0.5">
        {title && <p className="font-bold">{title}</p>}
        <div className="text-ink/85">{children}</div>
      </div>
    </div>
  )
}
