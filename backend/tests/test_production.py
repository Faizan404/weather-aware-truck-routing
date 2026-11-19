"""Production-readiness behaviour: client IP for throttling, request deadline,
cache size, health, CORS and security headers."""

import os
import pickle
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

import httpx
import pytest
import respx
from rest_framework.test import APIClient

from core import deadline, http
from core.client_ip import client_ip
from core.exceptions import UpstreamTimeout
from routing import service
from routing.providers.base import build_route
from weather import open_meteo

from .test_providers import OSRM_RE, line, ok, osrm_route

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def client():
    return APIClient()


# --- Client IP -------------------------------------------------------------------


@pytest.fixture
def behind_proxy(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}
    settings.TRUST_CDN_IP_HEADERS = True
    return settings


def test_cf_connecting_ip_comes_first(behind_proxy):
    meta = {
        "HTTP_CF_CONNECTING_IP": "203.0.113.7",
        "HTTP_TRUE_CLIENT_IP": "198.51.100.1",
        "HTTP_X_FORWARDED_FOR": "192.0.2.9",
        "REMOTE_ADDR": "10.0.0.1",
    }
    assert client_ip(meta) == ("203.0.113.7", "cf-connecting-ip")


def test_true_client_ip_when_no_cf_header(behind_proxy):
    meta = {"HTTP_TRUE_CLIENT_IP": "198.51.100.1", "HTTP_X_FORWARDED_FOR": "192.0.2.9", "REMOTE_ADDR": "10.0.0.1"}
    assert client_ip(meta) == ("198.51.100.1", "true-client-ip")


def test_x_forwarded_for_counts_proxies_from_the_right(behind_proxy):
    meta = {"HTTP_X_FORWARDED_FOR": "192.0.2.9", "REMOTE_ADDR": "10.0.0.1"}
    assert client_ip(meta) == ("192.0.2.9", "x-forwarded-for")


def test_spoofed_x_forwarded_for_entry_does_not_change_identity(behind_proxy):
    # The client sends its own X-Forwarded-For; the proxy appends the real address.
    real = {"HTTP_X_FORWARDED_FOR": "192.0.2.9", "REMOTE_ADDR": "10.0.0.1"}
    spoofed = {"HTTP_X_FORWARDED_FOR": "1.2.3.4, 5.6.7.8, 192.0.2.9", "REMOTE_ADDR": "10.0.0.1"}
    assert client_ip(spoofed) == client_ip(real) == ("192.0.2.9", "x-forwarded-for")


def test_remote_addr_without_proxies(settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
    meta = {"HTTP_X_FORWARDED_FOR": "1.2.3.4", "REMOTE_ADDR": "10.0.0.1"}
    assert client_ip(meta) == ("10.0.0.1", "remote-addr")


def test_cdn_headers_are_ignored_unless_trusted(settings):
    # Without Cloudflare in front, anyone can send these headers.
    settings.TRUST_CDN_IP_HEADERS = False
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}
    meta = {"HTTP_CF_CONNECTING_IP": "203.0.113.7", "HTTP_TRUE_CLIENT_IP": "198.51.100.1", "REMOTE_ADDR": "10.0.0.1"}
    assert client_ip(meta) == ("10.0.0.1", "remote-addr")


def test_malformed_header_falls_through(behind_proxy):
    meta = {"HTTP_CF_CONNECTING_IP": "not-an-ip", "HTTP_X_FORWARDED_FOR": "192.0.2.9", "REMOTE_ADDR": "10.0.0.1"}
    assert client_ip(meta) == ("192.0.2.9", "x-forwarded-for")


def test_throttle_counts_per_cf_client_ip(behind_proxy, client):
    for _ in range(60):
        assert client.get("/api/v1/geocode/?q=ab", HTTP_CF_CONNECTING_IP="203.0.113.7").status_code == 400
    assert client.get("/api/v1/geocode/?q=ab", HTTP_CF_CONNECTING_IP="203.0.113.7").status_code == 429
    # A different client behind the same proxy has its own budget.
    assert client.get("/api/v1/geocode/?q=ab", HTTP_CF_CONNECTING_IP="203.0.113.8").status_code == 400


# --- Request deadline --------------------------------------------------------------


def test_call_timeout_is_capped_by_time_left(settings):
    settings.HTTP_TIMEOUT_SECONDS = 20
    assert deadline.call_timeout() == 20  # no budget set
    with deadline.deadline(5):
        assert 4.5 < deadline.call_timeout() <= 5
    with deadline.deadline(60):
        assert deadline.call_timeout() == 20


@respx.mock
def test_upstream_call_uses_the_capped_timeout(settings):
    settings.HTTP_TIMEOUT_SECONDS = 20
    respx.get("https://example.test/x").mock(return_value=httpx.Response(200, json={}))
    seen = []
    real = http._client

    def spy(timeout):
        seen.append(timeout)
        return real(timeout)

    with mock.patch.object(http, "_client", side_effect=spy), deadline.deadline(3):
        http.request_json("GET", "https://example.test/x")
    assert 2.5 < seen[0] <= 3


