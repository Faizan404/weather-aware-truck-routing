import { Monitor, Moon, Sun } from 'lucide-react'

import type { ThemePreference } from '../hooks/useTheme'

const OPTIONS: { value: ThemePreference; label: string; Icon: typeof Sun }[] = [
  { value: 'light', label: 'Light theme', Icon: Sun },
  { value: 'dark', label: 'Dark theme', Icon: Moon },
  { value: 'system', label: 'Match system theme', Icon: Monitor },
]

export function ThemeSwitch({ value, onChange }: { value: ThemePreference; onChange: (v: ThemePreference) => void }) {
  return (
    <div className="clay-pressed flex rounded-full p-1" role="radiogroup" aria-label="Colour theme">
      {OPTIONS.map(({ value: v, label, Icon }) => {
        const active = v === value
        return (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => onChange(v)}
            className={`focus-ring flex h-7 w-7 items-center justify-center rounded-full transition-colors ${
              active ? 'clay-sm text-ink' : 'text-faint hover:text-muted'
            }`}
          >
            <Icon size={15} strokeWidth={1.9} aria-hidden />
          </button>
        )
      })}
    </div>
  )
}
