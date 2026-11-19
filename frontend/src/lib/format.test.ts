import { describe, expect, it } from 'vitest'

import { defaultDeparture, formatDuration, parseLatLon } from './format'

describe('formatDuration', () => {
  it('formats minutes and hours', () => {
    expect(formatDuration(45 * 60)).toBe('45 min')
    expect(formatDuration(3600 * 17 + 48 * 60)).toBe('17h 48m')
    expect(formatDuration(3600 * 2 + 5 * 60)).toBe('2h 05m')
  })
})

describe('parseLatLon', () => {
  it('accepts comma or space separated coordinates', () => {
    expect(parseLatLon('41.88, -87.63')).toEqual({ lat: 41.88, lon: -87.63 })
    expect(parseLatLon('41.88 -87.63')).toEqual({ lat: 41.88, lon: -87.63 })
  })
  it('rejects text and out-of-range values', () => {
    expect(parseLatLon('Chicago')).toBeNull()
    expect(parseLatLon('95, 10')).toBeNull()
    expect(parseLatLon('10, 190')).toBeNull()
  })
})

describe('defaultDeparture', () => {
  it('rounds up to the next quarter hour', () => {
    expect(defaultDeparture(new Date(2026, 10, 17, 10, 7))).toBe('2026-11-17T10:15')
    expect(defaultDeparture(new Date(2026, 10, 17, 10, 59))).toBe('2026-11-17T11:00')
    expect(defaultDeparture(new Date(2026, 10, 17, 10, 15))).toBe('2026-11-17T10:30')
  })
})
