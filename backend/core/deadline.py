"""A total time budget for one request, shared by all its upstream calls.

    with deadline(60):
        plan_trip(...)        # every request_json() inside respects it

Each upstream call's timeout is min(HTTP_TIMEOUT_SECONDS, time left), and
waits (rate-limit spacing, retry backoff, quota) never run past it. Once the
budget is spent, UpstreamTimeout (503, code "upstream_timeout") ends the
request instead of leaving the client hanging.

The deadline lives in a context variable, so it follows the request through
helper functions. Thread pools don't inherit it on their own: submit work with
contextvars.copy_context().run (see weather/open_meteo.py).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from django.conf import settings

from core.exceptions import UpstreamTimeout

_deadline: ContextVar[float | None] = ContextVar("request_deadline", default=None)


@contextmanager
def deadline(seconds: float) -> Iterator[None]:
    token = _deadline.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def time_left() -> float | None:
    """Seconds left in the current budget, or None when there is no budget."""
    end = _deadline.get()
    return None if end is None else end - time.monotonic()


def check() -> None:
    left = time_left()
    if left is not None and left <= 0:
        raise UpstreamTimeout("The request took too long. Please try again.")


def call_timeout() -> float:
    """Timeout for the next upstream call. Raises if the budget is spent."""
    check()
    left = time_left()
    return settings.HTTP_TIMEOUT_SECONDS if left is None else min(settings.HTTP_TIMEOUT_SECONDS, left)


def cap_wait(seconds: float) -> float:
    """Shorten a wait so it ends with the budget at the latest."""
    left = time_left()
    return seconds if left is None else max(0.0, min(seconds, left))
