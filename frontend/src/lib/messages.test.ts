import { expect, test } from 'vitest'

import backendServices from '../../../backend/planner/services.py?raw'
import { WEATHER_LIMIT_MESSAGE } from './messages'

test('rate-limit text matches the warning the backend sends', () => {
  expect(backendServices).toContain(`RATE_LIMIT_WARNING = "${WEATHER_LIMIT_MESSAGE}"`)
})
