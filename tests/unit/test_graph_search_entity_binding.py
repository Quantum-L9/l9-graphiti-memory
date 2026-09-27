# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_search_entity_binding.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""graph.search binds entity hits to canonical support (ADR-092).

Graphiti entity search returns entities that name no episode. They are bound
through the graph backend's entity -> episode support, and never dropped
silently: without a backend that can bind them they are reported as
unsupported observations. ``profile_ref`` is refused until profiles exist.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from l9_graphite_memory.adapters import GraphitiProjection
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphOperation,
    GraphProviderNode,
    GraphProviderResult,
    GraphReceiptStatus,
)
from l9_graphite_memory.graph.service import GraphIntelligenceService
from l9_graphite_memory.ports import ProjectionEntityHit, ProjectionHit
from tests.graph_fakes import FakeGraphPort, seeded_memory

ENTITY = uuid4()


class EntityProjection:
    name = "graphiti"
    capabilities = ("graph-search", "semantic-search")

    def __init__(self, hits) -> None:
        self.hits = hits
        self.calls: list[tuple] = []

    def search_entities(self, query, namespaces, *, limit, tenant_id):
        self.calls.append((query, namespaces, tenant_id))
        return list(self.hits)

    def search_strategy(self, strategy, query, namespaces, *, limit, tenant_id):
        raise AssertionError("graph.search must use entity search")


def _search(**overrides) -> GraphIntelligenceRequest:
    values = {
        "operation": GraphOperation.SEARCH,
        "namespaces": ("shared",),
        "anchor": GraphAnchor(query="falcon"),
    }
    values.update(overrides)
    return GraphIntelligenceRequest(**values)


def _node(tenant: str, *support) -> GraphProviderNode:
    return GraphProviderNode(
        entity_uuid=ENTITY,
        group_id=graph_group_id(tenant, "shared"),
        labels=("Entity",),
        name="Falcon",
        supporting_episode_ids=tuple(support),
    )


def _world(hits, describe=None, capabilities=None):
    service, store, principal, write = seeded_memory()
    own = write("tenant-a", "falcon depends on osprey")
    foreign = write("tenant-b", "bravo secret")
    port = FakeGraphPort(
        {} if describe is None else {"describe_entities": describe}, capabilities=capabilities
    )
    projection = EntityProjection(hits)
    graph = GraphIntelligenceService(
        store, port, namespace_policy=service.namespace_policy, projection=projection
    )
    return graph, port, projection, principal, own, foreign


def _entity_hit(score: float = 0.8) -> ProjectionEntityHit:
    return ProjectionEntityHit(entity_uuid=ENTITY, score=score, name="Falcon", namespace="shared")


def test_entity_hit_is_bound_to_canonical_support_through_the_backend() -> None:
    record = {}

    def describe(request, entity_uuids):
        return GraphProviderResult(
            operation=request.operation, nodes=(_node("tenant-a", record["own"]),)
        )

    graph, port, projection, principal, own, _ = _world([_entity_hit()], describe)
    record["own"] = own
    receipt = graph.execute(principal("tenant-a"), _search())
    assert receipt.status is GraphReceiptStatus.COMPLETE
    (item,) = receipt.results
    assert item["kind"] == "entity_hit"
    assert item["entity_uuid"] == str(ENTITY)
    assert item["score"] == 0.8
    assert item["supporting_record_ids"] == [str(own)]
    assert receipt.supporting_record_ids == (own,)
    assert port.described == (ENTITY,)
    # Scope is the principal's own derived group; no request field widens it.
    assert port.requests[-1].group_ids == (graph_group_id("tenant-a", "shared"),)
    assert projection.calls[0][2] == "tenant-a"


def test_entity_supported_only_by_another_tenant_is_not_served() -> None:
    record = {}

    def describe(request, entity_uuids):
        return GraphProviderResult(
            operation=request.operation, nodes=(_node("tenant-a", record["foreign"]),)
        )

    graph, _port, _projection, principal, _own, foreign = _world([_entity_hit()], describe)
    record["foreign"] = foreign
    receipt = graph.execute(principal("tenant-a"), _search())
    assert receipt.status is GraphReceiptStatus.COMPLETE
    assert receipt.results == ()
    assert str(foreign) not in receipt.model_dump_json()
    assert [u["reason"] for u in receipt.unsupported_projection_observations] == [
        "no_canonical_support"
    ]


def test_entity_hit_without_a_binding_backend_is_reported_not_dropped() -> None:
    graph, port, _projection, principal, *_ = _world([_entity_hit()], capabilities=())
    receipt = graph.execute(principal("tenant-a"), _search())
    assert receipt.status is GraphReceiptStatus.COMPLETE
    assert receipt.results == ()
    assert receipt.unsupported_projection_observations == (
        {"kind": "entity_hit", "entity_uuid": str(ENTITY), "reason": "graph_backend_unavailable"},
    )
    assert not hasattr(port, "described")


