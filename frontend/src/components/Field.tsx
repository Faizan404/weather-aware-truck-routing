import type { ReactNode } from 'react'

/** Label + pressed clay well with a leading icon. The input goes in children. */
export function Field({
  label,
  htmlFor,
  icon,
  error,
  hint,
  children,
  trailing,
}: {
  label: string
  htmlFor: string
  icon: ReactNode
  error?: string
  hint?: ReactNode
  children: ReactNode
  trailing?: ReactNode
}) {
  return (
    <div className="min-w-0">
      <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-semibold text-muted">
        {label}
      </label>
      <div
        className={`focus-ring clay-pressed flex items-center gap-2.5 rounded-2xl px-3.5 transition-shadow ${
          error ? 'ring-2 ring-danger/60' : ''
        }`}
      >
        <span className="shrink-0 text-faint" aria-hidden>
          {icon}
        </span>
        {children}
        {trailing}
      </div>
      {error ? (
        <p id={`${htmlFor}-error`} className="mt-1.5 text-[12.5px] font-medium text-danger">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1.5 text-[12.5px] text-faint">{hint}</p>
      ) : null}
    </div>
  )
}

export const inputClass =
  'h-11 w-full min-w-0 bg-transparent text-[15px] text-ink placeholder:text-faint outline-none'
