# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_evidence_linking.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Canonical evidence binding of provider graph observations (ADR-086, GI-025..027)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import (
    GraphOperation,
    GraphProviderEdge,
    GraphProviderNode,
    GraphProviderPath,
    GraphProviderResult,
    GraphProviderScore,
)
from l9_graphite_memory.graph.evidence import CanonicalEvidenceLinker, EvidenceScope
from tests.graph_fakes import seeded_memory

A_GROUP = graph_group_id("tenant-a", "shared")


def _scope(**overrides) -> EvidenceScope:
    values = {
        "tenant_id": "tenant-a",
        "namespaces": frozenset({"shared"}),
        "group_ids": frozenset({A_GROUP}),
    }
    values.update(overrides)
    return EvidenceScope(**values)


def _node(*support, group=A_GROUP):
    return GraphProviderNode(
        entity_uuid=uuid4(), group_id=group, name="entity", supporting_episode_ids=support
    )


def test_node_with_active_same_tenant_support_is_admitted() -> None:
    _service, store, _p, write = seeded_memory()
    record = write("tenant-a", "falcon depends on osprey")
    node = _node(record)
    linked = CanonicalEvidenceLinker(store).link(
        GraphProviderResult(operation=GraphOperation.NEIGHBORHOOD, nodes=(node,)), _scope()
    )
    assert linked.results[0]["supporting_record_ids"] == [str(record)]
    assert linked.results[0]["authority_class"] == "advisory_projection"
    assert linked.supporting_record_ids == [record]
    assert "content" not in linked.results[0]


def test_support_from_another_tenant_never_counts() -> None:
    _service, store, _p, write = seeded_memory()
    foreign = write("tenant-b", "bravo secret")
    linked = CanonicalEvidenceLinker(store).link(
        GraphProviderResult(operation=GraphOperation.NEIGHBORHOOD, nodes=(_node(foreign),)),
        _scope(),
    )
    assert linked.results == []
    assert linked.unsupported[0]["reason"] == "no_canonical_support"
    assert str(foreign) not in str(linked.unsupported)


def test_missing_or_other_namespace_or_inactive_support_is_unsupported() -> None:
    service, store, principal, write = seeded_memory()
    other_ns = write("tenant-a", "other namespace fact", namespace="other")
    archived = write("tenant-a", "to be archived")
    from l9_graphite_memory.contracts import MemoryState

    service.transition_lifecycle(
        principal("tenant-a"),
        "shared",
        record_ids=(archived,),
        new_state=MemoryState.ARCHIVED,
        reason="test archive",
    )
    nodes = (_node(uuid4()), _node(other_ns), _node(archived))
    linked = CanonicalEvidenceLinker(store).link(
        GraphProviderResult(operation=GraphOperation.TRAVERSE, nodes=nodes), _scope()
    )
    assert linked.results == []
    assert len(linked.unsupported) == 3


def test_items_in_unauthorized_groups_are_discarded() -> None:
    _service, store, _p, write = seeded_memory()
    record = write("tenant-a", "fact")
    linked = CanonicalEvidenceLinker(store).link(
        GraphProviderResult(
            operation=GraphOperation.TRAVERSE,
            nodes=(_node(record, group=graph_group_id("tenant-b", "shared")),),
        ),
        _scope(),
    )
    assert linked.results == [] and linked.unsupported == []
    assert linked.out_of_scope_dropped == 1


def test_as_of_excludes_edges_outside_their_validity() -> None:
    _service, store, _p, write = seeded_memory()
    record = write("tenant-a", "fact")
    as_of = datetime.now(timezone.utc)
    a, b = uuid4(), uuid4()
    later = GraphProviderEdge(
        source_uuid=a,
        target_uuid=b,
        relationship_type="RELATES_TO",
        group_id=A_GROUP,
        valid_at=as_of + timedelta(days=1),
        supporting_episode_ids=(record,),
    )
    invalidated = later.model_copy(
        update={"valid_at": as_of - timedelta(days=2), "invalid_at": as_of - timedelta(days=1)}
    )
    current = later.model_copy(update={"valid_at": as_of - timedelta(days=2)})
    linked = CanonicalEvidenceLinker(store).link(
        GraphProviderResult(operation=GraphOperation.TRAVERSE, edges=(later, invalidated, current)),
        _scope(as_of=as_of + timedelta(seconds=1)),
    )
    assert [item["kind"] for item in linked.results] == ["edge"]
    assert linked.temporal_excluded == 2


def test_path_through_an_unsupported_hop_is_not_authoritative() -> None:
    _service, store, _p, write = seeded_memory()
    record = write("tenant-a", "fact")
    supported, unsupported = _node(record), _node(uuid4())
    path = GraphProviderPath(node_uuids=(supported.entity_uuid, unsupported.entity_uuid), length=1)
    linked = CanonicalEvidenceLinker(store).link(
        GraphProviderResult(
            operation=GraphOperation.PATH, nodes=(supported, unsupported), paths=(path,)
        ),
        _scope(),
    )
    assert [item["kind"] for item in linked.results] == ["node"]
    assert {item["kind"] for item in linked.unsupported} == {"node", "path"}


def test_embeddings_are_digested_not_returned_by_default() -> None:
    _service, store, _p, write = seeded_memory()
    record = write("tenant-a", "fact")
    node = _node(record)
    score = GraphProviderScore(entity_uuid=node.entity_uuid, group_id=A_GROUP, embedding=(0.1, 0.2))
    result = GraphProviderResult(
        operation=GraphOperation.STRUCTURAL_EMBEDDING, nodes=(node,), scores=(score,)
    )
    item = CanonicalEvidenceLinker(store).link(result, _scope()).results[1]
    assert item["embedding_dimension"] == 2 and len(item["embedding_digest"]) == 64
    assert "embedding" not in item
    raw = CanonicalEvidenceLinker(store).link(result, _scope(include_raw_vectors=True)).results[1]
    assert raw["embedding"] == [0.1, 0.2]


def test_store_failure_is_a_rehydration_error_not_an_answer() -> None:
    class BrokenStore:
        def get_record(self, record_id):
            raise ConnectionError("store down")

    linked = CanonicalEvidenceLinker(BrokenStore()).link(  # type: ignore[arg-type]
        GraphProviderResult(operation=GraphOperation.TRAVERSE, nodes=(_node(uuid4()),)), _scope()
    )
    assert linked.rehydration_error == "ConnectionError"
    assert linked.results == [] and linked.supporting_record_ids == []