def test_entity_missing_from_the_backend_is_reported() -> None:
    def describe(request, entity_uuids):
        return GraphProviderResult(operation=request.operation)

    graph, *_rest = _world([_entity_hit()], describe)
    principal = _rest[2]
    receipt = graph.execute(principal("tenant-a"), _search())
    assert [u["reason"] for u in receipt.unsupported_projection_observations] == [
        "entity_not_found"
    ]


@pytest.mark.parametrize(("required", "status"), [(False, "PARTIAL"), (True, "FAILED")])
def test_binding_failure_is_partial_or_failed_never_empty_complete(required, status) -> None:
    graph, *_rest = _world([_entity_hit()], RuntimeError("backend down"))
    principal = _rest[2]
    receipt = graph.execute(principal("tenant-a"), _search(required=required))
    assert receipt.status.value == status
    assert {"class": "provider_error:RuntimeError", "stage": "evidence"} in receipt.failures
    assert "backend down" not in receipt.model_dump_json()


def test_record_hits_and_entity_hits_merge_by_score() -> None:
    record = {}

    def describe(request, entity_uuids):
        return GraphProviderResult(
            operation=request.operation, nodes=(_node("tenant-a", record["other"]),)
        )

    service, store, principal, write = seeded_memory()
    own = write("tenant-a", "falcon depends on osprey")
    record["other"] = write("tenant-a", "osprey owns billing")
    projection = EntityProjection(
        [ProjectionEntityHit(record_id=own, score=0.5, namespace="shared"), _entity_hit(0.9)]
    )
    graph = GraphIntelligenceService(
        store,
        FakeGraphPort({"describe_entities": describe}),
        namespace_policy=service.namespace_policy,
        projection=projection,
    )
    receipt = graph.execute(principal("tenant-a"), _search())
    assert [item["kind"] for item in receipt.results] == ["entity_hit", "record_hit"]
    assert set(receipt.supporting_record_ids) == {own, record["other"]}


@pytest.mark.parametrize(
    "request_",
    [
        _search(profile_ref="centrality-default"),
        GraphIntelligenceRequest(
            operation=GraphOperation.NEIGHBORHOOD,
            namespaces=("shared",),
            anchor=GraphAnchor(query="falcon"),
            profile_ref="neighborhood-default",
        ),
    ],
)
def test_profile_ref_is_refused_until_profiles_exist(request_) -> None:
    graph, port, projection, principal, *_ = _world([_entity_hit()])
    receipt = graph.execute(principal("tenant-a"), request_)
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures == ({"class": "profile_not_supported", "stage": "policy"},)
    assert projection.calls == []
    assert port.requests == []


class NodeTransport:
    name = "graphiti-http"

    def __init__(self, nodes) -> None:
        self.nodes = nodes
        self.arguments: list[dict] = []

    def list_tools(self):
        return ["search_nodes", "search_memory_facts", "add_memory", "delete_episode"]

    def call_tool(self, name, arguments=None):
        self.arguments.append(arguments)
        return {"nodes": self.nodes}


def test_graphiti_entity_search_keeps_hits_without_a_record_id() -> None:
    record_id = uuid4()
    transport = NodeTransport(
        [
            {"uuid": str(ENTITY), "name": "Falcon", "summary": "a service", "score": 0.7},
            {"uuid": "not-a-uuid", "name": "junk"},
            {"uuid": str(uuid4()), "name": "Ledger", "metadata": {"record_id": str(record_id)}},
        ]
    )
    projection = GraphitiProjection(transport)
    hits = projection.search_entities("falcon", ("shared",), limit=10, tenant_id="tenant-a")
    assert transport.arguments[0]["group_ids"] == [graph_group_id("tenant-a", "shared")]
    by_kind = {("entity" if h.record_id is None else "record"): h for h in hits}
    assert by_kind["entity"].entity_uuid == ENTITY and by_kind["entity"].name == "Falcon"
    assert by_kind["record"].record_id == record_id and by_kind["record"].entity_uuid is None
    assert len(hits) == 2
    # memory.search semantics are unchanged: the strategy still drops entity-only hits.
    strategy_hits = projection.search_strategy(
        "graph-search", "falcon", ("shared",), limit=10, tenant_id="tenant-a"
    )
    assert [h.record_id for h in strategy_hits] == [record_id]
    assert all(isinstance(h, ProjectionHit) for h in strategy_hits)
