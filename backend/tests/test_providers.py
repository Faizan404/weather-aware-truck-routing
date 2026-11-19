"""OSRM parsing, alternative-route generation and HTTP policy behaviour,
with HTTP mocked by respx."""

import threading
import time

import httpx
import pytest
import respx

from core import http
from core.exceptions import NoRouteFound, UpstreamUnavailable
from core.geo import encode_polyline
from routing import service
from routing.providers import osrm
from routing.providers.base import NoRoute

OSRM_RE = r"https://router\.project-osrm\.org/route/v1/driving/.*"


def line(lat, lon0, lon1, n=20):
    return [(lat, lon0 + (lon1 - lon0) * i / (n - 1)) for i in range(n)]


def arc(base, bulge):
    """Same endpoints as `base`, bowed north (+) or south (-) in the middle."""
    n = len(base)
    return [(lat + bulge * (1 - abs(1 - 2 * i / (n - 1))), lon) for i, (lat, lon) in enumerate(base)]


def osrm_route(coords, seconds):
    n = len(coords) - 1
    return {
        "geometry": encode_polyline(coords, 6),
        "duration": seconds,
        "distance": 1000,
        "legs": [{"annotation": {"duration": [seconds / n] * n}}],
    }


def ok(*routes):
    return httpx.Response(200, json={"code": "Ok", "routes": list(routes)})


