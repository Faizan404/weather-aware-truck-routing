import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test } from 'vitest'

import type { PlanResponse, RouteOption } from '../api/types'
import { RouteCards } from './RouteCards'

function route(id: string): RouteOption {
  return {
    id,
    label: `Route ${id}`,
    via: [],
    provider: 'osrm',
    synthetic: false,
    distance_miles: 100,
    duration_seconds: 7200,
    arrival: '2026-11-20T16:00:00+00:00',
    geometry: '',
    segments: [],
    checkpoints: [],
    summary: {
      miles_by_level: { low: 100, moderate: 0, high: 0, severe: 0, no_travel: 0 },
      unknown_miles: 0,
      avg_risk: 0,
      max_level: 'low',
      checkpoint_count: 5,
      incomplete: false,
    },
  }
}

// Routes arrive A, B, C but are ranked C, A, B: cards follow the ranking.
const plan: PlanResponse = {
  request: {
    origin: { lat: 0, lon: 0 },
    destination: { lat: 1, lon: 1 },
    departure_time: '2026-11-20T14:00:00+00:00',
    load_weight_lbs: 35000,
    interval_miles: 25,
  },
  routes: [route('A'), route('B'), route('C')],
  recommendation: { route_id: 'C', ranking: ['C', 'A', 'B'], criterion: null, reason: '', no_safe_route: false, notes: [] },
  warnings: [],
  generated_at: '2026-11-20T13:00:00+00:00',
}

function radios(selectedRouteId: string | null) {
  const html = renderToStaticMarkup(<RouteCards plan={plan} selectedRouteId={selectedRouteId} onSelect={() => {}} />)
  const doc = html.match(/<button[^>]*role="radio"[^>]*>/g) ?? []
  return doc.map((tag) => ({
    checked: tag.includes('aria-checked="true"'),
    tabIndex: Number(tag.match(/tabindex="(-?\d+)"/)?.[1]),
  }))
}

test('only the selected card is in the tab order', () => {
  // Visual order is C, A, B; B is the third card.
  expect(radios('B')).toEqual([
    { checked: false, tabIndex: -1 },
    { checked: false, tabIndex: -1 },
    { checked: true, tabIndex: 0 },
  ])
})

test('with nothing selected, the first card is the tab stop', () => {
  expect(radios(null).map((r) => r.tabIndex)).toEqual([0, -1, -1])
})
