"""Is a point in the United States? A local point-in-polygon check, no network.

Uses core/data/us_states.geojson: the 50 states and DC from the US Census
TIGER/Line legal boundaries (public domain), simplified by
scripts/build_us_borders.py. Legal boundaries include coastal and Great
Lakes waters and follow the middle of border rivers, so ports, lakefront
addresses and bridges count as US while Windsor, Ontario (across the Detroit
River) does not. Precision is about 200 m.

The outline is loaded once. Each state's edges go into 0.1-degree latitude
bands, so a ray-casting test only looks at the few edges near the point.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "us_states.geojson"
BAND_DEG = 0.1

Edge = tuple[float, float, float, float]  # lon1, lat1, lon2, lat2


@lru_cache(maxsize=1)
def _bands() -> dict[int, list[Edge]]:
    """Edges of the US outline by latitude band. Borders two states share
    cancel out (the builder keeps them identical), leaving the outline."""
    features = json.loads(DATA.read_text())["features"]
    edges: dict[tuple[tuple[float, float], tuple[float, float]], int] = {}
    for feature in features:
        for polygon in feature["geometry"]["coordinates"]:
            for ring in polygon:
                for a, b in zip(ring, ring[1:]):
                    if a == b:
                        continue
                    key = (tuple(a), tuple(b)) if tuple(a) < tuple(b) else (tuple(b), tuple(a))
                    edges[key] = edges.get(key, 0) + 1
    bands: dict[int, list[Edge]] = {}
    for ((lon1, lat1), (lon2, lat2)), count in edges.items():
        if count % 2 == 0:  # shared by two states: interior border
            continue
        for band in range(math.floor(min(lat1, lat2) / BAND_DEG), math.floor(max(lat1, lat2) / BAND_DEG) + 1):
            bands.setdefault(band, []).append((lon1, lat1, lon2, lat2))
    return bands


def in_us(lat: float, lon: float) -> bool:
    """True if (lat, lon) is inside one of the 50 states or DC."""
    inside = False
    for lon1, lat1, lon2, lat2 in _bands().get(math.floor(lat / BAND_DEG), ()):
        if (lat1 > lat) != (lat2 > lat) and lon < lon1 + (lat - lat1) * (lon2 - lon1) / (lat2 - lat1):
            inside = not inside
    return inside
