/**
 * The map's own sources and layers (routes, checkpoints, endpoints, heatmap)
 * and their theme colours. MapView calls addAppLayers on first load and after
 * every basemap switch, since setStyle() drops everything added before.
 * Type-only imports from MapLibre: the library itself loads with MapView.
 */
import type { ExpressionSpecification, Map as MlMap } from 'maplibre-gl'

import type { Theme } from '../hooks/useTheme'
import { RISK_HEX, riskColorExpression } from './risk'

export const STYLE_URL: Record<Theme, string> = {
  light: 'https://tiles.openfreemap.org/styles/positron',
  dark: 'https://tiles.openfreemap.org/styles/dark',
}
export const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

/** Colours for our own map layers, per theme. */
const MAP_INK: Record<Theme, { casing: string; stroke: string; origin: string; destination: string; label: string }> = {
  light: { casing: '#ffffff', stroke: '#ffffff', origin: '#1f5f7a', destination: '#1b2633', label: '#ffffff' },
  dark: { casing: '#0e141b', stroke: '#1e2631', origin: '#6db3d1', destination: '#e3e9f0', label: '#0f2430' },
}

export function rgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`
}

/**
 * Colour for the forecast hour. Weights put each risk band in a 0.225-wide
 * slot starting at 0.1 (see heatWeight); stops sit at band midpoints so each
 * band shows its own colour. Weight 0 (no data / zero) is transparent.
 */
export function heatColorExpression(hour: number, theme: Theme): ExpressionSpecification {
  const c = RISK_HEX[theme]
  return [
    'interpolate', ['linear'], ['get', `w${hour}`],
    0, rgba(c.low, 0),
    0.1, rgba(c.low, 0.32),
    0.2125, rgba(c.low, 0.42),
    0.4375, rgba(c.moderate, 0.66),
    0.6625, rgba(c.high, 0.76),
    0.8875, rgba(c.severe, 0.82),
    1, rgba(c.no_travel, 0.88),
  ]
}

// Lucide "flag" (24x24 viewBox), drawn into the finish marker.
const FLAG_PATH =
  'M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.333 2q2 0 3.067-.8A1 1 0 0 1 20 4v10a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528'
const MARKER_PX = 30
const MARKER_RATIO = 2

/** Start (ringed dot) and finish (flag) marker images. Drawn on a canvas so
 *  they match the theme, and re-added after every style switch. */
function markerImage(kind: 'start' | 'finish', fill: string, ring: string, glyph: string): ImageData | null {
  const size = MARKER_PX * MARKER_RATIO
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.scale(MARKER_RATIO, MARKER_RATIO)
  const c = MARKER_PX / 2
  ctx.beginPath()
  ctx.arc(c, c, c - 2, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
  ctx.lineWidth = 3
  ctx.strokeStyle = ring
  ctx.stroke()
  if (kind === 'start') {
    ctx.beginPath()
    ctx.arc(c, c, 4.5, 0, Math.PI * 2)
    ctx.fillStyle = glyph
    ctx.fill()
  } else {
    const scale = 15 / 24
    ctx.translate(c - 12 * scale + 0.5, c - 12 * scale)
    ctx.scale(scale, scale)
    ctx.lineWidth = 2.4
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = glyph
    ctx.stroke(new Path2D(FLAG_PATH))
  }
  return ctx.getImageData(0, 0, size, size)
}

function addMarkerImages(map: MlMap, theme: Theme) {
  const ink = MAP_INK[theme]
  for (const [id, kind, fill] of [
    ['marker-start', 'start', ink.origin],
    ['marker-finish', 'finish', ink.destination],
  ] as const) {
    const image = markerImage(kind, fill, ink.stroke, ink.label)
    if (!image) continue
    if (map.hasImage(id)) map.removeImage(id)
    map.addImage(id, image, { pixelRatio: MARKER_RATIO })
  }
}

/** Add our sources and layers. Runs on first load and after every basemap
 *  (theme) switch, because setStyle() removes everything we added. */
export function addAppLayers(map: MlMap, theme: Theme) {
  const ink = MAP_INK[theme]
  // Keep basemap labels above our layers.
  const firstSymbol = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
  for (const id of ['heat', 'route-lines', 'route-segments', 'checkpoints', 'endpoints']) {
    if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data: EMPTY })
  }
  // Value-faithful "heatmap": soft, blurred circles coloured by each cell's
  // own value. (A density heatmap sums overlapping points, which would make
  // calm areas look dangerous.)
  map.addLayer(
    {
      id: 'heat',
      type: 'circle',
      source: 'heat',
      paint: {
        'circle-color': heatColorExpression(0, theme),
        'circle-blur': 0.85,
        'circle-opacity': theme === 'dark' ? 0.55 : 0.75,
        'circle-radius': 10,
        'circle-pitch-alignment': 'map',
      },
    },
    firstSymbol,
  )
  map.addLayer({
    id: 'route-casing',
    type: 'line',
    source: 'route-lines',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': ink.casing, 'line-width': 9, 'line-opacity': 0.9 },
  })
  map.addLayer({
    id: 'route-segments',
    type: 'line',
    source: 'route-segments',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': riskColorExpression(theme), 'line-width': 5 },
  })
  // Wide invisible line for easy clicking.
  map.addLayer({
    id: 'route-hit',
    type: 'line',
    source: 'route-lines',
    paint: { 'line-color': '#000', 'line-width': 18, 'line-opacity': 0 },
  })
  map.addLayer({
    id: 'checkpoints',
    type: 'circle',
    source: 'checkpoints',
    paint: {
      'circle-color': riskColorExpression(theme),
      'circle-stroke-color': ink.stroke,
      'circle-stroke-width': ['case', ['boolean', ['feature-state', 'hover'], false], 3, 1.5],
      'circle-radius': ['case', ['boolean', ['feature-state', 'hover'], false], 9, 5],
    },
  })
  addMarkerImages(map, theme)
  map.addLayer({
    id: 'endpoints',
    type: 'symbol',
    source: 'endpoints',
    layout: {
      'icon-image': ['match', ['get', 'kind'], 'origin', 'marker-start', 'marker-finish'],
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
  })
}
