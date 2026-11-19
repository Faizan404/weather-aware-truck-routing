from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from weather import open_meteo

URL = "https://api.open-meteo.com/v1/forecast"


def hourly_payload(day: datetime, wind=10.0, rain=0.0, showers=0.0, snow=0.0):
    start = int(day.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    times = [start + 3600 * h for h in range(24)]
    return {"hourly": {
        "time": times,
        "wind_speed_10m": [wind] * 24,
        "rain": [rain] * 24,
        "showers": [showers] * 24,
        "snowfall": [snow] * 24,
    }}


def test_nearest_hour_rounds():
    t = datetime(2026, 11, 17, 10, 29, tzinfo=UTC)
    assert open_meteo.nearest_hour(t) == int(datetime(2026, 11, 17, 10, tzinfo=UTC).timestamp())
    t = datetime(2026, 11, 17, 10, 31, tzinfo=UTC)
    assert open_meteo.nearest_hour(t) == int(datetime(2026, 11, 17, 11, tzinfo=UTC).timestamp())


def test_snap_groups_nearby_points():
    assert open_meteo.snap((40.01, -100.02), 0.05) == open_meteo.snap((40.02, -100.01), 0.05)


@respx.mock
def test_sample_sums_rain_and_showers_and_caches():
    now = datetime.now(UTC) + timedelta(hours=2)
    route = respx.get(URL).mock(return_value=httpx.Response(
        200, json=[hourly_payload(now, wind=30, rain=0.1, showers=0.05, snow=0.2)]))
    samples, lookup = open_meteo.sample([((40.0, -100.0), now)])
    assert not lookup.had_errors
    s = samples[0]
    assert s.wind_mph == 30 and s.rain_in_hr == pytest.approx(0.15) and s.snow_in_hr == 0.2
    params = route.calls[0].request.url.params
    assert params["wind_speed_unit"] == "mph" and params["precipitation_unit"] == "inch"

    open_meteo.sample([((40.0, -100.0), now)])
    assert route.call_count == 1  # served from cache


@respx.mock
def test_failure_returns_unknown_not_low():
    respx.get(URL).mock(return_value=httpx.Response(500))
    samples, lookup = open_meteo.sample([((40.0, -100.0), datetime.now(UTC))])
    assert lookup.had_errors
    assert samples[0].wind_mph is None and samples[0].rain_in_hr is None


@respx.mock
def test_beyond_horizon_is_unknown_without_request():
    route = respx.get(URL)
    far = datetime.now(UTC) + timedelta(days=30)
    samples, lookup = open_meteo.sample([((40.0, -100.0), far)])
    assert route.call_count == 0 and not lookup.had_errors
    assert samples[0].wind_mph is None


@respx.mock
def test_batches_of_100_locations():
    now = datetime.now(UTC)
    def respond(request):
        n = len(request.url.params["latitude"].split(","))
        return httpx.Response(200, json=[hourly_payload(now)] * n)
    route = respx.get(URL).mock(side_effect=respond)
    points = [((30 + i * 0.1, -100.0), now) for i in range(250)]
    samples, lookup = open_meteo.sample(points)
    assert route.call_count == 3
    assert all(s.wind_mph == 10.0 for s in samples)


def test_checkpoint_resolution_per_interval():
    assert open_meteo.checkpoint_resolution(10) == 0.1
    assert open_meteo.checkpoint_resolution(25) == 0.25
    assert open_meteo.checkpoint_resolution(50) == 0.25


@respx.mock
def test_sample_dedupes_cells_across_routes():
    now = datetime.now(UTC) + timedelta(hours=1)
    def respond(request):
        n = len(request.url.params["latitude"].split(","))
        return httpx.Response(200, json=[hourly_payload(now)] * n)
    route = respx.get(URL).mock(side_effect=respond)
    # Three "routes" passing through the same two 0.25-degree cells.
    points = [((40.0 + d, -100.0 + d), now) for d in (0.0, 0.05, 0.08)] * 3
    open_meteo.sample(points, 0.25)
    assert route.call_count == 1
    assert len(route.calls[0].request.url.params["latitude"].split(",")) == 1


def test_adaptive_resolution_keeps_base_cells_on_short_trips():
    points = [(40.0, -100.0 + i * 0.15) for i in range(30)]  # ~250 mi
    assert open_meteo.adaptive_resolution(points, 0.1) == 0.1
    assert open_meteo.adaptive_resolution(points, 0.25) == 0.25


def test_adaptive_resolution_coarsens_long_trips_to_fit_the_budget():
    # ~2,700 mi of checkpoints every ~10 mi: too many 0.1-degree cells.
    points = [(30.0 + i * 0.01, -120.0 + i * 0.14) for i in range(300)]
    res = open_meteo.adaptive_resolution(points, 0.1, limit=100)
    assert res > 0.1
    assert len({open_meteo.snap(p, res) for p in points}) <= 100
    # It picks the finest size that fits, not just any coarser one.
    finer = [s for s in open_meteo.CELL_SIZES if 0.1 <= s < res]
    assert all(len({open_meteo.snap(p, s) for p in points}) > 100 for s in finer)


def test_adaptive_resolution_falls_back_to_the_coarsest_size():
    points = [(30.0 + i, -120.0 + i) for i in range(20)]
    assert open_meteo.adaptive_resolution(points, 0.1, limit=5) == open_meteo.CELL_SIZES[-1]


def test_plan_and_heatmap_budgets_fit_one_minute_together():
    per_minute = dict(open_meteo.QUOTA.windows)[60]
    assert open_meteo.PLAN_MAX_CELLS + open_meteo.HEATMAP_MAX_CELLS <= per_minute
