import { renderToStaticMarkup } from 'react-dom/server'
import { expect, test } from 'vitest'

import type { RiskRules } from '../api/types'
import rulesJson from '../test/riskRules.fixture.json'
import { Legend } from './Legend'

test('with thresholds, the legend offers the risk rules', () => {
  const html = renderToStaticMarkup(<Legend rules={rulesJson as RiskRules} />)
  expect(html).toContain('Risk rules')
  expect(html).toContain('No Travel')
})

test('if /risk-rules/ fails, the legend shows the colours without numbers', () => {
  const html = renderToStaticMarkup(<Legend rules={null} />)
  for (const label of ['Low', 'Moderate', 'High', 'Severe', 'No Travel', 'Unknown']) expect(html).toContain(label)
  expect(html).not.toContain('Risk rules')
  expect(html.replace(/<[^>]*>/g, '')).not.toMatch(/\d/)
})
