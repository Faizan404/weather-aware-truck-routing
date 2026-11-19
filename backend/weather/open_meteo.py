"""Hourly forecasts from Open-Meteo (free, no key).

Requested units: wind in mph; rain, showers and snowfall in inches. Values are
per hourly step, so they read directly as in/hr. Rain is `rain + showers`.

Free-tier limits: 600 calls/min, 5,000/hour, 10,000/day, and a multi-location
request is weighted by its number of locations. To stay well inside them:
- Points are snapped to a grid cell (0.1 degrees for 10-mile checkpoints,
  0.25 for 25/50-mile ones, coarser for the heatmap); nearby points share one
  forecast, and the cells of all 3 routes are deduplicated into one fetch.
- Long trips get coarser cells so a plan (<= PLAN_MAX_CELLS) plus its heatmap
  (<= HEATMAP_MAX_CELLS) fit in one minute's budget.
- Forecasts are cached per (cell, UTC date) for 60 minutes (the model
  updates hourly, so fresher data rarely exists).
- Missing cells are fetched in batches of up to 100 locations per request,
  several batches in parallel.

A failed batch or a missing value never becomes "Low": the caller gets None
for that value and the risk is reported as Unknown.
"""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from django.conf import settings
from django.core.cache import cache

from core import deadline
from core.geo import LatLon
from core.http import UpstreamError, request_json
from core.quota import RollingQuota
from risk.rules import WeatherSample

logger = logging.getLogger(__name__)

HOURLY_VARS = "wind_speed_10m,rain,showers,snowfall"
BATCH_SIZE = 100
CACHE_SECONDS = 60 * 60
# Free tier: 600 calls/min, 5,000/hour, 10,000/day, where a multi-location
# request counts once per location (we request 4 variables over <= 3 days, so
# no extra weighting). Budgets keep a ~20% safety margin. When a budget is
# full we wait up to QUOTA_MAX_WAIT_SECONDS for it to free up; past that the
# batch is skipped and its checkpoints show Unknown, instead of calling anyway.
QUOTA = RollingQuota([(60, 480), (3600, 4000), (86_400, 8000)])
QUOTA_MAX_WAIT_SECONDS = 10.0

OPEN_METEO_HOST = "api.open-meteo.com"

# Open-Meteo serves today plus 15 days ahead.
FORECAST_DAYS_AHEAD = 15

Cell = tuple[float, float]
# One day of data for one cell: unix hour -> (wind, rain, snow)
DaySeries = dict[int, tuple[float | None, float | None, float | None]]


def snap(point: LatLon, resolution: float) -> Cell:
    return (
        round(round(point[0] / resolution) * resolution, 4),
        round(round(point[1] / resolution) * resolution, 4),
    )


def nearest_hour(moment: datetime) -> int:
    ts = moment.timestamp()
    return int(round(ts / 3600) * 3600)


def horizon_end(now: datetime | None = None) -> date:
    now = now or datetime.now(UTC)
    return (now + timedelta(days=FORECAST_DAYS_AHEAD)).date()


def _key(cell: Cell, day: date) -> str:
    return f"wx:v1:{cell[0]:.4f}:{cell[1]:.4f}:{day.isoformat()}"


