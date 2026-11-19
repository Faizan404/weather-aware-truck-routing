import { Truck } from 'lucide-react'

import type { ThemePreference } from '../hooks/useTheme'
import { ThemeSwitch } from './ThemeSwitch'

export function AppHeader({
  className,
  theme,
  onThemeChange,
}: {
  className: string
  theme: ThemePreference
  onThemeChange: (t: ThemePreference) => void
}) {
  return (
    <header className={`items-center gap-3 ${className}`}>
      <span className="clay-accent flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl" aria-hidden>
        <Truck size={20} strokeWidth={2} />
      </span>
      <div className="min-w-0 flex-1">
        <h1 className="text-[16px] font-extrabold leading-tight tracking-[-0.01em] text-balance text-ink sm:text-[17px]">Weather-Aware Truck Routing</h1>
        <p className="text-[13px] text-muted">Route safety by weather and load</p>
      </div>
      <ThemeSwitch value={theme} onChange={onThemeChange} />
    </header>
  )
}
