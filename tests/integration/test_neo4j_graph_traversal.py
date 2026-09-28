# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_neo4j_graph_traversal.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Live bounded traversal, neighborhood, and path over a Graphiti-shaped graph (ADR-087).

Runs against the Neo4j named by ``L9_MEMORY_TEST_NEO4J_URI``; skips otherwise.
The canonical store is real: supporting episode UUIDs are the record ids of
memories written through ``MemoryService``, so evidence binding is exercised
end to end.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)
from l9_graphite_memory.contracts import MemoryPrincipal, MemoryWriteRequest, Provenance
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphLimits,
    GraphOperation,
    GraphReceiptStatus,
)
from l9_graphite_memory.graph.service import GraphIntelligenceService
from l9_graphite_memory.services import MemoryService
from tests.integration.neo4j_graph_fixture import GraphitiShapedGraph, live_neo4j_settings

NOW = datetime.now(timezone.utc)


@pytest.fixture
def world():
    settings = live_neo4j_settings()
    graph = GraphitiShapedGraph(settings)
    adapter = Neo4jGraphIntelligence(Neo4jGraphIntelligenceConfig(**settings))
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
                provenance=Provenance(source="live"),
                valid_from=NOW - timedelta(days=60),
            ),
        ).record_id

    a_group, b_group = graph.group("tenant-a", "shared"), graph.group("tenant-b", "shared")
    a_ep, b_ep = record("tenant-a", "falcon osprey kestrel"), record("tenant-b", "bravo secret")
    falcon = graph.entity(a_group, "Falcon", episodes=(a_ep,))
    osprey = graph.entity(a_group, "Osprey", episodes=(a_ep,))
    kestrel = graph.entity(a_group, "Kestrel", episodes=(a_ep,))
    orphan = graph.entity(a_group, "Orphan")  # no canonical support
    bravo = graph.entity(b_group, "Bravo", episodes=(b_ep,))
    graph.relate(falcon, osprey, a_group, episodes=(a_ep,), valid_at=NOW - timedelta(days=10))
    graph.relate(osprey, kestrel, a_group, episodes=(a_ep,), valid_at=NOW - timedelta(days=10))
    graph.relate(falcon, orphan, a_group)
    # Hostile fixture: a cross-tenant edge Graphiti would never write.
    graph.relate(kestrel, bravo, b_group, episodes=(b_ep,))
    graph.relate(kestrel, bravo, a_group, episodes=(a_ep,))
    # Historical edge: invalidated before now.
    graph.relate(
        falcon,
        kestrel,
        a_group,
        episodes=(a_ep,),
        valid_at=NOW - timedelta(days=20),
        invalid_at=NOW - timedelta(days=5),
    )
    service = GraphIntelligenceService(store, adapter, namespace_policy=memory.namespace_policy)
    yield {
        "service": service,
        "principal": principal,
        "ns": ns,
        "ids": {
            "falcon": falcon,
            "osprey": osprey,
            "kestrel": kestrel,
            "orphan": orphan,
            "bravo": bravo,
        },
        "records": {"a": a_ep, "b": b_ep},
        "graph": graph,
    }
    adapter.close()
    graph.cleanup()


def _names(receipt) -> set[str]:
    return {item["name"] for item in receipt.results if item["kind"] == "node"}


def _run(world, operation, anchor, **kwargs):
    return world["service"].execute(
        world["principal"]("tenant-a"),
        GraphIntelligenceRequest(
            operation=operation, namespaces=(world["ns"],), anchor=anchor, **kwargs
        ),
    )


def test_neighborhood_depth_zero_one_and_two(world) -> None:
    anchor = GraphAnchor(entity_uuid=world["ids"]["falcon"])
    as_of = NOW
    depth0 = _run(
        world, GraphOperation.NEIGHBORHOOD, anchor, limits=GraphLimits(max_depth=0), as_of=as_of
    )
    depth1 = _run(
        world, GraphOperation.NEIGHBORHOOD, anchor, limits=GraphLimits(max_depth=1), as_of=as_of
    )
    depth2 = _run(
        world, GraphOperation.NEIGHBORHOOD, anchor, limits=GraphLimits(max_depth=2), as_of=as_of
    )
    assert _names(depth0) == {"Falcon"}
    assert _names(depth1) == {"Falcon", "Osprey"}
    assert _names(depth2) == {"Falcon", "Osprey", "Kestrel"}
    for receipt in (depth0, depth1, depth2):
        assert receipt.status is GraphReceiptStatus.COMPLETE
        assert receipt.supporting_record_ids == (world["records"]["a"],)
    # The orphan entity is reachable but has no canonical support.
    unsupported = {o.get("entity_uuid") for o in depth1.unsupported_projection_observations}
    assert str(world["ids"]["orphan"]) in unsupported


