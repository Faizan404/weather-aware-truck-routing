from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from rest_framework.test import APIClient

from risk.rules import WeatherSample
from routing.providers.base import build_route
from weather.open_meteo import ForecastLookup

pytestmark = pytest.mark.filterwarnings("ignore")


def straight_route(lat, lon0, lon1, hours, n=50):
    coords = [(lat, lon0 + (lon1 - lon0) * i / (n - 1)) for i in range(n)]
    seconds = [hours * 3600 * i / (n - 1) for i in range(n)]
    return build_route(coords, seconds, "osrm", [])


@pytest.fixture
def client():
    return APIClient()


def test_plan_rejects_points_outside_us(client):
    # Toronto as origin (inside the old contiguous-US bounding box), Kansas destination
    res = client.post("/api/v1/plan/", body(origin={"lat": 43.65, "lon": -79.38}), format="json")
    assert res.status_code == 400
    details = res.json()["error"]["details"]
    assert details["origin"] == ["The origin must be in the United States."]
    assert "destination" not in details


def body(**overrides):
    data = {
        "origin": {"lat": 40.0, "lon": -100.0},
        "destination": {"lat": 40.0, "lon": -98.0},
        "departure_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "load_weight_lbs": 35_000,
        "interval_miles": 25,
    }
    data.update(overrides)
    return data


def fake_weather(queries, resolution=0.1):
    """Windy (47 mph) east of -99.0 on route A only; calm elsewhere."""
    out = []
    for (lat, lon), _ in queries:
        windy = lat == pytest.approx(40.0, abs=1e-6) and lon > -99.0
        out.append(WeatherSample(47.0 if windy else 5.0, 0.0, 0.0))
    return out, ForecastLookup({}, had_errors=False)


@mock.patch("planner.services.open_meteo.sample", side_effect=fake_weather)
@mock.patch("planner.services.get_routes")
def test_plan_recommends_safer_route(get_routes, _sample, client):
    a = straight_route(40.0, -100.0, -98.0, hours=2.0)  # fast, but windy half
    b = straight_route(40.3, -100.0, -98.0, hours=2.5)  # slower, calm
    get_routes.return_value = ([a, b], [])
    res = client.post("/api/v1/plan/", body(), format="json")
    assert res.status_code == 200, res.json()
    data = res.json()
    assert [r["id"] for r in data["routes"]] == ["A", "B"]
    route_a = data["routes"][0]
    # 47 mph with 35,000 lb -> No Travel (load rule)
    assert route_a["summary"]["miles_by_level"]["no_travel"] > 0
    assert any("lb load" in r for c in route_a["checkpoints"] for r in c["reasons"])
    assert data["recommendation"]["route_id"] == "B"
    assert data["recommendation"]["criterion"] == "no_travel_miles"
    # ETAs increase along the route and start at departure
    etas = [c["eta"] for c in route_a["checkpoints"]]
    assert etas == sorted(etas)
    assert route_a["checkpoints"][0]["elapsed_seconds"] == 0
    # Checkpoints every 25 mi plus the destination
    miles = [c["mile"] for c in route_a["checkpoints"]]
    assert miles[1] == 25 and miles[-1] == pytest.approx(route_a["distance_miles"], abs=0.1)
    # miles-by-level add up to the route length
    total = sum(route_a["summary"]["miles_by_level"].values()) + route_a["summary"]["unknown_miles"]
    assert total == pytest.approx(route_a["distance_miles"], abs=0.2)
    assert {s["level"] for s in route_a["segments"]} == {"low", "no_travel"}


