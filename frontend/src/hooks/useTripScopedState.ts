import { useCallback, useState } from 'react'

import { readScoped, type Scoped } from '../lib/tripScope'

/**
 * State that resets to `fallback` whenever the trip changes, worked out
 * during render instead of synced in an effect (so there's no frame showing
 * the old trip's value).
 */
export function useTripScopedState<T>(tripKey: string | null, fallback: T): [T, (value: T) => void] {
  const [scoped, setScoped] = useState<Scoped<T> | null>(null)
  const set = useCallback((value: T) => setScoped({ key: tripKey, value }), [tripKey])
  return [readScoped(scoped, tripKey, fallback), set]
}
