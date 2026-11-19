import polyline from '@mapbox/polyline'

import type { HeatmapResponse, PlanResponse } from '../api/types'
import type { HeatScales } from './riskRules'

type LngLat = [number, number]

/** Decode a precision-5 polyline into GeoJSON [lon, lat] order. */
export function decodeLine(encoded: string): LngLat[] {
  return polyline.decode(encoded).map(([lat, lon]) => [lon, lat])
}

export function routeSegmentsGeoJSON(plan: PlanResponse): GeoJSON.FeatureCollection<GeoJSON.LineString> {
  const features: GeoJSON.Feature<GeoJSON.LineString>[] = []
  for (const route of plan.routes) {
    for (const seg of route.segments) {
      features.push({
        type: 'Feature',
        properties: { routeId: route.id, level: seg.level },
        geometry: { type: 'LineString', coordinates: decodeLine(seg.polyline) },
      })
    }
  }
  return { type: 'FeatureCollection', features }
}

export function routeLinesGeoJSON(plan: PlanResponse): GeoJSON.FeatureCollection<GeoJSON.LineString> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.map((route) => ({
      type: 'Feature',
      properties: { routeId: route.id },
      geometry: { type: 'LineString', coordinates: decodeLine(route.geometry) },
    })),
  }
}

export function checkpointsGeoJSON(plan: PlanResponse): GeoJSON.FeatureCollection<GeoJSON.Point> {
  const features: GeoJSON.Feature<GeoJSON.Point>[] = []
  plan.routes.forEach((route) => {
    route.checkpoints.forEach((cp) => {
      features.push({
        type: 'Feature',
        // Numeric id so feature-state (hover highlight) works.
        id: route.id.charCodeAt(0) * 100_000 + cp.index,
        properties: { routeId: route.id, index: cp.index, level: cp.level },
        geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
      })
    })
  })
  return { type: 'FeatureCollection', features }
}

export const checkpointFeatureId = (routeId: string, index: number) => routeId.charCodeAt(0) * 100_000 + index

export function endpointsGeoJSON(plan: PlanResponse): GeoJSON.FeatureCollection<GeoJSON.Point> {
  const { origin, destination } = plan.request
  return {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', properties: { kind: 'origin' }, geometry: { type: 'Point', coordinates: [origin.lon, origin.lat] } },
      { type: 'Feature', properties: { kind: 'destination' }, geometry: { type: 'Point', coordinates: [destination.lon, destination.lat] } },
    ],
  }
}

export function planBounds(plan: PlanResponse): [LngLat, LngLat] {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity
  for (const route of plan.routes) {
    for (const [lon, lat] of decodeLine(route.geometry)) {
      if (lon < minLon) minLon = lon
      if (lon > maxLon) maxLon = lon
      if (lat < minLat) minLat = lat
      if (lat > maxLat) maxLat = lat
    }
  }
  return [[minLon, minLat], [maxLon, maxLat]]
}

// --- Heatmap ----------------------------------------------------------------

export type HeatMetric = 'risk' | 'wind' | 'rain' | 'snow'

export const HEAT_METRIC_LABEL: Record<HeatMetric, string> = { risk: 'Risk', wind: 'Wind', rain: 'Rain', snow: 'Snow' }

/**
 * Map a value to a 0..1 heat weight, so the heat colour lines up with the risk
 * colours (one 0.225 slot per band after 0.1). Risk uses the score (0..4);
 * wind/rain/snow use the band breaks from /risk-rules/. Null (no data, or no
 * breaks to place the value with) -> 0, i.e. transparent.
 */
export function heatWeight(value: number | null, breaks: number[] | null): number {
  if (value === null) return 0
  if (breaks === null) return 0.1 + (value / 4) * 0.9 // risk score
  if (value <= 0) return 0
  const last = breaks.length - 1
  if (value >= breaks[last]) return 1
  for (let i = 0; i < last; i++) {
    if (value < breaks[i + 1]) {
      const t = (value - breaks[i]) / (breaks[i + 1] - breaks[i])
      return 0.1 + (i + t) * (0.9 / last)
    }
  }
  return 1
}

/**
 * One feature per grid cell, with a weight property per forecast hour
 * (w0..w48). The slider then only swaps the paint expression; no data is
 * re-uploaded while scrubbing.
 */
export function heatmapGeoJSON(
  data: HeatmapResponse,
  metric: HeatMetric,
  scales: HeatScales | null,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  const source =
    metric === 'risk' ? data.risk : metric === 'wind' ? data.wind_mph : metric === 'rain' ? data.rain_in_hr : data.snow_in_hr
  let breaks: number[] | null = null
  if (metric !== 'risk') {
    // Without thresholds, wind/rain/snow can't be coloured honestly: draw nothing.
    if (!scales) return { type: 'FeatureCollection', features: [] }
    breaks = scales[metric].breaks
  }
  return {
    type: 'FeatureCollection',
    features: data.points.map(([lat, lon], i) => {
      const properties: Record<string, number> = {}
      source[i].forEach((value, h) => {
        properties[`w${h}`] = heatWeight(value, breaks)
      })
      return { type: 'Feature', properties, geometry: { type: 'Point', coordinates: [lon, lat] } }
    }),
  }
}
