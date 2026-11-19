// Vercel function: forwards weather requests to Open-Meteo from Vercel's network.
// Open-Meteo's free tier limits by IP, and the API host's shared outgoing IP is
// often exhausted by other apps; the backend points OPEN_METEO_URL here instead.
const UPSTREAM = 'https://api.open-meteo.com/v1/forecast'
const USER_AGENT = 'weather-aware-truck-routing/1.0 (+https://github.com/Faizan404/weather-aware-truck-routing)'

export default async function handler(req, res) {
  if (req.method !== 'GET') return res.status(405).json({ error: 'method not allowed' })
  const at = req.url.indexOf('?')
  const query = at === -1 ? '' : req.url.slice(at)
  if (query.length > 8000) return res.status(414).json({ error: 'query too long' })
  try {
    const upstream = await fetch(UPSTREAM + query, { headers: { 'User-Agent': USER_AGENT } })
    res.status(upstream.status)
    res.setHeader('Content-Type', upstream.headers.get('content-type') ?? 'application/json')
    const retry = upstream.headers.get('retry-after')
    if (retry) res.setHeader('Retry-After', retry)
    res.send(await upstream.text())
  } catch {
    res.status(502).json({ error: 'weather upstream unreachable' })
  }
}
