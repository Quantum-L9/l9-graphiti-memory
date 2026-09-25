# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_service.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""GraphIntelligenceService authorization, policy, failure, and receipts (ADR-086)."""

from __future__ import annotations

import json
from importlib import resources
from uuid import uuid4

import jsonschema
import pytest

from l9_graphite_memory.errors import AuthorizationError, GraphCapabilityUnavailable
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.algorithm_policy import AlgorithmMaturity, AlgorithmPolicy
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphLimits,
    GraphOperation,
    GraphProviderNode,
    GraphProviderResult,
    GraphReceiptStatus,
)
from l9_graphite_memory.graph.ports import GraphCapability
from l9_graphite_memory.graph.service import GraphIntelligenceService, GraphServiceConfig
from tests.graph_fakes import FakeGraphPort, seeded_memory

RECEIPT_SCHEMA = json.loads(
    resources.files("l9_graphite_memory")
    .joinpath("resources/graph/graph-intelligence-receipt.schema.json")
    .read_text()
)


def _request(**overrides) -> GraphIntelligenceRequest:
    values = {
        "operation": GraphOperation.NEIGHBORHOOD,
        "namespaces": ("shared",),
        "anchor": GraphAnchor(entity_uuid=uuid4()),
    }
    values.update(overrides)
    return GraphIntelligenceRequest(**values)


def _world(result_factory=None, **port_kwargs):
    service, store, principal, write = seeded_memory()
    record = write("tenant-a", "falcon depends on osprey")
    foreign = write("tenant-b", "bravo secret in the same namespace")

    def default_result(request):
        group = request.group_ids[0]
        return GraphProviderResult(
            operation=request.operation,
            nodes=(
                GraphProviderNode(
                    entity_uuid=uuid4(),
                    group_id=group,
                    name="falcon",
                    supporting_episode_ids=(record,),
                ),
                GraphProviderNode(
                    entity_uuid=uuid4(),
                    group_id=group,
                    name="ghost",
                    supporting_episode_ids=(foreign,),
                ),
            ),
        )

    port = FakeGraphPort(
        {GraphOperation.NEIGHBORHOOD: result_factory or default_result}, **port_kwargs
    )
    graph = GraphIntelligenceService(store, port, namespace_policy=service.namespace_policy)
    return graph, port, principal, record, foreign, write


def test_complete_receipt_binds_support_and_hides_unsupported_items() -> None:
    graph, _port, principal, record, foreign, _ = _world()
    receipt = graph.execute(principal("tenant-a"), _request())

    assert receipt.status is GraphReceiptStatus.COMPLETE
    assert receipt.supporting_record_ids == (record,)
    assert [item["name"] for item in receipt.results] == ["falcon"]
    assert receipt.unsupported_projection_observations[0]["reason"] == "no_canonical_support"
    assert str(foreign) not in receipt.model_dump_json()
    assert receipt.algorithm is not None and receipt.algorithm.id == "bounded-neighborhood"
    jsonschema.validate(receipt.contract_payload(), RECEIPT_SCHEMA)


def test_provider_sees_only_derived_groups_never_the_tenant() -> None:
    graph, port, principal, *_ = _world()
    graph.execute(principal("tenant-a"), _request(namespaces=("shared", "other")))
    sent = port.requests[0]
    assert sent.group_ids == (
        graph_group_id("tenant-a", "shared"),
        graph_group_id("tenant-a", "other"),
    )
    assert "tenant-a" not in sent.model_dump_json()


def test_receipt_is_deterministic_under_a_stable_provider() -> None:
    node_id = uuid4()

    def stable(request):
        return GraphProviderResult(
            operation=request.operation,
            nodes=(GraphProviderNode(entity_uuid=node_id, group_id=request.group_ids[0]),),
        )

    graph, _port, principal, *_ = _world(stable)
    anchor = GraphAnchor(entity_uuid=node_id)
    first = graph.execute(principal("tenant-a"), _request(anchor=anchor))
    second = graph.execute(principal("tenant-a"), _request(anchor=anchor))
    assert first == second
    assert first.result_digest == second.result_digest


def test_unauthorized_namespace_is_refused_before_the_provider() -> None:
    graph, port, principal, *_ = _world()
    with pytest.raises(AuthorizationError):
        graph.execute(
            principal("tenant-a", namespaces=("shared",)), _request(namespaces=("other",))
        )
    assert port.requests == []


def test_provider_failure_is_failed_not_empty_complete() -> None:
    graph, _port, principal, *_ = _world(
        lambda request: (_ for _ in ()).throw(RuntimeError("bolt://secret-host refused"))
    )
    receipt = graph.execute(principal("tenant-a"), _request())
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.results == ()
    assert receipt.failures[0]["class"] == "provider_error:RuntimeError"
    assert "secret-host" not in receipt.model_dump_json()


