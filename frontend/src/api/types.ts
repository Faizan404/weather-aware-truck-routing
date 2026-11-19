export type RiskKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel' | 'unknown'
export type KnownRiskKey = Exclude<RiskKey, 'unknown'>

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface PlanRequest {
  origin: Place
  destination: Place
  departure_time: string // ISO 8601 with offset
  load_weight_lbs: number
  interval_miles: 10 | 25 | 50
}

export interface Checkpoint {
  index: number
  mile: number
  lat: number
  lon: number
  eta: string
  elapsed_seconds: number
  coverage_miles: number
  wind_mph: number | null
  rain_in_hr: number | null
  snow_in_hr: number | null
  level: RiskKey
  wind_level: RiskKey
  rain_level: RiskKey
  snow_level: RiskKey
  reasons: string[]
  incomplete: boolean
}

export interface RouteSummary {
  miles_by_level: Record<KnownRiskKey, number>
  unknown_miles: number
  avg_risk: number | null
  max_level: RiskKey
  checkpoint_count: number
  incomplete: boolean
}

export interface RouteOption {
  id: string
  label: string
  via: string[]
  provider: string
  synthetic: boolean
  distance_miles: number
  duration_seconds: number
  arrival: string
  geometry: string // encoded polyline, precision 5
  segments: { level: RiskKey; polyline: string }[]
  checkpoints: Checkpoint[]
  summary: RouteSummary
}

export interface Recommendation {
  route_id: string
  ranking: string[]
  criterion: string | null
  reason: string
  no_safe_route: boolean
  notes: string[]
}

export interface PlanResponse {
  request: {
    origin: { lat: number; lon: number }
    destination: { lat: number; lon: number }
    departure_time: string
    load_weight_lbs: number
    interval_miles: number
  }
  routes: RouteOption[]
  recommendation: Recommendation
  warnings: string[]
  generated_at: string
}

export interface HeatmapResponse {
  hours: string[]
  resolution_deg: number
  points: [number, number][]
  risk: (number | null)[][]
  wind_mph: (number | null)[][]
  rain_in_hr: (number | null)[][]
  snow_in_hr: (number | null)[][]
  warnings: string[]
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> }
}

/** GET /risk-rules/: the spec's thresholds, the single source for the legend and heatmap scales. */
export interface RiskBand {
  level: KnownRiskKey
  min: number | null // null for Low (no lower bound)
  min_inclusive: boolean
  unit: string
}

export type ConditionKey = 'wind' | 'rain' | 'snow'

export interface LoadRule {
  wind_min_mph: number
  wind_max_mph?: number
  load_over_lbs: number | null // null = any load
  result: KnownRiskKey
}

export interface RiskRules {
  levels: { key: RiskKey; label: string; score: number | null }[]
  conditions: Record<ConditionKey, RiskBand[]>
  load_rules: LoadRule[]
}
