"""OSRM public demo server (driving profile). No API key and no distance limit.

Per-coordinate drive times come from OSRM's `annotations=duration`, so each
checkpoint's ETA follows the real speeds along the route, not an average."""

from __future__ import annotations

from django.conf import settings

from core.geo import LatLon, decode_polyline
from core.http import UpstreamError, request_json
from routing.models import Route
from routing.providers.base import NoRoute, ProviderUnavailable, build_route

NAME = "osrm"
# Max distance between an entered point and the road OSRM snaps it to.
MAX_SNAP_METERS = 25_000


def _parse(route: dict) -> Route:
    coords = decode_polyline(route["geometry"], 6)
    durations: list[float] = []
    for leg in route["legs"]:
        durations.extend(leg.get("annotation", {}).get("duration", []))
    if len(durations) == len(coords) - 1:
        cum = [0.0]
        for d in durations:
            cum.append(cum[-1] + d)
    else:
        cum = None
    route_obj = build_route(coords, [0.0] * len(coords), NAME, [])
    if cum is None:
        # Annotations don't line up with the geometry: assume constant speed.
        total_mi = route_obj.distance_miles or 1.0
        cum = [m / total_mi * float(route["duration"]) for m in route_obj.cum_miles]
    total = float(route["duration"])
    if cum[-1] > 0:
        cum = [s * total / cum[-1] for s in cum]
    route_obj.cum_seconds = cum
    names = [leg.get("summary", "") for leg in route["legs"] if leg.get("summary")]
    route_obj.via_names = names[:1]
    return route_obj


def fetch_routes(
    origin: LatLon, destination: LatLon, via: LatLon | None = None, alternates: int = 2
) -> list[Route]:
    points = [origin, *([via] if via else []), destination]
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points)
    params = {
        "overview": "full",
        "geometries": "polyline6",
        "annotations": "duration",
        "alternatives": "false" if via else str(max(alternates, 1) + 1),
        "steps": "false",
    }
    try:
        data = request_json("GET", f"{settings.OSRM_URL}/route/v1/driving/{path}", params=params)
    except UpstreamError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        if exc.status_code == 400 and body.get("code") in {"NoRoute", "NoSegment"}:
            raise NoRoute(body.get("message", "No route")) from exc
        raise ProviderUnavailable(str(exc)) from exc
    if data.get("code") != "Ok" or not data.get("routes"):
        raise NoRoute(data.get("message", "No route"))
    _check_snapping(data.get("waypoints", []))
    return [_parse(r) for r in data["routes"]]


def _check_snapping(waypoints: list[dict]) -> None:
    """OSRM snaps each point to the nearest road it can route from. When the
    points aren't connected by road (e.g. New York -> London) it may snap one
    thousands of km away and still answer "Ok". Reject that instead of
    showing a route that starts somewhere else. Via points are exempt: they
    are deliberately placed off the route."""
    if len(waypoints) < 2:
        return
    for label, wp in (("origin", waypoints[0]), ("destination", waypoints[-1])):
        snapped_m = float(wp.get("distance", 0))
        if snapped_m > MAX_SNAP_METERS:
            raise NoRoute(
                f"The {label} is {snapped_m / 1000:,.0f} km from the nearest road "
                "connected to the other point."
            )
