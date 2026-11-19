import { afterEach, expect, test, vi } from 'vitest'

// The Vercel functions live in api/ (every file there is deployed as a
// function), so their tests live here.
// @ts-expect-error -- plain-JS Vercel helpers, deliberately untyped
import { forwardTo, MAX_QUERY_LENGTH, USER_AGENT } from '../api/_forward.js'
// @ts-expect-error -- plain-JS Vercel function
import nominatim from '../api/nominatim/search.js'
// @ts-expect-error -- plain-JS Vercel function
import photon from '../api/photon/api.js'

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

function upstreamReturns(body: string, init: ResponseInit = { status: 200, headers: { 'content-type': 'application/json' } }) {
  const fetchMock = vi.fn(async () => new Response(body, init))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const calledUrl = (fetchMock: ReturnType<typeof vi.fn>) => (fetchMock.mock.calls[0] as unknown[])[0] as string

test('Photon forwarder sends the query unchanged to photon.komoot.io/api', async () => {
  const fetchMock = upstreamReturns('{"features":[]}')
  const res = fakeRes()
  const query = '?q=chica&limit=15&lang=en&lat=39.8&lon=-98.6&location_bias_scale=0.2&zoom=4'
  await photon({ method: 'GET', url: `/api/photon/api${query}` }, res)
  expect(calledUrl(fetchMock)).toBe(`https://photon.komoot.io/api${query}`)
  expect(res.statusCode).toBe(200)
  expect(res.body).toBe('{"features":[]}')
})

test('Nominatim forwarder sends the query unchanged to nominatim.openstreetmap.org/search', async () => {
  const fetchMock = upstreamReturns('[]')
  const res = fakeRes()
  const query = '?q=chicago&format=jsonv2&limit=6&countrycodes=us'
  await nominatim({ method: 'GET', url: `/api/nominatim/search${query}` }, res)
  expect(calledUrl(fetchMock)).toBe(`https://nominatim.openstreetmap.org/search${query}`)
  expect(res.body).toBe('[]')
})

test('every forward identifies the app with the repo URL', async () => {
  const fetchMock = upstreamReturns('[]')
  await nominatim({ method: 'GET', url: '/api/nominatim/search?q=x' }, fakeRes())
  const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit
  expect((init.headers as Record<string, string>)['User-Agent']).toBe(USER_AGENT)
  expect(USER_AGENT).toContain('https://github.com/Faizan404/weather-aware-truck-routing')
})

test('status, Content-Type and Retry-After are passed back (a 429 reaches the backend)', async () => {
  upstreamReturns('{"error":"rate limited"}', { status: 429, headers: { 'content-type': 'text/plain', 'retry-after': '60' } })
  const res = fakeRes()
  await photon({ method: 'GET', url: '/api/photon/api?q=x' }, res)
  expect(res.statusCode).toBe(429)
  expect(res.headers['Content-Type']).toBe('text/plain')
  expect(res.headers['Retry-After']).toBe('60')
})

test('only GET, queries up to 8000 characters, and a 502 when the upstream is unreachable', async () => {
  const fetchMock = vi.fn(async () => Promise.reject(new TypeError('fetch failed')))
  vi.stubGlobal('fetch', fetchMock)
  const handler = forwardTo('https://example.test/x', 'test')

  const post = fakeRes()
  await handler({ method: 'POST', url: '/x?q=1' }, post)
  expect(post.statusCode).toBe(405)

  const long = fakeRes()
  await handler({ method: 'GET', url: `/x?q=${'a'.repeat(MAX_QUERY_LENGTH)}` }, long)
  expect(long.statusCode).toBe(414)
  expect(fetchMock).not.toHaveBeenCalled()

  const down = fakeRes()
  await photon({ method: 'GET', url: '/api/photon/api?q=x' }, down)
  expect(down.statusCode).toBe(502)
  expect(down.body).toEqual({ error: 'place search upstream unreachable' })
})

test('the paths match what Django calls', async () => {
  // Django calls f"{PHOTON_URL}/api" and f"{NOMINATIM_URL}/search"; with
  // PHOTON_URL=https://<app>.vercel.app/api/photon and NOMINATIM_URL=.../api/nominatim
  // those are api/photon/api.js and api/nominatim/search.js.
  const backend = (await import('../../backend/routing/geocoding.py?raw')).default as string
  expect(backend).toContain('f"{settings.PHOTON_URL}/api"')
  expect(backend).toContain('f"{settings.NOMINATIM_URL}/search"')
})
