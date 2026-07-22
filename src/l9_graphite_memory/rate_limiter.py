# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/rate_limiter.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Thread-safe sliding-window rate limiter."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        per_minute: int = 60,
        per_hour: int = 1_000,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if per_minute < 1 or per_hour < 1:
            raise ValueError("rate limits must be positive")
        if per_hour < per_minute:
            raise ValueError("hourly limit cannot be lower than minute limit")
        self.per_minute = per_minute
        self.per_hour = per_hour
        self._clock = clock
        self._minute_window: deque[float] = deque()
        self._hour_window: deque[float] = deque()
        self._lock = threading.RLock()

    def _prune(self, now: float) -> None:
        while self._minute_window and now - self._minute_window[0] >= 60:
            self._minute_window.popleft()
        while self._hour_window and now - self._hour_window[0] >= 3_600:
            self._hour_window.popleft()

    def allow(self) -> bool:
        with self._lock:
            now = self._clock()
            self._prune(now)
            return (
                len(self._minute_window) < self.per_minute
                and len(self._hour_window) < self.per_hour
            )

    def record(self) -> None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            if (
                len(self._minute_window) >= self.per_minute
                or len(self._hour_window) >= self.per_hour
            ):
                raise RuntimeError("rate limit exceeded")
            self._minute_window.append(now)
            self._hour_window.append(now)

    def check_and_record(self) -> None:
        self.record()

    def status(self) -> dict[str, int]:
        with self._lock:
            now = self._clock()
            self._prune(now)
            return {
                "minute_count": len(self._minute_window),
                "minute_limit": self.per_minute,
                "hour_count": len(self._hour_window),
                "hour_limit": self.per_hour,
            }
