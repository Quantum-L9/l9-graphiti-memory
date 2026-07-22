# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/circuit_breaker.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Thread-safe circuit breaker used by optional external projections."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitSnapshot:
    state: CircuitState
    failure_count: int
    last_failure_monotonic: float | None


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock
        self._failure_count = 0
        self._last_failure: float | None = None
        self._state = CircuitState.CLOSED
        self._lock = threading.RLock()

    def record_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._last_failure = None
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure = self._clock()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        with self._lock:
            if self._state is CircuitState.CLOSED:
                return True
            if self._state is CircuitState.OPEN:
                if (
                    self._last_failure is not None
                    and self._clock() - self._last_failure >= self.recovery_timeout
                ):
                    self._state = CircuitState.HALF_OPEN
                    return True
                return False
            return False

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            return CircuitSnapshot(self._state, self._failure_count, self._last_failure)

    def status(self) -> dict[str, object]:
        snapshot = self.snapshot()
        return {
            "state": snapshot.state.value,
            "failure_count": snapshot.failure_count,
            "last_failure_monotonic": snapshot.last_failure_monotonic,
        }
