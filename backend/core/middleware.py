"""Request-level middleware.

HealthCheckMiddleware (first in MIDDLEWARE) answers GET/HEAD /api/v1/health/
before anything else runs. A platform's health checker may call the container
directly, by IP (Host "10.0.0.5:8000") and over plain HTTP; host validation
and the HTTPS redirect would otherwise answer 400 or 301 and mark a healthy
service as down. It never calls request.get_host().

RequestIDMiddleware gives each request an ID: the incoming X-Request-ID when
it looks safe, else a new one. It is echoed in the response and included in
every log line written while handling the request.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.http import HttpRequest, HttpResponse, JsonResponse

from core.health import HEALTH_PATH, health_payload

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class HealthCheckMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTH_PATH and request.method in ("GET", "HEAD"):
            response = JsonResponse(health_payload())
            response["Cache-Control"] = "no-store"
            if request.method == "HEAD":
                response.content = b""
            return response
        return self.get_response(request)


class RequestIDMiddleware:
    header = "X-Request-ID"

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(self.header, "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[self.header] = request_id
        return response


class RequestIDLogFilter(logging.Filter):
    """Adds `request_id` to log records ("-" outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
