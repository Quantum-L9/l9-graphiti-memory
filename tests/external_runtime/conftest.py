"""Fixtures for external-runtime lifecycle tests.

These tests exercise `ActiveAgentClient`/`ActiveAgentSession` — the
stable public SDK — against the in-memory reference adapter, simulating
backend outages, reconnects, and process-restart scenarios that a real
external consumer application would encounter against a real Redis
deployment.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from l9_graphite_memory.active.client import ActiveAgentClient
from l9_graphite_memory.active.deployment import ActiveDeployment, DeploymentEnvironment
from l9_graphite_memory.active.inmemory import InMemoryActiveStore, InMemoryAwarenessBus


class FakeClock:
    """Deterministic, manually advanced clock for external-runtime tests."""

    def __init__(self) -> None:
        self._current = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._current = self._current + timedelta(seconds=seconds)


@pytest.fixture
def deployment() -> ActiveDeployment:
    return ActiveDeployment(
        deployment_id="external-runtime-test",
        trust_domain="external-runtime",
        environment=DeploymentEnvironment.TEST,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def active_store(deployment: ActiveDeployment, clock: FakeClock) -> InMemoryActiveStore:
    return InMemoryActiveStore(
        deployment, clock=clock, context_ttl_seconds=60, presence_ttl_seconds=30
    )


@pytest.fixture
def awareness_bus(deployment: ActiveDeployment) -> InMemoryAwarenessBus:
    return InMemoryAwarenessBus(deployment)


@pytest.fixture
def client(
    active_store: InMemoryActiveStore,
    awareness_bus: InMemoryAwarenessBus,
    deployment: ActiveDeployment,
    clock: FakeClock,
) -> ActiveAgentClient:
    return ActiveAgentClient(
        store=active_store,
        bus=awareness_bus,
        deployment_id=deployment.deployment_id,
        clock=clock,
        heartbeat_interval_seconds=1,
        lease_ttl_seconds=3,
        heartbeat_failure_threshold=2,
    )
