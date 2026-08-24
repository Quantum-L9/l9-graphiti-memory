# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/admission/engine.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Pure admission decision engine; persistence is owned by MemoryService."""

from __future__ import annotations

from l9_graphite_memory.contracts import (
    AdmissionDecision,
    AuthorizationReceipt,
    EvidenceKind,
    MemoryClass,
    MemoryWriteRequest,
    WriteStatus,
)

from .normalization import NormalizationResult
from .policy import AdmissionPolicy


class AdmissionEngine:
    def __init__(self, policy: AdmissionPolicy | None = None) -> None:
        self.policy = policy or AdmissionPolicy()

    def evaluate(
        self,
        request: MemoryWriteRequest,
        normalization: NormalizationResult,
        authorization: AuthorizationReceipt,
        *,
        duplicate_record_exists: bool,
    ) -> AdmissionDecision:
        reasons: list[str] = []
        warnings: list[str] = []

        if not authorization.allowed:
            reasons.append("namespace authorization denied")
            status = WriteStatus.REJECTED
        elif duplicate_record_exists:
            reasons.append("idempotent duplicate already exists")
            status = WriteStatus.DUPLICATE
        elif request.memory_class not in self.policy.allowed_classes:
            reasons.append(f"memory class {request.memory_class.value} is not admitted")
            status = WriteStatus.REJECTED
        elif len(normalization.redacted_content) > self.policy.max_content_chars:
            reasons.append("normalized content exceeds policy limit")
            status = WriteStatus.REJECTED
        elif request.confidence.score < self.policy.min_confidence:
            reasons.append("confidence is below admission threshold")
            status = WriteStatus.REJECTED
        elif self.policy.private_classes_require_consent and request.memory_class in {
            MemoryClass.IDENTITY,
            MemoryClass.PREFERENCE,
        }:
            subject_id = request.assertion.subject if request.assertion else None
            if request.consent is None:
                reasons.append(
                    f"{request.memory_class.value} memory requires purpose-bound consent"
                )
                status = WriteStatus.REJECTED
            elif not request.consent.permits(
                request.namespace,
                request.memory_class,
                at=request.valid_from,
                subject_id=subject_id,
            ):
                reasons.append(
                    "consent does not authorize this subject, namespace, class, or validity time"
                )
                status = WriteStatus.REJECTED
            elif not any(item.kind is EvidenceKind.EXPLICIT for item in request.evidence):
                reasons.append(f"{request.memory_class.value} memory requires explicit evidence")
                status = WriteStatus.REJECTED
            else:
                status = WriteStatus.ADMITTED
        elif (
            self.policy.identity_requires_explicit_evidence
            and request.memory_class is MemoryClass.IDENTITY
        ):
            if not any(item.kind is EvidenceKind.EXPLICIT for item in request.evidence):
                reasons.append("identity memory requires explicit evidence")
                status = WriteStatus.REJECTED
            else:
                status = WriteStatus.ADMITTED
        elif (
            self.policy.preference_requires_explicit_evidence
            and request.memory_class is MemoryClass.PREFERENCE
        ):
            if not any(item.kind is EvidenceKind.EXPLICIT for item in request.evidence):
                reasons.append("preference memory requires explicit evidence")
                status = WriteStatus.REJECTED
            else:
                status = WriteStatus.ADMITTED
        else:
            status = WriteStatus.ADMITTED

        if normalization.pii_types:
            warnings.append(f"PII redacted: {', '.join(normalization.pii_types)}")
            if self.policy.quarantine_on_pii and status is WriteStatus.ADMITTED:
                reasons.append("PII requires review")
                status = WriteStatus.QUARANTINED
        if normalization.safety_signals:
            warnings.append(f"safety signals: {', '.join(normalization.safety_signals)}")
            if self.policy.quarantine_on_safety_signal and status is WriteStatus.ADMITTED:
                reasons.append("safety signal requires review")
                status = WriteStatus.QUARANTINED

        if status is WriteStatus.ADMITTED and request.supersedes:
            status = WriteStatus.SUPERSEDED
            reasons.append("new record supersedes existing records")
        if not reasons:
            reasons.append("candidate satisfies admission policy")

        return AdmissionDecision(
            status=status,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
            candidate_digest=normalization.normalized_digest,
        )
