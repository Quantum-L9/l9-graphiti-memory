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
from l9_graphite_memory.active.errors import ActiveMemoryUnavailableError
from l9_graphite_memory.active.inmemory import InMemoryActiveStore, InMemoryAwarenessBus
from l9_graphite_memory.active.null_adapters import NullActiveStore, NullAwarenessBus
from l9_graphite_memory.active.redis_adapters import RedisHealth
from l9_graphite_memory.adapters import build_active_memory
from l9_graphite_memory.adapters.factory import build_projection_runtime
from l9_graphite_memory.cli import build_parser
from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.contracts import OperationStatus
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.projections.compiler import compile_projection
from l9_graphite_memory.projections.manifest import parse_projection_manifest_data
from l9_graphite_memory.projections.runtime import ProjectionRuntime
from l9_graphite_memory.runtime import READINESS_FAMILIES, MemoryRuntime, _family, _full_capability
from tests.conftest import make_store
from tests.unit.test_projection_runtime import GRAPHITI, ZEP, StubAdapter, with_modes

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


_COMPLETE_STORE_PROBE = RedisHealth(capabilities=("ping", "scalar", "sorted_set"))
_COMPLETE_BUS_PROBE = RedisHealth(capabilities=("ping", "publish"))


class _ProbedStore(InMemoryActiveStore):
    """In-memory store whose probe reports the evidence a complete Redis probe yields.

    The bare in-memory adapter runs no capability probe, so readiness must not
    read it as proven; this double supplies the positive evidence explicitly.
    """

    async def health(self):  # type: ignore[override]
        observed = await super().health()
        return _COMPLETE_STORE_PROBE if observed.connectivity == "healthy" else observed


class _ProbedBus(InMemoryAwarenessBus):
    async def health(self):  # type: ignore[override]
        observed = await super().health()
        return _COMPLETE_BUS_PROBE if observed.connectivity == "healthy" else observed


class _FixedHealth:
    """Adapter stub whose probe returns (or raises) exactly the given result."""

    def __init__(self, result: object) -> None:
        self._result = result

    async def health(self) -> object:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    async def close(self) -> None:
        return None


def _probed_binding(store: object, bus: object, *, required: bool = True) -> ActiveMemoryBinding:
    return ActiveMemoryBinding(
        backend="redis",
        enabled=True,
        required=required,
        deployment_id="unit-dep",
        trust_domain="unit",
        environment="test",
        store=_FixedHealth(store),  # type: ignore[arg-type]
        bus=_FixedHealth(bus),  # type: ignore[arg-type]
    )


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
    store = _ProbedStore(deployment, clock=_Clock())
    store.set_unavailable(store_unavailable)
    bus = _ProbedBus(deployment, simulate_unavailable=bus_unavailable)
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


def _runtime(
    settings: MemorySettings,
    binding: ActiveMemoryBinding,
    tmp_path,
    projections: ProjectionRuntime | None = None,
) -> MemoryRuntime:
    from l9_graphite_memory.runtime import build_graph_service
    from l9_graphite_memory.services import MemoryService

    store = make_store("memory", tmp_path)
    store.initialize()
    service = MemoryService(store, projections or build_projection_runtime(settings))
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


def _active_families(binding: ActiveMemoryBinding, tmp_path):
    report = asyncio.run(_runtime(MemorySettings(), binding, tmp_path).readiness())
    return report, report.family("active_store"), report.family("awareness_bus")


@pytest.mark.parametrize(
    "store_probe",
    [
        RedisHealth(),  # a probe that completed no step at all
        RedisHealth(capabilities=("ping",)),
        RedisHealth(capabilities=("ping", "scalar")),  # sorted_set missing
        RedisHealth(capabilities=("ping", "sorted_set")),  # scalar missing
    ],
    ids=["empty", "ping-only", "no-sorted-set", "no-scalar"],
)
def test_an_incomplete_store_probe_is_never_green(store_probe, tmp_path) -> None:
    report, store, bus = _active_families(
        _probed_binding(store_probe, _COMPLETE_BUS_PROBE), tmp_path
    )
    assert store.healthy is False and store.ready is False
    assert bus.healthy is True and bus.ready is True  # the bus is judged on its own evidence
    assert report.ready is False and report.status is OperationStatus.FAILED
    assert report.full_capability is False
    assert "active_store is unhealthy" in report.degraded_reasons


