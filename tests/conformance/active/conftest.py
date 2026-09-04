# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/active/conftest.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""Shared fixtures for the active-memory adapter conformance suite.

Any adapter implementing `ActiveStore`/`AwarenessBus` (in-memory,
Redis, or future backends) MUST pass every test in this directory
unmodified. This is the enforcement mechanism for "Redis adapter
behavior matches the in-memory reference adapter exactly" required by
the build plan.

The ``store`` fixture is parameterized over the reference adapter and the
Redis adapter. The Redis leg runs whenever ``L9_MEMORY_TEST_REDIS_URL`` names
a throwaway server and skips loudly otherwise, so a missing server narrows the
matrix visibly rather than silently, as the PostgreSQL matrix does.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest

from l9_graphite_memory.active.deployment import ActiveDeployment, DeploymentEnvironment
from l9_graphite_memory.active.inmemory import InMemoryActiveStore, InMemoryAwarenessBus
from l9_graphite_memory.active.redis_adapters import RedisActiveStore

REDIS_URL_ENV = "L9_MEMORY_TEST_REDIS_URL"
ACTIVE_STORE_BACKENDS = ("memory", "redis")


class FakeClock:
    """Deterministic, manually advanced clock for conformance tests."""

    def __init__(self, start: datetime | None = None) -> None:
        self._current = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._current = self._current + timedelta(seconds=seconds)


class _UnavailableClient:
    """A Redis client whose server has gone away: every command fails."""

    def __getattr__(self, name: str) -> Any:
        async def fail(*args: Any, **kwargs: Any) -> Any:
            from redis.exceptions import ConnectionError as RedisConnectionError

            raise RedisConnectionError(f"simulated outage during {name}")

        return fail


class ConformanceRedisActiveStore(RedisActiveStore):
    """The production adapter plus the outage toggle the suite drives."""

    def __init__(self, url: str, deployment: ActiveDeployment, **kwargs: Any) -> None:
        super().__init__(url, deployment, **kwargs)
        self._live_client = self._r
        self._key_prefix = str(kwargs["key_prefix"])

    def set_unavailable(self, value: bool) -> None:
        self._r = _UnavailableClient() if value else self._live_client

    async def purge(self) -> None:
        """Remove every key this test wrote; the server is shared across tests."""

        async for key in self._live_client.scan_iter(match=f"{self._key_prefix}*"):
            await self._live_client.unlink(key)


@pytest.fixture
def deployment() -> ActiveDeployment:
    return ActiveDeployment(
        deployment_id="conformance-test",
        trust_domain="conformance",
        environment=DeploymentEnvironment.TEST,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(params=ACTIVE_STORE_BACKENDS)
async def store(
    request: pytest.FixtureRequest, deployment: ActiveDeployment, clock: FakeClock
) -> AsyncIterator[InMemoryActiveStore | ConformanceRedisActiveStore]:
    """Every ActiveStore adapter under test, one per parameter."""

    if request.param == "memory":
        yield InMemoryActiveStore(
            deployment,
            clock=clock,
            context_ttl_seconds=60,
            presence_ttl_seconds=30,
        )
        return
    url = os.environ.get(REDIS_URL_ENV, "").strip()
    if not url:
        pytest.skip(
            f"{REDIS_URL_ENV} is not set; the Redis leg of the active-store "
            "conformance matrix requires a throwaway Redis server"
        )
    redis_store = ConformanceRedisActiveStore(
        url,
        deployment,
        clock=clock,
        key_prefix=f"l9gm:conformance:{uuid.uuid4().hex}",
        context_ttl_seconds=60,
        presence_ttl_seconds=30,
    )
    try:
        yield redis_store
    finally:
        await redis_store.purge()
        await redis_store.close()


@pytest.fixture
def bus(deployment: ActiveDeployment) -> InMemoryAwarenessBus:
    """Reference AwarenessBus adapter under test."""
    return InMemoryAwarenessBus(deployment)
