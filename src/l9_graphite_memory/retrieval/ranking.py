# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/retrieval/ranking.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Explainable deterministic ranking with separated evidence signals."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from l9_graphite_memory.contracts import (
    MemoryClass,
    MemoryRecord,
    QueryPattern,
    ScoreFactors,
)
from l9_graphite_memory.curation.retention import RetentionPolicy
from l9_graphite_memory.version import RANKING_POLICY_VERSION

_TOKEN = re.compile(r"[A-Za-z0-9_\-]{2,}")

_CLASS_IMPORTANCE: dict[MemoryClass, float] = {
    MemoryClass.CONSTRAINT: 0.95,
    MemoryClass.DECISION: 0.90,
    MemoryClass.PROCEDURAL: 0.88,
    MemoryClass.IDENTITY: 0.85,
    MemoryClass.PREFERENCE: 0.78,
    MemoryClass.META: 0.75,
    MemoryClass.SEMANTIC: 0.72,
    MemoryClass.INSIGHT: 0.68,
    MemoryClass.OBSERVATION: 0.55,
    MemoryClass.EPISODIC: 0.50,
}

_PATTERN_RELEVANCE: dict[QueryPattern, tuple[float, float]] = {
    QueryPattern.ENTITY_LOOKUP: (0.35, 0.65),
    QueryPattern.REASONING_LINEAGE: (0.55, 0.45),
    QueryPattern.TEMPORAL: (0.70, 0.30),
    QueryPattern.IDENTITY: (0.65, 0.35),
    QueryPattern.EXPLORATORY: (0.35, 0.65),
    QueryPattern.FACTUAL: (0.70, 0.30),
    QueryPattern.DEFAULT: (0.60, 0.40),
}


@dataclass(frozen=True)
class RankingPolicy:
    """Keep authority, trust, confidence, relevance, importance, and recency distinct."""

    relevance_weight: float = 0.40
    confidence_weight: float = 0.15
    trust_weight: float = 0.10
    importance_weight: float = 0.20
    recency_weight: float = 0.15
    policy_version: str = RANKING_POLICY_VERSION
    retention_policy: RetentionPolicy = RetentionPolicy()

    def __post_init__(self) -> None:
        total = (
            self.relevance_weight
            + self.confidence_weight
            + self.trust_weight
            + self.importance_weight
            + self.recency_weight
        )
        if not math.isclose(total, 1.0, rel_tol=1e-9):
            raise ValueError("ranking weights must sum to 1.0")

    @staticmethod
    def tokens(value: str) -> set[str]:
        return {token.lower() for token in _TOKEN.findall(value)}

    def lexical_score(self, query: str, record: MemoryRecord) -> float:
        query_tokens = self.tokens(query)
        if not query_tokens:
            return 0.0
        record_tokens = self.tokens(record.content)
        if record.assertion:
            record_tokens.update(
                self.tokens(
                    " ".join(
                        filter(
                            None,
                            [
                                record.assertion.subject,
                                record.assertion.predicate,
                                record.assertion.object,
                            ],
                        )
                    )
                )
            )
        overlap = len(query_tokens & record_tokens) / len(query_tokens)
        phrase_bonus = 0.15 if query.lower() in record.content.lower() else 0.0
        return min(1.0, overlap + phrase_bonus)

    @staticmethod
    def importance_score(record: MemoryRecord) -> float:
        raw = record.metadata.get("importance")
        if raw is None:
            raw = record.metadata.get("importance_score")
        if raw is not None:
            try:
                return max(0.0, min(float(raw), 1.0))
            except (TypeError, ValueError):
                pass
        return _CLASS_IMPORTANCE[record.memory_class]

    def recency_score(
        self, record: MemoryRecord, *, now: datetime | None = None
    ) -> float:
        reference = now or datetime.now(timezone.utc)
        return self.retention_policy.decay_score(record, now=reference)

    @staticmethod
    def relevance_score(
        lexical: float,
        projection: float,
        *,
        pattern: QueryPattern,
    ) -> float:
        lexical_weight, projection_weight = _PATTERN_RELEVANCE[pattern]
        return min(1.0, lexical * lexical_weight + projection * projection_weight)

    def factors(
        self,
        query: str,
        record: MemoryRecord,
        *,
        projection_score: float = 0.0,
        pattern: QueryPattern = QueryPattern.DEFAULT,
        now: datetime | None = None,
    ) -> ScoreFactors:
        lexical = self.lexical_score(query, record)
        projection = max(0.0, min(projection_score, 1.0))
        return ScoreFactors(
            lexical=lexical,
            projection=projection,
            relevance=self.relevance_score(lexical, projection, pattern=pattern),
            confidence=record.confidence.score,
            trust=record.provenance.source_trust,
            importance=self.importance_score(record),
            recency=self.recency_score(record, now=now),
        )

    def total(self, factors: ScoreFactors) -> float:
        score = (
            factors.relevance * self.relevance_weight
            + factors.confidence * self.confidence_weight
            + factors.trust * self.trust_weight
            + factors.importance * self.importance_weight
            + factors.recency * self.recency_weight
        )
        return max(0.0, min(score, 1.0))
