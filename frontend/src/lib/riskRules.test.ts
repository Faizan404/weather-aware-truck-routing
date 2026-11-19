import { describe, expect, test } from 'vitest'

import type { RiskRules } from '../api/types'
import rulesJson from '../test/riskRules.fixture.json'
import geojsonSource from './geojson.ts?raw'
import legendSource from '../components/Legend.tsx?raw'
import riskSource from './risk.ts?raw'
import { bandLabels, heatScales, loadRuleRows, thresholdRows } from './riskRules'

// Captured from GET /api/v1/risk-rules/ (backend tests pin the same values).
const rules = rulesJson as RiskRules

describe('legend table built from /risk-rules/', () => {
  test('matches the spec table', () => {
    expect(thresholdRows(rules)).toEqual([
      { condition: 'Wind', unit: 'mph', values: ['< 25', '25–34', '35–44', '45–54', '≥ 55'] },
      { condition: 'Rain', unit: 'in/hr', values: ['< 0.10', '0.10–0.25', '0.25–0.50', '0.50–1.00', '> 1.00'] },
      { condition: 'Snow', unit: 'in/hr', values: ['< 0.5', '0.5–1.0', '1.0–2.0', '2.0–3.0', '> 3.0'] },
    ])
  })

  test('follows the backend when a threshold changes', () => {
    const wind = rules.conditions.wind.map((b) => (b.level === 'severe' ? { ...b, min: 50 } : b))
    expect(bandLabels(wind)).toEqual(['< 25', '25–34', '35–49', '50–54', '≥ 55'])
  })

  test('load rules read as sentences, with "any load" for no weight limit', () => {
    expect(loadRuleRows(rules)).toEqual([
      { wind: '55 mph or more', load: 'any load', result: 'no_travel' },
      { wind: '45–54 mph', load: 'over 30,000 lb', result: 'no_travel' },
      { wind: '35–44 mph', load: 'over 40,000 lb', result: 'severe' },
    ])
  })
})

describe('heatmap scales built from /risk-rules/', () => {
  test('breaks and tick labels per condition', () => {
    const scales = heatScales(rules)
    expect(scales.wind).toEqual({ breaks: [0, 25, 35, 45, 55], labels: ['0', '25', '35', '45', '55+'], unit: 'mph' })
    expect(scales.rain).toEqual({
      breaks: [0, 0.1, 0.25, 0.5, 1],
      labels: ['0', '0.10', '0.25', '0.50', '1.00+'],
      unit: 'in/hr',
    })
    expect(scales.snow.breaks).toEqual([0, 0.5, 1, 2, 3])
    expect(scales.snow.labels).toEqual(['0', '0.5', '1.0', '2.0', '3.0+'])
  })
})

test('no threshold is hard-coded in the legend or heatmap code', () => {
  for (const source of [geojsonSource, legendSource, riskSource]) {
    for (const token of ['0.10', '0.25', '30,000', '40,000', '55+', '< 25', '[0, 25', 'THRESHOLDS', 'LOAD_RULES', 'BREAKS']) {
      expect(source).not.toContain(token)
    }
  }
})
