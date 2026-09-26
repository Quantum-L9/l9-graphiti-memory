# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_neo4j_graph_intelligence_adapter.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Neo4j graph-intelligence adapter health and capability discovery (ADR-085)."""

from __future__ import annotations

import pytest

from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
    schema_fingerprint,
)
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.ports import (
    ANALYTICS_CAPABILITIES,
    BASELINE_CAPABILITIES,
    GraphCapability,
)
from tests.graph_fakes import FakeNeo4jDriver, healthy_graphiti_responses

SECRET = "reader-secret-value"


def _adapter(driver: FakeNeo4jDriver, **overrides) -> Neo4jGraphIntelligence:
    config = Neo4jGraphIntelligenceConfig(
        uri="bolt://graph.invalid:7687",
        database="graphiti",
        user="l9_graph_reader",
        password=SECRET,
        **overrides,
    )
    adapter = Neo4jGraphIntelligence(config, driver_factory=lambda: driver)
    driver.bind(adapter)
    return adapter


def test_healthy_backend_reports_every_dimension_separately() -> None:
    driver = FakeNeo4jDriver(
        responses=healthy_graphiti_responses(group_ids=(graph_group_id("t", "ns"),))
    )
    health = _adapter(driver).health()

    assert health.healthy and health.reachable and health.schema_compatible
    assert health.backend_version == "5.26.31"
    assert health.backend_edition == "community"
    assert health.database == "graphiti"
    assert health.analytics_available and health.analytics_version == "2.13.13"
    assert health.scope_scheme == "l9g-v1" and health.scope_scheme_conformant is True
    expected = (
        *BASELINE_CAPABILITIES,
        *(c for c in ANALYTICS_CAPABILITIES if c is not GraphCapability.LINK_PREDICTION),
    )
    assert health.supported_capabilities == expected
    # Served = supported AND implemented: baseline structural operations
    # (ADR-087) and GDS analytics (ADR-088); link prediction stays off by default.
    assert health.capabilities == expected


def test_every_probe_runs_in_a_bounded_read_session_on_the_bound_database() -> None:
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses())
    _adapter(driver, query_timeout_ms=1_500).health()
    assert driver.calls
    for call in driver.calls:
        assert call.session_config == {"database": "graphiti", "default_access_mode": "READ"}
        assert call.timeout == pytest.approx(1.5)


def test_link_prediction_is_supported_only_when_enabled() -> None:
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses())
    health = _adapter(driver, link_prediction_enabled=True).health()
    assert GraphCapability.LINK_PREDICTION in health.supported_capabilities


def test_missing_gds_disables_only_analytics() -> None:
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses(gds=False))
    health = _adapter(driver).health()
    assert health.healthy
    assert not health.analytics_available
    assert health.supported_capabilities == BASELINE_CAPABILITIES
    assert "gds.fastRP.stream" in health.missing_procedures


def test_missing_graphiti_constructs_fail_closed() -> None:
    responses = healthy_graphiti_responses()
    responses["schema_labels_v1"] = [{"labels": ["Person"]}]
    health = _adapter(FakeNeo4jDriver(responses=responses)).health()
    assert not health.healthy and not health.schema_compatible
    assert health.missing_labels == ("Entity", "Episodic")
    assert health.supported_capabilities == ()


def test_unknown_additive_labels_do_not_change_the_fingerprint() -> None:
    base = schema_fingerprint(["Entity", "Episodic"], ["MENTIONS"], ["uuid", "noise"])
    assert base == schema_fingerprint(["Episodic", "Entity"], ["MENTIONS"], ["uuid"])
    assert base != schema_fingerprint(["Entity", "Episodic", "Saga"], ["MENTIONS"], ["uuid"])


def test_fingerprint_mismatch_with_qualified_binding_fails_closed() -> None:
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses())
    health = _adapter(driver, expected_schema_fingerprint="0" * 64).health()
    assert not health.healthy and not health.schema_compatible
    assert "fingerprint" in health.detail
    assert health.schema_fingerprint != "0" * 64


def test_namespace_keyed_groups_mean_wrong_binding() -> None:
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses(group_ids=("shared",)))
    health = _adapter(driver).health()
    assert health.scope_scheme_conformant is False
    assert not health.healthy
    assert health.supported_capabilities == ()


def test_unreachable_backend_is_reported_not_raised() -> None:
    driver = FakeNeo4jDriver(unreachable=ConnectionRefusedError("refused"))
    health = _adapter(driver).health()
    assert not health.healthy and not health.reachable
    assert health.error_class == "ConnectionRefusedError"
    assert health.capabilities == ()


def test_credentials_never_appear_in_health_or_config_repr() -> None:
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses())
    adapter = _adapter(driver)
    assert SECRET not in adapter.health().model_dump_json()
    assert SECRET not in repr(adapter.config)


def test_close_releases_the_driver_once() -> None:
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses())
    adapter = _adapter(driver)
    adapter.health()
    adapter.close()
    assert driver.closed
    adapter.close()
