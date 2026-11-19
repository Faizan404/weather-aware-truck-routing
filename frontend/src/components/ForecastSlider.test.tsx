import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test } from 'vitest'

import type { RiskRules } from '../api/types'
import { heatScales } from '../lib/riskRules'
import rulesJson from '../test/riskRules.fixture.json'
import { ForecastSlider } from './ForecastSlider'

function render(metric: 'risk' | 'wind', scales: ReturnType<typeof heatScales> | null) {
  return renderToStaticMarkup(
    <ForecastSlider
      hours={null}
      hour={0}
      onHourChange={() => {}}
      metric={metric}
      onMetricChange={() => {}}
      visible
      onVisibleChange={() => {}}
      loading={false}
      error={null}
      hourHasNoData={false}
      rateLimited={false}
      scales={scales}
    />,
  )
}

function layerButtons(html: string) {
  return (html.match(/<button[^>]*role="radio"[^>]*>.*?<\/button>/g) ?? []).map((b) => ({
    label: b.replace(/<[^>]*>/g, ''),
    disabled: /\sdisabled=""/.test(b),
  }))
}

test('wind scale ticks come from /risk-rules/', () => {
  const html = render('wind', heatScales(rulesJson as RiskRules))
  for (const tick of ['>0<', '>25<', '>35<', '>45<', '>55+<']) expect(html).toContain(tick)
  expect(layerButtons(html).every((b) => !b.disabled)).toBe(true)
})

test('without thresholds only the risk layer is available', () => {
  expect(layerButtons(render('risk', null))).toEqual([
    { label: 'Risk', disabled: false },
    { label: 'Wind', disabled: true },
    { label: 'Rain', disabled: true },
    { label: 'Snow', disabled: true },
  ])
})
