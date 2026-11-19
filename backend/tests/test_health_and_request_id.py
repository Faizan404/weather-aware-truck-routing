"""Health check robustness (answered before host validation and the HTTPS
redirect) and request IDs."""

import logging

import pytest
from django.test import Client
from rest_framework.test import APIRequestFactory

from core.middleware import RequestIDLogFilter, request_id_var
from planner import views
from weather import open_meteo

HEALTH = "/api/v1/health/"


@pytest.fixture
def production_like(settings):
    """Host validation and the HTTPS redirect on, as with DJANGO_DEBUG=false."""
    settings.ALLOWED_HOSTS = ["api.example.com"]
    settings.SECURE_SSL_REDIRECT = True
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    return settings


def test_head_on_health_returns_200():
    res = Client().head(HEALTH)
    assert res.status_code == 200
    assert res.content == b""


def test_health_view_itself_allows_head():
    """The DRF view (the fallback behind the middleware) accepts HEAD too."""
    request = APIRequestFactory().head(HEALTH)
    assert views.health(request).status_code == 200


def test_health_answers_a_checker_calling_by_ip_over_plain_http(production_like):
    open_meteo.QUOTA.reset()
    res = Client().get(HEALTH, HTTP_HOST="10.0.0.5:8000")  # plain HTTP, unknown host
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["weather_budget_minute_left"] == 480
    assert Client().head(HEALTH, HTTP_HOST="10.0.0.5:8000").status_code == 200


def test_other_paths_with_an_unknown_host_are_still_rejected(production_like):
    assert Client().get("/api/v1/risk-rules/", HTTP_HOST="10.0.0.5:8000").status_code == 400
    # A look-alike path is not the health check.
    assert Client().get("/api/v1/health/extra", HTTP_HOST="10.0.0.5:8000").status_code == 400


def test_other_paths_are_still_redirected_to_https(production_like):
    res = Client().get("/api/v1/risk-rules/", HTTP_HOST="api.example.com")
    assert res.status_code == 301
    assert res["Location"].startswith("https://api.example.com/")


def test_health_post_is_not_short_circuited(production_like):
    # Only GET/HEAD are answered early; anything else goes through the normal checks.
    assert Client().post(HEALTH, HTTP_HOST="10.0.0.5:8000").status_code == 400


# --- Request IDs ---------------------------------------------------------------------


def test_response_carries_a_generated_request_id():
    res = Client().get("/api/v1/risk-rules/")
    assert len(res["X-Request-ID"]) == 32


def test_incoming_request_id_is_echoed():
    res = Client().get("/api/v1/risk-rules/", HTTP_X_REQUEST_ID="abc-123.test")
    assert res["X-Request-ID"] == "abc-123.test"


@pytest.mark.parametrize("bad", ["has spaces", "x" * 65, "new\nline", "<script>"])
def test_unsafe_incoming_request_id_is_replaced(bad):
    res = Client().get("/api/v1/risk-rules/", HTTP_X_REQUEST_ID=bad)
    assert res["X-Request-ID"] != bad
    assert len(res["X-Request-ID"]) == 32


def test_log_lines_include_the_request_id(caplog, monkeypatch):
    seen = []

    def spy(*args, **kwargs):
        seen.append(request_id_var.get())
        return {"levels": [], "conditions": {}, "load_rules": []}

    monkeypatch.setattr(views, "rules_payload", spy)
    Client().get("/api/v1/risk-rules/", HTTP_X_REQUEST_ID="req-42")
    assert seen == ["req-42"]

    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    token = request_id_var.set("req-42")
    try:
        RequestIDLogFilter().filter(record)
    finally:
        request_id_var.reset(token)
    assert record.request_id == "req-42"
    RequestIDLogFilter().filter(record)
    assert record.request_id == "-"  # outside a request


def test_logging_config_formats_the_request_id(settings):
    assert "%(request_id)s" in settings.LOGGING["formatters"]["default"]["format"]
    assert settings.LOGGING["handlers"]["console"]["filters"] == ["request_id"]
