import { afterEach, expect, test, vi } from 'vitest'

import { ApiError, TIMEOUT_MESSAGE, TIMEOUT_MS, api } from './client'

afterEach(() => vi.unstubAllGlobals())

function respond(status: number, body: unknown, headers: Record<string, string> = {}) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status, headers })))
}

test('a throttled request says when to try again', async () => {
  respond(429, { error: { code: 'throttled', message: 'Request was throttled.', details: {} } }, { 'Retry-After': '12' })
  const err = await api.geocode('denver').catch((e: unknown) => e)
  expect(err).toBeInstanceOf(ApiError)
  expect((err as ApiError).message).toBe('Too many requests. Try again in 12 seconds.')
})

test('a throttled request without Retry-After still reads well', async () => {
  respond(429, { error: { code: 'throttled', message: 'x', details: {} } })
  const err = (await api.geocode('denver').catch((e: unknown) => e)) as ApiError
  expect(err.message).toBe('Too many requests. Try again in a minute.')
})

// --- Headers and timeouts ----------------------------------------------------

/** AbortSignal.timeout runs on a native timer that fake timers can't advance;
 *  in tests it is replaced by a setTimeout-based signal they can. */
function fakeTimeoutSignals() {
  const spy = vi.spyOn(AbortSignal, 'timeout').mockImplementation((ms: number) => {
    const controller = new AbortController()
    setTimeout(() => controller.abort(new DOMException('signal timed out', 'TimeoutError')), ms)
    return controller.signal
  })
  return spy
}

/** A fetch that never answers until its signal aborts. */
function hangingFetch() {
  const fetchMock = vi.fn(
    (_url: string, init?: RequestInit) =>
      new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener('abort', () => reject(init.signal?.reason ?? new DOMException('aborted', 'AbortError')))
      }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

test('GET requests send no Content-Type, so they need no CORS preflight', async () => {
  respond(200, { results: [] })
  await api.geocode('denver')
  const init = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit
  expect(init.headers).toBeUndefined()
  expect(init.body).toBeUndefined()
})

test('POST requests send JSON with a Content-Type', async () => {
  respond(200, {})
  await api.heatmap({ polylines: ['abc'], departure_time: '2026-11-20T14:00:00Z', load_weight_lbs: 1000 })
  const init = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit
  expect(init.method).toBe('POST')
  expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
  expect(JSON.parse(init.body as string).load_weight_lbs).toBe(1000)
})

test('geocode gives up after 10 s with a clear message', async () => {
  vi.useFakeTimers()
  const timeouts = fakeTimeoutSignals()
  hangingFetch()
  const result = api.geocode('denver').catch((e: unknown) => e)
  await vi.advanceTimersByTimeAsync(9_999)
  await vi.advanceTimersByTimeAsync(1)
  const err = (await result) as ApiError
  expect(timeouts).toHaveBeenCalledWith(TIMEOUT_MS.geocode)
  expect(err).toBeInstanceOf(ApiError)
  expect(err.code).toBe('timeout')
  expect(err.message).toBe(TIMEOUT_MESSAGE)
})

test('a plan may wait 90 s (cold start plus the server budget) before timing out', async () => {
  vi.useFakeTimers()
  fakeTimeoutSignals()
  hangingFetch()
  let settled = false
  const result = api
    .plan({
      origin: { label: 'A', lat: 32.78, lon: -96.8 },
      destination: { label: 'B', lat: 29.76, lon: -95.37 },
      departure_time: '2026-11-20T14:00:00Z',
      load_weight_lbs: 1000,
      interval_miles: 50,
    })
    .catch((e: unknown) => e)
    .finally(() => (settled = true))
  await vi.advanceTimersByTimeAsync(89_000)
  expect(settled).toBe(false)
  await vi.advanceTimersByTimeAsync(1_000)
  expect(((await result) as ApiError).code).toBe('timeout')
})

test('a request cancelled by the caller stays an AbortError (TanStack cancellation)', async () => {
  hangingFetch()
  const controller = new AbortController()
  const result = api.geocode('denver', controller.signal).catch((e: unknown) => e)
  controller.abort()
  const err = (await result) as Error
  expect(err).not.toBeInstanceOf(ApiError)
  expect(err.name).toBe('AbortError')
})

test('a network failure says the server cannot be reached', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
  const err = (await api.geocode('denver').catch((e: unknown) => e)) as ApiError
  expect(err.code).toBe('network_error')
})
