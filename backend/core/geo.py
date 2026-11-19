"""Small, dependency-free geometry helpers. Coordinates are (lat, lon) tuples in
degrees; distances are in miles."""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence

EARTH_RADIUS_MI = 3958.7613
KM_PER_MILE = 1.609344

LatLon = tuple[float, float]


def haversine_mi(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def destination_point(origin: LatLon, bearing: float, distance_mi: float) -> LatLon:
    lat1, lon1 = map(math.radians, origin)
    brg = math.radians(bearing)
    d = distance_mi / EARTH_RADIUS_MI
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    lon = (math.degrees(lon2) + 540) % 360 - 180
    return (math.degrees(lat2), lon)


# --- Encoded polylines (Google algorithm; OSRM polyline6 uses precision 6) ---


def decode_polyline(encoded: str, precision: int = 5) -> list[LatLon]:
    factor = 10**precision
    coords: list[LatLon] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        values = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            values.append(~(result >> 1) if result & 1 else result >> 1)
        lat += values[0]
        lon += values[1]
        coords.append((lat / factor, lon / factor))
    return coords


def encode_polyline(coords: Sequence[LatLon], precision: int = 5) -> str:
    factor = 10**precision
    out: list[str] = []
    prev_lat = prev_lon = 0
    for lat, lon in coords:
        ilat, ilon = round(lat * factor), round(lon * factor)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


# --- Distances along a line ---------------------------------------------------


def cumulative_miles(coords: Sequence[LatLon]) -> list[float]:
    out = [0.0]
    for a, b in zip(coords, coords[1:]):
        out.append(out[-1] + haversine_mi(a, b))
    return out


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def interpolate_at(
    coords: Sequence[LatLon], cum: Sequence[float], values: Sequence[float], target_mi: float
) -> tuple[LatLon, float]:
    """Point on the line at `target_mi`, and the linearly interpolated value of
    `values` (one per coordinate, e.g. cumulative seconds) at that point."""
    if target_mi <= 0 or len(coords) == 1:
        return coords[0], values[0]
    if target_mi >= cum[-1]:
        return coords[-1], values[-1]
    i = bisect.bisect_right(cum, target_mi) - 1
    seg = cum[i + 1] - cum[i]
    t = 0.0 if seg == 0 else (target_mi - cum[i]) / seg
    (lat1, lon1), (lat2, lon2) = coords[i], coords[i + 1]
    return (_lerp(lat1, lat2, t), _lerp(lon1, lon2, t)), _lerp(values[i], values[i + 1], t)


def sample_distances(total_mi: float, interval_mi: float, min_tail_mi: float = 0.5) -> list[float]:
    """Mile markers 0, I, 2I, ... plus the end of the route. A marker closer
    than `min_tail_mi` to the end is dropped so the last two points don't
    nearly overlap."""
    if total_mi <= 0:
        return [0.0]
    marks = [0.0]
    d = interval_mi
    while d < total_mi - min_tail_mi:
        marks.append(d)
        d += interval_mi
    marks.append(total_mi)
    return marks


def coverage_miles(marks: Sequence[float]) -> list[float]:
    """Miles each sample point represents: half the gap to each neighbour.
    The result always sums to the route length."""
    if len(marks) == 1:
        return [0.0]
    out = []
    for i, m in enumerate(marks):
        left = (m - marks[i - 1]) / 2 if i > 0 else 0.0
        right = (marks[i + 1] - m) / 2 if i < len(marks) - 1 else 0.0
        out.append(left + right)
    return out


# --- Simplification -------------------------------------------------------------


def _perp_dist(p: LatLon, a: LatLon, b: LatLon) -> float:
    # Planar approximation with longitude scaled by cos(lat); fine for simplifying.
    k = math.cos(math.radians((a[0] + b[0]) / 2))
    px, py = p[1] * k, p[0]
    ax, ay = a[1] * k, a[0]
    bx, by = b[1] * k, b[0]
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(coords: Sequence[LatLon], tolerance_deg: float = 0.0005) -> list[LatLon]:
    """Iterative Douglas-Peucker (no recursion limit on long routes)."""
    n = len(coords)
    if n < 3:
        return list(coords)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        max_d, idx = 0.0, -1
        for i in range(start + 1, end):
            d = _perp_dist(coords[i], coords[start], coords[end])
            if d > max_d:
                max_d, idx = d, i
        if idx != -1 and max_d > tolerance_deg:
            keep[idx] = True
            stack.append((start, idx))
            stack.append((idx, end))
    return [c for c, k in zip(coords, keep) if k]


# --- Route comparison ------------------------------------------------------------


def resample(coords: Sequence[LatLon], count: int) -> list[LatLon]:
    cum = cumulative_miles(coords)
    total = cum[-1]
    if total == 0:
        return [coords[0]] * count
    return [
        interpolate_at(coords, cum, cum, total * i / (count - 1))[0] for i in range(count)
    ]


def overlap_ratio(a: Sequence[LatLon], b: Sequence[LatLon], tolerance_mi: float = 1.0) -> float:
    """Share of evenly spaced points on `a` that lie within `tolerance_mi` of
    some point on `b`. Used to drop near-duplicate alternative routes."""
    pa = resample(a, 100)
    pb = resample(b, 400)
    close = sum(1 for p in pa if min(haversine_mi(p, q) for q in pb) <= tolerance_mi)
    return close / len(pa)


def slice_line(
    coords: Sequence[LatLon], cum: Sequence[float], start_mi: float, end_mi: float
) -> list[LatLon]:
    """Part of the line between two mile markers (both ends interpolated)."""
    start_pt, _ = interpolate_at(coords, cum, cum, start_mi)
    end_pt, _ = interpolate_at(coords, cum, cum, end_mi)
    lo = bisect.bisect_right(cum, start_mi)
    hi = bisect.bisect_left(cum, end_mi)
    return [start_pt, *coords[lo:hi], end_pt]
