"""Domain errors and a DRF exception handler that renders one consistent shape:

    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Base class for errors we expect and want to show to the user."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NoRouteFound(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "no_route"


class UpstreamUnavailable(DomainError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "upstream_unavailable"


class UpstreamTimeout(DomainError):
    """The request's total time budget ran out (core/deadline.py)."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "upstream_timeout"


def _error(code: str, message: str, details: dict | None, http_status: int) -> Response:
    return Response(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status=http_status,
    )


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return _error(exc.code, exc.message, exc.details, exc.status_code)

    if isinstance(exc, ValidationError):
        return _error("validation_error", "Invalid request.", exc.detail, exc.status_code)

    response = exception_handler(exc, context)
    if response is not None and isinstance(exc, APIException):
        error = _error(exc.default_code, str(exc.detail), None, response.status_code)
        if "Retry-After" in response:  # throttled: tell the client when to retry
            error["Retry-After"] = response["Retry-After"]
        return error

    logger.exception("Unhandled error", exc_info=exc)
    return _error(
        "internal_error", "Something went wrong.", None, status.HTTP_500_INTERNAL_SERVER_ERROR
    )
