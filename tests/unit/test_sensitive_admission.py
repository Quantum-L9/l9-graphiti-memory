"""Sensitive admission: ambiguous numbers, explicit evidence, and consent time."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from l9_graphite_memory import cli
from l9_graphite_memory.admission.engine import AdmissionEngine
from l9_graphite_memory.admission.normalization import normalize_candidate
from l9_graphite_memory.contracts import (
    QUARANTINE_REVIEW_POLICY_VERSION,
    AuthorizationAction,
    AuthorizationReceipt,
    Confidence,
    ConsentGrant,
    EvidenceKind,
    EvidenceRef,
    MemoryAssertion,
    MemoryClass,
    MemoryPrincipal,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
    QuarantineReviewPolicy,
    QuarantineReviewVerdict,
    QuarantineVerdict,
    WriteStatus,
)
from l9_graphite_memory.curation.quarantine import apply_policy
from l9_graphite_memory.mcp_tools import MCPToolApplication, tool_definitions


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


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolated sqlite runtime for local CLI invocations."""

    monkeypatch.setenv("L9_MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("L9_MEMORY_NAMESPACE", "repo-a")
    monkeypatch.setenv("L9_MEMORY_JSON_LOGS", "0")
    for name in ("L9_MEMORY_CONFIG", "GRAPHITI_GROUP_ID", "CURSOR_CONVERSATION_ID"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _run_cli(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _authorization() -> AuthorizationReceipt:
    return AuthorizationReceipt(
        principal_id="principal-1",
        action=AuthorizationAction.WRITE,
        namespace="ops",
        allowed=True,
    )


def test_an_undeclared_epoch_is_quarantined_redacted() -> None:
    # Superseded contract (b8043698): the token was stored raw and named in
    # the reasons. Receipts persist reasons, and a bare 9/10-digit run may be
    # an SSN, so the token is now redacted and never echoed (ADR-080).
    normalization = normalize_candidate("deploy finished at 1761573600")
    decision = AdmissionEngine().evaluate(
        _request(),
        normalization,
        _authorization(),
        duplicate_record_exists=False,
    )
    assert "1761573600" not in normalization.redacted_content
    assert "[AMBIGUOUS_NUMERIC_REDACTED]" in normalization.redacted_content
    assert "ambiguous_numeric" in normalization.pii_types
    assert decision.status is WriteStatus.QUARANTINED
    assert any("ambiguous numeric" in reason for reason in decision.reasons)
    assert not any("1761573600" in item for item in (*decision.reasons, *decision.warnings))


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
    # Discriminating: main rewrote every bare 10-digit run as a phone number.
    assert normalization.redacted_content == "deploy finished at 1761573600"
    assert normalization.pii_types == ()
    assert not any("PII" in warning for warning in decision.warnings)


def test_mcp_transport_is_not_explicit_evidence() -> None:
    app = MCPToolApplication(service=None)  # type: ignore[arg-type]
    request = app._write_request(
        _principal(),
        {"namespace": "ops", "content": "a note", "memory_class": "observation"},
        tool="memory.ingest",
    )
    assert all(item.kind is not EvidenceKind.EXPLICIT for item in request.evidence)
    assert request.evidence[-1].kind is EvidenceKind.OBSERVATION


def test_identity_without_caller_explicit_evidence_is_rejected(memory_service, principal) -> None:
    issued = datetime(2020, 1, 1, tzinfo=timezone.utc)
    consent = ConsentGrant(
        subject_id="ada",
        namespace="ops",
        allowed_classes=(MemoryClass.IDENTITY,),
        purpose="support",
        evidence=EvidenceRef(kind=EvidenceKind.OBSERVATION, description="caller text"),
        granted_at=issued,
    )
    normalization = normalize_candidate("Ada is the account owner")
    decision = AdmissionEngine().evaluate(
        _request(
            memory_class=MemoryClass.IDENTITY,
            content="Ada is the account owner",
            assertion=MemoryAssertion(subject="ada", predicate="is", object="account owner"),
            consent=consent,
            evidence=(EvidenceRef(kind=EvidenceKind.OBSERVATION, description="mcp transport"),),
        ),
        normalization,
        _authorization(),
        duplicate_record_exists=False,
    )
    assert decision.status is WriteStatus.REJECTED
    assert any("explicit evidence" in reason for reason in decision.reasons)

    # Discriminating: on main the MCP transport itself was recorded as
    # EXPLICIT evidence, so this consented identity write was admitted.
    receipt = MCPToolApplication(memory_service).call(
        principal,
        "memory.ingest",
        {
            "namespace": "repo-a",
            "content": "Ada is the account owner",
            "memory_class": "identity",
            "subject": "ada",
            "predicate": "is",
            "object": "account owner",
            "consent": {
                "subject_id": "ada",
                "purpose": "support",
                "evidence_description": "caller text",
                "granted_at": "2020-01-01T00:00:00+00:00",
            },
        },
    )
    assert receipt.status is WriteStatus.REJECTED
    assert receipt.record_id is None
    assert any("explicit evidence" in reason for reason in receipt.admission.reasons)


def test_identity_with_server_verified_explicit_evidence_and_past_consent_is_admitted(
    cli_env, capsys
) -> None:
    # Renamed from ..._with_caller_explicit_evidence_...: since the operator
    # decision of 2026-11-02 the server, never the caller, decides explicit
    # evidence. The EXPLICIT ref here is one the server itself constructs.
    issued = datetime(2020, 1, 1, tzinfo=timezone.utc)
    valid_from = datetime(2020, 6, 1, tzinfo=timezone.utc)
    consent = ConsentGrant(
        subject_id="ada",
        namespace="ops",
        allowed_classes=(MemoryClass.IDENTITY,),
        purpose="support",
        evidence=EvidenceRef(kind=EvidenceKind.OBSERVATION, description="record of consent"),
        granted_at=issued,
        expires_at=datetime(2021, 1, 1, tzinfo=timezone.utc),
    )
    normalization = normalize_candidate("Ada is the account owner")
    decision = AdmissionEngine().evaluate(
        _request(
            memory_class=MemoryClass.IDENTITY,
            content="Ada is the account owner",
            assertion=MemoryAssertion(subject="ada", predicate="is", object="account owner"),
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

    # Discriminating: the local operator CLI is a server-verified path (it
    # constructs EXPLICIT evidence itself); main had no way to state when a
    # consent was granted, so a past-valid identity fact could not be consented.
    code, receipt = _run_cli(
        capsys,
        [
            "write",
            "Ada is the account owner",
            "--kind",
            "identity",
            "--subject",
            "ada",
            "--predicate",
            "is",
            "--object",
            "account owner",
            "--valid-from",
            "2020-06-01T00:00:00+00:00",
            "--consent-subject-id",
            "ada",
            "--consent-purpose",
            "support",
            "--consent-evidence",
            "signed consent form 2020-01-01",
            "--consent-granted-at",
            "2020-01-01T00:00:00+00:00",
            "--consent-expires-at",
            "2021-01-01T00:00:00+00:00",
        ],
    )
    assert code == 0
    assert receipt["status"] == "admitted"
    assert receipt["record_id"]


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

    # Discriminating: the purpose a write declares is bound into the consent
    # check, so a revoked or wrong-purpose grant rejects the write. Main
    # ignored the declared purpose and admitted the wrong-purpose write.
    def evaluate(at: datetime, purpose: str) -> WriteStatus:
        return (
            AdmissionEngine()
            .evaluate(
                _request(
                    memory_class=MemoryClass.PREFERENCE,
                    content="Ada prefers the window seat",
                    assertion=MemoryAssertion(subject="ada", predicate="prefers", object="window"),
                    consent=consent,
                    valid_from=at,
                    metadata={"purpose": purpose},
                    evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="signed form"),),
                ),
                normalize_candidate("Ada prefers the window seat"),
                _authorization(),
                duplicate_record_exists=False,
            )
            .status
        )

    assert evaluate(issued + timedelta(days=5), "support") is WriteStatus.ADMITTED
    assert evaluate(issued + timedelta(days=5), "marketing") is WriteStatus.REJECTED
    assert evaluate(issued + timedelta(days=11), "support") is WriteStatus.REJECTED


# ---------------------------------------------------------------------------
# numeric_declarations reach admission through MCP (T4)
# ---------------------------------------------------------------------------


def _ingest_schema() -> dict[str, Any]:
    return next(item for item in tool_definitions() if item["name"] == "memory.ingest")[
        "inputSchema"
    ]


def test_mcp_declared_epoch_is_admitted_and_undeclared_is_quarantined_redacted(
    memory_service, principal
) -> None:
    app = MCPToolApplication(memory_service)
    declared_args = {
        "namespace": "repo-a",
        "content": "deploy finished at 1761573600",
        "numeric_declarations": {"1761573600": "epoch"},
    }
    declared = app.call(principal, "memory.ingest", declared_args)
    assert declared.status is WriteStatus.ADMITTED
    record = memory_service.store.get_record(declared.record_id)
    assert record is not None
    assert record.state is MemoryState.ACTIVE
    assert record.content == "deploy finished at 1761573600"
    assert "numeric_declarations" not in record.metadata

    undeclared = app.call(
        principal,
        "memory.ingest",
        {"namespace": "repo-a", "content": "ssn on file 123456789"},
    )
    assert undeclared.status is WriteStatus.QUARANTINED
    held = memory_service.store.get_record(undeclared.record_id)
    assert held is not None
    assert held.state is MemoryState.QUARANTINED
    assert "123456789" not in held.content
    assert "ambiguous_numeric" in held.metadata["pii_types"]
    assert "123456789" not in json.dumps(undeclared.model_dump(mode="json"))
    # The published input schema admits the declaration a schema-checking
    # client sends.
    jsonschema.validate(declared_args, _ingest_schema())


def test_mcp_declared_ssn_is_never_persisted_in_metadata(memory_service, principal) -> None:
    receipt = MCPToolApplication(memory_service).call(
        principal,
        "memory.ingest",
        {
            "namespace": "repo-a",
            "content": "ssn on file 123456789",
            "numeric_declarations": {"123456789": "ssn"},
        },
    )
    record = memory_service.store.get_record(receipt.record_id)
    assert record is not None
    assert record.content == "ssn on file [SSN_REDACTED]"
    assert "123456789" not in json.dumps(record.model_dump(mode="json"))


def test_numeric_declarations_reject_a_malformed_token_or_kind(memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    for declarations in ({"12345": "epoch"}, {"1761573600": "timestamp"}):
        args = {"namespace": "repo-a", "content": "x", "numeric_declarations": declarations}
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(args, _ingest_schema())
        with pytest.raises(ValueError, match="numeric_declarations"):
            app.call(principal, "memory.ingest", args)


# ---------------------------------------------------------------------------
# consent producer and consumer agree (T5)
# ---------------------------------------------------------------------------


class _InProcessRemote:
    """A remote client that validates against the published schema, then serves."""

    def __init__(self, service: Any, principal: MemoryPrincipal) -> None:
        self.app = MCPToolApplication(service)
        self.principal = principal
        self.sent: list[dict[str, Any]] = []
        self.receipts: list[Any] = []

    def ingest(self, arguments: dict[str, Any]) -> Any:
        jsonschema.validate(arguments, _ingest_schema())
        self.sent.append(arguments)
        receipt = self.app.call(self.principal, "memory.ingest", arguments)
        self.receipts.append(receipt)
        return receipt


def test_remote_cli_write_with_consent_passes_schema_and_handler(
    memory_service, principal, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("L9_MEMORY_NAMESPACE", "repo-a")
    monkeypatch.delenv("L9_MEMORY_CONFIG", raising=False)
    args = cli.build_parser().parse_args(
        [
            "write",
            "Ada prefers the window seat",
            "--kind",
            "preference",
            "--group-id",
            "repo-a",
            "--consent-subject-id",
            "ada",
            "--consent-purpose",
            "support",
            "--consent-evidence",
            "ada asked in ticket 7",
            "--consent-granted-at",
            "2020-01-01T00:00:00+00:00",
            "--valid-from",
            "2020-06-01T00:00:00+00:00",
        ]
    )
    client = _InProcessRemote(memory_service, principal)
    code = cli._remote_write(args, client)  # type: ignore[arg-type]
    capsys.readouterr()
    assert client.sent[0]["consent"]["granted_at"] == "2020-01-01T00:00:00+00:00"
    # The schema and the handler both accepted the consent, and it permits
    # the past-valid fact; the write is refused only for want of explicit
    # evidence, which no remote caller can supply (T6).
    receipt = client.receipts[0]
    assert code == 2
    assert receipt.status is WriteStatus.REJECTED
    assert receipt.admission.reasons == ("preference memory requires explicit evidence",)


def test_remote_cli_consent_without_granted_at_defaults_to_the_invocation(
    memory_service, principal, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("L9_MEMORY_NAMESPACE", "repo-a")
    args = cli.build_parser().parse_args(
        [
            "write",
            "Ada prefers the window seat",
            "--kind",
            "preference",
            "--group-id",
            "repo-a",
            "--consent-subject-id",
            "ada",
            "--consent-purpose",
            "support",
            "--consent-evidence",
            "ada asked in ticket 7",
        ]
    )
    client = _InProcessRemote(memory_service, principal)
    cli._remote_write(args, client)  # type: ignore[arg-type]
    capsys.readouterr()
    sent = client.sent[0]
    assert sent["consent"]["granted_at"] == sent["valid_from"]


# ---------------------------------------------------------------------------
# explicit evidence is server-decided, never caller-decided (T6)
# ---------------------------------------------------------------------------


def _confident_release(record: Any) -> QuarantineReviewVerdict:
    """What the policy makes of a reviewer that confidently says RELEASE."""

    return apply_policy(
        QuarantineReviewVerdict(
            record_id=record.record_id,
            verdict=QuarantineVerdict.RELEASE,
            confidence=0.99,
            reasons=("looks fine",),
            reviewer="unit",
            policy_version=QUARANTINE_REVIEW_POLICY_VERSION,
        ),
        record,
        QuarantineReviewPolicy(),
    )


def _caller_explicit_preference(**overrides: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "namespace": "repo-a",
        "content": "Ada prefers the window seat",
        "memory_class": "preference",
        "subject": "ada",
        "predicate": "prefers",
        "object": "window seat",
        "valid_from": "2020-06-01T00:00:00+00:00",
        "evidence": [{"kind": "explicit", "description": "user said so", "source_id": "chat-1"}],
        "consent": {
            "subject_id": "ada",
            "purpose": "support",
            "evidence_description": "user said so",
            "granted_at": "2020-01-01T00:00:00+00:00",
        },
    }
    args.update(overrides)
    return args


def test_caller_explicit_evidence_with_backdated_consent_is_quarantined_not_admitted(
    memory_service, principal
) -> None:
    args = _caller_explicit_preference()
    receipt = MCPToolApplication(memory_service).call(principal, "memory.ingest", args)
    assert receipt.status is WriteStatus.QUARANTINED
    assert any("caller-asserted" in reason for reason in receipt.admission.reasons)
    record = memory_service.store.get_record(receipt.record_id)
    assert record is not None
    assert record.state is MemoryState.QUARANTINED
    assert all(item.kind is not EvidenceKind.EXPLICIT for item in record.evidence)
    claimed = [item for item in record.evidence if "caller-asserted" in item.description]
    assert len(claimed) == 1
    assert claimed[0].kind is EvidenceKind.OBSERVATION
    assert claimed[0].source_id == "chat-1"
    assert "user said so" in claimed[0].description

    # Automated review can never release it: only a person may.
    judged = _confident_release(record)
    assert judged.verdict is QuarantineVerdict.ESCALATE
    assert any("caller-asserted" in item for item in judged.blockers)
    # The evidence a caller sends is a declared input, not an extra property.
    jsonschema.validate(args, _ingest_schema())


def test_mcp_explicit_claim_on_a_non_sensitive_class_is_admitted_as_observation(
    memory_service, principal
) -> None:
    receipt = MCPToolApplication(memory_service).call(
        principal,
        "memory.ingest",
        {
            "namespace": "repo-a",
            "content": "the deploy finished",
            "evidence": [{"kind": "explicit", "description": "ci log"}],
        },
    )
    assert receipt.status is WriteStatus.ADMITTED
    record = memory_service.store.get_record(receipt.record_id)
    assert record is not None
    assert all(item.kind is not EvidenceKind.EXPLICIT for item in record.evidence)


def test_an_ambiguous_numeric_record_cannot_be_released_automatically(
    memory_service, principal
) -> None:
    receipt = MCPToolApplication(memory_service).call(
        principal, "memory.ingest", {"namespace": "repo-a", "content": "ssn 123456789"}
    )
    record = memory_service.store.get_record(receipt.record_id)
    assert record is not None and record.state is MemoryState.QUARANTINED
    judged = _confident_release(record)
    assert judged.verdict is QuarantineVerdict.ESCALATE
    assert any("ambiguous_numeric" in item for item in judged.blockers)