@mock.patch("planner.services.open_meteo.sample", side_effect=fake_weather)
@mock.patch("planner.services.get_routes")
def test_light_load_is_only_severe(get_routes, _sample, client):
    get_routes.return_value = ([straight_route(40.0, -100.0, -98.0, 2.0)], [])
    res = client.post("/api/v1/plan/", body(load_weight_lbs=30_000), format="json")
    summary = res.json()["routes"][0]["summary"]
    assert summary["miles_by_level"]["no_travel"] == 0
    assert summary["miles_by_level"]["severe"] > 0


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"load_weight_lbs": -1}, "load_weight_lbs"),
        ({"load_weight_lbs": 80_001}, "load_weight_lbs"),
        ({"load_weight_lbs": 250_000}, "load_weight_lbs"),
        ({"interval_miles": 15}, "interval_miles"),
        ({"departure_time": (datetime.now(UTC) - timedelta(hours=2)).isoformat()}, "departure_time"),
        ({"departure_time": (datetime.now(UTC) + timedelta(days=20)).isoformat()}, "departure_time"),
        ({"departure_time": "2026-11-20T10:00:00"}, "departure_time"),  # no timezone
        ({"destination": {"lat": 40.0, "lon": -100.0}}, "destination"),  # same as origin
        ({"origin": {"lat": 95, "lon": 0}}, "origin"),
    ],
)
def test_plan_validation(client, overrides, field):
    res = client.post("/api/v1/plan/", body(**overrides), format="json")
    assert res.status_code == 400
    err = res.json()["error"]
    assert err["code"] == "validation_error"
    assert field in err["details"]


@mock.patch("planner.services.get_routes")
def test_plan_no_route_is_422(get_routes, client):
    from core.exceptions import NoRouteFound

    get_routes.side_effect = NoRouteFound("No drivable route was found between these locations.")
    res = client.post("/api/v1/plan/", body(), format="json")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "no_route"


def test_risk_rules_endpoint(client):
    data = client.get("/api/v1/risk-rules/").json()
    assert [lvl["key"] for lvl in data["levels"]][:5] == [
        "low", "moderate", "high", "severe", "no_travel"]
    assert len(data["load_rules"]) == 3


def test_risk_rules_carry_the_spec_thresholds(client):
    """The frontend builds its legend and heatmap scales from this payload."""
    data = client.get("/api/v1/risk-rules/").json()
    mins = {c: [b["min"] for b in bands] for c, bands in data["conditions"].items()}
    assert mins == {
        "wind": [None, 25, 35, 45, 55],
        "rain": [None, 0.10, 0.25, 0.50, 1.00],
        "snow": [None, 0.5, 1.0, 2.0, 3.0],
    }
    # "> 1.00" and "> 3.0" for No Travel; every other band includes its minimum.
    assert [b["min_inclusive"] for b in data["conditions"]["rain"]][-1] is False
    assert [b["min_inclusive"] for b in data["conditions"]["wind"]][-1] is True
    assert data["load_rules"][0] == {"wind_min_mph": 55, "load_over_lbs": None, "result": "no_travel"}
    assert [r["load_over_lbs"] for r in data["load_rules"][1:]] == [30_000, 40_000]


def test_geocode_requires_three_chars(client):
    assert client.get("/api/v1/geocode/?q=ab").status_code == 400


@mock.patch("planner.services.open_meteo.grid_series")
def test_heatmap_shape(grid_series, client):
    from core.geo import encode_polyline

    def fake(points, hours, resolution):
        cells = [(40.0, -100.0), (40.1, -99.9)]
        return cells, [[WeatherSample(50.0, 0.0, 0.0)] * len(hours)] * 2, ForecastLookup({}, False)

    grid_series.side_effect = fake
    res = client.post("/api/v1/heatmap/", {
        "polylines": [encode_polyline([(40.0, -100.0), (40.0, -99.0)])],
        "departure_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "load_weight_lbs": 35_000,
    }, format="json")
    assert res.status_code == 200
    data = res.json()
    assert len(data["hours"]) == 49
    assert len(data["risk"]) == 2 and len(data["risk"][0]) == 49
    assert data["risk"][0][0] == 4  # 50 mph + 35,000 lb -> No Travel


def test_heatmap_rejects_bad_polyline(client):
    res = client.post("/api/v1/heatmap/", {
        "polylines": ["@@@"], "departure_time": datetime.now(UTC).isoformat(),
        "load_weight_lbs": 1000,
    }, format="json")
    assert res.status_code == 400


def test_corridor_grid_is_capped_and_continuous():
    from core.geo import haversine_mi
    from planner.services import MAX_GRID_POINTS, corridor_points

    line = [(35.0, -120.0 + i * 0.5) for i in range(100)]  # ~2,800 mi
    points, res = corridor_points([line, line, line])
    assert len(points) <= MAX_GRID_POINTS
    # every point on the route has a grid cell within about one cell size
    for p in line:
        nearest = min(haversine_mi(p, c) for c in points)
        assert nearest <= res * 69