@pytest.mark.parametrize(
    "bus_probe",
    [RedisHealth(), RedisHealth(capabilities=("ping",))],
    ids=["empty", "ping-only-no-publish"],
)
def test_an_incomplete_bus_probe_is_never_green(bus_probe, tmp_path) -> None:
    report, store, bus = _active_families(
        _probed_binding(_COMPLETE_STORE_PROBE, bus_probe), tmp_path
    )
    assert bus.healthy is False and bus.ready is False
    assert store.healthy is True
    assert report.ready is False and report.full_capability is False


class _NoAuthenticationField:
    """A structurally incomplete probe result: no authentication attribute."""

    backend = "redis"
    connectivity = "healthy"
    capabilities = ("ping", "scalar", "sorted_set")


@pytest.mark.parametrize(
    ("store_probe", "expected_detail"),
    [
        (
            RedisHealth(
                connectivity="unavailable",
                authentication="failed",
                capabilities=(),
                error="ping probe failed: invalid password",
            ),
            {"authentication": "failed"},
        ),
        (
            RedisHealth(
                connectivity="degraded",
                authentication="insufficient_acl",
                capabilities=("ping",),
                error="scalar probe failed: NOPERM",
            ),
            {"authentication": "insufficient_acl"},
        ),
        # ACL denial classified without an error string must still fail closed.
        (
            RedisHealth(authentication="insufficient_acl", capabilities=("ping",)),
            {"authentication": "insufficient_acl"},
        ),
        (
            ActiveMemoryUnavailableError("ping probe failed: connection refused"),
            {"connectivity": "unavailable"},
        ),
        (_NoAuthenticationField(), {"connectivity": "healthy"}),
    ],
    ids=["auth-refused", "acl-denied", "acl-denied-no-error", "unavailable", "no-auth-field"],
)
def test_a_refused_or_unproven_probe_fails_closed_and_keeps_its_classification(
    store_probe, expected_detail, tmp_path
) -> None:
    report, store, _ = _active_families(_probed_binding(store_probe, _COMPLETE_BUS_PROBE), tmp_path)
    assert store.healthy is False and store.ready is False
    assert report.full_capability is False
    for key, value in expected_detail.items():
        assert store.detail[key] == value


def test_complete_probes_are_healthy_and_leave_canonical_writes_independent(tmp_path) -> None:
    report, store, bus = _active_families(
        _probed_binding(_COMPLETE_STORE_PROBE, _COMPLETE_BUS_PROBE), tmp_path
    )
    assert store.healthy and store.ready and bus.healthy and bus.ready
    assert report.ready is True and report.status is OperationStatus.COMPLETE
    # Projection and graph are not selected here, so the stricter verdict is
    # still withheld; the live suite proves full_capability=true end to end.
    assert report.full_capability is False


def test_an_optional_unproven_active_memory_only_degrades(tmp_path) -> None:
    report, store, _ = _active_families(
        _probed_binding(RedisHealth(), _COMPLETE_BUS_PROBE, required=False), tmp_path
    )
    assert store.healthy is False and store.ready is True
    assert report.ready is True and report.status is OperationStatus.PARTIAL
    assert report.full_capability is False


def _families(*, all_healthy: bool) -> list:
    reasons: list[str] = []
    return [
        _family(
            name,
            selected=True,
            required=True,
            healthy=all_healthy or name != "graph",
            detail={},
            reasons=reasons,
        )
        for name in READINESS_FAMILIES
    ]


