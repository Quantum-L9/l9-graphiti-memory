# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_contracts.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Graph-intelligence request/receipt contracts vs the shipped JSON Schemas (ADR-086)."""

from __future__ import annotations

import json
from importlib import resources
from uuid import uuid4

import jsonschema
import pytest
from pydantic import ValidationError

from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceReceipt,
    GraphIntelligenceRequest,
    GraphLimits,
    GraphOperation,
    GraphProviderIdentity,
    GraphProviderRequest,
    GraphReceiptStatus,
)


def _schema(name: str) -> dict:
    text = resources.files("l9_graphite_memory").joinpath(f"resources/graph/{name}").read_text()
    return json.loads(text)


def test_request_payload_conforms_to_the_request_schema() -> None:
    request = GraphIntelligenceRequest(
        operation=GraphOperation.PATH,
        namespaces=("repo-a",),
        anchor=GraphAnchor(entity_uuid=uuid4()),
        target=GraphAnchor(record_id=uuid4()),
        relationship_types=("RELATES_TO",),
        limits=GraphLimits(max_depth=3),
    )
    jsonschema.validate(
        request.contract_payload(), _schema("graph-intelligence-request.schema.json")
    )


def test_receipt_payload_conforms_to_the_receipt_schema() -> None:
    receipt = GraphIntelligenceReceipt(
        status=GraphReceiptStatus.COMPLETE,
        operation=GraphOperation.TRAVERSE,
        scope_digest="a" * 64,
        provider=GraphProviderIdentity(projection_provider="graphiti", graph_backend="neo4j"),
        limits_applied=GraphLimits().model_dump(),
        supporting_record_ids=(uuid4(),),
        result_digest="b" * 64,
    )
    jsonschema.validate(
        receipt.contract_payload(), _schema("graph-intelligence-receipt.schema.json")
    )


@pytest.mark.parametrize("field", ["tenant_id", "group_ids", "cypher", "query_text"])
def test_request_has_no_scope_authority_or_query_text_field(field: str) -> None:
    with pytest.raises(ValidationError):
        GraphIntelligenceRequest(operation="graph.traverse", namespaces=("repo-a",), **{field: "x"})


@pytest.mark.parametrize(
    "limits",
    [{"max_depth": 999}, {"max_nodes": 1_000_000}, {"max_edges": 0}, {"max_runtime_ms": 60_000}],
)
def test_unbounded_limits_are_rejected_before_any_provider(limits: dict) -> None:
    with pytest.raises(ValidationError):
        GraphLimits(**limits)


def test_relationship_type_with_cypher_syntax_is_rejected() -> None:
    with pytest.raises(ValidationError, match="relationship type"):
        GraphIntelligenceRequest(
            operation="graph.traverse",
            namespaces=("repo-a",),
            relationship_types=("RELATES_TO]->(x) DETACH DELETE x //",),
        )


def test_anchor_requires_exactly_one_identity() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        GraphAnchor()
    with pytest.raises(ValidationError, match="exactly one"):
        GraphAnchor(record_id=uuid4(), query="both")
    with pytest.raises(ValidationError):
        GraphAnchor(query="x" * 1_001)


def test_namespaces_are_required_unique_and_non_blank() -> None:
    for namespaces in ((), ("repo-a", "repo-a"), (" ",)):
        with pytest.raises(ValidationError):
            GraphIntelligenceRequest(operation="graph.traverse", namespaces=namespaces)


def test_provider_request_accepts_only_scope_key_groups() -> None:
    with pytest.raises(ValidationError, match="GraphScopeKey"):
        GraphProviderRequest(
            operation=GraphOperation.TRAVERSE,
            group_ids=("shared",),
            limits=GraphLimits(),
            operation_id="op",
        )
    GraphProviderRequest(
        operation=GraphOperation.TRAVERSE,
        group_ids=(graph_group_id("t", "shared"),),
        limits=GraphLimits(),
        operation_id="op",
    )
