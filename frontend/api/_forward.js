// Shared helper for the Vercel forwarders in this folder (the leading
// underscore keeps Vercel from deploying this file as a function itself).
//
// Free services like Open-Meteo, Photon and Nominatim limit requests per IP.
// The API host's shared outgoing IP is often throttled by other apps' traffic,
// so the backend reaches them through these functions, from Vercel's network.
// Requests are forwarded unchanged; the backend still spaces its calls per
// real service (core/http.py, throttle_key).
export const USER_AGENT = 'weather-aware-truck-routing/1.0 (+https://github.com/Faizan404/weather-aware-truck-routing)'
export const MAX_QUERY_LENGTH = 8000

/**
 * A GET-only Vercel handler that forwards the query string to `upstream` and
 * passes back the status, Content-Type, Retry-After and body.
 * `name` is used in the 502 message when the upstream can't be reached.
 */
export function forwardTo(upstream, name) {
  return async function handler(req, res) {
    if (req.method !== 'GET') return res.status(405).json({ error: 'method not allowed' })
    const at = req.url.indexOf('?')
    const query = at === -1 ? '' : req.url.slice(at)
    if (query.length > MAX_QUERY_LENGTH) return res.status(414).json({ error: 'query too long' })
    try {
      const response = await fetch(upstream + query, { headers: { 'User-Agent': USER_AGENT } })
      res.status(response.status)
      res.setHeader('Content-Type', response.headers.get('content-type') ?? 'application/json')
      const retry = response.headers.get('retry-after')
      if (retry) res.setHeader('Retry-After', retry)
      res.send(await response.text())
    } catch {
      res.status(502).json({ error: `${name} upstream unreachable` })
    }
  }
}
