import type { PlanRequest } from './types'

/** Every TanStack Query key in one place. A key holds all of a request's
 *  inputs, so changing any input is a new request (and cancels the old one). */
export const queryKeys = {
  riskRules: ['risk-rules'] as const,
  geocode: (query: string) => ['geocode', query.toLowerCase()] as const,
  plan: (request: PlanRequest | null) => ['plan', request] as const,
  heatmap: (body: HeatmapBody | null) => ['heatmap', body] as const,
}

export interface HeatmapBody {
  polylines: string[]
  departure_time: string
  load_weight_lbs: number
}