@respx.mock
def test_spent_budget_stops_before_calling():
    route = respx.get("https://example.test/x").mock(return_value=httpx.Response(200, json={}))
    with deadline.deadline(-1), pytest.raises(UpstreamTimeout):
        http.request_json("GET", "https://example.test/x")
    assert route.call_count == 0


@respx.mock
def test_retry_backoff_never_outlasts_the_budget():
    respx.get("https://example.test/x").mock(return_value=httpx.Response(503))
    started = time.monotonic()
    with deadline.deadline(0.3), pytest.raises(UpstreamTimeout):
        http.request_json("GET", "https://example.test/x", retries=3, backoff=5.0)
    assert time.monotonic() - started < 1.0


@respx.mock
def test_weather_pool_threads_inherit_the_deadline():
    route = respx.get(url__regex=r"https://api\.open-meteo\.com/.*").mock(return_value=httpx.Response(200, json=[]))
    today = datetime.now(UTC).date()
    with deadline.deadline(-1), pytest.raises(UpstreamTimeout):
        open_meteo.load({((40.0, -100.0), today)})
    assert route.call_count == 0


@respx.mock
def test_plan_returns_503_upstream_timeout_when_the_budget_runs_out(settings, client):
    settings.PLAN_DEADLINE_SECONDS = 0.2

    def slow_primary(request):
        time.sleep(0.3)  # the primary route alone uses up the budget
        return ok(osrm_route(line(40.0, -100.0, -98.0), 7200))

    respx.get(url__regex=OSRM_RE).mock(side_effect=slow_primary)
    res = client.post("/api/v1/plan/", {
        "origin": {"lat": 40.0, "lon": -100.0},
        "destination": {"lat": 40.0, "lon": -98.0},
        "departure_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "load_weight_lbs": 35_000,
        "interval_miles": 25,
    }, format="json")
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "upstream_timeout"


def test_gunicorn_timeout_stays_above_the_deadline(settings):
    import re

    timeout = int(re.search(r"--timeout (\d+)", (BACKEND / "Dockerfile").read_text()).group(1))
    assert timeout > settings.PLAN_DEADLINE_SECONDS


# --- Cache size ------------------------------------------------------------------------


def test_cached_long_route_stays_small():
    """A ~3,000 mi route with OSRM-like density (a vertex every ~0.1 mi) is
    stored thinned and compact: well under 150 KB, same distance and time."""
    n = 30_000
    coords = [(47.6 - 21.8 * i / (n - 1), -122.3 + 42.1 * i / (n - 1)) for i in range(n)]
    dense = build_route(coords, [200_000 * i / (n - 1) for i in range(n)], "osrm", [])
    assert dense.distance_miles > 2_500

    with mock.patch.object(service.osrm, "fetch_routes", return_value=[dense]), \
         mock.patch.object(service, "via_points", return_value=[]):
        fresh, _ = service.get_routes(coords[0], coords[-1])
        cached, _ = service.get_routes(coords[0], coords[-1])

    stored, _ = service.cache.get(service._cache_key(coords[0], coords[-1]))
    assert len(pickle.dumps(stored[0])) < 150 * 1024
    assert len(fresh[0].coords) < n / 2
    assert fresh[0].distance_miles == pytest.approx(dense.distance_miles, rel=1e-6)
    assert fresh[0].duration_seconds == pytest.approx(dense.duration_seconds, rel=1e-6)
    assert cached[0].coords == fresh[0].coords  # first and cached responses match


def test_locmem_cache_is_bounded():
    from django.conf import settings

    if "locmem" in settings.CACHES["default"]["BACKEND"]:
        assert settings.CACHES["default"]["OPTIONS"]["MAX_ENTRIES"] == 3000


# --- Health, CORS, headers -------------------------------------------------------------


def test_health_reports_version_and_weather_budget(settings, client):
    settings.GIT_SHA = "abc1234"
    open_meteo.QUOTA.reserve(80)
    data = client.get("/api/v1/health/").json()
    assert data == {"status": "ok", "version": "abc1234", "weather_budget_minute_left": 400}


def test_cors_preflight_is_cached_and_retry_after_is_exposed(client):
    origin = "http://localhost:5173"
    pre = client.options(
        "/api/v1/plan/",
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )
    assert pre.status_code == 200
    assert pre["Access-Control-Allow-Origin"] == origin
    assert pre["Access-Control-Max-Age"] == "86400"
    res = client.get("/api/v1/risk-rules/", HTTP_ORIGIN=origin)
    exposed = res["Access-Control-Expose-Headers"].lower()
    assert "retry-after" in exposed and "x-request-id" in exposed


def test_responses_forbid_framing(client):
    assert client.get("/api/v1/risk-rules/")["X-Frame-Options"] == "DENY"


def test_deploy_check_passes_with_production_settings():
    env = {
        **os.environ,
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": "x" * 20 + "-production-like-secret-key-for-the-deploy-check-0123456789",
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
    }
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=BACKEND, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
