/**
 * Turns GET /risk-rules/ into what the UI shows: the legend's threshold table
 * and load rules, and the Wind/Rain/Snow heatmap scales. No threshold is
 * written in the frontend; the backend's risk/rules.py is the only source.
 */
import type { ConditionKey, KnownRiskKey, RiskBand, RiskRules } from '../api/types'

export const CONDITIONS: ConditionKey[] = ['wind', 'rain', 'snow']
const CONDITION_LABEL: Record<ConditionKey, string> = { wind: 'Wind', rain: 'Rain', snow: 'Snow' }

/** Decimals the spec writes a condition's thresholds with (25 / 0.10 / 0.5). */
function decimalsOf(values: number[]): number {
  return Math.max(0, ...values.map((v) => (String(v).split('.')[1] ?? '').length))
}

/** Rain thresholds come as 0.1 but the spec writes 0.10: pad to the widest. */
function bandMins(bands: RiskBand[]) {
  const mins = bands.slice(1).map((b) => b.min as number)
  return { mins, digits: decimalsOf(mins) }
}

/**
 * One label per level, as the spec's table writes them:
 * wind "< 25", "25–34", ..., "≥ 55"; rain "< 0.10", "0.10–0.25", ..., "> 1.00".
 * Whole-number thresholds (wind) show a band as min to next-1, since
 * [25, 35) is "25–34"; decimal ones show min to next.
 */
export function bandLabels(bands: RiskBand[]): string[] {
  const { mins, digits } = bandMins(bands)
  const fmt = (v: number) => v.toFixed(digits)
  return bands.map((band, i) => {
    if (i === 0) return `< ${fmt(mins[0])}`
    const min = band.min as number
    if (i === bands.length - 1) return `${band.min_inclusive ? '≥' : '>'} ${fmt(min)}`
    const next = bands[i + 1].min as number
    const upper = digits === 0 && bands[i + 1].min_inclusive ? next - 1 : next
    return `${fmt(min)}–${fmt(upper)}`
  })
}

export interface ThresholdRow {
  condition: string
  unit: string
  values: string[]
}

export function thresholdRows(rules: RiskRules): ThresholdRow[] {
  return CONDITIONS.map((key) => {
    const bands = rules.conditions[key]
    return { condition: CONDITION_LABEL[key], unit: bands[0]?.unit ?? '', values: bandLabels(bands) }
  })
}

export interface LoadRuleRow {
  wind: string
  load: string
  result: KnownRiskKey
}

export function loadRuleRows(rules: RiskRules): LoadRuleRow[] {
  return rules.load_rules.map((r) => ({
    wind: r.wind_max_mph === undefined ? `${r.wind_min_mph} mph or more` : `${r.wind_min_mph}–${r.wind_max_mph} mph`,
    load: r.load_over_lbs === null ? 'any load' : `over ${r.load_over_lbs.toLocaleString('en-US')} lb`,
    result: r.result,
  }))
}

export interface HeatScale {
  /** Value at the start of each band: [0, moderate, high, severe, no travel]. */
  breaks: number[]
  /** Tick labels under the colour bar. */
  labels: string[]
  unit: string
}

export type HeatScales = Record<ConditionKey, HeatScale>

export function heatScales(rules: RiskRules): HeatScales {
  const out = {} as HeatScales
  for (const key of CONDITIONS) {
    const bands = rules.conditions[key]
    const { mins, digits } = bandMins(bands)
    out[key] = {
      breaks: [0, ...mins],
      labels: ['0', ...mins.map((m, i) => m.toFixed(digits) + (i === mins.length - 1 ? '+' : ''))],
      unit: bands[0]?.unit ?? '',
    }
  }
  return out
}
