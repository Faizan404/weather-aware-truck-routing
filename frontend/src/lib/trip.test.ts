import { describe, expect, test } from 'vitest'

import { draftMatchesTrip, showPlanError, toPlanRequest, type TripDraft, type TripInput } from './trip'

const chicago = { label: 'Chicago, Illinois, United States', lat: 41.8755616, lon: -87.6244212 }
const denver = { label: 'Denver, Colorado, United States', lat: 39.7392364, lon: -104.984862 }
const trip: TripInput = {
  origin: chicago,
  destination: denver,
  departureLocal: '2026-11-20T08:00',
  loadWeightLbs: 35000,
  intervalMiles: 25,
}
const draft: TripDraft = { origin: chicago, destination: denver, departureLocal: '2026-11-20T08:00', load: '35000' }

describe('interval change re-plans only when the form matches the trip on screen', () => {
  test('unchanged form matches, so a new interval re-plans', () => {
    expect(draftMatchesTrip(draft, trip)).toBe(true)
    expect(draftMatchesTrip({ ...draft, load: ' 35000 ' }, trip)).toBe(true)
  })

  test('no trip on screen yet: wait for submit', () => {
    expect(draftMatchesTrip(draft, null)).toBe(false)
  })

  test.each<[string, Partial<TripDraft>]>([
    ['origin changed', { origin: { label: 'Dallas, Texas, United States', lat: 32.78, lon: -96.8 } }],
    ['origin cleared', { origin: null }],
    ['destination changed', { destination: chicago }],
    ['departure edited', { departureLocal: '2026-11-20T09:00' }],
    ['load edited', { load: '40000' }],
    ['load emptied', { load: '' }],
    ['load not a number', { load: 'abc' }],
  ])('%s: wait for submit', (_, change) => {
    expect(draftMatchesTrip({ ...draft, ...change }, trip)).toBe(false)
  })
})

describe('server error banner', () => {
  const failed = { isError: true, isFetching: false, errorUpdatedAt: 1_000 }

  test('shows a fresh error', () => {
    expect(showPlanError(failed, 0)).toBe(true)
  })

  test('hides once the form is edited after the error', () => {
    expect(showPlanError(failed, 1_500)).toBe(false)
  })

  test('hides while a new submit is running', () => {
    expect(showPlanError({ ...failed, isFetching: true }, 0)).toBe(false)
  })

  test('shows again when the new submit fails too', () => {
    // Edited at 1,500, re-submitted, failed again at 2,000.
    expect(showPlanError({ ...failed, errorUpdatedAt: 2_000 }, 1_500)).toBe(true)
  })

  test('nothing to show without an error', () => {
    expect(showPlanError({ isError: false, isFetching: false, errorUpdatedAt: 0 }, 0)).toBe(false)
  })
})

test('a submitted trip becomes the API request', () => {
  const trip: TripInput = {
    origin: { label: 'Chicago', lat: 41.88, lon: -87.63 },
    destination: { label: 'Denver', lat: 39.74, lon: -104.99 },
    departureLocal: '2026-11-20T08:00',
    loadWeightLbs: 35000,
    intervalMiles: 10,
  }
  const req = toPlanRequest(trip)
  expect(req.interval_miles).toBe(10)
  expect(req.load_weight_lbs).toBe(35000)
  expect(req.departure_time).toBe(new Date('2026-11-20T08:00').toISOString())
})
