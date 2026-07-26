# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/retrieval/query_classifier.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic query classification for retrieval planning."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from l9_graphite_memory.contracts import QueryPattern


class QueryClassification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pattern: QueryPattern
    reason: str
    strategies: tuple[str, ...]
    policy_version: str = "query-classification/v1"


class QueryClassifier:
    """Classify intent without an LLM so routing remains reproducible."""

    _patterns: tuple[tuple[QueryPattern, re.Pattern[str], tuple[str, ...]], ...] = (
        (
            QueryPattern.REASONING_LINEAGE,
            re.compile(
                r"\b(why|reasoning|lineage|trace|reconstruct|ancestor|supersed)\b", re.IGNORECASE
            ),
            ("lexical-ranking", "graph-search"),
        ),
        (
            QueryPattern.TEMPORAL,
            re.compile(
                r"\b(recent|latest|before|after|since|until|when|history|last|valid)\b|\bas\s+of\b",
                re.IGNORECASE,
            ),
            ("temporal-filter", "lexical-ranking", "semantic-search"),
        ),
        (
            QueryPattern.IDENTITY,
            re.compile(
                r"\b(identity|preference|prefer|value|goal|style|always|never)\b", re.IGNORECASE
            ),
            ("lexical-ranking", "graph-search", "semantic-search"),
        ),
        (
            QueryPattern.ENTITY_LOOKUP,
            re.compile(r"\b(who|what|where|which)\s+(is|are|was|were)\b", re.IGNORECASE),
            ("graph-search", "lexical-ranking"),
        ),
        (
            QueryPattern.FACTUAL,
            re.compile(r"\b(fact|value|retrieve|get|show|find)\b", re.IGNORECASE),
            ("lexical-ranking", "semantic-search", "temporal-filter"),
        ),
        (
            QueryPattern.EXPLORATORY,
            re.compile(
                r"\b(explore|overview|tell me|what do we know|context|discover)\b", re.IGNORECASE
            ),
            ("semantic-search", "lexical-ranking", "graph-search"),
        ),
    )

    def classify(self, query: str) -> QueryClassification:
        normalized = query.strip()
        for pattern, expression, strategies in self._patterns:
            if expression.search(normalized):
                return QueryClassification(
                    pattern=pattern,
                    reason=f"matched deterministic {pattern.value} pattern",
                    strategies=strategies,
                )
        return QueryClassification(
            pattern=QueryPattern.DEFAULT,
            reason="no specialized pattern matched",
            strategies=("lexical-ranking", "semantic-search", "temporal-filter"),
        )
