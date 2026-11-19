"""Trip planning: routes -> checkpoints -> weather at ETA -> risk -> recommendation,
plus the corridor heatmap."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core.geo import (
    LatLon,
    coverage_miles,
    cumulative_miles,
    decode_polyline,
    encode_polyline,
    haversine_mi,
    interpolate_at,
    sample_distances,
    simplify,
    slice_line,
)
from risk.rules import RiskLevel, assess
from risk.scoring import recommend, route_metrics
from routing.models import Route
from routing.service import get_routes
from weather import open_meteo

ROUTE_IDS = "ABC"
HEATMAP_HOURS = 48
WEATHER_WARNING = (
    "Some weather data could not be loaded; affected checkpoints are marked Unknown."
)
RATE_LIMIT_WARNING = "Weather service limit reached, try again later."
HORIZON_WARNING = (
    "Part of this trip is beyond the 16-day forecast range; those checkpoints are Unknown."
)


@dataclass(frozen=True)
class TripRequest:
    origin: LatLon
    destination: LatLon
    departure: datetime  # timezone-aware
    load_lbs: float
    interval_miles: int


def _weather_warning(lookup: open_meteo.ForecastLookup) -> str | None:
    if lookup.rate_limited:
        return RATE_LIMIT_WARNING
    return WEATHER_WARNING if lookup.had_errors else None


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()


def _checkpoint_marks(route: Route, interval: int):
    marks = sample_distances(route.distance_miles, interval)
    coverage = coverage_miles(marks)
    points = []
    for mile in marks:
        point, seconds = interpolate_at(route.coords, route.cum_miles, route.cum_seconds, mile)
        points.append((mile, point, seconds))
    return marks, coverage, points


def _segments(route: Route, marks: list[float], levels: list[RiskLevel]) -> list[dict]:
    """Route pieces coloured by checkpoint risk. Each checkpoint owns the
    stretch halfway to its neighbours; equal neighbours are merged."""
    if len(marks) == 1:
        return [{"level": levels[0].key, "polyline": encode_polyline(route.coords)}]
    bounds = [0.0] + [(a + b) / 2 for a, b in zip(marks, marks[1:])] + [route.distance_miles]
    pieces: list[tuple[RiskLevel, float, float]] = []
    for i, level in enumerate(levels):
        start, end = bounds[i], bounds[i + 1]
        if end <= start:
            continue
        if pieces and pieces[-1][0] is level:
            pieces[-1] = (level, pieces[-1][1], end)
        else:
            pieces.append((level, start, end))
    return [
        {
            "level": level.key,
            "polyline": encode_polyline(
                simplify(slice_line(route.coords, route.cum_miles, start, end))
            ),
        }
        for level, start, end in pieces
    ]


def plan_trip(req: TripRequest) -> dict:
    routes, warnings = get_routes(req.origin, req.destination)

    # Sample every route first so the weather is fetched in one batched call.
    sampled = [_checkpoint_marks(route, req.interval_miles) for route in routes]
    queries = [
        (point, req.departure + timedelta(seconds=seconds))
        for _, _, points in sampled
        for _, point, seconds in points
    ]
    resolution = open_meteo.adaptive_resolution(
        [point for point, _ in queries], open_meteo.checkpoint_resolution(req.interval_miles)
    )
    samples, lookup = open_meteo.sample(queries, resolution)
    warning = _weather_warning(lookup)
    if warning:
        warnings.append(warning)

    horizon = open_meteo.horizon_end()
    beyond_horizon = False
    results, metrics = [], []
    cursor = 0
    for idx, (route, (marks, coverage, points)) in enumerate(zip(routes, sampled)):
        route_id = ROUTE_IDS[idx]
        checkpoints, levels = [], []
        for i, (mile, (lat, lon), seconds) in enumerate(points):
            sample = samples[cursor]
            cursor += 1
            eta = req.departure + timedelta(seconds=seconds)
            if eta.astimezone(UTC).date() > horizon:
                beyond_horizon = True
            risk = assess(sample, req.load_lbs)
            levels.append(risk.level)
            checkpoints.append(
                {
                    "index": i,
                    "mile": round(mile, 2),
                    "lat": round(lat, 5),
                    "lon": round(lon, 5),
                    "eta": _iso(eta),
                    "elapsed_seconds": round(seconds),
                    "coverage_miles": round(coverage[i], 2),
                    "wind_mph": _round(sample.wind_mph, 1),
                    "rain_in_hr": _round(sample.rain_in_hr, 3),
                    "snow_in_hr": _round(sample.snow_in_hr, 3),
                    "level": risk.level.key,
                    "wind_level": risk.wind.key,
                    "rain_level": risk.rain.key,
                    "snow_level": risk.snow.key,
                    "reasons": risk.reasons,
                    "incomplete": risk.incomplete,
                }
            )
        m = route_metrics(
            route_id, route.distance_miles, route.duration_seconds, levels, coverage
        )
        metrics.append(m)
        results.append(
            {
                "id": route_id,
                "label": f"Route {route_id}",
                "via": route.via_names,
                "provider": route.provider,
                "synthetic": route.synthetic,
                "distance_miles": round(route.distance_miles, 1),
                "duration_seconds": round(route.duration_seconds),
                "arrival": _iso(req.departure + timedelta(seconds=route.duration_seconds)),
                "geometry": encode_polyline(simplify(route.coords)),
                "segments": _segments(route, marks, levels),
                "checkpoints": checkpoints,
                "summary": {
                    "miles_by_level": {k: round(v, 1) for k, v in m.miles_by_level.items()},
                    "unknown_miles": round(m.unknown_miles, 1),
                    "avg_risk": _round(m.avg_risk, 2),
                    "max_level": m.max_level.key,
                    "checkpoint_count": len(checkpoints),
                    "incomplete": m.incomplete,
                },
            }
        )

    if beyond_horizon:
        warnings.append(HORIZON_WARNING)

    rec = recommend(metrics)
    return {
        "request": {
            "origin": {"lat": req.origin[0], "lon": req.origin[1]},
            "destination": {"lat": req.destination[0], "lon": req.destination[1]},
            "departure_time": _iso(req.departure),
            "load_weight_lbs": req.load_lbs,
            "interval_miles": req.interval_miles,
        },
        "routes": results,
        "recommendation": {
            "route_id": rec.route_id,
            "ranking": rec.ranking,
            "criterion": rec.criterion,
            "reason": rec.reason,
            "no_safe_route": rec.no_safe_route,
            "notes": rec.notes,
        },
        "warnings": warnings,
        "generated_at": _iso(datetime.now(UTC)),
    }


# --- Heatmap ---------------------------------------------------------------------

# Each grid cell counts toward the per-minute weather budget, which a plan
# and its heatmap share (see open_meteo.PLAN_MAX_CELLS).
MAX_GRID_POINTS = open_meteo.HEATMAP_MAX_CELLS
CORRIDOR_BUFFER_MI = 31.0  # about 50 km either side of each route
# Cell sizes tried in order; the first one that fits MAX_GRID_POINTS is used.
GRID_RESOLUTIONS = (0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0)


def _corridor_cells(lines: list[list[LatLon]], res: float, limit: int) -> set[tuple[int, int]] | None:
    """Grid cells (lat/lon indices) whose centre lies within the buffer of any
    route. Returns None as soon as the count exceeds `limit`."""
    cells: set[tuple[int, int]] = set()
    step_mi = max(1.0, res * 69.0 / 2)
    buf_lat = CORRIDOR_BUFFER_MI / 69.0
    for line in lines:
        cum = cumulative_miles(line)
        length = cum[-1]
        steps = max(1, math.ceil(length / step_mi))
        for k in range(steps + 1):
            p, _ = interpolate_at(line, cum, cum, length * k / steps)
            buf_lon = buf_lat / max(0.2, math.cos(math.radians(p[0])))
            for i in range(math.floor((p[0] - buf_lat) / res), math.ceil((p[0] + buf_lat) / res) + 1):
                for j in range(math.floor((p[1] - buf_lon) / res), math.ceil((p[1] + buf_lon) / res) + 1):
                    if (i, j) in cells:
                        continue
                    if haversine_mi(p, (i * res, j * res)) <= CORRIDOR_BUFFER_MI:
                        cells.add((i, j))
                        if len(cells) > limit:
                            return None
    return cells


def corridor_points(lines: list[list[LatLon]]) -> tuple[list[LatLon], float]:
    """A uniform band of grid cells covering every route plus ~50 km either
    side. The cell size grows until the band fits MAX_GRID_POINTS, so coverage
    stays continuous on any trip length. Returns cell centres and cell size."""
    for res in GRID_RESOLUTIONS:
        cells = _corridor_cells(lines, res, MAX_GRID_POINTS)
        if cells is not None:
            break
    else:  # extremely long trips: accept the coarsest grid, truncated
        res = GRID_RESOLUTIONS[-1]
        cells = _corridor_cells(lines, res, 10**9) or set()
        cells = set(sorted(cells)[:MAX_GRID_POINTS])
    points = [(round(i * res, 4), round(j * res, 4)) for i, j in sorted(cells)]
    return points, res


def heatmap(polylines: list[str], departure: datetime, load_lbs: float) -> dict:
    lines = [decode_polyline(p) for p in polylines]
    lines = [line for line in lines if line]
    points, resolution = corridor_points(lines)

    start = open_meteo.nearest_hour(departure)
    hours = [start + 3600 * h for h in range(HEATMAP_HOURS + 1)]
    cells, matrix, lookup = open_meteo.grid_series(points, hours, resolution)

    risk, wind, rain, snow = [], [], [], []
    for row in matrix:
        risk.append([assess(s, load_lbs).level.score for s in row])
        wind.append([_round(s.wind_mph, 1) for s in row])
        rain.append([_round(s.rain_in_hr, 3) for s in row])
        snow.append([_round(s.snow_in_hr, 3) for s in row])

    warning = _weather_warning(lookup)
    warnings = [warning] if warning else []
    return {
        "hours": [datetime.fromtimestamp(h, UTC).isoformat() for h in hours],
        "resolution_deg": resolution,
        "points": [[lat, lon] for lat, lon in cells],
        "risk": risk,
        "wind_mph": wind,
        "rain_in_hr": rain,
        "snow_in_hr": snow,
        "warnings": warnings,
    }
