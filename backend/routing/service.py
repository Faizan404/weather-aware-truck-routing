"""Get 3 distinct route options for a trip from OSRM.

1. Ask OSRM for a primary route plus alternatives.
2. Public routers often return fewer than 3 routes. To fill the gap, a
   waypoint is forced off to each side of the primary route's midpoint and the
   trip is routed through it. Candidates are dropped if they mostly overlap an
   existing route, are unreasonably long or slow detours, or retrace
   themselves (drive out to the waypoint and back on the same road, as happens
   on dead-end corridors like Miami -> Key West).

The public OSRM server allows at most 1 request per second (FOSSGIS terms).
Candidates are therefore tried one at a time, nearest offset first, and we stop
as soon as we have 3 routes; core.http spaces the calls 1 s apart.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from collections.abc import Iterable

from django.core.cache import cache

from core import deadline
from core.exceptions import NoRouteFound, UpstreamTimeout, UpstreamUnavailable
from core.geo import LatLon, bearing_deg, destination_point, interpolate_at, overlap_ratio
from routing.models import Route
from routing.providers import osrm
from routing.providers.base import NoRoute, ProviderUnavailable

logger = logging.getLogger(__name__)

TARGET_ROUTES = 3
DUPLICATE_OVERLAP = 0.85
MAX_DETOUR_FACTOR = 1.6  # candidate distance vs the primary route
MAX_DURATION_FACTOR = 1.5  # candidate drive time vs the primary route
# A candidate "retraces itself" when more than RETRACE_SHARE of its length runs
# within RETRACE_RADIUS_MI of an earlier, non-adjacent part of the same route.
RETRACE_RADIUS_MI = 0.5
RETRACE_SHARE = 0.15
RETRACE_MAX_SAMPLES = 20_000
# Forced-waypoint offsets as a fraction of the primary route length, nearest first.
VIA_OFFSET_FRACTIONS = (0.15, 0.30)
ROUTE_CACHE_SECONDS = 24 * 3600
# Routes are stored with one vertex per ~0.3 mi (OSRM returns one every ~0.1 mi)
# in a compact form, so a cross-country trip stays small in the cache.
CACHE_VERTEX_SPACING_MI = 0.3

# One lock per trip, so simultaneous requests for the same trip (e.g. a quick
# re-submit) share one set of OSRM calls instead of repeating them.
_trip_locks: dict[str, threading.Lock] = {}
_trip_locks_guard = threading.Lock()


def _trip_lock(key: str) -> threading.Lock:
    with _trip_locks_guard:
        if len(_trip_locks) > 1000:
            _trip_locks.clear()
        return _trip_locks.setdefault(key, threading.Lock())


def _cache_key(origin: LatLon, destination: LatLon) -> str:
    raw = f"{origin[0]:.5f},{origin[1]:.5f}|{destination[0]:.5f},{destination[1]:.5f}"
    return "routes:v5:" + hashlib.sha1(raw.encode()).hexdigest()


def _store(key: str, routes: list[Route], warnings: list[str]) -> None:
    cache.set(key, ([r.to_cache() for r in routes], warnings), ROUTE_CACHE_SECONDS)


def _load(key: str) -> tuple[list[Route], list[str]] | None:
    cached = cache.get(key)
    if not cached:
        return None
    routes, warnings = cached
    return [Route.from_cache(r) for r in routes], list(warnings)


def is_duplicate(candidate: Route, existing: list[Route]) -> bool:
    for route in existing:
        a, b = candidate.coords, route.coords
        if max(overlap_ratio(a, b), overlap_ratio(b, a)) >= DUPLICATE_OVERLAP:
            return True
    return False


def retrace_share(route: Route) -> float:
    """Fraction of the route that runs within RETRACE_RADIUS_MI of an earlier,
    non-adjacent part of itself (0 for a route that never doubles back)."""
    total = route.distance_miles
    if total <= 0:
        return 0.0
    spacing = max(RETRACE_RADIUS_MI / 2, total / RETRACE_MAX_SAMPLES)
    n = max(2, math.ceil(total / spacing) + 1)
    # Points closer than this along the route are neighbours, not a retrace.
    adjacent_mi = max(3 * RETRACE_RADIUS_MI, 2 * spacing)
    cell = RETRACE_RADIUS_MI
    grid: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
    hits = 0
    for k in range(n):
        mile = total * k / (n - 1)
        (lat, lon), _ = interpolate_at(route.coords, route.cum_miles, route.cum_miles, mile)
        # Local flat projection in miles; accurate enough at this radius.
        x, y = lon * 69.17 * math.cos(math.radians(lat)), lat * 69.0
        cx, cy = math.floor(x / cell), math.floor(y / cell)
        found = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for px, py, pm in grid.get((cx + dx, cy + dy), ()):
                    if mile - pm > adjacent_mi and math.hypot(x - px, y - py) <= RETRACE_RADIUS_MI:
                        found = True
                        break
                if found:
                    break
            if found:
                break
        hits += found
        grid.setdefault((cx, cy), []).append((x, y, mile))
    return hits / n


def retraces_itself(route: Route) -> bool:
    return retrace_share(route) > RETRACE_SHARE


def via_points(base: Route) -> list[LatLon]:
    total = base.distance_miles

    def at(fraction: float) -> LatLon:
        return interpolate_at(base.coords, base.cum_miles, base.cum_miles, total * fraction)[0]

    mid = at(0.5)
    heading = bearing_deg(at(0.45), at(0.55))
    points = []
    for fraction in VIA_OFFSET_FRACTIONS:
        offset = min(max(total * fraction, 1.0), 250.0)
        for side in (90, -90):
            points.append(destination_point(mid, (heading + side) % 360, offset))
    return points


def _via_route(origin: LatLon, via: LatLon, destination: LatLon) -> Route | None:
    try:
        route = osrm.fetch_routes(origin, destination, via=via)[0]
    except (NoRoute, ProviderUnavailable) as exc:
        logger.info("Via-point route failed: %s", exc)
        return None
    route.synthetic = True
    return route


def pick_alternatives(
    base: Route, existing: list[Route], candidates: Iterable[Route | None]
) -> list[Route]:
    """Take candidates in order (lazily, so routing stops once we have enough)."""
    added: list[Route] = []
    for candidate in candidates:
        if candidate is None:
            continue
        if candidate.distance_miles > base.distance_miles * MAX_DETOUR_FACTOR:
            continue
        if candidate.duration_seconds > base.duration_seconds * MAX_DURATION_FACTOR:
            continue
        if retraces_itself(candidate):
            continue
        if is_duplicate(candidate, existing + added):
            continue
        added.append(candidate)
        if len(existing) + len(added) >= TARGET_ROUTES:
            break
    return added


def get_routes(origin: LatLon, destination: LatLon) -> tuple[list[Route], list[str]]:
    """Return up to 3 distinct routes (primary first) plus user-facing warnings."""
    key = _cache_key(origin, destination)
    cached = _load(key)
    if cached:
        return cached
    lock = _trip_lock(key)
    left = deadline.time_left()
    if not lock.acquire(timeout=-1 if left is None else max(0.0, left)):
        raise UpstreamTimeout("The request took too long. Please try again.")
    try:
        cached = _load(key)  # another request may have just computed it
        if cached:
            return cached
        return _compute_routes(key, origin, destination)
    finally:
        lock.release()


def _compute_routes(key: str, origin: LatLon, destination: LatLon) -> tuple[list[Route], list[str]]:
    try:
        routes = osrm.fetch_routes(origin, destination)
    except NoRoute as exc:
        raise NoRouteFound(
            "No drivable route was found between these locations.", {"reason": str(exc)}
        ) from exc
    except ProviderUnavailable as exc:
        raise UpstreamUnavailable(
            "The routing service is unavailable. Please try again shortly."
        ) from exc

    distinct: list[Route] = []
    for route in routes:
        if not is_duplicate(route, distinct):
            distinct.append(route)

    if len(distinct) < TARGET_ROUTES and distinct[0].distance_miles >= 1.0:
        candidates = (_via_route(origin, v, destination) for v in via_points(distinct[0]))
        distinct += pick_alternatives(distinct[0], distinct, candidates)

    warnings: list[str] = []
    if len(distinct) < TARGET_ROUTES:
        warnings.append(
            f"Only {len(distinct)} distinct route option(s) could be found for this trip."
        )

    # Thin before returning too, so a fresh and a cached response are identical.
    stored = [r.thinned(CACHE_VERTEX_SPACING_MI) for r in distinct[:TARGET_ROUTES]]
    _store(key, stored, warnings)
    return _load(key) or (stored, warnings)
