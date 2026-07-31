# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/active/conftest.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Shared fixtures for the active-memory adapter conformance suite.

Any adapter implementing `ActiveStore`/`AwarenessBus` (in-memory,
Redis, or future backends) MUST pass every test in this directory
unmodified. This is the enforcement mechanism for "Redis adapter
behavior matches the in-memory reference adapter exactly" required by
the build plan.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from l9_graphite_memory.active.deployment import ActiveDeployment, DeploymentEnvironment
from l9_graphite_memory.active.inmemory import InMemoryActiveStore, InMemoryAwarenessBus


class FakeClock:
    """Deterministic, manually advanced clock for conformance tests."""

    def __init__(self, start: datetime | None = None) -> None:
        self._current = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._current = self._current + timedelta(seconds=seconds)


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


@pytest.fixture
def store(deployment: ActiveDeployment, clock: FakeClock) -> InMemoryActiveStore:
    """Reference ActiveStore adapter under test.

    NOTE: When a Redis adapter is implemented in a follow-up change, add
    a parallel fixture (e.g. via `pytest.fixture(params=[...])`) that
    yields both this in-memory instance and a real Redis-backed instance
    so every test below runs against both backends.
    """
    return InMemoryActiveStore(
        deployment,
        clock=clock,
        context_ttl_seconds=60,
        presence_ttl_seconds=30,
    )


@pytest.fixture
def bus(deployment: ActiveDeployment) -> InMemoryAwarenessBus:
    """Reference AwarenessBus adapter under test. See `store` fixture note."""
    return InMemoryAwarenessBus(deployment)
