import { afterEach, expect, test, vi } from 'vitest'

// The Vercel function lives in api/ (every file there becomes a function), so
// its tests live here.
// @ts-expect-error -- a plain-JS Vercel function, deliberately untyped
import handler from '../api/v1/forecast.js'

afterEach(() => vi.unstubAllGlobals())

function fakeRes() {
  const res = {
    statusCode: 200,
    headers: {} as Record<string, string>,
    body: undefined as unknown,
    status(code: number) {
      res.statusCode = code
      return res
    },
    setHeader(name: string, value: string) {
      res.headers[name] = value
      return res
    },
    json(value: unknown) {
      res.body = value
      return res
    },
    send(value: unknown) {
      res.body = value
      return res
    },
  }
  return res
}

const QUERY = '?latitude=41.9,39.7&longitude=-87.6,-105.0&hourly=wind_speed_10m,rain,showers,snowfall&timezone=GMT'

test('forwards the query unchanged to Open-Meteo and relays the answer', async () => {
  const fetchMock = vi.fn(async () => new Response('[{"hourly":{}}]', { status: 200, headers: { 'content-type': 'application/json; charset=utf-8' } }))
  vi.stubGlobal('fetch', fetchMock)
  const res = fakeRes()
  await handler({ method: 'GET', url: `/api/v1/forecast${QUERY}` }, res)
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  expect(url).toBe(`https://api.open-meteo.com/v1/forecast${QUERY}`)
  expect((init.headers as Record<string, string>)['User-Agent']).toContain('github.com/Faizan404/weather-aware-truck-routing')
  expect(res.statusCode).toBe(200)
  expect(res.headers['Content-Type']).toBe('application/json; charset=utf-8')
  expect(res.body).toBe('[{"hourly":{}}]')
})

test('passes a 429 and its Retry-After through, so the backend backs off', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{"reason":"limit"}', { status: 429, headers: { 'retry-after': '120' } })))
  const res = fakeRes()
  await handler({ method: 'GET', url: `/api/v1/forecast${QUERY}` }, res)
  expect(res.statusCode).toBe(429)
  expect(res.headers['Retry-After']).toBe('120')
})

test('only GET is allowed', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const res = fakeRes()
  await handler({ method: 'POST', url: `/api/v1/forecast${QUERY}` }, res)
  expect(res.statusCode).toBe(405)
  expect(fetchMock).not.toHaveBeenCalled()
})

test('overlong queries are refused with 414', async () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  const res = fakeRes()
  await handler({ method: 'GET', url: `/api/v1/forecast?latitude=${'1,'.repeat(4001)}` }, res)
  expect(res.statusCode).toBe(414)
  expect(fetchMock).not.toHaveBeenCalled()
})

test('an unreachable upstream is a 502', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('fetch failed'))))
  const res = fakeRes()
  await handler({ method: 'GET', url: `/api/v1/forecast${QUERY}` }, res)
  expect(res.statusCode).toBe(502)
  expect(res.body).toEqual({ error: 'weather upstream unreachable' })
})

test('the backend URL it serves matches what Django calls', async () => {
  // Django calls f"{OPEN_METEO_URL}/v1/forecast"; with OPEN_METEO_URL=https://<app>.vercel.app/api
  // that is this function's path.
  const backend = (await import('../../backend/weather/open_meteo.py?raw')).default as string
  expect(backend).toContain('f"{settings.OPEN_METEO_URL}/v1/forecast"')
})
