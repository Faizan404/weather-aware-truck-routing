"""Django settings. Everything environment-specific comes from env vars."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or (
    "dev-insecure-key-change-me" if DEBUG else None
)
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "planner",
]

MIDDLEWARE = [
    # First: answers /api/v1/health/ before host validation and the HTTPS
    # redirect, so a health checker calling by IP over HTTP gets a 200.
    "core.middleware.HealthCheckMiddleware",
    "core.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# The app keeps no persistent state, so no database is configured.
DATABASES: dict = {}

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

USE_TZ = True
TIME_ZONE = "UTC"

REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"IGNORE_EXCEPTIONS": True},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            # Bounded for the 512 MB free plan: forecasts are one entry per
            # (cell, day); routes are stored thinned (routing/service.py).
            "OPTIONS": {"MAX_ENTRIES": 3000},
        }
    }

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
# The frontend reads Retry-After to say when to try again after a 429.
CORS_EXPOSE_HEADERS = ["Retry-After", "X-Request-ID"]
CORS_PREFLIGHT_MAX_AGE = 86400

# Trust CF-Connecting-IP / True-Client-IP for the client IP (core/client_ip.py).
# Only behind Cloudflare (Render is); elsewhere clients could forge them.
TRUST_CDN_IP_HEADERS = env_bool("TRUST_CDN_IP_HEADERS", False)

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    # Per-IP limits (core/throttling.py).
    "DEFAULT_THROTTLE_RATES": {"plan": "20/min", "heatmap": "20/min", "geocode": "60/min"},
    # Number of reverse proxies in front of the app (1 on Render), so the
    # client IP is read from X-Forwarded-For correctly and can't be spoofed.
    # 0 = use the socket address (local development).
    "NUM_PROXIES": int(os.environ.get("NUM_PROXIES", "0")),
}

# External services (all free, no API key).
OSRM_URL = os.environ.get("OSRM_URL", "https://router.project-osrm.org")
PHOTON_URL = os.environ.get("PHOTON_URL", "https://photon.komoot.io")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org")
OPEN_METEO_URL = os.environ.get("OPEN_METEO_URL", "https://api.open-meteo.com")
# Public OSRM, Nominatim and Photon ask clients to identify themselves with a
# contact; the repository URL serves as one.
REPO_URL = os.environ.get("REPO_URL", "https://github.com/Faizan404/weather-aware-truck-routing")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", f"weather-aware-truck-routing/1.0 (+{REPO_URL})")
HTTP_TIMEOUT_SECONDS = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "20"))
# Total time budget for one /plan/ or /heatmap/ request, across all upstream
# calls (core/deadline.py). Keep gunicorn's --timeout above it.
PLAN_DEADLINE_SECONDS = float(os.environ.get("PLAN_DEADLINE_SECONDS", "60"))

# Reported by /api/v1/health/ (set by the deploy, e.g. Render's RENDER_GIT_COMMIT).
GIT_SHA = os.environ.get("GIT_SHA") or os.environ.get("RENDER_GIT_COMMIT") or "dev"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "core.middleware.RequestIDLogFilter"}},
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "filters": ["request_id"], "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

if not DEBUG:
    # TLS ends at the platform's proxy, which sets X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True  # /api/v1/health/ is answered before this (core/middleware.py)
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    X_FRAME_OPTIONS = "DENY"

SILENCED_SYSTEM_CHECKS = [
    # CSRF middleware: a cookie-less JSON API (no sessions, no auth cookies),
    # so there is nothing for a cross-site request to ride on.
    "security.W003",
    # HSTS preload: an *.onrender.com host can't be submitted to the preload list.
    "security.W021",
]
