# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_neo4j_restart_outage_live.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Live outage degradation and restart recovery (GI-080, ADR-092).

Stops the Neo4j server under a running graph-intelligence service, then
starts it again, and proves:

- during the outage, health says unreachable and operations answer FAILED
  with a typed failure, never an empty COMPLETE (GI-029);
- canonical memory keeps accepting writes and serving reads (GI-031);
- after the restart, the same service instance recovers without a process
  restart, and a fresh adapter binds the same graph with the same schema
  fingerprint.

The server is controlled by two commands the environment supplies, because
only the harness knows how its Neo4j runs (CI: ``docker stop/start`` of the
service container; locally: the container name). Without them the test skips
loudly, like every live suite; CI sets both and fails if this test skips.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time

import pytest

from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)
from l9_graphite_memory.contracts import MemorySearchRequest, MemoryWriteRequest, Provenance
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphOperation,
    GraphReceiptStatus,
)
from tests.integration.neo4j_graph_fixture import live_neo4j_settings, warm_analytics
from tests.integration.test_neo4j_graph_traversal import world  # noqa: F401 - fixture

STOP_ENV = "L9_MEMORY_TEST_NEO4J_STOP_CMD"
START_ENV = "L9_MEMORY_TEST_NEO4J_START_CMD"
RECOVERY_TIMEOUT_S = 240.0


def _control(env: str) -> list[str]:
    command = os.environ.get(env, "").strip()
    if not command:
        pytest.skip(f"{env} is not set; outage/restart qualification needs server control")
    return shlex.split(command)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=120)


def _wait_reachable(adapter: Neo4jGraphIntelligence) -> None:
    deadline = time.monotonic() + RECOVERY_TIMEOUT_S
    while time.monotonic() < deadline:
        health = adapter.health()
        if health.reachable and health.healthy:
            return
        time.sleep(2)
    pytest.fail(f"Neo4j did not recover within {RECOVERY_TIMEOUT_S:.0f}s")


def _neighborhood(world, **kwargs):  # noqa: F811 - the fixture is passed in
    return world["service"].execute(
        world["principal"]("tenant-a"),
        GraphIntelligenceRequest(
            operation=GraphOperation.NEIGHBORHOOD,
            namespaces=(world["ns"],),
            anchor=GraphAnchor(entity_uuid=world["ids"]["falcon"]),
            **kwargs,
        ),
    )


def _names(receipt) -> set[str]:
    return {item["name"] for item in receipt.results if item["kind"] == "node"}


def test_outage_degrades_explicitly_and_restart_recovers(world) -> None:  # noqa: F811
    stop, start = _control(STOP_ENV), _control(START_ENV)
    service = world["service"]
    adapter: Neo4jGraphIntelligence = service.port
    memory = world["memory"]
    principal = world["principal"]("tenant-a")

    before = _neighborhood(world)
    assert before.status is GraphReceiptStatus.COMPLETE
    assert {"Falcon", "Osprey"} <= _names(before)
    fingerprint = adapter.health().schema_fingerprint

    _run(stop)
    try:
        # Outage: health is a typed unreachable state, not an exception.
        down = service.health(refresh=True)
        assert down.reachable is False
        assert down.error_class
        assert down.capabilities == ()
        report = service.capability_report(refresh=True)
        assert report.capabilities == () or "graph.neighborhood" not in report.capabilities

        # Graph intelligence fails explicitly, never as an empty COMPLETE.
        failed = _neighborhood(world)
        assert failed.status is GraphReceiptStatus.FAILED
        assert failed.results == ()
        assert failed.failures

        # Canonical memory is untouched by the graph outage (GI-031).
        written = memory.write(
            principal,
            MemoryWriteRequest(
                namespace=world["ns"],
                content="osprey outage note",
                provenance=Provenance(source="outage-test"),
            ),
        )
        found = memory.search(
            principal, MemorySearchRequest(namespaces=(world["ns"],), query="osprey")
        )
        assert written.record_id in {hit.record.record_id for hit in found.hits}
    finally:
        _run(start)

    # Recovery: the same service instance works again without a restart.
    _wait_reachable(adapter)
    service.health(refresh=True)
    after = _neighborhood(world)
    assert after.status is GraphReceiptStatus.COMPLETE
    assert _names(after) == _names(before)

    # Analytics recover too. The first GDS call on a restarted server pays a
    # cold-start cost, so it runs under the ceiling budget (runbook: warm up
    # analytics after a restart before enabling callers).
    if adapter.health().analytics_available:
        assert warm_analytics(live_neo4j_settings())

    # A fresh adapter (a process restart) binds the same durable graph.
    fresh = Neo4jGraphIntelligence(Neo4jGraphIntelligenceConfig(**live_neo4j_settings()))
    try:
        health = fresh.health()
        assert health.healthy
        assert health.schema_fingerprint == fingerprint
        assert health.gds_catalog_active in (0, None)
    finally:
        fresh.close()
