# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_full_capability_readiness_live.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.6.0
#   updated: 2026-07-22

"""The full-capability deployment composed from settings, over real backends (ADR-097).

One ``build_runtime()`` from environment binds the shared PostgreSQL canonical
store, the Neo4j graph-intelligence reader and the Redis active store plus
awareness bus, every one marked required. The readiness report must then say
so on each family's own evidence, canonical writes must reach graph
intelligence through the composed service, and ``/readyz`` must carry the
same verdict. A required family that is absent or down must fail readiness
while canonical memory keeps working.

Three backends are named by ``L9_MEMORY_TEST_POSTGRES_DSN``,
``L9_MEMORY_TEST_REDIS_URL`` and ``L9_MEMORY_TEST_NEO4J_URI``; the test skips
naming the first one missing. The projection family needs a Graphiti MCP
endpoint; the composition case runs it against the in-process official-dialect
server of ``test_graphiti_http_projection_loop`` and says so in its name, so a
full-capability verdict here proves the wiring, not a live Graphiti.
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

from l9_graphite_memory.active import ActiveAgentSessionState, AgentStatus
from l9_graphite_memory.contracts import (
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryWriteRequest,
    OperationStatus,
    Provenance,
)
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphOperation,
    GraphReceiptStatus,
)
from l9_graphite_memory.runtime import READINESS_FAMILIES, MemoryRuntime, build_runtime
from tests.integration.neo4j_graph_fixture import (
    NEO4J_URI_ENV,
    GraphitiShapedGraph,
    live_neo4j_settings,
)
from tests.integration.test_active_memory_redis_live import (
    REDIS_URL_ENV,
    START_ENV,
    STOP_ENV,
    _control,
    _purge,
    _run,
    _wait_reachable,
)
from tests.integration.test_graphiti_http_projection_loop import (
    TOKEN,
    FakeGraphitiState,
    _handler,
)

POSTGRES_DSN_ENV = "L9_MEMORY_TEST_POSTGRES_DSN"
NOW = datetime.now(timezone.utc)


def _require(env: str, what: str) -> str:
    value = os.environ.get(env, "").strip()
    if not value:
        pytest.skip(f"{env} is not set; the full-capability deployment needs {what}")
    return value


@pytest.fixture
def full_capability_env(monkeypatch, tmp_path):
    """Environment for one full-capability process; yields the schema and prefix."""

    dsn = _require(POSTGRES_DSN_ENV, "PostgreSQL")
    _require(REDIS_URL_ENV, "Redis")
    neo4j = live_neo4j_settings()
    schema = f"l9_full_{uuid.uuid4().hex}"
    prefix = f"l9gm:full:{uuid.uuid4().hex}"

    import psycopg2
    import psycopg2.sql

    connection = psycopg2.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                psycopg2.sql.SQL("CREATE SCHEMA {}").format(psycopg2.sql.Identifier(schema))
            )
        connection.commit()
    finally:
        connection.close()

    for key, value in {
        "L9_MEMORY_DATA_DIR": str(tmp_path / "data"),
        "L9_MEMORY_STATE_DIR": str(tmp_path / "state"),
        "L9_MEMORY_STORE_BACKEND": "postgres",
        "L9_MEMORY_POSTGRES_DSN": f"{dsn} options=-csearch_path={schema}",
        "L9_MEMORY_GRAPH_BACKEND": "neo4j",
        "L9_MEMORY_GRAPH_REQUIRED": "true",
        "L9_MEMORY_GRAPH_NEO4J_URI": neo4j["uri"],
        "L9_MEMORY_GRAPH_NEO4J_DATABASE": neo4j["database"],
        "L9_MEMORY_GRAPH_NEO4J_USER": neo4j["user"],
        "L9_MEMORY_GRAPH_NEO4J_PASSWORD": neo4j["password"],
        "L9_MEMORY_GRAPH_QUERY_TIMEOUT_MS": "20000",
        "L9_MEMORY_ACTIVE_BACKEND": "redis",
        "L9_MEMORY_ACTIVE_REQUIRED": "true",
        "L9_MEMORY_ACTIVE_DEPLOYMENT_ID": "full-capability",
        "L9_MEMORY_ACTIVE_TRUST_DOMAIN": "live",
        "L9_MEMORY_ACTIVE_ENVIRONMENT": "test",
        "L9_MEMORY_ACTIVE_REDIS_URL_ENV": REDIS_URL_ENV,
        "L9_MEMORY_ACTIVE_KEY_PREFIX": prefix,
        "L9_MEMORY_ACTIVE_HEARTBEAT_INTERVAL_SECONDS": "1",
        "L9_MEMORY_ACTIVE_LEASE_TTL_SECONDS": "3",
        "L9_MEMORY_ACTIVE_HEARTBEAT_FAILURE_THRESHOLD": "2",
        "L9_MEMORY_HTTP_AUTH_REQUIRED": "false",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("L9_MEMORY_PROJECTION_BACKEND", "GRAPHITI_MCP_URL", "GRAPHITI_MCP_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    try:
        yield {"schema": schema, "prefix": prefix, "neo4j": neo4j}
    finally:
        asyncio.run(_purge(prefix))
        connection = psycopg2.connect(dsn)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    psycopg2.sql.SQL("DROP SCHEMA {} CASCADE").format(
                        psycopg2.sql.Identifier(schema)
                    )
                )
            connection.commit()
        finally:
            connection.close()


@pytest.fixture
def graphiti_dialect_server():
    state = FakeGraphitiState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _principal(namespace: str) -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="full-agent",
        tenant_id="tenant-full",
        read_namespaces=(namespace,),
        write_namespaces=(namespace,),
    )


async def _readiness(runtime: MemoryRuntime):
    return await runtime.readiness()


def _families(report) -> dict[str, tuple[bool, bool, bool]]:
    return {f.name: (f.selected, f.healthy, f.ready) for f in report.families}


def test_every_selected_family_is_proven_independently(full_capability_env) -> None:
    runtime = build_runtime()
    try:
        assert runtime.settings.store_backend == "postgres"
        assert runtime.active_memory.enabled and runtime.active_memory.required
        report = asyncio.run(_readiness(runtime))
        families = _families(report)
        assert tuple(families) == READINESS_FAMILIES
        for name in ("canonical", "graph", "active_store", "awareness_bus"):
            assert families[name] == (True, True, True), (name, report.family(name))
        # No Graphiti MCP endpoint is configured in this environment, and the
        # verdict says so: ready for what was selected, not full capability.
        assert families["projection"] == (False, False, True)
        assert report.ready is True and report.status is OperationStatus.COMPLETE
        assert report.full_capability is False
        assert report.family("canonical").detail["name"] == "postgres"
        assert report.family("graph").detail["backend"]["analytics_available"] is True
        assert report.family("active_store").detail["credential_source"] == "url_env"
        assert report.family("active_store").detail["capabilities"] == [
            "ping",
            "scalar",
            "sorted_set",
        ]
        assert report.family("awareness_bus").detail["capabilities"] == ["ping", "publish"]
    finally:
        runtime.close()


def test_canonical_writes_reach_graph_intelligence_through_the_composed_runtime(
    full_capability_env,
) -> None:
    runtime = build_runtime()
    graph = GraphitiShapedGraph(full_capability_env["neo4j"])
    namespace = graph.namespace("full")
    principal = _principal(namespace)
    try:
        record_id = runtime.service.write(
            principal,
            MemoryWriteRequest(
                namespace=namespace,
                content="falcon osprey over the shared store",
                provenance=Provenance(source="full-capability"),
                valid_from=NOW - timedelta(days=30),
            ),
        ).record_id
        group = graph.group("tenant-full", "full")
        falcon = graph.entity(group, "Falcon", episodes=(record_id,))
        osprey = graph.entity(group, "Osprey", episodes=(record_id,))
        graph.relate(falcon, osprey, group, episodes=(record_id,), valid_at=NOW - timedelta(days=5))

        hits = runtime.service.search(
            principal, MemorySearchRequest(namespaces=(namespace,), query="falcon")
        )
        assert {hit.record.record_id for hit in hits.hits} == {record_id}

        assert runtime.graph_service is not None
        receipt = runtime.graph_service.execute(
            principal,
            GraphIntelligenceRequest(
                operation=GraphOperation.NEIGHBORHOOD,
                namespaces=(namespace,),
                anchor=GraphAnchor(record_id=record_id),
            ),
        )
        assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
        names = {item["name"] for item in receipt.results if item["kind"] == "node"}
        assert {"Falcon", "Osprey"} <= names
    finally:
        runtime.close()


def test_readyz_reports_the_composed_deployment(full_capability_env) -> None:
    from fastapi.testclient import TestClient

    from l9_graphite_memory.server import create_http_app

    runtime = build_runtime()
    try:
        response = TestClient(create_http_app(runtime)).get("/readyz")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["store"]["name"] == "postgres"
        assert body["graph"]["ready"] is True
        assert body["active_memory"]["store"]["healthy"] is True
        assert body["active_memory"]["bus"]["healthy"] is True
        assert body["readiness"]["ready"] is True
        assert [f["name"] for f in body["readiness"]["families"]] == list(READINESS_FAMILIES)
    finally:
        runtime.close()


def test_the_projection_family_joins_the_verdict_when_graphiti_is_bound(
    full_capability_env, graphiti_dialect_server, monkeypatch
) -> None:
    """Composition proof: with an official-dialect Graphiti endpoint every family is live."""

    monkeypatch.setenv("L9_MEMORY_PROJECTION_BACKEND", "http")
    monkeypatch.setenv("GRAPHITI_MCP_URL", graphiti_dialect_server)
    monkeypatch.setenv("GRAPHITI_MCP_TOKEN", TOKEN)
    runtime = build_runtime()
    try:
        report = asyncio.run(_readiness(runtime))
        assert all(f.selected and f.healthy and f.ready for f in report.families), _families(report)
        assert report.full_capability is True
        assert report.status is OperationStatus.COMPLETE
    finally:
        runtime.close()


def test_a_required_active_memory_outage_fails_readiness_but_not_canonical_memory(
    full_capability_env,
) -> None:
    stop, start = _control(STOP_ENV), _control(START_ENV)
    url = os.environ[REDIS_URL_ENV]
    runtime = build_runtime()
    namespace = f"outage-{uuid.uuid4().hex[:8]}"
    principal = _principal(namespace)

    async def scenario() -> None:
        client = runtime.active_memory.client()
        async with client.open_session(agent_id="w", role="r", principal_id="p") as session:
            await asyncio.to_thread(_run, stop)
            try:
                await session._heartbeat_once()
                await session._heartbeat_once()
                assert session.state is ActiveAgentSessionState.DEGRADED
                down = await runtime.readiness()
                assert down.ready is False and down.status is OperationStatus.FAILED
                assert down.family("active_store").ready is False
                assert down.family("awareness_bus").ready is False
                assert down.family("canonical").ready and down.family("graph").ready
                assert "active_store is unhealthy" in down.degraded_reasons
                receipt = runtime.service.write(
                    principal,
                    MemoryWriteRequest(
                        namespace=namespace,
                        content="canonical write during the active-memory outage",
                        provenance=Provenance(source="full-capability"),
                    ),
                )
                hits = runtime.service.search(
                    principal, MemorySearchRequest(namespaces=(namespace,), query="outage")
                )
                assert {hit.record.record_id for hit in hits.hits} == {receipt.record_id}
                await asyncio.sleep(4)
            finally:
                await asyncio.to_thread(_run, start)
                await asyncio.to_thread(_wait_reachable, url)
            await session._heartbeat_once()
            assert session.state is ActiveAgentSessionState.ACTIVE
            await session.replace_context(objective="recovered", status=AgentStatus.ACTIVE)
        up = await runtime.readiness()
        assert up.ready is True
        assert up.family("active_store").healthy and up.family("awareness_bus").healthy
        await runtime.active_memory.close()

    try:
        asyncio.run(scenario())
    finally:
        runtime.close()
        _wait_reachable(url)


def test_a_required_family_that_is_not_configured_is_never_green(
    full_capability_env, monkeypatch
) -> None:
    monkeypatch.setenv("L9_MEMORY_ACTIVE_BACKEND", "none")
    runtime = build_runtime()
    try:
        report = asyncio.run(_readiness(runtime))
        assert report.ready is False and report.status is OperationStatus.FAILED
        assert report.family("active_store").selected is False
        assert "active_store is required but not configured" in report.degraded_reasons
        assert report.family("canonical").ready and report.family("graph").ready
    finally:
        runtime.close()


def test_neo4j_env_name_is_the_one_ci_binds() -> None:
    assert NEO4J_URI_ENV == "L9_MEMORY_TEST_NEO4J_URI"
