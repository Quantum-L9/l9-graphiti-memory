"""Sensitive admission: ambiguous numbers, explicit evidence, and consent time."""

from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.admission.engine import AdmissionEngine
from l9_graphite_memory.admission.normalization import normalize_candidate
from l9_graphite_memory.contracts import (
    AuthorizationAction,
    AuthorizationReceipt,
    Confidence,
    ConsentGrant,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemoryWriteRequest,
    Provenance,
    WriteStatus,
)
from l9_graphite_memory.mcp_tools import MCPToolApplication


def _principal() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="principal-1",
        tenant_id="tenant-1",
        agent_id="agent-1",
        write_namespaces=("ops",),
    )


def _request(**overrides: object) -> MemoryWriteRequest:
    payload = {
        "namespace": "ops",
        "memory_class": MemoryClass.OBSERVATION,
        "content": "deploy finished at 1761573600",
        "provenance": Provenance(source="test", tool="unit"),
        "evidence": (EvidenceRef(kind=EvidenceKind.OBSERVATION, description="unit observation"),),
        "confidence": Confidence(score=1.0, evidence_count=1),
        "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    payload.update(overrides)
    return MemoryWriteRequest(**payload)


def _authorization() -> AuthorizationReceipt:
    return AuthorizationReceipt(
        principal_id="principal-1",
        action=AuthorizationAction.WRITE,
        namespace="ops",
        allowed=True,
    )


def test_an_undeclared_epoch_is_quarantined_without_being_rewritten() -> None:
    normalization = normalize_candidate("deploy finished at 1761573600")
    decision = AdmissionEngine().evaluate(
        _request(),
        normalization,
        _authorization(),
        duplicate_record_exists=False,
    )
    assert "1761573600" in normalization.redacted_content
    assert decision.status is WriteStatus.QUARANTINED
    assert any("1761573600" in reason for reason in decision.reasons)


def test_a_declared_epoch_is_admitted() -> None:
    normalization = normalize_candidate(
        "deploy finished at 1761573600",
        context={"numeric_declarations": {"1761573600": "epoch"}},
    )
    decision = AdmissionEngine().evaluate(
        _request(),
        normalization,
        _authorization(),
        duplicate_record_exists=False,
    )
    assert decision.status is WriteStatus.ADMITTED


def test_mcp_transport_is_not_explicit_evidence() -> None:
    app = MCPToolApplication(service=None)  # type: ignore[arg-type]
    request = app._write_request(
        _principal(),
        {"namespace": "ops", "content": "a note", "memory_class": "observation"},
        tool="memory.ingest",
    )
    assert all(item.kind is not EvidenceKind.EXPLICIT for item in request.evidence)
    assert request.evidence[-1].kind is EvidenceKind.OBSERVATION


def test_identity_without_caller_explicit_evidence_is_rejected() -> None:
    issued = datetime(2020, 1, 1, tzinfo=timezone.utc)
    consent = ConsentGrant(
        subject_id="ada",
        namespace="ops",
        purpose="support",
        evidence=EvidenceRef(kind=EvidenceKind.OBSERVATION, description="caller text"),
        granted_at=issued,
    )
    normalization = normalize_candidate("Ada prefers the window seat")
    decision = AdmissionEngine().evaluate(
        _request(
            memory_class=MemoryClass.PREFERENCE,
            content="Ada prefers the window seat",
            assertion=None,
            consent=consent,
            evidence=(EvidenceRef(kind=EvidenceKind.OBSERVATION, description="mcp transport"),),
        ),
        normalization,
        _authorization(),
        duplicate_record_exists=False,
    )
    assert decision.status is WriteStatus.REJECTED
    assert any("explicit evidence" in reason for reason in decision.reasons)


def test_identity_with_caller_explicit_evidence_and_past_consent_is_admitted() -> None:
    issued = datetime(2020, 1, 1, tzinfo=timezone.utc)
    valid_from = datetime(2020, 6, 1, tzinfo=timezone.utc)
    consent = ConsentGrant(
        subject_id="ada",
        namespace="ops",
        purpose="support",
        evidence=EvidenceRef(kind=EvidenceKind.OBSERVATION, description="record of consent"),
        granted_at=issued,
        expires_at=datetime(2021, 1, 1, tzinfo=timezone.utc),
    )
    normalization = normalize_candidate("Ada prefers the window seat")
    decision = AdmissionEngine().evaluate(
        _request(
            memory_class=MemoryClass.PREFERENCE,
            content="Ada prefers the window seat",
            consent=consent,
            valid_from=valid_from,
            evidence=(
                EvidenceRef(
                    kind=EvidenceKind.EXPLICIT,
                    description="signed consent form 2020-01-01",
                    source_id="consent-form-19",
                ),
            ),
        ),
        normalization,
        _authorization(),
        duplicate_record_exists=False,
    )
    assert decision.status is WriteStatus.ADMITTED


def test_consent_rejects_the_wrong_subject_purpose_and_expired_time() -> None:
    issued = datetime(2020, 1, 1, tzinfo=timezone.utc)
    consent = ConsentGrant(
        subject_id="ada",
        namespace="ops",
        purpose="support",
        evidence=EvidenceRef(kind=EvidenceKind.OBSERVATION, description="record"),
        granted_at=issued,
        expires_at=datetime(2020, 2, 1, tzinfo=timezone.utc),
    )
    assert consent.permits(
        "ops",
        MemoryClass.PREFERENCE,
        at=datetime(2020, 1, 15, tzinfo=timezone.utc),
        subject_id="ada",
        expected_purpose="support",
    )
    assert not consent.permits(
        "ops",
        MemoryClass.PREFERENCE,
        at=datetime(2020, 1, 15, tzinfo=timezone.utc),
        subject_id="grace",
    )
    assert not consent.permits(
        "ops",
        MemoryClass.PREFERENCE,
        at=datetime(2020, 1, 15, tzinfo=timezone.utc),
        subject_id="ada",
        expected_purpose="marketing",
    )
    assert not consent.permits(
        "ops",
        MemoryClass.PREFERENCE,
        at=datetime(2020, 3, 1, tzinfo=timezone.utc),
        subject_id="ada",
    )


def test_mcp_consent_requires_an_issued_time_and_honors_a_past_one() -> None:
    from l9_graphite_memory.mcp_tools import _consent_from_payload

    with pytest.raises(ValueError, match="granted_at"):
        _consent_from_payload(
            {
                "subject_id": "ada",
                "purpose": "support",
                "evidence_description": "form",
            },
            namespace="ops",
            memory_class=MemoryClass.PREFERENCE,
            principal=_principal(),
        )
    consent = _consent_from_payload(
        {
            "subject_id": "ada",
            "purpose": "support",
            "evidence_description": "form",
            "granted_at": "2020-01-01T00:00:00+00:00",
            "expires_at": "2021-01-01T00:00:00+00:00",
        },
        namespace="ops",
        memory_class=MemoryClass.PREFERENCE,
        principal=_principal(),
    )
    assert consent is not None
    assert consent.evidence.kind is EvidenceKind.OBSERVATION
    assert consent.permits(
        "ops",
        MemoryClass.PREFERENCE,
        at=datetime(2020, 6, 1, tzinfo=timezone.utc),
        subject_id="ada",
    )


def test_revoked_consent_does_not_permit() -> None:
    issued = datetime(2020, 1, 1, tzinfo=timezone.utc)
    consent = ConsentGrant(
        subject_id="ada",
        namespace="ops",
        purpose="support",
        evidence=EvidenceRef(kind=EvidenceKind.OBSERVATION, description="record"),
        granted_at=issued,
        revoked_at=issued + timedelta(days=10),
    )
    assert not consent.permits(
        "ops",
        MemoryClass.PREFERENCE,
        at=issued + timedelta(days=11),
        subject_id="ada",
    )
