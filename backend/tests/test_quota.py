from datetime import UTC, datetime

import httpx
import respx

from core.quota import RollingQuota
from weather import open_meteo


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_rolling_windows():
    clock = FakeClock()
    q = RollingQuota([(60, 10), (3600, 15)], clock=clock)
    assert q.try_reserve(6)
    assert not q.try_reserve(5)  # minute window would hit 11
    assert q.try_reserve(4)  # exactly 10
    clock.t = 61
    assert q.try_reserve(5)  # minute window freed; hour now 15
    assert not q.try_reserve(1)  # hour window full
    clock.t = 3601
    assert q.try_reserve(10)


@respx.mock
def test_open_meteo_skips_calls_when_budget_is_spent(monkeypatch):
    monkeypatch.setattr(open_meteo, "QUOTA", RollingQuota([(60, 5)]))
    route = respx.get("https://api.open-meteo.com/v1/forecast")
    points = [((30 + i * 0.1, -100.0), datetime.now(UTC)) for i in range(10)]
    samples, lookup = open_meteo.sample(points)
    assert route.call_count == 0  # 10 locations > budget of 5: never sent
    assert lookup.had_errors and lookup.rate_limited
    assert all(s.wind_mph is None for s in samples)  # Unknown, not Low


class FakeSleep:
    def __init__(self, clock):
        self.clock, self.calls = clock, []

    def __call__(self, seconds):
        self.calls.append(seconds)
        self.clock.t += seconds


def test_reserve_waits_for_the_window_to_free_up():
    clock = FakeClock()
    q = RollingQuota([(60, 10)], clock=clock, sleep=FakeSleep(clock))
    assert q.reserve(8)
    clock.t = 55
    assert q.reserve(5, max_wait=10)  # waits ~5 s for the first 8 to expire
    assert 60 <= clock.t < 61


def test_reserve_gives_up_past_max_wait():
    clock = FakeClock()
    sleep = FakeSleep(clock)
    q = RollingQuota([(60, 10)], clock=clock, sleep=sleep)
    assert q.reserve(8)
    clock.t = 30
    assert not q.reserve(5, max_wait=10)  # would need 30 s
    assert sleep.calls == []  # no pointless sleeping
    assert not q.reserve(11, max_wait=100)  # bigger than the window: never fits


def test_reserve_frees_only_as_much_as_needed():
    clock = FakeClock()
    q = RollingQuota([(60, 10)], clock=clock, sleep=FakeSleep(clock))
    assert q.reserve(3)
    clock.t = 20
    assert q.reserve(7)
    clock.t = 50
    assert q.reserve(3, max_wait=15)  # only the first 3 must expire (at t=60)
    assert 60 <= clock.t < 61


@respx.mock
def test_open_meteo_waits_instead_of_skipping(monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(open_meteo, "QUOTA", RollingQuota([(60, 5)], clock=clock, sleep=FakeSleep(clock)))
    now = datetime.now(UTC)

    def respond(request):
        n = len(request.url.params["latitude"].split(","))
        return httpx.Response(200, json=[{"hourly": {"time": [], "wind_speed_10m": []}}] * n)

    respx.get("https://api.open-meteo.com/v1/forecast").mock(side_effect=respond)
    assert open_meteo.QUOTA.reserve(5)  # budget full right now
    clock.t = 55
    _, lookup = open_meteo.sample([((30.0, -100.0), now), ((31.0, -100.0), now)])
    assert not lookup.rate_limited and not lookup.had_errors
    assert clock.t >= 60


@respx.mock
def test_open_meteo_429_is_reported_as_rate_limited():
    respx.get("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(429))
    samples, lookup = open_meteo.sample([((30.0, -100.0), datetime.now(UTC))])
    assert lookup.had_errors and lookup.rate_limited
    assert samples[0].wind_mph is None
