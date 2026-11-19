"""Place search through forwarders: spacing and cool-downs follow the real
service (throttle_key), caching rules, and Photon relevance."""

import json
from pathlib import Path
from unittest import mock

import httpx
import pytest
import respx
from django.core.cache import cache

from core import http
from core.exceptions import UpstreamUnavailable
from routing import geocoding
from weather import open_meteo

FIXTURES = Path(__file__).parent / "fixtures"
FORWARDER = "https://app.vercel.app/api"


@pytest.fixture
def forwarders(settings):
    """Production setup: both geocoders reached through Vercel forwarders."""
    settings.PHOTON_URL = f"{FORWARDER}/photon"
    settings.NOMINATIM_URL = f"{FORWARDER}/nominatim"
    return settings


def photon_feature(name, state="Illinois", osm_key="place", country="US", lon=-87.6, lat=41.9):
    return {
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"name": name, "state": state, "country": "United States",
                       "countrycode": country, "osm_key": osm_key, "type": "city"},
    }


# --- throttle_key: spacing and cool-down per real service ------------------------------


def test_spacing_uses_the_real_service_not_the_forwarder_host(monkeypatch):
    monkeypatch.setattr(http, "HOST_MIN_INTERVAL", {"nominatim.openstreetmap.org": 1.0, "photon.komoot.io": 0.3})
    calls = []

    def fake_run(key, interval, fn):
        calls.append((key, interval))
        return httpx.Response(200, json={}, request=httpx.Request("GET", "https://x"))

    monkeypatch.setattr(http.throttle, "run", fake_run)
    http.request_json("GET", f"{FORWARDER}/nominatim/search", throttle_key="nominatim.openstreetmap.org")
    http.request_json("GET", f"{FORWARDER}/photon/api", throttle_key="photon.komoot.io")
    assert calls == [("nominatim.openstreetmap.org", 1.0), ("photon.komoot.io", 0.3)]


def test_spacing_defaults_to_the_url_host(monkeypatch):
    monkeypatch.setattr(http, "HOST_MIN_INTERVAL", {"nominatim.openstreetmap.org": 1.0})
    calls = []
    monkeypatch.setattr(
        http.throttle, "run",
        lambda key, interval, fn: calls.append((key, interval)) or httpx.Response(200, json={}),
    )
    http.request_json("GET", "https://nominatim.openstreetmap.org/search")
    assert calls == [("nominatim.openstreetmap.org", 1.0)]
    # A forwarder URL without a key has no published limit of its own: no spacing.
    with respx.mock:
        respx.get(f"{FORWARDER}/nominatim/search").mock(return_value=httpx.Response(200, json={}))
        http.request_json("GET", f"{FORWARDER}/nominatim/search")
    assert len(calls) == 1


@respx.mock
def test_cooldown_applies_per_key():
    photon = respx.get(f"{FORWARDER}/photon/api").mock(return_value=httpx.Response(429))
    nominatim = respx.get(f"{FORWARDER}/nominatim/search").mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(http.UpstreamError):
        http.request_json("GET", f"{FORWARDER}/photon/api", throttle_key="photon.komoot.io", retries=0)
    # Photon is paused, whichever URL reaches it...
    with pytest.raises(http.UpstreamError, match="paused"):
        http.request_json("GET", "https://photon.komoot.io/api", throttle_key="photon.komoot.io")
    assert photon.call_count == 1
    # ...but Nominatim, behind the same forwarder host, is not.
    http.request_json("GET", f"{FORWARDER}/nominatim/search", throttle_key="nominatim.openstreetmap.org")
    assert nominatim.call_count == 1


def test_each_client_passes_its_real_service_as_key(forwarders):
    with mock.patch.object(geocoding, "request_json", return_value={"features": []}) as rj:
        geocoding._photon("chicago")
    assert rj.call_args.kwargs["throttle_key"] == "photon.komoot.io"
    assert rj.call_args.args[1] == f"{FORWARDER}/photon/api"

    with mock.patch.object(geocoding, "request_json", return_value=[]) as rj:
        geocoding._nominatim("chicago")
    assert rj.call_args.kwargs["throttle_key"] == "nominatim.openstreetmap.org"
    assert rj.call_args.args[1] == f"{FORWARDER}/nominatim/search"

    with mock.patch.object(open_meteo, "request_json", return_value=[]) as rj:
        from datetime import date

        open_meteo._fetch_batch([(40.0, -100.0)], date.today(), date.today())
    assert rj.call_args.kwargs["throttle_key"] == "api.open-meteo.com"


