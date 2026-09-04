# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/review.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""Port through which scheduled maintenance asks for a quarantine verdict (ADR-080)."""

from __future__ import annotations

from typing import Protocol

from l9_graphite_memory.contracts import MemoryRecord, QuarantineReviewVerdict


class QuarantineReviewer(Protocol):
    """Judge one quarantined record.

    Implementations may consult a language model, a rule set, or a person.
    Whatever they consult, they return a verdict and never mutate canonical
    state: the maintenance service applies the verdict under the review
    policy, through ``MemoryService.transition_lifecycle``, with the verdict
    recorded as evidence on the lifecycle receipt.
    """

    name: str
    policy_version: str

    def review(self, record: MemoryRecord) -> QuarantineReviewVerdict: ...
