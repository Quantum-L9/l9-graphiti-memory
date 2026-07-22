# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_query_classifier.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.contracts import QueryPattern
from l9_graphite_memory.retrieval import QueryClassifier


def test_query_classifier_identifies_temporal_and_lineage_queries() -> None:
    classifier = QueryClassifier()

    temporal = classifier.classify("What was valid as of January 2026?")
    lineage = classifier.classify("Why does this fact exist and what superseded it?")

    assert temporal.pattern is QueryPattern.TEMPORAL
    assert "temporal-filter" in temporal.strategies
    assert lineage.pattern is QueryPattern.REASONING_LINEAGE
    assert "graph-search" in lineage.strategies


def test_query_classifier_defaults_without_concealing_strategy() -> None:
    classification = QueryClassifier().classify("memory architecture")

    assert classification.pattern in {QueryPattern.ENTITY_LOOKUP, QueryPattern.DEFAULT}
    assert classification.strategies