# --- Caching -------------------------------------------------------------------------------


def _key(query):
    import hashlib

    return geocoding.CACHE_PREFIX + hashlib.sha1(query.encode()).hexdigest()


@respx.mock
def test_empty_results_are_never_cached(forwarders):
    photon = respx.get(f"{FORWARDER}/photon/api").mock(return_value=httpx.Response(200, json={"features": []}))
    assert geocoding.search("zzzz") == []
    assert geocoding.search("zzzz") == []
    assert photon.call_count == 2
    assert cache.get(_key("zzzz")) is None


@respx.mock
def test_photon_results_are_cached_for_a_day(forwarders):
    photon = respx.get(f"{FORWARDER}/photon/api").mock(
        return_value=httpx.Response(200, json={"features": [photon_feature("Chicago")]})
    )
    with mock.patch.object(geocoding.cache, "set", wraps=cache.set) as cache_set:
        first = geocoding.search("Chicago")
    assert cache_set.call_args.args[2] == 24 * 3600
    assert geocoding.search("chicago") == first  # served from cache
    assert photon.call_count == 1


@respx.mock
def test_fallback_results_are_cached_only_ten_minutes(forwarders):
    respx.get(f"{FORWARDER}/photon/api").mock(return_value=httpx.Response(503))
    respx.get(f"{FORWARDER}/nominatim/search").mock(return_value=httpx.Response(200, json=[
        {"display_name": "Chicago, Cook County, Illinois, United States", "lat": "41.88", "lon": "-87.63"},
    ]))
    with mock.patch.object(geocoding.cache, "set", wraps=cache.set) as cache_set:
        results = geocoding.search("chicago")
    assert results[0]["label"].startswith("Chicago")
    assert cache_set.call_args.args[2] == 10 * 60


def test_cache_prefix_ignores_stale_entries():
    assert geocoding.CACHE_PREFIX == "geo:v3:"
    import hashlib

    cache.set("geo:v2:" + hashlib.sha1(b"chicago").hexdigest(), [{"label": "stale", "lat": 0, "lon": 0}])
    with mock.patch.object(geocoding, "_photon", return_value=[{"label": "Chicago, Illinois", "lat": 41.9, "lon": -87.6}]):
        assert geocoding.search("chicago")[0]["label"] == "Chicago, Illinois"


@respx.mock
def test_both_providers_down_is_a_503(forwarders):
    respx.get(f"{FORWARDER}/photon/api").mock(return_value=httpx.Response(503))
    respx.get(f"{FORWARDER}/nominatim/search").mock(return_value=httpx.Response(503))
    with pytest.raises(UpstreamUnavailable):
        geocoding.search("chicago")


# --- Relevance ----------------------------------------------------------------------------


@respx.mock
def test_chica_ranks_chicago_illinois_first(forwarders):
    """Recorded Photon response for "chica" with the US bias (zoom=4)."""
    route = respx.get(f"{FORWARDER}/photon/api").mock(
        return_value=httpx.Response(200, json=json.loads((FIXTURES / "photon_chica.json").read_text()))
    )
    results = geocoding.search("Chica")
    assert results[0]["label"] == "Chicago, Illinois, United States"
    # Streets, stations, buildings and the river are dropped: there were enough places.
    labels = " | ".join(r["label"] for r in results)
    for dropped in ("Union Station", "Greyhound", "River", "Stadium"):
        assert dropped not in labels
    params = route.calls[0].request.url.params
    assert (params["lat"], params["lon"], params["location_bias_scale"], params["zoom"]) == ("39.8", "-98.6", "0.2", "4")


def test_non_places_are_kept_when_places_are_scarce(forwarders):
    data = {"features": [photon_feature("Chicago", osm_key="place"),
                         photon_feature("Chicago Avenue", osm_key="highway"),
                         photon_feature("Chicago Union Station", osm_key="railway")]}
    with mock.patch.object(geocoding, "request_json", return_value=data):
        labels = [r["label"] for r in geocoding._photon("chicago")]
    assert len(labels) == 3  # only 1 place: nothing is dropped


def test_non_us_results_are_dropped(forwarders):
    data = {"features": [photon_feature("Chica", state="Sergipe", country="BR"),
                         photon_feature("Chicago")]}
    with mock.patch.object(geocoding, "request_json", return_value=data):
        assert [r["label"] for r in geocoding._photon("chica")] == ["Chicago, Illinois, United States"]
