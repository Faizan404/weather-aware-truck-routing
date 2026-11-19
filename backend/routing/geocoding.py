"""Place search for the origin/destination inputs. Photon (komoot) first,
Nominatim as fallback; both free and keyless. Trips must start and end in the
US, so results are limited to US places (submitted points are then checked
locally by core.borders)."""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache

from core.exceptions import UpstreamUnavailable
from core.http import UpstreamError, request_json

logger = logging.getLogger(__name__)

CACHE_SECONDS = 24 * 3600
LIMIT = 6
# Ask for more than we show: non-US matches are filtered out afterwards.
FETCH_LIMIT = 15
US = "US"

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
        params={"q": query, "limit": FETCH_LIMIT, "lang": "en"},
        retries=1,
    )
    results = []
    for feature in data.get("features", []):
        if feature.get("properties", {}).get("countrycode", "").upper() != US:
            continue
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
    )
    return [
        {"label": item["display_name"], "lat": float(item["lat"]), "lon": float(item["lon"])}
        for item in data
    ]


def search(query: str) -> list[dict]:
    normalized = " ".join(query.lower().split())
    key = "geo:v2:" + hashlib.sha1(normalized.encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    for provider in (_photon, _nominatim):
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
        cache.set(key, unique, CACHE_SECONDS)
        return unique
    raise UpstreamUnavailable("Place search is unavailable. Please try again shortly.")
