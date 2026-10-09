# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_active_memory_runtime.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.6.0
#   updated: 2026-07-22

"""Active memory reaches the runtime: settings, factory, readiness, lifecycle (ADR-097)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from l9_graphite_memory.active import (
    ActiveAgentSessionState,
    ActiveMemoryBinding,
    AgentEvent,
    AgentEventType,
    AgentStatus,
    LeaseExpiredError,
)
from l9_graphite_memory.active.deployment import ActiveDeployment, DeploymentEnvironment
from l9_graphite_memory.active.inmemory import InMemoryActiveStore, InMemoryAwarenessBus
from l9_graphite_memory.active.null_adapters import NullActiveStore, NullAwarenessBus
from l9_graphite_memory.adapters import build_active_memory
from l9_graphite_memory.adapters.factory import build_projection_runtime
from l9_graphite_memory.cli import build_parser
from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.contracts import OperationStatus
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.runtime import READINESS_FAMILIES, MemoryRuntime
from tests.conftest import make_store

# --- settings ----------------------------------------------------------------


def test_default_is_the_explicit_null_backend_and_not_selected() -> None:
    binding = build_active_memory(MemorySettings())
    assert binding.backend == "none" and binding.enabled is False
    assert isinstance(binding.store, NullActiveStore)
    assert isinstance(binding.bus, NullAwarenessBus)
    health = asyncio.run(binding.health())
    assert health.enabled is False and health.healthy is False


def test_redis_backend_requires_a_deployment_identity() -> None:
    with pytest.raises(ValidationError, match="deployment identity"):
        MemorySettings(active_memory_backend="redis", active_redis_url_env="X")


def test_redis_backend_requires_exactly_one_credential_source() -> None:
    base = {
        "active_memory_backend": "redis",
        "active_deployment_id": "dep",
        "active_trust_domain": "dom",
    }
    with pytest.raises(ValidationError, match="exactly one credential source"):
        MemorySettings(**base)
    with pytest.raises(ValidationError, match="exactly one credential source"):
        MemorySettings(**base, active_redis_url_env="A", active_redis_url_file="/run/secret")
    with pytest.raises(ValidationError, match="requires active_redis_host"):
        MemorySettings(**base, active_redis_password_file="/run/secret")
    with pytest.raises(ValidationError, match="must exceed"):
        MemorySettings(
            **base,
            active_redis_url_env="A",
            active_heartbeat_interval_seconds=30,
            active_lease_ttl_seconds=30,
        )


def test_environment_binds_every_active_setting(monkeypatch, tmp_path) -> None:
    for key, value in {
        "L9_MEMORY_DATA_DIR": str(tmp_path),
        "L9_MEMORY_STATE_DIR": str(tmp_path),
        "L9_MEMORY_ACTIVE_BACKEND": "redis",
        "L9_MEMORY_ACTIVE_REQUIRED": "true",
        "L9_MEMORY_ACTIVE_DEPLOYMENT_ID": "fleet-a",
        "L9_MEMORY_ACTIVE_TRUST_DOMAIN": "org",
        "L9_MEMORY_ACTIVE_ENVIRONMENT": "staging",
        "L9_MEMORY_ACTIVE_REDIS_URL_ENV": "FLEET_REDIS_URL",
        "L9_MEMORY_ACTIVE_REDIS_TLS": "false",
        "L9_MEMORY_ACTIVE_KEY_PREFIX": "fleet:active",
        "L9_MEMORY_ACTIVE_CONTEXT_TTL_SECONDS": "120",
        "L9_MEMORY_ACTIVE_PRESENCE_TTL_SECONDS": "45",
        "L9_MEMORY_ACTIVE_HEARTBEAT_INTERVAL_SECONDS": "5",
        "L9_MEMORY_ACTIVE_LEASE_TTL_SECONDS": "20",
        "L9_MEMORY_ACTIVE_HEARTBEAT_FAILURE_THRESHOLD": "2",
    }.items():
        monkeypatch.setenv(key, value)
    settings = load_settings()
    assert settings.active_memory_backend == "redis"
    assert settings.active_memory_required is True
    assert settings.active_deployment_id == "fleet-a"
    assert settings.active_trust_domain == "org"
    assert settings.active_environment == "staging"
    assert settings.active_redis_credential_sources == ("url_env",)
    assert settings.active_redis_tls is False
    assert settings.active_key_prefix == "fleet:active"
    assert settings.active_context_ttl_seconds == 120
    assert settings.active_presence_ttl_seconds == 45
    assert settings.active_heartbeat_interval_seconds == 5
    assert settings.active_lease_ttl_seconds == 20
    assert settings.active_heartbeat_failure_threshold == 2


# --- factory -----------------------------------------------------------------


def _redis_settings(**overrides: object) -> MemorySettings:
    values: dict[str, object] = {
        "active_memory_backend": "redis",
        "active_deployment_id": "fleet-a",
        "active_trust_domain": "org",
        "active_redis_url_env": "L9_TEST_FLEET_REDIS_URL",
    }
    values.update(overrides)
    return MemorySettings(**values)  # type: ignore[arg-type]


def test_factory_resolves_the_named_credential_source_without_connecting(monkeypatch) -> None:
    monkeypatch.setenv("L9_TEST_FLEET_REDIS_URL", "redis://:secret-value@redis.invalid:6379/0")
    binding = build_active_memory(_redis_settings(active_memory_required=True))
    assert binding.backend == "redis" and binding.enabled and binding.required
    assert binding.credential_source == "url_env"
    assert binding.deployment_id == "fleet-a" and binding.trust_domain == "org"
    described = binding.describe()
    assert "secret-value" not in repr(described) and "redis.invalid" not in repr(described)
    client = binding.client()
    assert client._deployment_id == "fleet-a"
    assert client._runtime_config.lease_ttl_seconds == 30


def test_factory_fails_closed_on_an_unresolvable_credential(monkeypatch) -> None:
    monkeypatch.delenv("L9_TEST_FLEET_REDIS_URL", raising=False)
    with pytest.raises(ConfigurationError, match="credential unresolved"):
        build_active_memory(_redis_settings())


def test_factory_rejects_a_placeholder_production_identity(monkeypatch) -> None:
    monkeypatch.setenv("L9_TEST_FLEET_REDIS_URL", "redis://redis.invalid:6379/0")
    with pytest.raises(ConfigurationError, match="deployment identity rejected"):
        build_active_memory(
            _redis_settings(active_deployment_id="changeme", active_environment="production")
        )


# --- readiness ---------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now_value = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now_value

    def advance(self, seconds: float) -> None:
        self.now_value += timedelta(seconds=seconds)


def _binding(
    *,
    enabled: bool = True,
    required: bool = False,
    store_unavailable: bool = False,
    bus_unavailable: bool = False,
) -> ActiveMemoryBinding:
    deployment = ActiveDeployment(
        deployment_id="unit-dep", trust_domain="unit", environment=DeploymentEnvironment.TEST
    )
    if not enabled:
        return ActiveMemoryBinding(
            backend="none",
            enabled=False,
            required=required,
            deployment_id="unit-dep",
            trust_domain="unit",
            environment="test",
            store=NullActiveStore(),
            bus=NullAwarenessBus(),
        )
    store = InMemoryActiveStore(deployment, clock=_Clock())
    store.set_unavailable(store_unavailable)
    bus = InMemoryAwarenessBus(deployment, simulate_unavailable=bus_unavailable)
    return ActiveMemoryBinding(
        backend="memory",
        enabled=True,
        required=required,
        deployment_id="unit-dep",
        trust_domain="unit",
        environment="test",
        store=store,
        bus=bus,
    )


def _runtime(settings: MemorySettings, binding: ActiveMemoryBinding, tmp_path) -> MemoryRuntime:
    from l9_graphite_memory.runtime import build_graph_service
    from l9_graphite_memory.services import MemoryService

    store = make_store("memory", tmp_path)
    store.initialize()
    service = MemoryService(store, build_projection_runtime(settings))
    service.initialize()
    from l9_graphite_memory.adapters import NullGraphIntelligence

    graph = NullGraphIntelligence()
    return MemoryRuntime(
        settings=settings,
        service=service,
        graph_intelligence=graph,
        graph_service=build_graph_service(settings, service, graph),
        active_memory=binding,
    )


def test_readiness_reports_every_family_independently(tmp_path) -> None:
    runtime = _runtime(MemorySettings(), _binding(), tmp_path)
    report = asyncio.run(runtime.readiness())
    assert tuple(f.name for f in report.families) == READINESS_FAMILIES
    assert report.ready is True and report.status is OperationStatus.COMPLETE
    assert report.full_capability is False  # projection and graph not selected
    assert report.family("canonical").healthy and report.family("canonical").required
    assert report.family("projection").selected is False
    assert report.family("graph").selected is False
    assert report.family("active_store").selected and report.family("active_store").healthy
    assert report.family("awareness_bus").selected and report.family("awareness_bus").healthy


def test_a_required_active_memory_that_is_absent_is_never_green(tmp_path) -> None:
    runtime = _runtime(
        MemorySettings(active_memory_required=True),
        _binding(enabled=False, required=True),
        tmp_path,
    )
    report = asyncio.run(runtime.readiness())
    assert report.ready is False and report.status is OperationStatus.FAILED
    assert report.family("active_store").ready is False
    assert report.family("awareness_bus").ready is False
    assert "active_store is required but not configured" in report.degraded_reasons


def test_an_unhealthy_required_family_fails_and_an_optional_one_only_degrades(tmp_path) -> None:
    required = _runtime(MemorySettings(), _binding(required=True, store_unavailable=True), tmp_path)
    report = asyncio.run(required.readiness())
    assert report.ready is False and report.status is OperationStatus.FAILED
    assert report.family("active_store").healthy is False
    assert report.family("awareness_bus").healthy is True
    assert "active_store is unhealthy" in report.degraded_reasons

    optional = _runtime(MemorySettings(), _binding(bus_unavailable=True), tmp_path)
    report = asyncio.run(optional.readiness())
    assert report.ready is True and report.status is OperationStatus.PARTIAL
    assert report.family("awareness_bus").healthy is False
    assert report.family("awareness_bus").ready is True
    assert report.full_capability is False


def test_readyz_carries_the_active_memory_families_and_gates_on_them(tmp_path) -> None:
    from fastapi.testclient import TestClient

    from l9_graphite_memory.server import create_http_app

    runtime = _runtime(
        MemorySettings(http_auth_required=False),
        _binding(required=True, store_unavailable=True),
        tmp_path,
    )
    response = TestClient(create_http_app(runtime)).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["active_memory"]["store"]["ready"] is False
    assert body["readiness"]["status"] == "failed"
    assert body["graph"]["ready"] is True

    runtime = _runtime(MemorySettings(http_auth_required=False), _binding(), tmp_path)
    response = TestClient(create_http_app(runtime)).get("/readyz")
    assert response.status_code == 200
    assert response.json()["readiness"]["ready"] is True


def test_cli_exposes_readiness() -> None:
    assert build_parser().parse_args(["readiness"]).command == "readiness"


# --- lifecycle ---------------------------------------------------------------


def _session_world():
    deployment = ActiveDeployment(
        deployment_id="unit-dep", trust_domain="unit", environment=DeploymentEnvironment.TEST
    )
    clock = _Clock()
    store = InMemoryActiveStore(deployment, clock=clock, presence_ttl_seconds=30)
    bus = InMemoryAwarenessBus(deployment)
    binding = ActiveMemoryBinding(
        backend="memory",
        enabled=True,
        required=False,
        deployment_id="unit-dep",
        trust_domain="unit",
        environment="test",
        store=store,
        bus=bus,
        heartbeat_interval_seconds=1,
        lease_ttl_seconds=3,
        heartbeat_failure_threshold=2,
    )
    return binding, store, clock


@pytest.mark.asyncio
async def test_an_outage_longer_than_the_lease_recovers_through_resynchronization() -> None:
    """A lease that lapsed during the outage used to end the heartbeat loop for good."""

    binding, store, clock = _session_world()
    client = binding.client(clock=clock)
    async with client.open_session(agent_id="a", role="r", principal_id="p") as session:
        first_instance = session.instance_id
        store.set_unavailable(True)
        await session._heartbeat_once()
        await session._heartbeat_once()
        assert session.state is ActiveAgentSessionState.DEGRADED
        clock.advance(10)  # longer than lease_ttl_seconds=3
        store.set_unavailable(False)
        with pytest.raises(LeaseExpiredError):
            await store.renew(session._lease)
        await session._heartbeat_once()
        assert session.state is ActiveAgentSessionState.ACTIVE
        assert session.instance_id != first_instance
        assert session.background_exception() is None
        await session.replace_context(objective="back", status=AgentStatus.ACTIVE)


@pytest.mark.asyncio
async def test_two_sessions_share_presence_context_and_awareness() -> None:
    binding, _store, clock = _session_world()
    client = binding.client(clock=clock)
    received: list[AgentEvent] = []

    async with client.open_session(
        agent_id="observer", role="r", principal_id="p", group_ids=("team",)
    ) as observer:

        async def consume() -> None:
            async for event in observer.subscribe(group_id="team"):
                received.append(event)
                if event.event_type is AgentEventType.AGENT_CONTEXT_UPDATED:
                    break

        task = asyncio.ensure_future(consume())
        await asyncio.sleep(0.01)
        async with client.open_session(
            agent_id="worker", role="r", principal_id="p", group_ids=("team",)
        ) as worker:
            context = await worker.replace_context(objective="share", status=AgentStatus.ACTIVE)
            await asyncio.wait_for(task, timeout=2.0)
            peers = {p.identity.agent_id for p in await observer.list_active(group_id="team")}
            assert peers == {"observer", "worker"}
            seen = await observer.get_peer_context("worker", worker.instance_id)
            assert seen is not None and seen.version == context.version
            assert seen.draft.objective == "share"
    kinds = [event.event_type for event in received]
    assert kinds[0] is AgentEventType.AGENT_REGISTERED
    assert AgentEventType.AGENT_CONTEXT_UPDATED in kinds
    assert all(event.agent_id == "worker" for event in received)


# --- redis probe classification (no server) ----------------------------------


class _RefusingRedis:
    """A Redis client whose server answers and refuses the credential."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def ping(self) -> bool:
        raise self._exc

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_a_refused_credential_is_reported_as_an_authentication_failure() -> None:
    from redis.exceptions import AuthenticationError, ConnectionError, NoPermissionError

    from l9_graphite_memory.active.errors import ActiveMemoryUnavailableError
    from l9_graphite_memory.active.redis_adapters import RedisActiveStore, RedisAwarenessBus

    deployment = ActiveDeployment(
        deployment_id="unit-dep", trust_domain="unit", environment=DeploymentEnvironment.TEST
    )
    refused = RedisActiveStore(
        "redis://127.0.0.1:1/0", deployment, client=_RefusingRedis(AuthenticationError("WRONGPASS"))
    )
    health = await refused.health()
    assert (health.connectivity, health.authentication) == ("unavailable", "failed")
    assert health.capabilities == () and "WRONGPASS" in str(health.error)

    restricted = RedisAwarenessBus(
        "redis://127.0.0.1:1/0", deployment, client=_RefusingRedis(NoPermissionError("NOPERM"))
    )
    bus_health = await restricted.health()
    assert bus_health.authentication == "insufficient_acl"

    unreachable = RedisActiveStore(
        "redis://127.0.0.1:1/0", deployment, client=_RefusingRedis(ConnectionError("refused"))
    )
    with pytest.raises(ActiveMemoryUnavailableError):
        await unreachable.health()

    binding = ActiveMemoryBinding(
        backend="redis",
        enabled=True,
        required=True,
        deployment_id="unit-dep",
        trust_domain="unit",
        environment="test",
        store=refused,
        bus=restricted,
    )
    report = await binding.health()
    assert report.healthy is False
    assert report.store["authentication"] == "failed"
    assert report.bus["authentication"] == "insufficient_acl"
