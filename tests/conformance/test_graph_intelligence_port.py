# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/test_graph_intelligence_port.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""GraphIntelligencePort conformance for every shipped backend (ADR-085/086)."""

from __future__ import annotations

import pytest

from l9_graphite_memory.adapters import NullGraphIntelligence
from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)
from l9_graphite_memory.errors import GraphCapabilityUnavailable
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import GraphLimits, GraphProviderRequest
from l9_graphite_memory.graph.ports import PORT_METHODS, GraphBackendHealth
from tests.graph_fakes import FakeNeo4jDriver, healthy_graphiti_responses

REQUIRED = {"health", "capabilities", "close", *PORT_METHODS.values()}
FORBIDDEN = {
    "execute_raw_cypher",
    "write_node",
    "write_edge",
    "merge_entity",
    "delete_entity",
    "mutate_persistent_graph",
    "gds_write",
}


def _backends():
    driver = FakeNeo4jDriver(responses=healthy_graphiti_responses())
    neo4j = Neo4jGraphIntelligence(
        Neo4jGraphIntelligenceConfig(uri="bolt://graph.invalid:7687"), driver_factory=lambda: driver
    )
    driver.bind(neo4j)
    return [NullGraphIntelligence(), neo4j]


@pytest.mark.parametrize("backend", _backends(), ids=lambda b: b.name)
def test_backend_implements_the_port_and_nothing_forbidden(backend) -> None:
    members = {name for name in dir(backend) if not name.startswith("_")}
    assert REQUIRED <= members
    assert not members & FORBIDDEN
    assert isinstance(backend.health(), GraphBackendHealth)


@pytest.mark.parametrize("backend", _backends(), ids=lambda b: b.name)
def test_unserved_operations_refuse_instead_of_answering_empty(backend) -> None:
    served = {capability.value for capability in backend.capabilities()}
    for operation, method in PORT_METHODS.items():
        if operation.value in served:
            continue
        request = GraphProviderRequest(
            operation=operation,
            group_ids=(graph_group_id("t", "ns"),),
            limits=GraphLimits(),
            operation_id="conformance",
        )
        with pytest.raises(GraphCapabilityUnavailable):
            getattr(backend, method)(request)
