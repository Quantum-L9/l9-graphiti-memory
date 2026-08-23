# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/curation/promotion.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic, default-deny promotion rules harvested from the legacy system."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from l9_graphite_memory.contracts import MemoryClass, MemoryRecord, PromotionRequest


class PromotionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approved: bool
    reasons: tuple[str, ...]
    policy_version: str = "memory-promotion/v1"


class PromotionPolicy:
    """Promotions require explicit authority or repeated evidence."""

    def evaluate(self, record: MemoryRecord, request: PromotionRequest) -> PromotionDecision:
        reasons: list[str] = []
        approved = False
        if request.target_class is record.memory_class:
            reasons.append("target class is unchanged")
        elif request.governance_approval:
            approved = True
            reasons.append("governance approval supplied")
        elif request.explicit_confirmation and request.target_class in {
            MemoryClass.IDENTITY,
            MemoryClass.PREFERENCE,
            MemoryClass.CONSTRAINT,
            MemoryClass.DECISION,
        }:
            approved = True
            reasons.append("explicit confirmation supplied for governed memory class")
        elif request.test_success_count >= 3 and request.target_class is MemoryClass.PROCEDURAL:
            approved = True
            reasons.append("procedure has at least three test-backed successes")
        elif len(request.supporting_record_ids) >= 3 and request.target_class in {
            MemoryClass.SEMANTIC,
            MemoryClass.INSIGHT,
            MemoryClass.META,
        }:
            approved = True
            reasons.append("promotion is supported by at least three source records")
        else:
            reasons.append("default deny: promotion evidence is insufficient")
        return PromotionDecision(approved=approved, reasons=tuple(reasons))
