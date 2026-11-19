# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver choose the safest route based on **weather, load weight and travel time**.

The driver enters an origin, a destination, a departure date/time and a load weight. The app then:

1. generates **3 route options** from a routing API;
2. places weather **checkpoints every 10 / 25 / 50 miles** (user-selectable) and reads the forecast for the hour the truck is **expected to reach each checkpoint**;
3. classifies each checkpoint with the spec's **risk thresholds and load rules**;
4. **recommends** a route: fewest Severe miles → fewest High miles → lowest average risk → shortest travel time;
5. shows every route, checkpoint, risk level, ETA and route summary on a **map**, plus a **weather heatmap along the trip corridor** with a **0–48 hour forecast slider**.

| | |
|---|---|
| Live app | _add Vercel URL_ |
| API | _add Render URL_ `/api/v1/health/` |
| Walkthrough | _add Loom URL_ |

---

## Free APIs used (no keys needed)

| Purpose | Service | Notes |
|---|---|---|
| Routing | [OSRM](https://router.project-osrm.org) public server (driving profile) | No distance limit. Per-segment durations (`annotations=duration`) give the drive time to every point on the route. |
| Weather | [Open-Meteo](https://open-meteo.com) hourly forecast | `wind_speed_10m` (mph), `rain` + `showers` and `snowfall` (inches per hourly step = in/hr). Today + 15 days. Many locations per request. |
| Geocoding | [Photon](https://photon.komoot.io) → [Nominatim](https://nominatim.openstreetmap.org) fallback | Proxied and cached by the backend. |
| Basemap | [OpenFreeMap](https://openfreemap.org) vector tiles | Rendered with MapLibre GL. |

---

## How it works

### 1. Three route options
OSRM usually returns only 2 routes (e.g. Chicago → Denver), so `backend/routing/service.py` does this:

- Ask OSRM for the primary route plus alternatives.
- **Fewer than 3 distinct routes:** a waypoint is forced off to each side of the primary route's midpoint (15%, then 30% of the route length) and the trip is routed through it. A candidate is dropped if it overlaps an existing route by ≥ 85%, is more than 1.6× the primary route's length or 1.5× its drive time, or **retraces itself** (more than 15% of it runs within 0.5 mi of an earlier, non-adjacent part of the same route, i.e. it drives out to the waypoint and back, as on Miami → Key West). Candidates are tried **one at a time** and routing stops as soon as there are 3 routes, so a typical trip needs only 2 requests. If 3 distinct routes don't exist (e.g. a short city trip), the app shows what it found and says so.

### Respecting the free APIs' usage policies
| Service | Policy | How the app complies |
|---|---|---|
| OSRM public server (run by FOSSGIS) | Max **1 request/second**, valid User-Agent, no heavy use | A process-wide per-host throttle in `core/http.py` (≥ 1 s between calls, never in parallel), an identifying User-Agent, routes cached 24 h, one gunicorn worker so the throttle holds for the whole service |
| Nominatim (geocoding fallback) | Max 1 request/second | Same throttle; Photon is tried first; results cached 24 h |
| Open-Meteo | 600 calls/min, 5,000/hour, 10,000/day; multi-location requests weighted by location count | A rolling quota guard (`core/quota.py`) budgets 480/min, 4,000/hour, 8,000/day locations (~20% margin). When a budget is full the call waits up to 10 s for the window to free up; past that it is skipped and values show Unknown with *"Weather service limit reached, try again later"* (same for a 429). Checkpoints are snapped to 0.1° cells (10-mi interval) or 0.25° (25/50 mi) and deduplicated across all 3 routes. A plan may use at most 240 cells and its heatmap 220, so both fit one minute's budget together: long trips get coarser cells instead of Unknown miles (Seattle→Miami at 10 mi uses 0.6° ≈ 40 mi cells, with a 0.8° heatmap). 60-min cache |
| Photon | Fair use (no published number) | ≥ 0.3 s between calls, debounced autocomplete (300 ms, ≥ 3 chars), 24 h cache |
| All | | A `429 Too Many Requests` is never retried, and it pauses every call to that host for 60 s (or `Retry-After`). Only network errors and 5xx are retried, with backoff. Every request carries a User-Agent with the repository URL as contact (`REPO_URL`) |

Terms to keep in mind before any wider use:
- **Open-Meteo's free API is for non-commercial use only.** A commercial deployment needs an [Open-Meteo API plan](https://open-meteo.com/en/pricing) (then set `OPEN_METEO_URL` to the customer endpoint).
- **The public OSRM server** ([FOSSGIS usage policy](https://github.com/Project-OSRM/osrm-backend/wiki/Demo-server)), **Photon** ([komoot](https://photon.komoot.io)) and **Nominatim** ([usage policy](https://operations.osmfoundation.org/policies/nominatim/)) are free community services under fair-use terms: low volume, an identifying User-Agent, no bulk or heavy use, no uptime guarantee. Real traffic should use self-hosted instances; only the `*_URL` settings change.

### 2. Checkpoints and ETAs
- Checkpoints sit at mile 0, I, 2I, … and the destination (I = 10, 25 or 50). A marker closer than 0.5 mi to the destination is dropped.
- Each route keeps the **cumulative drive time at every geometry point**, from OSRM's per-segment durations. A checkpoint's ETA = departure + the interpolated drive time at that mile.
- The weather used is the **forecast hour nearest the ETA**.

### 3. Risk rules (`backend/risk/rules.py`)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules (applied to the wind level; weight compared with a strict `>`):
- ≥ 55 mph → No Travel for any load
- 45–54 mph and > 30,000 lb → No Travel
- 35–44 mph and > 40,000 lb → Severe

A checkpoint's level is the **worst** of wind (after load rules), rain and snow. Each checkpoint also stores the reason, e.g. "Wind 47 mph with 35,000 lb load".

### 4. Recommendation (`backend/risk/scoring.py`)
- Each checkpoint **covers half the distance to its neighbours**, so miles-by-level always add up exactly to the route length.
- **Average risk** = distance-weighted mean of level scores (Low 0 … No Travel 4).
- Routes are ranked by the spec order: **No Travel miles → Severe miles → High miles → average risk → travel time**. Miles are rounded to 0.1 so float noise can't decide a tie.
- **Average-risk differences under 0.1 count as a tie**, so travel time decides. A distance-weighted average favours long detours (more low-risk miles dilute the same risky stretch): without this, Atlanta → Miami picked a route 214 mi / 6 h longer for an average of 0.03 vs 0.04.
- **Missing data ranks last:** a route with more than 10% of its miles Unknown is ranked after every route with ≥ 90% forecast coverage, and the recommendation notes say why.
- The response explains the decision, e.g. *"Fewest Severe miles: 0.0 mi vs 48.5 mi on the next best route."* If a faster route lost, the reason says why instead, e.g. *"Route A is 2h 00m faster but has 25 mi of High risk."*

### 5. Corridor heatmap + 0–48 h slider
- The backend builds a grid along and beside every route (about 50 km either side), snapped to 0.1–2° cells. The grid is capped at 220 points, and the cell size grows on long trips.
- One batched Open-Meteo call returns **all 49 hours** (departure + 0…48 h) for every cell, for risk (using the entered load), wind, rain and snow. Gzipped, this is about 20 KB for a 1,000-mile trip.
- The frontend stores all 49 hourly values on each map feature. **Moving the slider only swaps one paint expression**, so there's no network call and no data re-upload while scrubbing.
- Cells are drawn as soft, blurred circles **coloured by each cell's own value**. A density heatmap adds overlapping points together, which made calm areas look dangerous; this rendering keeps the colours true to the risk bands.

---

## Interpretation decisions

The spec leaves a few things open. These are the most literal readings, and each is applied in one place in the code:

| Topic | Decision |
|---|---|
| Wind | Sustained 10 m wind speed (not gusts). |
| Rain | `rain + showers` from Open-Meteo, in/hr. |
| Band edges | The table shares values at its edges (e.g. 0.25 is in both Moderate and High). Each band includes its lower bound; Severe's upper bound is inclusive because No Travel is strictly "> 1.00" / "> 3.0". Wind is continuous, so "25–34" means [25, 35). |
| No Travel vs Severe miles | No Travel is worse than Severe, so it is compared first. Otherwise a route with 10 No Travel miles would beat one with 20 Severe miles. |
| Missing forecast | Shown as **Unknown**, never as Low. Unknown miles are excluded from all buckets and flagged on the route and the recommendation. With partial data, the worst known value is used and the checkpoint is flagged as incomplete. |
| Heatmap hour 0 | Departure time (the slider covers the trip window). |
| Load weight | Cargo weight, 0–80,000 lb. 0 = empty trailer (the PDF's "≥ 55 mph → No Travel for **any** load" rule); 80,000 lb is the US federal Interstate limit. |

## Edge cases handled

- Origin or destination outside the United States → validation error. Place search only lists US places, and every submitted point (including typed `lat, lon`) is checked locally against the 50 states and DC (`core/borders.py`, no network call). The outlines are the US Census TIGER/Line legal boundaries (public domain), simplified to about 200 m by `scripts/build_us_borders.py`. Legal boundaries include coastal and Great Lakes waters and follow the middle of border rivers, so ports, lakefront addresses and bridges count as US, while Windsor, Ontario (across the Detroit River) and Tijuana do not.
- Unroutable trips (water, another continent) → `422 no_route`, shown inline.
- Origin = destination (< 0.1 mi apart) → validation error.
- Route shorter than the interval → checkpoints at the start and end only.
- Departure in the past (> 15 min) or > 14 days ahead → validation error. Checkpoints beyond the 16-day forecast range → Unknown, with a warning.
- Timezone-naive datetimes are rejected. The browser sends ISO 8601 with an offset, the backend works in UTC, and the UI shows local time.
- Weather/geocoder/router failures → retries with backoff (never on 429), then degrade (Unknown values, geocoder fallback, or a clear `503`).
- Every route has No Travel → a "No safe route at this departure time" banner.
- A new submit cancels the request already in flight (AbortSignal). Switching the interval back is served from cache.
- Changing the interval re-plans at once only while the form still matches the trip on screen; after other edits, the new interval waits for "Find safest route".
- A server error banner clears as soon as the form is edited or a new request starts.
- Rate limits: snapped coordinates, batched requests (≤ 100 locations each), forecasts cached 60 min, routes and geocodes cached 24 h.

---

## API (`/api/v1`)

All errors return `{"error": {"code", "message", "details"}}`, including `404` for unknown URLs. Per-IP limits: `/plan/` and `/heatmap/` 20/min, `/geocode/` 60/min (`429` with `Retry-After`). `/heatmap/` only accepts polylines whose every point passes the same US border check. Set `NUM_PROXIES` to the number of proxies in front of the app (1 on Render) so the client IP is read correctly.

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health/` | | `{"status": "ok"}` |
| GET | `/geocode/?q=` | `q` ≥ 3 chars | `{"results": [{label, lat, lon}]}` |
| GET | `/risk-rules/` | | Thresholds and load rules. The frontend fetches this once and builds the legend and the Wind/Rain/Snow heatmap scales from it, so `risk/rules.py` is the only place thresholds are written. If it fails, the legend shows colours only and just the Risk layer is available. |
| POST | `/plan/` | `{origin: {lat, lon}, destination: {lat, lon}, departure_time: ISO8601+offset, load_weight_lbs, interval_miles: 10\|25\|50}` | `routes[]` (geometry, risk-coloured segments, checkpoints with ETA/weather/levels/reasons, summary), `recommendation`, `warnings` |
| POST | `/heatmap/` | `{polylines: [≤3 encoded polylines], departure_time, load_weight_lbs}` | `hours[49]`, `points[]`, and per-point 49-hour arrays for `risk`, `wind_mph`, `rain_in_hr`, `snow_in_hr` |

## Project layout

```
backend/
  config/      settings (env-driven), urls
  core/        geo.py (polylines, sampling, interpolation, slicing), borders.py (local US check, data/us_states.geojson),
               http.py (throttle, retries), deadline.py (per-request time budget), client_ip.py,
               middleware.py (early health check, request IDs),
               quota.py, throttling.py, exceptions.py
  scripts/     build_us_borders.py (rebuilds the bundled state outlines from the Census file)
  routing/     providers/osrm.py, service.py (3 options), geocoding.py
  weather/     open_meteo.py (batched + cached forecasts)
  risk/        rules.py (thresholds, load rules), scoring.py (metrics, recommendation)
  planner/     services.py (plan + heatmap), serializers.py, views.py, urls.py
  tests/       234 pytest tests (rules boundaries, scoring, geo, borders, providers, weather, API)
frontend/
  src/api/         typed client (per-call timeouts), query keys
  src/hooks/       usePlan, useHeatmap, useRiskRules, useTripScopedState, useSlowPending, ...
  src/components/  MapView (MapLibre), TripForm, PlaceInput, RouteCards, CheckpointList, ForecastSlider, Legend
  src/lib/         risk colours, legend/scales from /risk-rules/, GeoJSON builders, heat weights, formatting,
                   trip/keyboard helpers (+ vitest tests)
scripts/smoke.sh   post-deploy smoke test
.github/workflows/ci.yml
```

## Run locally

Requirements: Python 3.12+, Node 20+.

```bash
# Backend (http://127.0.0.1:8765)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/python manage.py runserver 8765

# Frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Or run everything with `docker compose up`.

## Tests

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest
cd frontend && npm run lint && npm run typecheck && npm test
cd frontend && VITE_API_URL=https://truck-routing-api-mo4g.onrender.com/api/v1 npm run build
```

CI (`.github/workflows/ci.yml`) runs all of these on every push and pull request, plus `manage.py check --deploy` with production settings and a Docker build of the API.

## Deployment

The API runs on **Render (free plan, Docker)** and the React app on **Vercel**. **It's a single instance by design:** the weather budget, the 1 request/second spacing for public OSRM/Nominatim and the per-trip locks live in process memory, so the API runs one gunicorn worker (8 threads) on one instance. Don't scale it out without moving those to Redis first (`REDIS_URL` only shares the cache).

### 1. API on Render

Create a Blueprint from `render.yaml` (root `backend`, Docker). Environment variables:

| Variable | Value | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | generated by Render | Required when `DJANGO_DEBUG` is false |
| `DJANGO_DEBUG` | `false` | Turns on HTTPS redirect, HSTS, nosniff, referrer policy |
| `DJANGO_ALLOWED_HOSTS` | `.onrender.com` (or your exact host) | |
| `CORS_ALLOWED_ORIGINS` | `https://<your-app>.vercel.app` | Exact origin, no trailing slash. Comma-separate several |
| `NUM_PROXIES` | `1` | Proxies in front of the app, for reading `X-Forwarded-For` |
| `TRUST_CDN_IP_HEADERS` | `true` | Render runs behind Cloudflare, which sets `CF-Connecting-IP`. Leave `false` anywhere clients could send that header themselves |
| `REPO_URL` | `https://github.com/Faizan404/weather-aware-truck-routing` | Contact URL in the User-Agent sent to OSRM, Photon and Nominatim |
| `OPEN_METEO_URL` | `https://<frontend>.vercel.app/api` | Sends weather calls through the Vercel function `frontend/api/v1/forecast.js` (see below) |
| `PLAN_DEADLINE_SECONDS` | `60` | Time budget for one plan or heatmap request; past it the API answers `503 upstream_timeout`. Keep it below gunicorn's `--timeout 90` |
| `REDIS_URL` | *(optional)* | Shared cache; not needed for one instance |
| `LOG_LEVEL` | *(optional)* `INFO` | `DEBUG` also logs which header the client IP came from. Every log line carries the request's `X-Request-ID` (echoed in responses) |

**Why weather goes through Vercel:** Open-Meteo's free tier limits requests per IP address. Render's outgoing IP is shared with other apps, and its daily limit was already used up (every call returned 429 with a Retry-After of about 8.8 hours), so every checkpoint came back Unknown. A small Vercel function in the frontend project, `frontend/api/v1/forecast.js`, forwards the request unchanged to `https://api.open-meteo.com/v1/forecast` from Vercel's network and passes back the status, `Content-Type`, `Retry-After` and body. The backend already calls `${OPEN_METEO_URL}/v1/forecast`, so setting `OPEN_METEO_URL=https://<frontend>.vercel.app/api` on Render is the only change; no backend code changed. Leave it unset locally to call Open-Meteo directly.

`/api/v1/health/` is the health check (GET or HEAD). It's answered before host validation and the HTTPS redirect, so a checker calling the container by IP over plain HTTP still gets a 200. It reports the deployed commit (`version`, from Render's `RENDER_GIT_COMMIT` or `GIT_SHA`) and `weather_budget_minute_left`.

### 2. App on Vercel

Import the repo with root directory `frontend` (framework: Vite). Set **`VITE_API_URL=https://truck-routing-api-mo4g.onrender.com/api/v1`**.

The Content-Security-Policy in `frontend/vercel.json` allows that API origin in `connect-src` (currently `https://truck-routing-api-mo4g.onrender.com`); if the API moves, update both. The build fails with a clear message if `VITE_API_URL` is missing, or if the CSP doesn't allow its origin, so a misconfigured deploy never goes live with every API call blocked. `vercel.json` also sets `X-Content-Type-Options`, `Referrer-Policy` and `Permissions-Policy`. The font is self-hosted, so the CSP allows no third-party font or script host.

### 3. After every deploy

```bash
scripts/smoke.sh https://truck-routing-api-mo4g.onrender.com https://<your-app>.vercel.app
```

It checks health, risk rules, place search, a small plan (Dallas → Houston, every 50 mi) and its heatmap, and a CORS preflight from the app's origin. It exits non-zero on the first failure.

### Cold starts and keep-alive

Render's free plan stops the service after about 15 minutes without traffic, and the next request waits while it starts (up to about a minute). The app says so after 8 s: *"The server is starting up — this can take up to a minute on the free plan."* Plan and heatmap calls are allowed 90 s before the browser gives up.

To avoid most cold starts, add an [UptimeRobot](https://uptimerobot.com) HTTP monitor on `https://truck-routing-api-mo4g.onrender.com/api/v1/health/` **every 10 minutes**. The health check makes no upstream calls, so it costs nothing against the free API quotas. A keep-alive keeps the instance running around the clock, which uses free-plan instance hours.

## Known limitations

- Travel times come from OSRM's driving profile, not a truck-specific model. All three routes use the same speed model, so the travel-time comparison between them stays fair.
- The public OSRM server is a shared demo service (1 request/second, no uptime guarantee). For production traffic, self-host OSRM (same API, so only `OSRM_URL` changes).
- Weather is sampled at the nearest forecast hour, at grid cells of 0.1–0.25° (about 7–17 mi) for checkpoints (coarser on very long trips) and 0.1–2° for the heatmap.
- Runs as one instance by design: the weather budget, per-host rate limits and trip locks are in memory. Scaling out means moving them to Redis; `REDIS_URL` only shares the cache.
- Planning is synchronous and bounded by the public OSRM server at 1 request/second (about 8–12 s for an uncached long trip). In production: self-hosted OSRM, or a background job with polling.
- The weather budget (480 locations/min) is shared by all users. Long trips get coarser cells, and several long trips in the same minute can leave parts of the heatmap empty.
- Weather depends on one free provider reached through one shared IP (now Vercel's, via `frontend/api/v1/forecast.js`). Cloud IPs are shared, so the per-IP free limit can still run out. The next step is a second weather provider to fall back on, or a paid Open-Meteo plan. The forwarding function is also public; restricting it to the API (e.g. with a shared secret header) would stop others from using its quota.
- `/heatmap/` receives the route polylines back from the client; a `trip_id` would avoid re-sending them.
- The US check is strict for heatmap polylines: a route that legally passes through Canada (e.g. Detroit → Buffalo via Ontario, or to Alaska) gets no heatmap.