def test_full_capability_requires_the_shared_postgres_canonical_store() -> None:
    assert _full_capability(_families(all_healthy=True), shared_store=True) is True
    # Every family selected and healthy over a process-local SQLite ledger is
    # still not the shared-agent deployment.
    assert _full_capability(_families(all_healthy=True), shared_store=False) is False
    assert _full_capability(_families(all_healthy=False), shared_store=True) is False


def test_a_sqlite_canonical_store_is_ready_but_reports_it_is_not_shared(tmp_path) -> None:
    report = asyncio.run(_runtime(MemorySettings(), _binding(), tmp_path).readiness())
    canonical = report.family("canonical")
    assert canonical.ready and canonical.healthy
    assert canonical.detail["shared_store"] is False
    assert report.full_capability is False


def _manifest_projections(graphiti_mode: str, zep_mode: str, status: str, *, healthy: bool):
    compiled = compile_projection(
        parse_projection_manifest_data(with_modes(graphiti_mode, zep_mode, status=status))
    )
    return ProjectionRuntime.from_compiled(
        compiled,
        {
            GRAPHITI: StubAdapter("graphiti", healthy=healthy),
            ZEP: StubAdapter("zep", healthy=healthy),
        },
    )


def test_a_shadow_only_projection_is_not_a_selected_family(tmp_path) -> None:
    # Both targets unreachable: a shadow target delivers but never feeds
    # retrieval or degrades health, so it must not stand in for a projection.
    projections = _manifest_projections("shadow", "shadow", "shadow", healthy=False)
    assert projections.enabled and not projections.active_targets()
    report = asyncio.run(
        _runtime(MemorySettings(), _binding(), tmp_path, projections=projections).readiness()
    )
    projection = report.family("projection")
    assert projection.selected is False and projection.healthy is False
    assert projection.ready is True  # an unselected optional family never blocks ready
    assert report.full_capability is False


def test_a_projection_with_an_active_target_is_selected_and_probed(tmp_path) -> None:
    healthy = _manifest_projections("active", "shadow", "active", healthy=True)
    report = asyncio.run(
        _runtime(MemorySettings(), _binding(), tmp_path, projections=healthy).readiness()
    )
    assert report.family("projection").selected and report.family("projection").healthy

    down = _manifest_projections("active", "shadow", "active", healthy=False)
    report = asyncio.run(
        _runtime(MemorySettings(), _binding(), tmp_path, projections=down).readiness()
    )
    assert report.family("projection").selected and not report.family("projection").healthy
    assert report.ready is False and report.full_capability is False


class _ExpireDeniedRedis:
    """Permits ZADD but refuses EXPIRE, as a misconfigured restricted ACL does."""

    def __init__(self, refusal: Exception) -> None:
        self._refusal = refusal
        self.values: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}

    async def ping(self) -> bool:
        return True

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def unlink(self, key: str) -> None:
        self.values.pop(key, None)
        self.zsets.pop(key, None)

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.zsets.setdefault(key, {}).update(mapping)

    async def expire(self, key: str, seconds: int) -> None:
        raise self._refusal

    async def zrem(self, key: str, member: str) -> None:
        members = self.zsets.get(key, {})
        members.pop(member, None)
        if key in self.zsets and not members:
            del self.zsets[key]  # Redis deletes an emptied sorted set

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_a_refused_expire_leaves_no_probe_key_behind() -> None:
    from redis.exceptions import NoPermissionError

    from l9_graphite_memory.active.redis_adapters import RedisActiveStore

    deployment = ActiveDeployment(
        deployment_id="unit-dep", trust_domain="unit", environment=DeploymentEnvironment.TEST
    )
    client = _ExpireDeniedRedis(NoPermissionError("NOPERM expire"))
    store = RedisActiveStore("redis://127.0.0.1:1/0", deployment, client=client)
    for _ in range(3):  # every readiness poll uses a fresh timestamped key
        health = await store.health()
        assert health.authentication == "insufficient_acl"
        assert health.capabilities == ("ping", "scalar")
    assert client.zsets == {} and client.values == {}


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