def test_unimplemented_backend_operation_is_failed() -> None:
    def unavailable(request):
        raise GraphCapabilityUnavailable("not served")

    graph, *_rest = _world(unavailable)
    receipt = graph.execute(_rest[1]("tenant-a"), _request())
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == "capability_unavailable"


def test_capability_absent_from_backend_short_circuits() -> None:
    graph, port, principal, *_ = _world(capabilities=(GraphCapability.TRAVERSE,))
    receipt = graph.execute(principal("tenant-a"), _request())
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures == ({"class": "capability_unavailable", "stage": "capability"},)
    assert port.requests == []


def test_relationship_type_outside_the_allowlist_is_refused() -> None:
    graph, port, principal, *_ = _world()
    receipt = graph.execute(principal("tenant-a"), _request(relationship_types=("KNOWS",)))
    assert receipt.failures[0]["class"] == "relationship_type_not_allowed"
    assert port.requests == []


def test_alpha_algorithm_is_refused_without_opt_in() -> None:
    _service, store, principal, _write = seeded_memory()
    port = FakeGraphPort({}, capabilities=(GraphCapability.LINK_PREDICTION,))
    graph = GraphIntelligenceService(store, port)
    receipt = graph.execute(
        principal("tenant-a"), _request(operation=GraphOperation.LINK_PREDICTION)
    )
    assert receipt.failures[0]["class"] == "algorithm_not_admitted"
    assert port.requests == []
    opted_in = GraphIntelligenceService(
        store,
        FakeGraphPort(
            {
                GraphOperation.LINK_PREDICTION: GraphProviderResult(
                    operation="graph.link_prediction"
                )
            },
            capabilities=(GraphCapability.LINK_PREDICTION,),
        ),
        config=GraphServiceConfig(
            algorithm_policy=AlgorithmPolicy(
                maturity_ceiling=AlgorithmMaturity.ALPHA, link_prediction_enabled=True
            )
        ),
    ).execute(principal("tenant-a"), _request(operation=GraphOperation.LINK_PREDICTION))
    assert opted_in.status is GraphReceiptStatus.COMPLETE
    assert opted_in.algorithm is not None and opted_in.algorithm.maturity == "alpha"


def test_anchor_record_of_another_tenant_is_refused_like_a_missing_one() -> None:
    graph, port, principal, _record, foreign, _ = _world()
    foreign_receipt = graph.execute(
        principal("tenant-a"), _request(anchor=GraphAnchor(record_id=foreign))
    )
    missing_receipt = graph.execute(
        principal("tenant-a"), _request(anchor=GraphAnchor(record_id=uuid4()))
    )
    assert foreign_receipt.failures == missing_receipt.failures
    assert foreign_receipt.failures[0]["class"] == "anchor_not_in_scope"
    assert port.requests == []


def test_caps_truncate_deterministically_and_mark_partial_or_failed() -> None:
    def many(request):
        return GraphProviderResult(
            operation=request.operation,
            nodes=tuple(
                GraphProviderNode(
                    entity_uuid=uuid4(),
                    group_id=request.group_ids[0],
                    supporting_episode_ids=(record_ref[0],),
                )
                for _ in range(5)
            ),
        )

    record_ref: list = []
    graph, _port, principal, record, _foreign, _ = _world(many)
    record_ref.append(record)
    partial = graph.execute(principal("tenant-a"), _request(limits=GraphLimits(max_nodes=2)))
    assert partial.status is GraphReceiptStatus.PARTIAL
    assert len(partial.results) == 2
    assert {"class": "truncated", "stage": "limits"} in partial.failures
    required = graph.execute(
        principal("tenant-a"), _request(limits=GraphLimits(max_nodes=2), required=True)
    )
    assert required.status is GraphReceiptStatus.FAILED and required.results == ()


def test_runtime_budget_is_clamped_to_the_deployment_ceiling() -> None:
    _service, store, principal, _ = seeded_memory()
    port = FakeGraphPort(
        {GraphOperation.NEIGHBORHOOD: GraphProviderResult(operation="graph.neighborhood")}
    )
    graph = GraphIntelligenceService(store, port, config=GraphServiceConfig(max_runtime_ms=500))
    receipt = graph.execute(
        principal("tenant-a"), _request(limits=GraphLimits(max_runtime_ms=9_000))
    )
    assert receipt.limits_applied["max_runtime_ms"] == 500
    assert port.requests[0].limits.max_runtime_ms == 500


def test_backend_health_is_cached_between_operations() -> None:
    graph, port, principal, *_ = _world()
    graph.execute(principal("tenant-a"), _request())
    graph.execute(principal("tenant-a"), _request())
    assert port.health_calls == 1