def test_corridor_grid_short_trip_is_fine_grained():
    from planner.services import corridor_points

    points, res = corridor_points([[(40.71, -74.0), (40.75, -73.98)]])
    assert res == 0.1
    assert 10 <= len(points) <= 300


@pytest.mark.parametrize("load", [0, 30_000, 40_001, 80_000])
@mock.patch("planner.services.open_meteo.sample", side_effect=fake_weather)
@mock.patch("planner.services.get_routes")
def test_plan_accepts_loads_from_empty_to_federal_limit(get_routes, _sample, client, load):
    get_routes.return_value = ([straight_route(40.0, -100.0, -98.0, 2.0)], [])
    res = client.post("/api/v1/plan/", body(load_weight_lbs=load), format="json")
    assert res.status_code == 200, res.json()


def test_load_error_message(client):
    res = client.post("/api/v1/plan/", body(load_weight_lbs=90_000), format="json")
    assert res.json()["error"]["details"]["load_weight_lbs"] == [
        "Load weight must be between 0 and 80,000 lb (US federal limit)."
    ]


# --- Abuse protection ------------------------------------------------------------

def heat_body(points):
    from core.geo import encode_polyline

    return {
        "polylines": [encode_polyline(points)],
        "departure_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "load_weight_lbs": 1000,
    }


def test_heatmap_rejects_polylines_outside_us(client):
    res = client.post("/api/v1/heatmap/", heat_body([(48.85, 2.35), (45.76, 4.84)]), format="json")  # France
    assert res.status_code == 400
    assert res.json()["error"]["details"]["polylines"] == ["Routes must be inside the United States."]
    # Partly outside (Chicago -> Toronto, north of the contiguous-US box) is also refused.
    res = client.post("/api/v1/heatmap/", heat_body([(41.88, -87.63), (50.5, -80.0)]), format="json")
    assert res.status_code == 400


@pytest.mark.parametrize("path, limit", [("/api/v1/geocode/?q=ab", 60)])
def test_geocode_is_throttled_per_ip(client, path, limit):
    for _ in range(limit):
        assert client.get(path).status_code == 400  # validation, but counted
    res = client.get(path)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "throttled"
    assert int(res["Retry-After"]) > 0
    # Another IP has its own budget.
    assert client.get(path, REMOTE_ADDR="10.0.0.9").status_code == 400


@pytest.mark.parametrize("path", ["/api/v1/plan/", "/api/v1/heatmap/"])
def test_plan_and_heatmap_allow_20_per_minute(client, path):
    for _ in range(20):
        assert client.post(path, {}, format="json").status_code == 400
    assert client.post(path, {}, format="json").status_code == 429


def test_unknown_urls_return_json_404(client, settings):
    settings.DEBUG = False
    for path in ("/", "/admin/", "/api/v1/nope/"):
        res = client.get(path)
        assert res.status_code == 404
        assert res["Content-Type"] == "application/json"
        assert res.json()["error"]["code"] == "not_found"


@mock.patch("planner.services.get_routes")
def test_plan_snaps_weather_by_interval_and_reports_rate_limit(get_routes, client):
    get_routes.return_value = ([straight_route(40.0, -100.0, -98.0, 2.0)], [])
    seen = []

    def limited(queries, resolution):
        seen.append(resolution)
        return [WeatherSample(None, None, None)] * len(queries), ForecastLookup({}, True, rate_limited=True)

    with mock.patch("planner.services.open_meteo.sample", side_effect=limited):
        for interval in (10, 25, 50):
            data = client.post("/api/v1/plan/", body(interval_miles=interval), format="json").json()
            assert "Weather service limit reached, try again later." in data["warnings"]
    assert seen == [0.1, 0.25, 0.25]


def _route_through(waypoints, mph=60.0, step_deg=0.05):
    """A dense route through `waypoints`, driven at a constant speed."""
    from core.geo import cumulative_miles

    coords = []
    for (a_lat, a_lon), (b_lat, b_lon) in zip(waypoints, waypoints[1:]):
        n = max(2, int(max(abs(b_lat - a_lat), abs(b_lon - a_lon)) / step_deg))
        coords += [(a_lat + (b_lat - a_lat) * i / n, a_lon + (b_lon - a_lon) * i / n) for i in range(n)]
    coords.append(waypoints[-1])
    seconds = [m / mph * 3600 for m in cumulative_miles(coords)]
    return build_route(coords, seconds, "osrm", [])


