"""Rolling-window usage budget, so the app never exceeds a provider's quota.

Each window is (seconds, max units). `reserve(n, max_wait)` records n units
once every window has room. If a window is full it waits for enough old usage
to expire, but only up to `max_wait` seconds; past that nothing is recorded
and the caller must skip the call. Process-wide and thread-safe (production
runs a single gunicorn worker, see Dockerfile).
"""

from __future__ import annotations

import threading
import time
from collections import deque


class RollingQuota:
    def __init__(self, windows: list[tuple[float, int]], clock=time.monotonic, sleep=time.sleep):
        self.windows = sorted(windows)
        self._events: deque[tuple[float, int]] = deque()  # (timestamp, units)
        self._lock = threading.Lock()
        self._clock = clock
        self._sleep = sleep

    def _prune(self, now: float) -> None:
        longest = self.windows[-1][0]
        while self._events and now - self._events[0][0] >= longest:
            self._events.popleft()

    def _wait_needed(self, now: float, units: int) -> float | None:
        """Seconds until `units` fit in every window (0 = now), or None if
        they never can (more units than a window allows)."""
        wait = 0.0
        for span, limit in self.windows:
            if units > limit:
                return None
            live = [(ts, u) for ts, u in self._events if now - ts < span]
            excess = sum(u for _, u in live) + units - limit
            freed = 0
            for ts, u in live:  # oldest first
                if excess <= 0:
                    break
                freed += u
                if freed >= excess:
                    wait = max(wait, ts + span - now)
                    break
        return wait

    def reserve(self, units: int, max_wait: float = 0.0) -> bool:
        deadline = self._clock() + max_wait
        while True:
            with self._lock:
                now = self._clock()
                self._prune(now)
                wait = self._wait_needed(now, units)
                if wait == 0:
                    self._events.append((now, units))
                    return True
            if wait is None or now + wait > deadline:
                return False
            self._sleep(wait + 0.01)

    def remaining(self, span: float) -> int:
        """Units still available now in the window of `span` seconds."""
        limit = dict(self.windows)[span]
        with self._lock:
            now = self._clock()
            used = sum(u for ts, u in self._events if now - ts < span)
        return max(0, limit - used)

    def try_reserve(self, units: int) -> bool:
        return self.reserve(units, max_wait=0.0)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
