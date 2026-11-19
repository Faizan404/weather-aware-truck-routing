import type { PlanResponse } from '../api/types'

/** Identifies a trip regardless of the checkpoint interval: changing only the
 *  interval keeps the selected route and forecast hour; a new trip resets them. */
export function tripKeyOf(plan: PlanResponse | null): string | null {
  if (!plan) return null
  const { origin, destination, departure_time, load_weight_lbs } = plan.request
  return JSON.stringify([origin, destination, departure_time, load_weight_lbs])
}

/** A value remembered together with the trip it was chosen for. */
export interface Scoped<T> {
  key: string | null
  value: T
}

/** The remembered value if it belongs to this trip, else the trip's default. */
export function readScoped<T>(scoped: Scoped<T> | null, key: string | null, fallback: T): T {
  return scoped && scoped.key === key ? scoped.value : fallback
}
