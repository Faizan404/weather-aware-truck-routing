import { describe, expect, it } from 'vitest'

import type { HeatmapResponse, PlanResponse, RiskRules } from '../api/types'
import rulesJson from '../test/riskRules.fixture.json'
import { endpointsGeoJSON, heatmapGeoJSON, heatWeight } from './geojson'
import { heatScales } from './riskRules'

const scales = heatScales(rulesJson as RiskRules)

describe('heatWeight', () => {
  it('maps risk scores to evenly spaced weights', () => {
    expect(heatWeight(0, null)).toBeCloseTo(0.1)
    expect(heatWeight(4, null)).toBeCloseTo(1)
  })
  it('treats missing data as transparent', () => {
    expect(heatWeight(null, scales.wind.breaks)).toBe(0)
    expect(heatWeight(null, null)).toBe(0)
  })
  it('aligns band edges with the thresholds from /risk-rules/', () => {
    expect(heatWeight(25, scales.wind.breaks)).toBeCloseTo(0.1 + 0.225)
    expect(heatWeight(55, scales.wind.breaks)).toBe(1)
    expect(heatWeight(0.5, scales.rain.breaks)).toBeCloseTo(0.1 + 3 * 0.225)
    expect(heatWeight(0, scales.snow.breaks)).toBe(0)
  })
})

describe('heatmapGeoJSON', () => {
  const data = {
    hours: ['2026-11-20T14:00:00+00:00'],
    resolution_deg: 0.5,
    points: [[40, -100]],
    risk: [[2]],
    wind_mph: [[25]],
    rain_in_hr: [[0]],
    snow_in_hr: [[0]],
    warnings: [],
  } as HeatmapResponse

  it('colours wind by the backend thresholds', () => {
    expect(heatmapGeoJSON(data, 'wind', scales).features[0].properties?.w0).toBeCloseTo(0.325)
  })
  it('draws no raw layer without thresholds, but the risk layer still works', () => {
    expect(heatmapGeoJSON(data, 'wind', null).features).toEqual([])
    expect(heatmapGeoJSON(data, 'risk', null).features[0].properties?.w0).toBeCloseTo(0.1 + 0.45)
  })
})

describe('endpointsGeoJSON', () => {
  it('marks start and finish by kind, without letters that clash with route names', () => {
    const plan = { request: { origin: { lat: 40, lon: -100 }, destination: { lat: 41, lon: -99 } } } as PlanResponse
    const features = endpointsGeoJSON(plan).features
    expect(features.map((f) => f.properties)).toEqual([{ kind: 'origin' }, { kind: 'destination' }])
    expect(features[1].geometry.coordinates).toEqual([-99, 41])
  })
})
