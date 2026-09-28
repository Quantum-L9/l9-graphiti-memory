# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_algorithm_policy.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Graph algorithm maturity and feature gates (ADR-086)."""

from __future__ import annotations

import pytest

from l9_graphite_memory.errors import GraphQueryPolicyViolation
from l9_graphite_memory.graph.algorithm_policy import (
    ALGORITHMS,
    AlgorithmMaturity,
    AlgorithmPolicy,
    algorithm_identity,
)
from l9_graphite_memory.graph.contracts import GraphOperation

STRUCTURAL = [
    op for op in GraphOperation if op.value not in {"graph.search", "graph.semantic_search"}
]


def test_every_structural_operation_has_exactly_one_default() -> None:
    for operation in STRUCTURAL:
        defaults = [a for a in ALGORITHMS if a.operation is operation and a.default]
        assert len(defaults) == 1, operation


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (GraphOperation.TRAVERSE, "bounded-traversal"),
        (GraphOperation.PATH, "shortest-path"),
        (GraphOperation.NEIGHBORHOOD, "bounded-neighborhood"),
        (GraphOperation.COMMUNITY, "louvain"),
        (GraphOperation.CENTRALITY, "pagerank"),
        (GraphOperation.STRUCTURAL_EMBEDDING, "fastrp"),
        (GraphOperation.STRUCTURAL_SIMILARITY, "fastrp-cosine"),
    ],
)
def test_production_defaults_run_under_the_default_policy(operation, expected) -> None:
    assert AlgorithmPolicy().resolve(operation, None).id == expected


def test_algorithm_from_another_operation_is_not_admissible() -> None:
    with pytest.raises(GraphQueryPolicyViolation, match="not admissible"):
        AlgorithmPolicy().resolve(GraphOperation.CENTRALITY, "louvain")
    with pytest.raises(GraphQueryPolicyViolation, match="not admissible"):
        AlgorithmPolicy().resolve(GraphOperation.CENTRALITY, "gds.pageRank.write")


def test_similarity_cannot_fall_back_to_semantic_embeddings() -> None:
    with pytest.raises(GraphQueryPolicyViolation):
        AlgorithmPolicy().resolve(GraphOperation.STRUCTURAL_SIMILARITY, "semantic-cosine")


def test_link_prediction_needs_the_flag_and_an_alpha_ceiling() -> None:
    with pytest.raises(GraphQueryPolicyViolation, match="disabled"):
        AlgorithmPolicy(maturity_ceiling=AlgorithmMaturity.ALPHA).resolve(
            GraphOperation.LINK_PREDICTION, None
        )
    with pytest.raises(GraphQueryPolicyViolation, match="alpha"):
        AlgorithmPolicy(link_prediction_enabled=True).resolve(GraphOperation.LINK_PREDICTION, None)
    with pytest.raises(GraphQueryPolicyViolation, match="alpha"):
        AlgorithmPolicy(
            maturity_ceiling=AlgorithmMaturity.BETA, link_prediction_enabled=True
        ).resolve(GraphOperation.LINK_PREDICTION, None)
    admitted = AlgorithmPolicy(
        maturity_ceiling=AlgorithmMaturity.ALPHA, link_prediction_enabled=True
    ).resolve(GraphOperation.LINK_PREDICTION, None)
    assert admitted.maturity is AlgorithmMaturity.ALPHA


def test_identity_binds_algorithm_and_config_by_digest() -> None:
    algorithm = AlgorithmPolicy().resolve(GraphOperation.CENTRALITY, "degree")
    first = algorithm_identity(algorithm, {"max_nodes": 10})
    assert first == algorithm_identity(algorithm, {"max_nodes": 10})
    assert first.config_digest != algorithm_identity(algorithm, {"max_nodes": 11}).config_digest
    assert (first.id, first.maturity) == ("degree", "production")
