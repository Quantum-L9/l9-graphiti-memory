# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_neo4j_graph_intelligence_live.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Live Neo4j 5.26 + GDS 2.13 binding checks for the graph-intelligence adapter.

Runs when ``L9_MEMORY_TEST_NEO4J_URI`` (plus ``_USER``/``_PASSWORD``) names a
disposable Neo4j database; skips loudly otherwise, as the postgres matrix does.
"""

from __future__ import annotations

import os

import pytest

from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)

NEO4J_URI_ENV = "L9_MEMORY_TEST_NEO4J_URI"


@pytest.fixture
def live_adapter():
    uri = os.environ.get(NEO4J_URI_ENV, "").strip()
    if not uri:
        pytest.skip(f"{NEO4J_URI_ENV} is not set; live graph-intelligence checks need Neo4j")
    adapter = Neo4jGraphIntelligence(
        Neo4jGraphIntelligenceConfig(
            uri=uri,
            database=os.environ.get("L9_MEMORY_TEST_NEO4J_DATABASE", "neo4j"),
            user=os.environ.get("L9_MEMORY_TEST_NEO4J_USER", "neo4j"),
            password=os.environ.get("L9_MEMORY_TEST_NEO4J_PASSWORD", ""),
        )
    )
    yield adapter
    adapter.close()


def test_live_health_reports_backend_and_analytics_versions(live_adapter) -> None:
    health = live_adapter.health()
    assert health.reachable, health.error_class
    assert health.backend_version and health.backend_version.startswith("5.26")
    if health.analytics_available:
        assert health.analytics_version and health.analytics_version.startswith("2.13")
        assert health.missing_procedures == ()


def test_live_read_session_cannot_write(live_adapter) -> None:
    """The server, not only the lexical guard, refuses writes on this path."""

    from neo4j.exceptions import ClientError

    driver = live_adapter._driver_instance()
    with (
        driver.session(database=live_adapter.config.database, default_access_mode="READ") as s,
        pytest.raises(ClientError, match="AccessMode|read"),
    ):
        s.execute_read(lambda tx: tx.run("CREATE (:L9WriteProbe)").consume())
