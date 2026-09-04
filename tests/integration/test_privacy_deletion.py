# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_privacy_deletion.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore
from l9_graphite_memory.authz import NamespacePolicy
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    ConsentGrant,
    DeletionRequest,
    DeletionStatus,
    EvidenceKind,
    EvidenceRef,
    MemoryAssertion,
    MemoryClass,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.ports import ProjectionHit
from l9_graphite_memory.services import MemoryService, OutboxWorker


def _consent(*, revoked: bool = False) -> ConsentGrant:
    now = datetime.now(timezone.utc)
    return ConsentGrant(
        subject_id="user-1",
        namespace="repo-a",
        purpose="remember communication preferences",
        evidence=EvidenceRef(
            kind=EvidenceKind.EXPLICIT,
            description="user granted consent",
            source_id="consent-form-1",
        ),
        granted_at=now - timedelta(minutes=1),
        revoked_at=now if revoked else None,
    )


def _preference_request(consent: ConsentGrant | None) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        namespace="repo-a",
        memory_class=MemoryClass.PREFERENCE,
        content="user-1 prefers concise answers",
        assertion=MemoryAssertion(
            subject="user-1",
            predicate="prefers:communication",
            object="concise answers",
        ),
        provenance=Provenance(source="test"),
        evidence=(
            EvidenceRef(
                kind=EvidenceKind.EXPLICIT,
                description="explicit preference",
                source_id="message-1",
            ),
        ),
        consent=consent,
    )


def test_sensitive_memory_requires_current_purpose_bound_consent(memory_service, principal) -> None:
    missing = memory_service.write(principal, _preference_request(None))
    revoked = memory_service.write(principal, _preference_request(_consent(revoked=True)))
    admitted = memory_service.write(principal, _preference_request(_consent()))

    assert missing.status.value == "rejected"
    assert revoked.status.value == "rejected"
    assert admitted.record_id is not None
    record = memory_service.get(principal, admitted.record_id)
    assert record is not None
    assert record.consent is not None


def test_verified_deletion_redacts_canonical_record_without_projection(
    memory_service,
    principal,
    admin_principal,
) -> None:
    write = memory_service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            content="sensitive memory",
            provenance=Provenance(source="test"),
        ),
    )

    receipt = memory_service.delete(
        admin_principal,
        DeletionRequest(
            record_id=write.record_id,
            reason="verified subject deletion request",
            verification_reference="ticket-123",
        ),
    )

    assert receipt.status is DeletionStatus.COMPLETE
    with pytest.raises(AuthorizationError):
        memory_service.get(principal, write.record_id)
    tombstone = memory_service.get(admin_principal, write.record_id)
    assert tombstone is not None
    assert tombstone.state is MemoryState.DELETED
    assert "sensitive memory" not in tombstone.content
    assert tombstone.evidence == ()
    assert tombstone.consent is None


class ErasingProjection:
    name = "test-projection"
    capabilities = ("semantic-search",)

    def __init__(self) -> None:
        self.erased: list[tuple[str, str]] = []

    def health(self) -> dict[str, object]:
        return {"healthy": True}

    def project(self, record) -> dict[str, object]:
        return {"projected": True, "locator": f"episode-{record.record_id}"}

    def erase(
        self,
        record_id,
        namespace: str,
        *,
        locator: str | None = None,
    ) -> dict[str, object]:
        assert locator == f"episode-{record_id}"
        self.erased.append((str(record_id), namespace))
        return {"erased": True, "locator": locator}

    def search(
        self, _query: str, _namespaces: tuple[str, ...], *, limit: int
    ) -> list[ProjectionHit]:
        return []


def test_projection_deletion_completes_through_outbox(tmp_path, principal, admin_principal) -> None:
    store = InMemoryRecordStore()
    projection = ErasingProjection()
    service = MemoryService(store, projection, namespace_policy=NamespacePolicy())
    service.initialize()
    write = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            content="projected sensitive memory",
            provenance=Provenance(source="test"),
        ),
    )
    worker = OutboxWorker(
        store,
        projection,
        MemorySettings(data_dir=tmp_path / "data", state_dir=tmp_path / "state"),
    )
    assert worker.run_once()["delivered"] == 1  # the record is projected while active
    assert store.get_projection_link(write.record_id, projection.name) is not None

    deletion = service.delete(
        admin_principal,
        DeletionRequest(
            record_id=write.record_id,
            reason="verified deletion",
            verification_reference="ticket-456",
        ),
    )

    assert deletion.status is DeletionStatus.PENDING_PROJECTION
    pending = service.get(admin_principal, write.record_id)
    assert pending is not None and pending.state is MemoryState.DELETION_PENDING

    result = worker.run_once()

    assert result["delivered"] == 1  # the erasure
    deleted = service.get(admin_principal, write.record_id)
    assert deleted is not None and deleted.state is MemoryState.DELETED
    assert projection.erased == [(str(write.record_id), "repo-a")]
    assert store.get_projection_link(write.record_id, projection.name) is None
    # The lifecycle ledger records both halves of the deletion (ADR-024).
    ledger = [
        (event.previous_state, event.new_state)
        for event in store.status_events
        if event.record_id == write.record_id
    ]
    assert ledger == [
        (None, MemoryState.ACTIVE),
        (MemoryState.ACTIVE, MemoryState.DELETION_PENDING),
        (MemoryState.DELETION_PENDING, MemoryState.DELETED),
    ]
