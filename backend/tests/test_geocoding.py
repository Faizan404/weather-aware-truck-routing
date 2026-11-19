import httpx
import respx

from routing import geocoding


def feature(lon, lat, **props):
    return {"geometry": {"coordinates": [lon, lat]}, "properties": props}


@respx.mock
def test_city_and_state_with_same_name_stay_distinct():
    respx.get("https://photon.komoot.io/api").mock(return_value=httpx.Response(200, json={"features": [
        feature(-74.006, 40.7127, type="city", name="New York", state="New York", country="United States", countrycode="US"),
        feature(-75.5, 43.0, type="state", name="New York", country="United States", countrycode="US"),
        feature(-74.006, 40.7127, type="city", name="New York", state="New York", country="United States", countrycode="US"),
    ]}))
    results = geocoding.search("new york")
    assert [r["label"] for r in results] == [
        "New York, New York, United States",
        "New York (state), United States",
    ]
    assert results[0]["lat"] == 40.7127  # the city keeps the city's coordinates


@respx.mock
def test_falls_back_to_nominatim():
    respx.get("https://photon.komoot.io/api").mock(return_value=httpx.Response(503))
    respx.get("https://nominatim.openstreetmap.org/search").mock(return_value=httpx.Response(200, json=[
        {"display_name": "Denver, Colorado, United States", "lat": "39.74", "lon": "-104.99"}]))
    assert geocoding.search("denver")[0]["lat"] == 39.74


@respx.mock
def test_search_lists_only_us_places():
    respx.get("https://photon.komoot.io/api").mock(return_value=httpx.Response(200, json={"features": [
        feature(2.35, 48.85, type="city", name="Paris", state="Ile-de-France", country="France", countrycode="FR"),
        feature(-95.55, 33.66, type="city", name="Paris", state="Texas", country="United States", countrycode="US"),
    ]}))
    results = geocoding.search("paris")
    assert [r["label"] for r in results] == ["Paris, Texas, United States"]


@respx.mock
def test_nominatim_fallback_is_restricted_to_us():
    respx.get("https://photon.komoot.io/api").mock(return_value=httpx.Response(503))
    nom = respx.get("https://nominatim.openstreetmap.org/search").mock(return_value=httpx.Response(200, json=[]))
    geocoding.search("springfield")
    assert nom.calls[0].request.url.params["countrycodes"] == "us"
