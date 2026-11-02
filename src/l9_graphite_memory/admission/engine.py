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
from .policy import AdmissionPolicy, is_caller_asserted_explicit


def _expected_purpose(request: MemoryWriteRequest) -> str | None:
    purpose = request.metadata.get("purpose")
    return purpose if isinstance(purpose, str) else None


def _has_explicit_evidence(request: MemoryWriteRequest) -> bool:
    return any(item.kind is EvidenceKind.EXPLICIT for item in request.evidence)


def _missing_explicit_evidence(
    request: MemoryWriteRequest, reason: str, reasons: list[str]
) -> WriteStatus:
    """A write lacking server-recognized explicit evidence is never admitted.

    A caller's own claim of explicit evidence holds the record in quarantine
    for a person; with no claim at all the write is rejected.
    """

    if any(is_caller_asserted_explicit(item) for item in request.evidence):
        reasons.append(f"{reason}; caller-asserted explicit evidence is held for review")
        return WriteStatus.QUARANTINED
    reasons.append(reason)
    return WriteStatus.REJECTED


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
                expected_purpose=_expected_purpose(request),
            ):
                reasons.append(
                    "consent does not authorize this subject, namespace, class, or validity time"
                )
                status = WriteStatus.REJECTED
            elif not _has_explicit_evidence(request):
                status = _missing_explicit_evidence(
                    request,
                    f"{request.memory_class.value} memory requires explicit evidence",
                    reasons,
                )
            else:
                status = WriteStatus.ADMITTED
        elif (
            self.policy.identity_requires_explicit_evidence
            and request.memory_class is MemoryClass.IDENTITY
        ):
            if not _has_explicit_evidence(request):
                status = _missing_explicit_evidence(
                    request, "identity memory requires explicit evidence", reasons
                )
            else:
                status = WriteStatus.ADMITTED
        elif (
            self.policy.preference_requires_explicit_evidence
            and request.memory_class is MemoryClass.PREFERENCE
        ):
            if not _has_explicit_evidence(request):
                status = _missing_explicit_evidence(
                    request, "preference memory requires explicit evidence", reasons
                )
            else:
                status = WriteStatus.ADMITTED
        else:
            status = WriteStatus.ADMITTED

        if (
            normalization.unresolved_ambiguous
            and status is WriteStatus.ADMITTED
            and self.policy.quarantine_on_ambiguous_numeric
        ):
            # Receipts persist reasons and warnings, so they name a count and
            # never the token: a bare 9-digit run may be an SSN (ADR-080).
            count = len(normalization.unresolved_ambiguous)
            warnings.append(f"ambiguous numeric token redacted: {count}")
            reasons.append(
                f"{count} ambiguous numeric token(s) require a numeric_declarations entry"
            )
            status = WriteStatus.QUARANTINED
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
