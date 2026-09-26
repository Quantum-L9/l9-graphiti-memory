# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_neo4j_gds_analytics.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Live GDS 2.13 analytics over a Graphiti-shaped graph (ADR-088).

Needs ``L9_MEMORY_TEST_NEO4J_URI`` naming a Neo4j 5.26 with GDS 2.13; skips
otherwise. Verifies stream-only execution, catalog cleanup, and that scores
never involve another tenant's graph.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)
from l9_graphite_memory.contracts import MemoryPrincipal, MemoryWriteRequest, Provenance
from l9_graphite_memory.graph.algorithm_policy import AlgorithmMaturity, AlgorithmPolicy
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphLimits,
    GraphOperation,
    GraphReceiptStatus,
)
from l9_graphite_memory.graph.service import GraphIntelligenceService, GraphServiceConfig
from l9_graphite_memory.services import MemoryService
from tests.integration.neo4j_graph_fixture import GraphitiShapedGraph, live_neo4j_settings

NOW = datetime.now(timezone.utc)


@pytest.fixture
def world():
    settings = live_neo4j_settings()
    graph = GraphitiShapedGraph(settings)
    adapter = Neo4jGraphIntelligence(
        Neo4jGraphIntelligenceConfig(**settings, link_prediction_enabled=True)
    )
    if not adapter.health().analytics_available:
        adapter.close()
        graph.cleanup()
        pytest.skip("GDS 2.13 is not installed on the live Neo4j")
    store = InMemoryRecordStore()
    memory = MemoryService(store, NullProjection())
    memory.initialize()
    ns = graph.namespace("shared")

    def principal(tenant: str) -> MemoryPrincipal:
        return MemoryPrincipal(
            principal_id=f"{tenant}-agent",
            tenant_id=tenant,
            read_namespaces=(ns,),
            write_namespaces=(ns,),
        )

    def record(tenant: str, content: str):
        return memory.write(
            principal(tenant),
            MemoryWriteRequest(
                namespace=ns,
                content=content,
                provenance=Provenance(source="live-gds"),
                valid_from=NOW - timedelta(days=60),
            ),
        ).record_id

    a_group, b_group = graph.group("tenant-a", "shared"), graph.group("tenant-b", "shared")
    ep_a, ep_b = record("tenant-a", "birds of prey"), record("tenant-b", "bravo secret")
    names = ["Hub", "A1", "A2", "A3", "B1", "B2", "B3"]
    ids = {name: graph.entity(a_group, name, episodes=(ep_a,)) for name in names}
    for left, right in [
        ("A1", "A2"),
        ("A2", "A3"),
        ("A1", "A3"),
        ("B1", "B2"),
        ("B2", "B3"),
        ("B1", "B3"),
    ]:
        graph.relate(ids[left], ids[right], a_group, episodes=(ep_a,))
    for spoke in ["A1", "B1", "A2", "B2"]:
        graph.relate(ids["Hub"], ids[spoke], a_group, episodes=(ep_a,))
    # Tenant B's dense subgraph in the same namespace must not affect tenant A.
    b_ids = [graph.entity(b_group, f"X{i}", episodes=(ep_b,)) for i in range(6)]
    for i in range(6):
        for j in range(i + 1, 6):
            graph.relate(b_ids[i], b_ids[j], b_group, episodes=(ep_b,))
    service = GraphIntelligenceService(
        store,
        adapter,
        namespace_policy=memory.namespace_policy,
        config=GraphServiceConfig(
            algorithm_policy=AlgorithmPolicy(
                maturity_ceiling=AlgorithmMaturity.ALPHA, link_prediction_enabled=True
            )
        ),
    )
    yield {
        "service": service,
        "adapter": adapter,
        "principal": principal,
        "ns": ns,
        "ids": ids,
        "b_ids": b_ids,
        "records": (ep_a, ep_b),
    }
    adapter.close()
    graph.cleanup()


def _run(world, operation, **kwargs):
    return world["service"].execute(
        world["principal"]("tenant-a"),
        GraphIntelligenceRequest(operation=operation, namespaces=(world["ns"],), **kwargs),
    )


def _scores(receipt):
    return [item for item in receipt.results if item["kind"] == "score"]


def _catalog(world) -> list[str]:
    rows = world["adapter"]._read("gds_catalog_list_v1", {"prefix": "l9gi_"})
    return list(rows[0]["names"]) if rows else []


def _assert_isolated(world, receipt) -> None:
    dumped = receipt.model_dump_json()
    for foreign in world["b_ids"]:
        assert str(foreign) not in dumped
    assert str(world["records"][1]) not in dumped


@pytest.mark.parametrize("algorithm", ["pagerank", "degree", "betweenness"])
def test_centrality_ranks_the_hub_and_records_algorithm_identity(world, algorithm) -> None:
    receipt = _run(world, GraphOperation.CENTRALITY, algorithm=algorithm)
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    scores = _scores(receipt)
    assert len(scores) == 7
    if algorithm in {"degree", "betweenness"}:
        assert scores[0]["entity_uuid"] == str(world["ids"]["Hub"])
    assert receipt.algorithm is not None and receipt.algorithm.id == algorithm
    assert receipt.provider.gds_version and receipt.provider.gds_version.startswith("2.13")
    _assert_isolated(world, receipt)
    assert _catalog(world) == []


