import { expect, test } from 'vitest'

import { ApiError } from '../api/client'
import { errorMessages } from './errors'

test('validation errors list each field message', () => {
  const err = new ApiError(400, 'validation_error', 'Invalid request.', {
    origin: ['The origin must be in the United States.'],
  })
  expect(errorMessages(err)).toEqual(['The origin must be in the United States.'])
})

test('other API errors show the message and any reason', () => {
  const err = new ApiError(422, 'no_route', 'No drivable route was found.', { reason: 'Impossible route' })
  expect(errorMessages(err)).toEqual(['No drivable route was found.', 'Impossible route'])
  expect(errorMessages(new ApiError(503, 'upstream_timeout', 'The request took too long.'))).toEqual([
    'The request took too long.',
  ])
})

test('anything else gets a generic line', () => {
  expect(errorMessages(new Error('boom'))).toEqual(['Something went wrong. Please try again.'])
})
