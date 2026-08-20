# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_projection_lifecycle.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SP-08 / SP-09: projection retirement is atomic and is not privacy erasure."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    DeletionRequest,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryState,
    MemoryWriteRequest,
    OutboxStatus,
    Provenance,
)
from l9_graphite_memory.errors import StoreError
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker


class LifecycleProjection:
    """Projection that records which lifecycle operation it was asked for."""

    name = "lifecycle"
    capabilities: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.projected: list[UUID] = []
        self.retired: list[tuple[UUID, str]] = []
        self.erased: list[UUID] = []

    def health(self) -> dict[str, object]:
        return {"healthy": True}

    def project(self, record) -> dict[str, object]:
        self.projected.append(record.record_id)
        return {"locator": f"episode-{record.record_id}"}

    def retire(self, record_id, namespace, *, locator=None, reason="") -> dict[str, object]:
        self.retired.append((record_id, reason))
        return {"retired": True, "erased": False, "locator": locator}

    def erase(self, record_id, namespace, *, locator=None) -> dict[str, object]:
        self.erased.append(record_id)
        return {"erased": True, "locator": locator}

    def search_strategy(self, strategy, query, namespaces, *, limit):
        return []

    def search(self, query, namespaces, *, limit):
        return []


@pytest.fixture
def projection() -> LifecycleProjection:
    return LifecycleProjection()


@pytest.fixture
def store() -> InMemoryRecordStore:
    return InMemoryRecordStore()


@pytest.fixture
def service(store, projection) -> MemoryService:
    service = MemoryService(store, projection)
    service.initialize()
    return service


@pytest.fixture
def worker(store, projection) -> OutboxWorker:
    return OutboxWorker(store, projection, MemorySettings(), worker_id="test-worker")


def _write(service, principal, content: str, **kwargs):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=kwargs.pop("memory_class", MemoryClass.OBSERVATION),
            content=content,
            provenance=Provenance(source="lifecycle-test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
            **kwargs,
        ),
    )


def _drain(worker) -> dict[str, int]:
    totals = {"delivered": 0, "retried": 0, "dead": 0}
    for _ in range(5):
        result = worker.run_once()
        for key in totals:
            totals[key] += result[key]
        if result["claimed"] == 0:
            break
    return totals


def test_supersession_atomically_emits_canonical_transition_and_retirement(
    service, store, principal
) -> None:
    """SP-08: the canonical transition and the retirement intent share a commit."""

    original = _write(service, principal, "the pipeline runs on ubuntu-20.04")
    replacement = _write(
        service,
        principal,
        "the pipeline runs on ubuntu-latest",
        supersedes=(original.record_id,),
    )

    assert replacement.superseded_record_ids == (original.record_id,)
    assert store.records[original.record_id].state is MemoryState.SUPERSEDED

    retire_events = [
        event
        for event in store.outbox.values()
        if event.event_type == "memory.record.retire"
    ]
    assert len(retire_events) == 1
    assert retire_events[0].aggregate_id == original.record_id
    assert str(replacement.record_id) in retire_events[0].payload["superseded_by"]


def test_supersession_retirement_is_rolled_back_with_the_transition(
    service, store, principal, monkeypatch
) -> None:
    """SP-08: a failed commit leaves neither the transition nor the intent."""

    original = _write(service, principal, "first observation")
    outbox_before = set(store.outbox)

    def fail_commit(*_args, **_kwargs):
        raise StoreError("canonical store unavailable")

    monkeypatch.setattr(store, "commit_write", fail_commit)

    with pytest.raises(StoreError):
        _write(
            service,
            principal,
            "second observation",
            supersedes=(original.record_id,),
        )

    assert store.records[original.record_id].state is MemoryState.ACTIVE
    assert set(store.outbox) == outbox_before


def test_worker_retires_the_superseded_projection(
    service, store, projection, worker, principal
) -> None:
    original = _write(service, principal, "original truth")
    _drain(worker)
    assert projection.projected == [original.record_id]
    assert store.get_projection_link(original.record_id, "lifecycle") is not None

    replacement = _write(
        service, principal, "revised truth", supersedes=(original.record_id,)
    )
    _drain(worker)

    retired_ids = [record_id for record_id, _ in projection.retired]
    assert retired_ids == [original.record_id]
    assert projection.erased == []
    # The stale projection no longer resolves, so retrieval cannot surface it.
    assert store.get_projection_link(original.record_id, "lifecycle") is None
    # The replacement is projected and stays projected.
    assert store.get_projection_link(replacement.record_id, "lifecycle") is not None


def test_archive_retires_without_invoking_erasure(
    service, store, projection, worker, admin_principal, principal
) -> None:
    """SP-09: retention retires the projection and preserves canonical content."""

    now = datetime.now(timezone.utc)
    written = _write(
        service,
        principal,
        "expired but historically true",
        valid_from=now - timedelta(days=2),
        valid_to=now - timedelta(days=1),
    )
    _drain(worker)
    assert store.get_projection_link(written.record_id, "lifecycle") is not None

    receipt = service.apply_retention(admin_principal, "repo-a", apply=True)
    assert receipt.archive_receipt.archived_record_ids == (written.record_id,)

    _drain(worker)

    # Retirement happened.
    assert [record_id for record_id, _ in projection.retired] == [written.record_id]
    assert store.get_projection_link(written.record_id, "lifecycle") is None

    # Erasure did not.
    assert projection.erased == []
    record = store.records[written.record_id]
    assert record.state is MemoryState.ARCHIVED
    assert record.content == "expired but historically true"
    assert record.evidence
    assert store.deletion_receipts == {}
    assert "tombstone_id" not in record.metadata


def test_privacy_deletion_still_erases_rather_than_retires(
    service, store, projection, worker, admin_principal, principal
) -> None:
    """The two paths stay distinct: deletion erases and tombstones."""

    written = _write(service, principal, "delete this content")
    _drain(worker)

    service.delete(
        admin_principal,
        DeletionRequest(
            record_id=written.record_id,
            reason="verified deletion",
            verification_reference="ticket-1",
        ),
    )
    _drain(worker)

    assert projection.erased == [written.record_id]
    assert [record_id for record_id, _ in projection.retired] == []
    record = store.records[written.record_id]
    assert record.state is MemoryState.DELETED
    assert "delete this content" not in record.content
    assert store.deletion_receipts


def test_retirement_of_an_unprojected_record_is_satisfied(
    service, store, projection, worker, principal
) -> None:
    """A record with no projection link has nothing to withdraw.

    Retirement must succeed rather than dead-letter: the desired end state --
    no live projection for this record -- already holds.
    """

    original = _write(service, principal, "never projected")
    replacement = _write(
        service, principal, "replacement", supersedes=(original.record_id,)
    )

    # Drop the project event so the original is never projected, leaving the
    # retire event to run against a record that has no link.
    for event_id, event in list(store.outbox.items()):
        if (
            event.event_type == "memory.record.project"
            and event.aggregate_id == original.record_id
        ):
            del store.outbox[event_id]

    _drain(worker)

    assert projection.retired == []
    assert projection.erased == []
    assert projection.projected == [replacement.record_id]
    # The retirement is settled, not dead-lettered or endlessly retried.
    assert [
        event.status
        for event in store.outbox.values()
        if event.event_type == "memory.record.retire"
    ] == [OutboxStatus.DELIVERED]