@respx.mock
def test_osrm_parse_uses_per_segment_durations():
    coords = line(40, -100, -99)
    n = len(coords) - 1
    durations = [100.0] * (n // 2) + [300.0] * (n - n // 2)  # second half slower
    body = osrm_route(coords, sum(durations))
    body["legs"][0]["annotation"]["duration"] = durations
    respx.get(url__regex=OSRM_RE).mock(return_value=httpx.Response(200, json={"code": "Ok", "routes": [body]}))
    route = osrm.fetch_routes((40, -100), (40, -99))[0]
    assert route.duration_seconds == pytest.approx(sum(durations))
    assert route.cum_seconds[n // 2] == pytest.approx(100.0 * (n // 2))
    assert route.cum_seconds == sorted(route.cum_seconds)


@respx.mock
def test_osrm_falls_back_to_constant_speed_when_annotations_mismatch():
    body = osrm_route(line(40, -100, -99), 3600)
    body["legs"][0]["annotation"]["duration"] = [1.0, 2.0]  # wrong length
    respx.get(url__regex=OSRM_RE).mock(return_value=httpx.Response(200, json={"code": "Ok", "routes": [body]}))
    route = osrm.fetch_routes((40, -100), (40, -99))[0]
    assert route.duration_seconds == pytest.approx(3600)
    assert route.cum_seconds[10] == pytest.approx(3600 * route.cum_miles[10] / route.distance_miles)


@respx.mock
def test_osrm_no_route():
    respx.get(url__regex=OSRM_RE).mock(return_value=httpx.Response(400, json={"code": "NoRoute", "message": "Impossible route"}))
    with pytest.raises(NoRoute):
        osrm.fetch_routes((40, -100), (40, -99))


@respx.mock
def test_service_synthesizes_alternatives_one_call_at_a_time():
    base = line(40, -100, -99)
    responses = iter([
        ok(osrm_route(base, 3600)),  # primary: only one route
        ok(osrm_route(arc(base, 0.3), 4000)),  # via north
        ok(osrm_route(base, 3600)),  # via south snaps back onto primary -> duplicate
        ok(osrm_route(arc(base, -0.3), 4200)),  # wider offset
    ])
    route = respx.get(url__regex=OSRM_RE).mock(side_effect=lambda req: next(responses))
    routes, warnings = service.get_routes((40, -100), (40, -99))
    assert len(routes) == 3
    assert [r.synthetic for r in routes] == [False, True, True]
    assert warnings == []
    assert route.call_count == 4  # stopped once 3 were found (5th candidate unused)


@respx.mock
def test_service_drops_long_detours():
    base = line(40, -100, -99)
    detour = [(40, -100), (43, -99.5), (40, -99)]  # far more than 1.6x longer
    responses = iter([ok(osrm_route(base, 3600))] + [ok(osrm_route(detour, 9000))] * 4)
    respx.get(url__regex=OSRM_RE).mock(side_effect=lambda req: next(responses))
    routes, warnings = service.get_routes((40, -100), (40, -99))
    assert len(routes) == 1
    assert any("Only 1 distinct" in w for w in warnings)


def out_and_back(base, spur_lat=0.4, n=20):
    """`base` with a spur driven north from its midpoint and straight back."""
    mid = len(base) // 2
    lat, lon = base[mid]
    spur = [(lat + spur_lat * i / (n - 1), lon) for i in range(n)]
    return base[:mid] + spur + spur[::-1][1:] + base[mid + 1:]


def test_retrace_share_flags_out_and_back_routes():
    from routing.providers.base import build_route

    base = line(40, -100, -99, n=50)  # ~53 mi
    honest = build_route(arc(base, 0.3), [0] * 50, "osrm", [])
    assert service.retrace_share(honest) == 0
    assert not service.retraces_itself(honest)

    spur = out_and_back(base)  # ~28 mi spur out and back: ~25% retraced
    coords = spur
    fake = build_route(coords, [i * 10.0 for i in range(len(coords))], "osrm", [])
    assert service.retrace_share(fake) > service.RETRACE_SHARE
    assert service.retraces_itself(fake)


def test_retrace_ignores_a_short_spur():
    from routing.providers.base import build_route

    base = line(40, -100, -98, n=80)  # ~105 mi
    coords = out_and_back(base, spur_lat=0.05)  # ~3.5 mi each way: ~3%
    route = build_route(coords, [i * 10.0 for i in range(len(coords))], "osrm", [])
    assert not service.retraces_itself(route)


@respx.mock
def test_service_drops_retracing_and_slow_candidates():
    base = line(40, -100, -99)
    responses = iter([
        ok(osrm_route(base, 3600)),
        ok(osrm_route(out_and_back(base, 0.2), 4000)),  # out to the waypoint and back
        ok(osrm_route(arc(base, -0.3), 5500)),  # distinct but > 1.5x slower
        ok(osrm_route(arc(base, 0.3), 4000)),  # fine
        ok(osrm_route(arc(base, -0.45), 4100)),  # fine
    ])
    respx.get(url__regex=OSRM_RE).mock(side_effect=lambda req: next(responses))
    routes, _ = service.get_routes((40, -100), (40, -99))
    assert [round(r.duration_seconds) for r in routes] == [3600, 4000, 4100]
    # The retracing candidate was within the distance limit: only the retrace rule dropped it.
    from routing.providers.base import build_route
    spur = out_and_back(base, 0.2)
    spur_route = build_route(spur, [0.0] * len(spur), "osrm", [])
    assert spur_route.distance_miles < routes[0].distance_miles * service.MAX_DETOUR_FACTOR
    assert service.retraces_itself(spur_route)
    assert not any(service.retraces_itself(r) for r in routes)


@respx.mock
def test_service_maps_no_route_and_outage():
    respx.get(url__regex=OSRM_RE).mock(return_value=httpx.Response(400, json={"code": "NoRoute"}))
    with pytest.raises(NoRouteFound):
        service.get_routes((40, -100), (40, -99))


@respx.mock
def test_service_outage_is_503():
    respx.get(url__regex=OSRM_RE).mock(return_value=httpx.Response(503))
    with pytest.raises(UpstreamUnavailable):
        service.get_routes((41, -100), (41, -99))


@respx.mock
def test_routes_are_cached():
    route = respx.get(url__regex=OSRM_RE).mock(
        return_value=ok(osrm_route(line(40, -100, -99), 3600), osrm_route(arc(line(40, -100, -99), 0.3), 4000),
                        osrm_route(arc(line(40, -100, -99), -0.3), 4100)))
    service.get_routes((40, -100), (40, -99))
    service.get_routes((40, -100), (40, -99))
    assert route.call_count == 1


# --- HTTP policy ------------------------------------------------------------------


@respx.mock
def test_429_is_not_retried_and_pauses_the_host():
    route = respx.get("https://api.example.test/x").mock(return_value=httpx.Response(429))
    with pytest.raises(http.UpstreamError):
        http.request_json("GET", "https://api.example.test/x")
    assert route.call_count == 1
    # During the cool-down nothing is sent to that host at all.
    with pytest.raises(http.UpstreamError, match="paused"):
        http.request_json("GET", "https://api.example.test/x")
    assert route.call_count == 1
    # Other hosts are unaffected.
    other = respx.get("https://other.example.test/y").mock(return_value=httpx.Response(200, json={}))
    http.request_json("GET", "https://other.example.test/y")
    assert other.call_count == 1


@respx.mock
def test_5xx_is_retried(monkeypatch):
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    route = respx.get("https://api.example.test/y").mock(
        side_effect=[httpx.Response(502), httpx.Response(200, json={"ok": True})])
    assert http.request_json("GET", "https://api.example.test/y") == {"ok": True}
    assert route.call_count == 2


@respx.mock
def test_throttle_spaces_requests_across_threads(monkeypatch):
    monkeypatch.setattr(http, "HOST_MIN_INTERVAL", {"router.project-osrm.org": 0.2})
    times: list[float] = []

    def record(request):
        times.append(time.monotonic())
        return httpx.Response(200, json={})

    respx.get(url__regex=OSRM_RE).mock(side_effect=record)
    threads = [
        threading.Thread(target=http.request_json, args=("GET", "https://router.project-osrm.org/route/v1/driving/x"))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    times.sort()
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert len(times) == 4
    assert min(gaps) >= 0.19


@respx.mock
def test_osrm_rejects_far_snapped_endpoint():
    """New York -> London: OSRM snaps New York to Portugal and says "Ok"."""
    body = {
        "code": "Ok",
        "routes": [osrm_route(line(38.8, -9.5, -0.1), 100_000)],
        "waypoints": [{"distance": 5_534_800.0, "location": [-9.49, 38.78]}, {"distance": 0.0, "location": [-0.12, 51.5]}],
    }
    respx.get(url__regex=OSRM_RE).mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(NoRoute, match="origin is 5,535 km"):
        osrm.fetch_routes((40.71, -74.0), (51.5, -0.12))
    with pytest.raises(NoRouteFound):
        service.get_routes((40.71, -74.0), (51.5, -0.12))


@respx.mock
def test_osrm_ignores_via_snap_distance():
    body = {
        "code": "Ok",
        "routes": [osrm_route(line(40, -100, -99), 3600)],
        "waypoints": [{"distance": 10.0}, {"distance": 60_000.0}, {"distance": 5.0}],
    }
    respx.get(url__regex=OSRM_RE).mock(return_value=httpx.Response(200, json=body))
    assert osrm.fetch_routes((40, -100), (40, -99), via=(40.5, -99.5))


@respx.mock
def test_concurrent_identical_trips_share_one_set_of_calls():
    base = line(40, -100, -99)
    body = ok(osrm_route(base, 3600), osrm_route(arc(base, 0.3), 4000), osrm_route(arc(base, -0.3), 4100))

    def slow(request):
        time.sleep(0.2)
        return body

    route = respx.get(url__regex=OSRM_RE).mock(side_effect=slow)
    threads = [threading.Thread(target=service.get_routes, args=((40, -100), (40, -99))) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert route.call_count == 1
