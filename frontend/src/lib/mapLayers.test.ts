import { afterEach, expect, test, vi } from 'vitest'

import { addAppLayers, EMPTY, heatColorExpression, rgba, STYLE_URL } from './mapLayers'
import { RISK_HEX } from './risk'

afterEach(() => vi.unstubAllGlobals())

test('basemap per theme', () => {
  expect(STYLE_URL.light).toMatch(/^https:\/\/tiles\.openfreemap\.org\//)
  expect(STYLE_URL.dark).toMatch(/^https:\/\/tiles\.openfreemap\.org\//)
})

test('heat colour reads the slider hour and is transparent without data', () => {
  const expr = heatColorExpression(7, 'light') as unknown[]
  expect(expr[2]).toEqual(['get', 'w7'])
  expect(expr[3]).toBe(0)
  expect(expr[4]).toBe(rgba(RISK_HEX.light.low, 0))
  expect(expr.at(-1)).toBe(rgba(RISK_HEX.light.no_travel, 0.88))
  expect(rgba('#ff8000', 0.5)).toBe('rgba(255,128,0,0.5)')
})

test('layers are added in drawing order, below basemap labels', () => {
  // A stand-in map that records calls; markers need a canvas, which is absent here.
  vi.stubGlobal('document', { createElement: () => ({ getContext: () => null }) })
  const sources: string[] = []
  const layers: { id: string; before?: string }[] = []
  const map = {
    getStyle: () => ({ layers: [{ id: 'water', type: 'fill' }, { id: 'place-labels', type: 'symbol' }] }),
    getSource: () => undefined,
    addSource: (id: string, spec: { data: unknown }) => {
      expect(spec.data).toBe(EMPTY)
      sources.push(id)
    },
    addLayer: (layer: { id: string }, before?: string) => layers.push({ id: layer.id, before }),
    hasImage: () => false,
    addImage: vi.fn(),
    removeImage: vi.fn(),
  }
  addAppLayers(map as never, 'dark')
  expect(sources).toEqual(['heat', 'route-lines', 'route-segments', 'checkpoints', 'endpoints'])
  expect(layers.map((l) => l.id)).toEqual(['heat', 'route-casing', 'route-segments', 'route-hit', 'checkpoints', 'endpoints'])
  expect(layers[0].before).toBe('place-labels') // heat stays under the place names
})
