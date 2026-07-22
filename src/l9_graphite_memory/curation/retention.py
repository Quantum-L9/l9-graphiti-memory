# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/curation/retention.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Reference-aware retention, decay, and archive decisions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from l9_graphite_memory.contracts import MemoryClass, MemoryRecord, RetentionDecision
from l9_graphite_memory.version import RETENTION_POLICY_VERSION


@dataclass(frozen=True)
class RetentionPolicy:
    """Decay changes ranking; archiving preserves immutable historical content."""

    archive_expired_records: bool = True
    refresh_on_use: bool = False
    default_half_life_days: float = 120.0
    class_half_life_days: tuple[tuple[MemoryClass, float], ...] = (
        (MemoryClass.EPISODIC, 30.0),
        (MemoryClass.OBSERVATION, 60.0),
        (MemoryClass.INSIGHT, 180.0),
        (MemoryClass.SEMANTIC, 365.0),
        (MemoryClass.META, 365.0),
    )
    never_archive_classes: tuple[MemoryClass, ...] = (
        MemoryClass.IDENTITY,
        MemoryClass.CONSTRAINT,
        MemoryClass.DECISION,
        MemoryClass.PROCEDURAL,
    )
    policy_version: str = RETENTION_POLICY_VERSION

    def half_life_days(self, memory_class: MemoryClass) -> float:
        return dict(self.class_half_life_days).get(
            memory_class, self.default_half_life_days
        )

    def decay_score(self, record: MemoryRecord, *, now: datetime) -> float:
        age_days = max(
            0.0, (now - record.temporal.recorded_at).total_seconds() / 86_400
        )
        half_life = self.half_life_days(record.memory_class)
        return math.exp(-math.log(2) * age_days / half_life)


class RetentionEngine:
    def __init__(self, policy: RetentionPolicy | None = None) -> None:
        self.policy = policy or RetentionPolicy()

    @staticmethod
    def reference_counts(records: tuple[MemoryRecord, ...]) -> dict[UUID, int]:
        counts: dict[UUID, int] = {}
        known = {record.record_id for record in records}
        for record in records:
            references = {
                *record.references,
                *record.supersedes,
                *record.conflicts_with,
            }
            for target in references:
                if target in known:
                    counts[target] = counts.get(target, 0) + 1
        return counts

    def evaluate(
        self,
        records: tuple[MemoryRecord, ...],
        *,
        now: datetime,
    ) -> tuple[RetentionDecision, ...]:
        counts = self.reference_counts(records)
        decisions: list[RetentionDecision] = []
        for record in records:
            decay = self.policy.decay_score(record, now=now)
            reference_count = counts.get(record.record_id, 0)
            expired = (
                record.temporal.valid_to is not None and record.temporal.valid_to <= now
            )
            if record.memory_class in self.policy.never_archive_classes:
                action = "retain"
                reason = "class is protected from automatic archive"
            elif not self.policy.archive_expired_records or not expired:
                action = "retain"
                reason = "record has not reached archive eligibility"
            elif reference_count:
                action = "soft-expire"
                reason = "record remains referenced; exclude from active retrieval but preserve linkage"
            else:
                action = "archive"
                reason = "record expired and has no incoming references"
            decisions.append(
                RetentionDecision(
                    record_id=record.record_id,
                    action=action,
                    reason=reason,
                    reference_count=reference_count,
                    decay_score=decay,
                )
            )
        return tuple(decisions)