def test_seattle_to_miami_at_10_miles_has_no_unknown_miles_and_a_full_heatmap():
    """Plan + heatmap for a ~3,300 mi trip fit one minute's weather budget:
    no Unknown miles, and the heatmap right after it is under 5% empty."""
    import httpx
    import respx

    from planner import services

    seattle, miami = (47.61, -122.33), (25.76, -80.19)
    routes = [
        _route_through([seattle, (43.6, -116.2), (39.7, -105.0), (35.1, -90.0), (33.7, -84.4), miami]),
        _route_through([seattle, (46.9, -114.0), (41.3, -96.0), (36.2, -86.8), (30.3, -81.7), miami]),
        _route_through([seattle, (40.8, -111.9), (35.5, -97.5), (32.3, -90.2), (30.4, -84.3), miami]),
    ]
    assert all(r.distance_miles > 2_800 for r in routes)
    units = []

    def respond(request):
        n = len(request.url.params["latitude"].split(","))
        units.append(n)
        start = int(datetime.fromisoformat(request.url.params["start_date"]).replace(tzinfo=UTC).timestamp())
        end = datetime.fromisoformat(request.url.params["end_date"]).replace(tzinfo=UTC)
        hours = int((end.timestamp() - start) // 3600) + 24
        times = [start + 3600 * h for h in range(hours)]
        zeros = [0.0] * hours
        item = {"hourly": {"time": times, "wind_speed_10m": [8.0] * hours, "rain": zeros, "showers": zeros, "snowfall": zeros}}
        return httpx.Response(200, json=[item] * n)

    departure = datetime.now(UTC) + timedelta(hours=1)
    with respx.mock, mock.patch("planner.services.get_routes", return_value=(routes, [])):
        respx.get(url__regex=r"https://api\.open-meteo\.com/.*").mock(side_effect=respond)
        plan = services.plan_trip(services.TripRequest(seattle, miami, departure, 35_000, 10))
        heat = services.heatmap([r["geometry"] for r in plan["routes"]], departure, 35_000)

    assert [r["summary"]["unknown_miles"] for r in plan["routes"]] == [0, 0, 0]
    assert plan["warnings"] == []
    values = [v for row in heat["wind_mph"] for v in row]
    assert sum(v is None for v in values) / len(values) < 0.05
    assert heat["warnings"] == []
    assert sum(units) <= 480


@pytest.mark.parametrize("field, point", [
    ("destination", {"lat": 42.3149, "lon": -83.0364}),  # Windsor, ON
    ("destination", {"lat": 32.5149, "lon": -117.0382}),  # Tijuana
    ("origin", {"lat": 35.0, "lon": -140.0}),  # open ocean
])
def test_plan_rejects_non_us_points_without_network(client, field, point):
    with mock.patch("core.http.request_json", side_effect=AssertionError("no network in validation")):
        res = client.post("/api/v1/plan/", body(**{field: point}), format="json")
    assert res.status_code == 400
    assert res.json()["error"]["details"][field] == [f"The {field} must be in the United States."]


@mock.patch("planner.services.get_routes")
def test_plan_accepts_honolulu_and_chicago_points(get_routes, client):
    get_routes.return_value = ([straight_route(21.30, -157.86, -157.80, 0.2)], [])
    with mock.patch("planner.services.open_meteo.sample", side_effect=fake_weather):
        res = client.post("/api/v1/plan/", body(
            origin={"lat": 21.3069, "lon": -157.8583}, destination={"lat": 21.30, "lon": -157.80}), format="json")
        assert res.status_code == 200
        res = client.post("/api/v1/plan/", body(destination={"lat": 41.8781, "lon": -87.6298}), format="json")
        assert res.status_code == 200


def test_heatmap_uses_the_border_check_not_bounding_boxes(client):
    # Detroit -> Windsor -> Toronto stays inside the old contiguous-US box but leaves the US.
    res = client.post("/api/v1/heatmap/", heat_body([(42.33, -83.05), (42.31, -83.03), (43.65, -79.38)]), format="json")
    assert res.status_code == 400
    assert res.json()["error"]["details"]["polylines"] == ["Routes must be inside the United States."]