def _sum(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    return (a or 0.0) + (b or 0.0)


def _fetch_batch(cells: list[Cell], start: date, end: date) -> dict[tuple[Cell, date], DaySeries]:
    params = {
        "latitude": ",".join(f"{c[0]:.4f}" for c in cells),
        "longitude": ",".join(f"{c[1]:.4f}" for c in cells),
        "hourly": HOURLY_VARS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "timeformat": "unixtime",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    # Keyed by the real upstream, so a 429 pauses Open-Meteo calls even when
    # OPEN_METEO_URL points at the Vercel forwarder.
    data = request_json(
        "GET", f"{settings.OPEN_METEO_URL}/v1/forecast", params=params, throttle_key=OPEN_METEO_HOST
    )
    items = data if isinstance(data, list) else [data]
    out: dict[tuple[Cell, date], DaySeries] = {}
    for cell, item in zip(cells, items):
        hourly = item.get("hourly", {})
        times = hourly.get("time", [])
        wind = hourly.get("wind_speed_10m", [None] * len(times))
        rain = hourly.get("rain", [None] * len(times))
        showers = hourly.get("showers", [None] * len(times))
        snow = hourly.get("snowfall", [None] * len(times))
        for i, ts in enumerate(times):
            day = datetime.fromtimestamp(ts, UTC).date()
            out.setdefault((cell, day), {})[int(ts)] = (wind[i], _sum(rain[i], showers[i]), snow[i])
    return out


@dataclass
class ForecastLookup:
    """Forecast data for a set of cells and days, plus whether anything failed
    and whether a failure was a rate limit (our budget or a 429)."""

    data: dict[tuple[Cell, date], DaySeries]
    had_errors: bool
    rate_limited: bool = False

    def at(self, cell: Cell, hour_ts: int) -> WeatherSample:
        day = datetime.fromtimestamp(hour_ts, UTC).date()
        values = self.data.get((cell, day), {}).get(hour_ts)
        if values is None:
            return WeatherSample(None, None, None)
        return WeatherSample(*values)


def load(needs: set[tuple[Cell, date]]) -> ForecastLookup:
    """Fetch (or read from cache) the forecast for each (cell, day)."""
    limit = horizon_end()
    needs = {(c, d) for c, d in needs if d <= limit}
    keys = {need: _key(*need) for need in needs}
    cached = cache.get_many(list(keys.values()))
    data = {need: cached[k] for need, k in keys.items() if k in cached}

    missing = [need for need in needs if need not in data]
    if not missing:
        return ForecastLookup(data, had_errors=False)

    # One date range for all missing cells (Open-Meteo applies a single range
    # to every location in a request). Slight over-fetch is cheap.
    start = min(d for _, d in missing)
    end = max(d for _, d in missing)
    cells = sorted({c for c, _ in missing})
    batches = [cells[i : i + BATCH_SIZE] for i in range(0, len(cells), BATCH_SIZE)]

    # Each batch returns (data or None, rate_limited).
    def run(batch: list[Cell]):
        if not QUOTA.reserve(len(batch), max_wait=deadline.cap_wait(QUOTA_MAX_WAIT_SECONDS)):
            logger.warning("Open-Meteo quota budget reached; skipping %d cells", len(batch))
            return None, True
        try:
            return _fetch_batch(batch, start, end), False
        except UpstreamError as exc:
            logger.warning("Open-Meteo batch failed (%d cells): %s", len(batch), exc)
            return None, exc.status_code == 429
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("Open-Meteo batch failed (%d cells): %s", len(batch), exc)
            return None, False

    had_errors = rate_limited = False
    fetched: dict[tuple[Cell, date], DaySeries] = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        # Each batch runs in a copy of this context, so the request deadline
        # (core/deadline.py) applies inside the pool threads too.
        futures = [pool.submit(contextvars.copy_context().run, run, batch) for batch in batches]
        for result, limited in (f.result() for f in futures):
            if result is None:
                had_errors = True
                rate_limited = rate_limited or limited
            else:
                fetched.update(result)

    cache.set_many({_key(*need): series for need, series in fetched.items()}, CACHE_SECONDS)
    data.update(fetched)
    return ForecastLookup(data, had_errors, rate_limited)


# Checkpoint cell size per sampling interval: about half the spacing or finer,
# so neighbouring checkpoints rarely share a cell.
CHECKPOINT_RESOLUTION = {10: 0.1, 25: 0.25, 50: 0.25}

# A plan and the heatmap that follows it must fit one per-minute budget
# together (QUOTA allows 480/min): at most PLAN_MAX_CELLS for the checkpoints
# of all 3 routes, and HEATMAP_MAX_CELLS for the corridor grid. Long trips get
# coarser checkpoint cells instead of Unknown miles.
PLAN_MAX_CELLS = 240
HEATMAP_MAX_CELLS = 220
# Coarser checkpoint cell sizes tried, in order, when the base size is too many.
CELL_SIZES = (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0)


def checkpoint_resolution(interval_miles: int) -> float:
    return CHECKPOINT_RESOLUTION.get(interval_miles, 0.25)


def adaptive_resolution(points: list[LatLon], base: float, limit: int = PLAN_MAX_CELLS) -> float:
    """The finest cell size, starting at `base`, at which `points` fall in at
    most `limit` unique cells. Short trips keep `base`; long ones get coarser."""
    sizes = [base] + [s for s in CELL_SIZES if s > base]
    for res in sizes:
        if len({snap(p, res) for p in points}) <= limit:
            return res
    return sizes[-1]


def sample(points: list[tuple[LatLon, datetime]], resolution: float = 0.1) -> tuple[list[WeatherSample], ForecastLookup]:
    """Weather at each (point, time), using the forecast hour nearest the time.
    Every point is fetched in one deduplicated load. Returns the samples and
    the lookup (for its error flags)."""
    cells = [snap(p, resolution) for p, _ in points]
    hours = [nearest_hour(t) for _, t in points]
    needs = {(c, datetime.fromtimestamp(h, UTC).date()) for c, h in zip(cells, hours)}
    lookup = load(needs)
    return [lookup.at(c, h) for c, h in zip(cells, hours)], lookup


def grid_series(
    points: list[LatLon], hours: list[int], resolution: float
) -> tuple[list[Cell], list[list[WeatherSample]], ForecastLookup]:
    """Forecast at each grid cell for each unix hour (heatmap).
    Returns unique cells, a [cell][hour] matrix, and the lookup."""
    cells = sorted({snap(p, resolution) for p in points})
    days = {datetime.fromtimestamp(h, UTC).date() for h in hours}
    lookup = load({(c, d) for c in cells for d in days})
    matrix = [[lookup.at(c, h) for h in hours] for c in cells]
    return cells, matrix, lookup