@pytest.mark.parametrize("algorithm", ["louvain", "leiden"])
def test_communities_separate_the_two_triangles(world, algorithm) -> None:
    receipt = _run(world, GraphOperation.COMMUNITY, algorithm=algorithm)
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    community = {item["entity_uuid"]: item["community_id"] for item in _scores(receipt)}
    ids = world["ids"]
    assert community[str(ids["A1"])] == community[str(ids["A2"])] == community[str(ids["A3"])]
    assert community[str(ids["B1"])] == community[str(ids["B2"])] == community[str(ids["B3"])]
    assert community[str(ids["A1"])] != community[str(ids["B1"])]
    _assert_isolated(world, receipt)
    assert _catalog(world) == []


def test_fastrp_embeddings_are_digested_and_deterministic(world) -> None:
    first = _run(world, GraphOperation.STRUCTURAL_EMBEDDING)
    second = _run(world, GraphOperation.STRUCTURAL_EMBEDDING)
    assert first.status is GraphReceiptStatus.COMPLETE, first.failures
    items = _scores(first)
    assert items and all(item["embedding_dimension"] == 64 for item in items)
    assert all("embedding" not in item for item in items)
    assert first.result_digest == second.result_digest
    assert first.algorithm is not None and first.algorithm.id == "fastrp"
    _assert_isolated(world, first)


def test_structural_similarity_ranks_triangle_peers(world) -> None:
    receipt = _run(
        world,
        GraphOperation.STRUCTURAL_SIMILARITY,
        anchor=GraphAnchor(entity_uuid=world["ids"]["A3"]),
        limits=GraphLimits(max_nodes=3),
    )
    assert receipt.status is GraphReceiptStatus.PARTIAL  # 6 candidates, capped at 3
    ranked = [item["entity_uuid"] for item in _scores(receipt)]
    assert str(world["ids"]["A3"]) not in ranked
    assert all(item["target_uuid"] == str(world["ids"]["A3"]) for item in _scores(receipt))
    _assert_isolated(world, receipt)


def test_link_prediction_is_advisory_and_never_materialized(world) -> None:
    adapter = world["adapter"]
    before = adapter._read("schema_relationship_types_v1")
    receipt = _run(
        world,
        GraphOperation.LINK_PREDICTION,
        anchor=GraphAnchor(entity_uuid=world["ids"]["A3"]),
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    assert receipt.algorithm is not None and receipt.algorithm.maturity == "alpha"
    targets = [item["target_uuid"] for item in _scores(receipt)]
    assert str(world["ids"]["Hub"]) in targets  # hub shares A1, A2 with A3
    assert str(world["ids"]["A1"]) not in targets  # already linked
    assert adapter._read("schema_relationship_types_v1") == before
    _assert_isolated(world, receipt)


def test_analytics_ceiling_refuses_before_projecting(world) -> None:
    settings = live_neo4j_settings()
    small = Neo4jGraphIntelligence(Neo4jGraphIntelligenceConfig(**settings, gds_max_nodes=3))
    service = GraphIntelligenceService(
        world["service"].store, small, namespace_policy=world["service"].namespace_policy
    )
    receipt = service.execute(
        world["principal"]("tenant-a"),
        GraphIntelligenceRequest(operation=GraphOperation.CENTRALITY, namespaces=(world["ns"],)),
    )
    small.close()
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == "query_policy_violation"
    assert _catalog(world) == []


def test_catalog_graph_is_dropped_when_the_stream_fails(world) -> None:
    adapter = world["adapter"]
    request_rows = []

    def failing_stream(graph_name: str):
        request_rows.append(graph_name)
        assert graph_name in _catalog(world)
        raise RuntimeError("stream failed mid-operation")

    from l9_graphite_memory.graph import graph_group_id
    from l9_graphite_memory.graph.contracts import GraphProviderRequest

    request = GraphProviderRequest(
        operation=GraphOperation.CENTRALITY,
        group_ids=(graph_group_id("tenant-a", world["ns"]),),
        relationship_types=("RELATES_TO",),
        limits=GraphLimits(),
        algorithm_id="pagerank",
        operation_id="failurepath",
    )
    with pytest.raises(RuntimeError, match="stream failed"):
        adapter._projected(request, failing_stream)
    assert request_rows and _catalog(world) == []


def test_stale_catalog_entries_are_swept(world) -> None:
    adapter = world["adapter"]
    from l9_graphite_memory.graph import graph_group_id
    from l9_graphite_memory.graph.contracts import GraphProviderRequest

    stale_request = GraphProviderRequest(
        operation=GraphOperation.CENTRALITY,
        group_ids=(graph_group_id("tenant-a", world["ns"]),),
        relationship_types=("RELATES_TO",),
        limits=GraphLimits(),
        operation_id="stale",
    )
    # Simulate a crash between projection and drop.
    adapter._read(
        "gds_project_undirected_v1",
        {
            **adapter._base_parameters(stale_request),
            "graph_name": "l9gi_stale_probe",
            "max_relationships": 100,
        },
    )
    assert "l9gi_stale_probe" in _catalog(world)
    assert adapter.cleanup_stale_catalog() >= 1
    assert _catalog(world) == []
