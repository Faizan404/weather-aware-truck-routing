import type { ExpressionSpecification } from 'maplibre-gl'

import type { KnownRiskKey, RiskKey } from '../api/types'
import type { Theme } from '../hooks/useTheme'

export const RISK_ORDER: KnownRiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

export const RISK_LABEL: Record<RiskKey, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
  unknown: 'Unknown',
}

/** CSS variable for a risk colour (follows the theme automatically). */
export const riskVar = (key: RiskKey) => `var(--risk-${key.replace('_', '-')})`

/** Text colour that stays readable on each risk colour. */
export const RISK_TEXT: Record<RiskKey, string> = {
  low: '#ffffff',
  moderate: '#2a2104',
  high: '#ffffff',
  severe: '#ffffff',
  no_travel: '#ffffff',
  unknown: '#ffffff',
}

/** Concrete hex values for the map (MapLibre can't read CSS variables).
 *  Kept in sync with the --risk-* tokens in index.css. */
export const RISK_HEX: Record<Theme, Record<RiskKey, string>> = {
  light: {
    low: '#3e9b6b',
    moderate: '#d6a21e',
    high: '#de7731',
    severe: '#cf4038',
    no_travel: '#7149a6',
    unknown: '#8d99a7',
  },
  dark: {
    low: '#4fb07f',
    moderate: '#e2b23a',
    high: '#ec8a45',
    severe: '#e0574f',
    no_travel: '#9a76d1',
    unknown: '#7d8998',
  },
}

/** MapLibre `match` expression: level key -> colour, for the current theme. */
export function riskColorExpression(theme: Theme): ExpressionSpecification {
  const hex = RISK_HEX[theme]
  return [
    'match',
    ['get', 'level'],
    ...Object.entries(hex).flatMap(([key, color]) => [key, color]),
    hex.unknown,
  ] as unknown as ExpressionSpecification
}
