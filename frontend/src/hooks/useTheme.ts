import { useCallback, useEffect, useState } from 'react'

export type ThemePreference = 'light' | 'dark' | 'system'
export type Theme = 'light' | 'dark'

const KEY = 'theme'
const query = () => window.matchMedia('(prefers-color-scheme: dark)')

function readPreference(): ThemePreference {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

function resolve(pref: ThemePreference): Theme {
  if (pref === 'system') return query().matches ? 'dark' : 'light'
  return pref
}

/** Light / dark / follow-system theme, stored per browser. */
export function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference)
  const [theme, setTheme] = useState<Theme>(() => resolve(readPreference()))

  useEffect(() => {
    const apply = () => {
      const next = resolve(preference)
      setTheme(next)
      document.documentElement.dataset.theme = next
    }
    apply()
    if (preference !== 'system') return
    const mq = query()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [preference])

  const setPreference = useCallback((pref: ThemePreference) => {
    setPreferenceState(pref)
    try {
      if (pref === 'system') localStorage.removeItem(KEY)
      else localStorage.setItem(KEY, pref)
    } catch {
      /* storage unavailable: preference lasts for this visit only */
    }
  }, [])

  return { preference, theme, setPreference }
}
