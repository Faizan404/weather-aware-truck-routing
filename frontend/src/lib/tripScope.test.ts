import { expect, test } from 'vitest'

import type { PlanResponse } from '../api/types'
import { readScoped, tripKeyOf } from './tripScope'

const plan = (interval: number, load = 35000) =>
  ({
    request: {
      origin: { lat: 41.88, lon: -87.63 },
      destination: { lat: 39.74, lon: -104.99 },
      departure_time: '2026-11-20T14:00:00+00:00',
      load_weight_lbs: load,
      interval_miles: interval,
    },
  }) as PlanResponse

test('changing only the interval is the same trip', () => {
  expect(tripKeyOf(plan(10))).toBe(tripKeyOf(plan(25)))
  expect(tripKeyOf(plan(25, 40000))).not.toBe(tripKeyOf(plan(25)))
  expect(tripKeyOf(null)).toBeNull()
})

test('a choice is kept for its trip and reset for a new one', () => {
  const chosen = { key: tripKeyOf(plan(25)), value: 'B' }
  expect(readScoped(chosen, tripKeyOf(plan(10)), 'A')).toBe('B') // interval change keeps it
  expect(readScoped(chosen, tripKeyOf(plan(25, 40000)), 'A')).toBe('A') // new trip: recommended route
  expect(readScoped(null, tripKeyOf(plan(25)), 'A')).toBe('A')
})
