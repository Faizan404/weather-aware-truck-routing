import { expect, test } from 'vitest'

import type { Checkpoint, RouteOption } from '../api/types'
import { popupHtml } from './mapPopup'

const cp = {
  index: 3,
  mile: 75.4,
  lat: 40,
  lon: -100,
  eta: '2026-11-20T15:00:00+00:00',
  wind_mph: 47,
  rain_in_hr: 0,
  snow_in_hr: 0,
  level: 'no_travel',
  wind_level: 'no_travel',
  rain_level: 'low',
  snow_level: 'low',
  reasons: ['Wind 47 mph + 35,000 lb load <b>'],
} as Checkpoint

test('popup shows the checkpoint and escapes text', () => {
  const html = popupHtml({ label: 'Route <A>' } as RouteOption, cp)
  expect(html).toContain('Route &lt;A&gt;, mile 75')
  expect(html).toContain('No Travel')
  expect(html).toContain('47.0 mph')
  expect(html).toContain('Wind 47 mph + 35,000 lb load &lt;b&gt;')
  expect(html).not.toContain('<b>')
})
