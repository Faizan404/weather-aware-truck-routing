import os

import pytest

os.environ.setdefault("DJANGO_DEBUG", "true")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret")


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    from core.http import reset_cooldowns
    from weather.open_meteo import QUOTA

    cache.clear()
    QUOTA.reset()
    reset_cooldowns()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _no_throttle_delay(monkeypatch):
    """Tests mock HTTP, so skip the real 1 s spacing (tested separately)."""
    from core import http

    monkeypatch.setattr(http, "HOST_MIN_INTERVAL", {})