def test_cross_tenant_nodes_and_edges_never_appear(world) -> None:
    receipt = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        GraphAnchor(entity_uuid=world["ids"]["falcon"]),
        limits=GraphLimits(max_depth=6),
    )
    dumped = receipt.model_dump_json()
    assert str(world["ids"]["bravo"]) not in dumped
    assert str(world["records"]["b"]) not in dumped
    assert "Bravo" not in dumped


def test_other_tenants_entity_cannot_be_used_as_an_anchor(world) -> None:
    receipt = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        GraphAnchor(entity_uuid=world["ids"]["bravo"]),
        limits=GraphLimits(max_depth=2),
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE
    assert receipt.results == () and receipt.supporting_record_ids == ()


def test_as_of_excludes_invalidated_and_not_yet_valid_edges(world) -> None:
    anchor = GraphAnchor(entity_uuid=world["ids"]["falcon"])
    now = _run(
        world, GraphOperation.NEIGHBORHOOD, anchor, limits=GraphLimits(max_depth=1), as_of=NOW
    )
    past = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        anchor,
        limits=GraphLimits(max_depth=1),
        as_of=NOW - timedelta(days=15),
    )
    assert "Kestrel" not in _names(now)
    assert "Kestrel" in _names(past)
    assert "Osprey" not in _names(past)


def test_directed_traversal_respects_direction(world) -> None:
    anchor = GraphAnchor(entity_uuid=world["ids"]["osprey"])
    out = _run(
        world,
        GraphOperation.TRAVERSE,
        anchor,
        direction="out",
        limits=GraphLimits(max_depth=1),
        as_of=NOW,
    )
    inbound = _run(
        world,
        GraphOperation.TRAVERSE,
        anchor,
        direction="in",
        limits=GraphLimits(max_depth=1),
        as_of=NOW,
    )
    assert _names(out) == {"Osprey", "Kestrel"}
    assert _names(inbound) == {"Osprey", "Falcon"}


def test_relationship_allowlist_filters_edges(world) -> None:
    receipt = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        GraphAnchor(entity_uuid=world["ids"]["falcon"]),
        relationship_types=("MENTIONS",),
        limits=GraphLimits(max_depth=2),
    )
    assert _names(receipt) == {"Falcon"}


def test_record_and_text_anchors_resolve_inside_scope(world) -> None:
    world["graph"].ensure_fulltext_index()
    by_record = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        GraphAnchor(record_id=world["records"]["a"]),
        limits=GraphLimits(max_depth=0),
    )
    by_text = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        GraphAnchor(query="Falcon) OR (Bravo"),
        limits=GraphLimits(max_depth=0),
    )
    assert _names(by_record) == {"Falcon", "Osprey", "Kestrel"}
    assert "Bravo" not in _names(by_text)


def test_shortest_path_and_no_path(world) -> None:
    found = _run(
        world,
        GraphOperation.PATH,
        GraphAnchor(entity_uuid=world["ids"]["falcon"]),
        target=GraphAnchor(entity_uuid=world["ids"]["kestrel"]),
        limits=GraphLimits(max_depth=3),
        as_of=NOW,
    )
    paths = [item for item in found.results if item["kind"] == "path"]
    assert found.status is GraphReceiptStatus.COMPLETE
    assert paths and paths[0]["length"] == 2
    assert paths[0]["node_uuids"][0] == str(world["ids"]["falcon"])
    assert all(item["supporting_record_ids"] for item in paths)

    none = _run(
        world,
        GraphOperation.PATH,
        GraphAnchor(entity_uuid=world["ids"]["falcon"]),
        target=GraphAnchor(entity_uuid=world["ids"]["bravo"]),
        limits=GraphLimits(max_depth=6),
    )
    assert none.status is GraphReceiptStatus.COMPLETE
    assert [item for item in none.results if item["kind"] == "path"] == []


def test_node_cap_truncates_and_marks_partial(world) -> None:
    receipt = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        GraphAnchor(entity_uuid=world["ids"]["falcon"]),
        limits=GraphLimits(max_depth=2, max_nodes=1),
        as_of=NOW,
    )
    assert receipt.status is GraphReceiptStatus.PARTIAL
    assert len([i for i in receipt.results if i["kind"] == "node"]) == 1
    assert {"class": "truncated", "stage": "limits"} in receipt.failures


def test_unknown_anchor_id_is_empty_complete_not_failure(world) -> None:
    receipt = _run(
        world,
        GraphOperation.NEIGHBORHOOD,
        GraphAnchor(entity_uuid=uuid4()),
        limits=GraphLimits(max_depth=1),
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE and receipt.results == ()
