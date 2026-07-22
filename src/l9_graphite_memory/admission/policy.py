# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/admission/policy.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Versioned admission policy."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import MemoryClass
from l9_graphite_memory.version import ADMISSION_POLICY_VERSION


class AdmissionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str = ADMISSION_POLICY_VERSION
    max_content_chars: int = Field(default=64_000, ge=1_000, le=1_000_000)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    quarantine_on_safety_signal: bool = True
    quarantine_on_pii: bool = False
    identity_requires_explicit_evidence: bool = True
    preference_requires_explicit_evidence: bool = True
    private_classes_require_consent: bool = True
    allowed_classes: tuple[MemoryClass, ...] = tuple(MemoryClass)
