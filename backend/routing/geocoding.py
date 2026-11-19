"""Place search for the origin/destination inputs. Photon (komoot) first,
Nominatim as fallback; both free and keyless. Trips must start and end in the
US, so results are limited to US places (submitted points are then checked
locally by core.borders).

In production both are reached through Vercel forwarders (PHOTON_URL /
NOMINATIM_URL), because the API host's shared outgoing IP gets throttled.
Calls are still spaced and cooled down per real service (throttle_key).
"""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

from core.exceptions import UpstreamUnavailable
from core.http import UpstreamError, request_json

logger = logging.getLogger(__name__)

PHOTON_HOST = "photon.komoot.io"
NOMINATIM_HOST = "nominatim.openstreetmap.org"

# Photon is the real answer: cache it a day. Nominatim is only the fallback
# (no prefix search, so weaker results): cache briefly so Photon gets another
# chance soon. Empty results are never cached.
PHOTON_CACHE_SECONDS = 24 * 3600
FALLBACK_CACHE_SECONDS = 10 * 60
CACHE_PREFIX = "geo:v3:"
LIMIT = 6
# Ask for more than we show: non-US matches are filtered out afterwards.
FETCH_LIMIT = 15
US = "US"

# Bias Photon towards the middle of the contiguous US at country scale.
# zoom=4 matters: Photon's default bias radius is street level, which ranks
# streets near the bias point (e.g. "Chicago Avenue" in Kansas) above the
# city of Chicago.
US_BIAS = {"lat": 39.8, "lon": -98.6, "location_bias_scale": 0.2, "zoom": 4}
PLACE_KEYS = {"place", "boundary"}
MIN_PLACE_RESULTS = 3

# Photon result types shown as a hint so e.g. New York (state) and New York
# (city) can be told apart in the suggestions.
TYPE_HINTS = {"state": "state", "county": "county", "country": "country", "district": "district"}


def photon_label(props: dict, fallback: str) -> str:
    name = props.get("name")
    if not name and props.get("street"):
        name = " ".join(filter(None, [props.get("housenumber"), props.get("street")]))
    name = name or fallback
    hint = TYPE_HINTS.get(props.get("type", ""))
    head = f"{name} ({hint})" if hint else name
    parts = [head]
    # Keep the state even when it equals the name (New York, New York, ...).
    for key in ("city", "state", "country"):
        value = props.get(key)
        if value and value not in parts[1:] and not (key == "city" and value == name):
            if hint == "state" and key == "state":
                continue
            parts.append(value)
    return ", ".join(parts)


def _photon(query: str) -> list[dict]:
    data = request_json(
        "GET",
        f"{settings.PHOTON_URL}/api",
        params={"q": query, "limit": FETCH_LIMIT, "lang": "en", **US_BIAS},
        retries=1,
        throttle_key=PHOTON_HOST,
    )
    features = [
        f for f in data.get("features", [])
        if f.get("properties", {}).get("countrycode", "").upper() == US
    ]
    # Trip ends are towns and cities: when there are enough of them, drop
    # streets, stations, buildings and the like.
    places = [f for f in features if f.get("properties", {}).get("osm_key") in PLACE_KEYS]
    if len(places) >= MIN_PLACE_RESULTS:
        features = places
    results = []
    for feature in features:
        lon, lat = feature["geometry"]["coordinates"]
        results.append(
            {"label": photon_label(feature.get("properties", {}), query), "lat": lat, "lon": lon}
        )
    return results


def _nominatim(query: str) -> list[dict]:
    data = request_json(
        "GET",
        f"{settings.NOMINATIM_URL}/search",
        params={"q": query, "format": "jsonv2", "limit": LIMIT, "countrycodes": "us"},
        retries=0,
        throttle_key=NOMINATIM_HOST,
    )
    return [
        {"label": item["display_name"], "lat": float(item["lat"]), "lon": float(item["lon"])}
        for item in data
    ]


def search(query: str) -> list[dict]:
    normalized = " ".join(query.lower().split())
    key = CACHE_PREFIX + hashlib.sha1(normalized.encode()).hexdigest()
    cached = cache.get(key)
    if cached:
        return cached
    for provider, ttl in ((_photon, PHOTON_CACHE_SECONDS), (_nominatim, FALLBACK_CACHE_SECONDS)):
        try:
            results = provider(normalized)
        except (UpstreamError, KeyError, ValueError, TypeError) as exc:
            logger.warning("Geocoder %s failed: %s", provider.__name__, exc)
            continue
        # Drop duplicate labels, keeping the first (best-ranked) match.
        seen: set[str] = set()
        unique = []
        for r in results:
            if r["label"] not in seen:
                seen.add(r["label"])
                unique.append(r)
        unique = unique[:LIMIT]
        if unique:  # an empty answer may just be a bad moment upstream
            cache.set(key, unique, ttl)
        return unique
    raise UpstreamUnavailable("Place search is unavailable. Please try again shortly.")
