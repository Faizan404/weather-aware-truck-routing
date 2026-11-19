"""Shared HTTP client for third-party APIs.

- Identifies the app with a User-Agent (required by the OSRM/FOSSGIS and
  Nominatim usage policies).
- Spaces requests to rate-limited public servers. The FOSSGIS routing servers
  (router.project-osrm.org) and Nominatim allow at most 1 request per second;
  the throttle is shared by all threads in the process.
- Retries connection errors and 5xx with backoff. A 429 (rate limited) is
  never retried: the server is asking us to slow down, so all calls to that
  host are paused for COOLDOWN_SECONDS (or Retry-After, if longer) and fail
  fast in the meantime.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from core import deadline
from core.exceptions import UpstreamTimeout

logger = logging.getLogger(__name__)

RETRY_STATUS = {500, 502, 503, 504}

# Minimum seconds between requests to a host (published usage policies).
HOST_MIN_INTERVAL: dict[str, float] = {
    "router.project-osrm.org": 1.0,
    "nominatim.openstreetmap.org": 1.0,
    # Photon has no published number; keep autocomplete gentle.
    "photon.komoot.io": 0.3,
}


COOLDOWN_SECONDS = 60.0
_cooldown_until: dict[str, float] = {}
_cooldown_lock = threading.Lock()


def _start_cooldown(host: str, retry_after: str | None) -> None:
    seconds = COOLDOWN_SECONDS
    try:
        seconds = max(seconds, float(retry_after)) if retry_after else seconds
    except ValueError:
        pass
    with _cooldown_lock:
        _cooldown_until[host] = time.monotonic() + seconds
    logger.warning("Rate limited by %s; pausing calls for %.0f s", host, seconds)


def _in_cooldown(host: str) -> bool:
    with _cooldown_lock:
        return time.monotonic() < _cooldown_until.get(host, 0.0)


def reset_cooldowns() -> None:
    with _cooldown_lock:
        _cooldown_until.clear()


class UpstreamError(Exception):
    """A third-party call failed after retries."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class _HostThrottle:
    """Process-wide spacing of requests per host: one at a time, at least
    `interval` seconds apart (measured from the end of the previous one)."""

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._last: dict[str, float] = {}
        self._guard = threading.Lock()

    def lock_for(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())

    def run(self, host: str, interval: float, fn):
        lock = self.lock_for(host)
        left = deadline.time_left()
        # Queue behind other requests to this host only while the budget lasts.
        if not lock.acquire(timeout=-1 if left is None else max(0.0, left)):
            raise UpstreamTimeout("The request took too long. Please try again.")
        try:
            wait = self._last.get(host, 0.0) + interval - time.monotonic()
            if wait > 0:
                time.sleep(deadline.cap_wait(wait))
                deadline.check()
            try:
                return fn()
            finally:
                self._last[host] = time.monotonic()
        finally:
            lock.release()


throttle = _HostThrottle()


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        headers={"User-Agent": settings.HTTP_USER_AGENT},
        follow_redirects=True,
    )


def _send(method: str, url: str, params: dict | None, json: Any, key: str) -> httpx.Response:
    def call() -> httpx.Response:
        # Timeout taken when the call starts, after any wait for the host.
        with _client(deadline.call_timeout()) as client:
            return client.request(method, url, params=params, json=json)

    interval = HOST_MIN_INTERVAL.get(key)
    return throttle.run(key, interval, call) if interval else call()


def request_json(
    method: str,
    url: str,
    *,
    params: dict | None = None,
    json: Any = None,
    retries: int = 2,
    backoff: float = 1.0,
    throttle_key: str | None = None,
) -> Any:
    """Send a request and return decoded JSON.

    Raises UpstreamError for network failures or non-2xx responses. For 4xx
    responses the decoded body is attached so callers can tell "no route"
    apart from "service down".

    `throttle_key` names the service whose limits apply, for the request
    spacing and the 429 cool-down. It defaults to the URL's host; pass the
    real upstream's host when calling it through a forwarder (e.g. a
    *.vercel.app function), so its published limits still hold.
    """
    host = throttle_key or urlsplit(url).hostname or ""
    if _in_cooldown(host):
        raise UpstreamError(f"{url}: paused after rate limiting", 429)
    last_error: UpstreamError | None = None
    for attempt in range(retries + 1):
        deadline.check()
        try:
            response = _send(method, url, params, json, host)
        except httpx.HTTPError as exc:
            deadline.check()  # a timeout cut short by the budget ends the request
            last_error = UpstreamError(f"{url}: {exc.__class__.__name__}")
        else:
            if response.is_success:
                return response.json()
            body: Any
            try:
                body = response.json()
            except ValueError:
                body = response.text[:500]
            last_error = UpstreamError(
                f"{url}: HTTP {response.status_code}", response.status_code, body
            )
            if response.status_code == 429:
                _start_cooldown(host, response.headers.get("Retry-After"))
            if response.status_code not in RETRY_STATUS:
                break
        if attempt < retries:
            time.sleep(deadline.cap_wait(backoff * (2**attempt)))
    assert last_error is not None
    logger.warning("Upstream request failed: %s", last_error)
    raise last_error
