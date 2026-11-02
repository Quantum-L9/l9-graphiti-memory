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

from l9_graphite_memory.contracts import EvidenceKind, EvidenceRef, MemoryClass
from l9_graphite_memory.version import ADMISSION_POLICY_VERSION

#: Classes whose admission requires explicit evidence.
EXPLICIT_EVIDENCE_CLASSES = frozenset({MemoryClass.IDENTITY, MemoryClass.PREFERENCE})

#: The server decides what is explicit evidence, never the caller (operator
#: decision 2026-11-02). A caller that labels its own evidence ``explicit`` is
#: recorded as having *claimed* it: an OBSERVATION-grade ref whose description
#: starts with this marker. A claim never satisfies an explicit-evidence class;
#: it holds the write in quarantine for a person instead of rejecting it.
CALLER_ASSERTED_EXPLICIT_MARKER = "caller-asserted explicit evidence (unverified by the server): "


def caller_asserted_explicit(description: str, *, source_id: str | None = None) -> EvidenceRef:
    """Record a caller's claim of explicit evidence as an unverified observation."""

    return EvidenceRef(
        kind=EvidenceKind.OBSERVATION,
        description=f"{CALLER_ASSERTED_EXPLICIT_MARKER}{description}"[:2_000],
        source_id=source_id,
    )


def is_caller_asserted_explicit(ref: EvidenceRef) -> bool:
    return ref.kind is EvidenceKind.OBSERVATION and ref.description.startswith(
        CALLER_ASSERTED_EXPLICIT_MARKER
    )


class AdmissionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str = ADMISSION_POLICY_VERSION
    max_content_chars: int = Field(default=64_000, ge=1_000, le=1_000_000)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    quarantine_on_safety_signal: bool = True
    quarantine_on_pii: bool = False
    quarantine_on_ambiguous_numeric: bool = True
    identity_requires_explicit_evidence: bool = True
    preference_requires_explicit_evidence: bool = True
    private_classes_require_consent: bool = True
    allowed_classes: tuple[MemoryClass, ...] = tuple(MemoryClass)
