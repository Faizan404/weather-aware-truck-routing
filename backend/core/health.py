"""The health payload, shared by the early health middleware and the view."""

from __future__ import annotations

from django.conf import settings

HEALTH_PATH = "/api/v1/health/"


def health_payload() -> dict:
    from weather import open_meteo  # imported lazily: keeps the middleware light at startup

    return {
        "status": "ok",
        "version": settings.GIT_SHA,
        # Open-Meteo locations left in this minute's budget (shared by all users).
        "weather_budget_minute_left": open_meteo.QUOTA.remaining(60),
    }
