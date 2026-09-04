# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/record_store.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Canonical record-store protocol."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from l9_graphite_memory.contracts import (
    ArchiveReceipt,
    ConflictLinkReceipt,
    DeletionReceipt,
    LifecycleTransitionReceipt,
    MaintenanceRunReceipt,
    MemoryRecord,
    MemorySearchRequest,
    MemoryState,
    MemoryStatusEvent,
    OutboxEvent,
    OutboxStatus,
    PhaseLockReceipt,
    ProjectionLink,
    ProjectionRebuildReceipt,
    ProjectionRetirementReceipt,
    WriteReceipt,
)

from .phase_lock import PhaseLockPrecondition
from .service_capability import ServiceWriteCapability


class RecordStore(Protocol):
    name: str

    def initialize(self) -> None: ...

    def close(self) -> None: ...

    def health(self) -> dict[str, Any]: ...

    def commit_write(
        self,
        capability: ServiceWriteCapability,
        record: MemoryRecord | None,
        receipt: WriteReceipt,
        *,
        outbox_events: tuple[OutboxEvent, ...] = (),
        status_events: tuple[MemoryStatusEvent, ...] = (),
        expected_phase_lock: PhaseLockPrecondition | None = None,
    ) -> None:
        """Commit one canonical write atomically.

        When ``expected_phase_lock`` is supplied the implementation must
        re-verify its ``expected_snapshot_digest`` against the namespace's live
        active records *inside* the committing transaction, and raise
        ``PhaseLockSnapshotConflict`` when it no longer matches. Verifying
        before the transaction is not sufficient: a concurrent writer sharing
        the store can change the namespace in between (ADR-079).

        When the record's ``(tenant_id, namespace, idempotency_key)`` is already
        held by another record the implementation must raise
        ``IdempotencyConflict`` and leave nothing behind, so the service can
        resolve the race into a DUPLICATE receipt (ADR-008).
        """
        ...

    def get_record(self, record_id: UUID) -> MemoryRecord | None: ...

    def find_by_idempotency(
        self,
        tenant_id: str,
        namespace: str,
        idempotency_key: str,
    ) -> MemoryRecord | None: ...

    def search_records(
        self,
        tenant_id: str,
        request: MemorySearchRequest,
        namespaces: tuple[str, ...],
    ) -> list[MemoryRecord]: ...

    def list_records(
        self,
        tenant_id: str,
        namespace: str,
        *,
        states: tuple[MemoryState, ...] = (),
        limit: int | None = 1_000,
    ) -> list[MemoryRecord]:
        """Most-recent-first records in one namespace.

        ``limit=None`` returns every matching record. The phase-lock snapshot
        digest is computed over the complete active set, so the service must be
        able to read the same set the store re-verifies in-transaction; a
        bounded listing there would make the two digests disagree (ADR-079).
        """

    def transition_state(
        self, capability: ServiceWriteCapability, event: MemoryStatusEvent
    ) -> None:
        """Append one lifecycle event and move the record between states.

        A canonical mutation like the commit methods, so it carries the
        service-issued capability (ADR-036). Production callers go through
        ``MemoryService.transition_lifecycle`` so the transition commits with
        its receipt and projection intent; this single-event primitive exists
        for the adapters' own composition and for conformance work.
        """

    def commit_lifecycle(
        self,
        capability: ServiceWriteCapability,
        receipt: LifecycleTransitionReceipt,
        *,
        status_events: tuple[MemoryStatusEvent, ...],
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        """Atomically record governed lifecycle transitions.

        The receipt, every status event, and the projection intent the
        transitions imply (retire on SUPERSEDED/ARCHIVED, project on
        reactivation) commit together or not at all, so the projection can
        never disagree with canonical state about what is current (ADR-074).
        """

    def save_phase_lock(
        self, capability: ServiceWriteCapability, receipt: PhaseLockReceipt
    ) -> None: ...

    def get_phase_lock(
        self, tenant_id: str, namespace: str, task_signature: str
    ) -> PhaseLockReceipt | None: ...

    def claim_outbox(
        self,
        *,
        limit: int,
        now: datetime,
        lease_seconds: int = 300,
        lease_owner: str = "outbox-worker",
    ) -> list[OutboxEvent]:
        """Lease due events, including any whose prior lease has expired."""
        ...

    def update_outbox(
        self,
        event_id: UUID,
        *,
        status: OutboxStatus,
        attempts: int,
        next_attempt_at: datetime,
        last_error: str | None,
        delivered_at: datetime | None = None,
        lease_id: UUID | None = None,
    ) -> None:
        """Settle a leased event. A non-matching ``lease_id`` must be rejected."""
        ...

    def outbox_backlog(self) -> int: ...

    def save_projection_link(self, link: ProjectionLink) -> None: ...

    def get_projection_link(
        self,
        record_id: UUID,
        projection_name: str,
    ) -> ProjectionLink | None: ...

    def delete_projection_link(self, record_id: UUID, projection_name: str) -> None: ...

    def save_projection_retirement(self, receipt: ProjectionRetirementReceipt) -> None:
        """Record that a projection was withdrawn, and why, in canonical state."""
        ...

    def list_unprojected_records(
        self,
        tenant_id: str,
        namespace: str,
        projection_name: str,
        *,
        limit: int = 1_000,
    ) -> list[MemoryRecord]:
        """Active records with no live projection link for this provider."""
        ...

    def commit_projection_rebuild(
        self,
        capability: ServiceWriteCapability,
        receipt: ProjectionRebuildReceipt,
        *,
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        """Atomically record a rebuild and enqueue its projection events.

        A canonical mutation, so it requires the service-issued capability
        like the other four (ADR-036).
        """
        ...

    def stats(self) -> dict[str, Any]: ...

    def save_maintenance_run(self, receipt: MaintenanceRunReceipt) -> None:
        """Append one maintenance run to the ledger."""
        ...

    def get_maintenance_watermark(self, tenant_id: str, namespace: str) -> datetime | None:
        """Watermark of the most recent applied run, or None if never run."""
        ...

    def find_maintenance_action_digests(self, tenant_id: str, namespace: str) -> frozenset[str]:
        """Digests of actions already applied, so a rerun does not repeat them."""
        ...

    def list_expired(
        self,
        tenant_id: str,
        namespace: str,
        *,
        before: datetime,
    ) -> list[MemoryRecord]: ...

    def commit_archive(
        self,
        capability: ServiceWriteCapability,
        receipt: ArchiveReceipt,
        *,
        status_events: tuple[MemoryStatusEvent, ...],
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None: ...

    def commit_conflict_links(
        self,
        capability: ServiceWriteCapability,
        receipt: ConflictLinkReceipt,
    ) -> None:
        """Atomically record that pairs of records contradict each other.

        Every link in the receipt is written to ``conflicts_with`` on both
        records, and the receipt is persisted, in one transaction. A link that
        already exists on a record is left as is. The link is what the
        conflict report, phase locks, and promotion consult; it is resolved by
        a later supersession or archive of one side, never by removing it
        (ADR-081).
        """

    def commit_deletion(
        self,
        capability: ServiceWriteCapability,
        receipt: DeletionReceipt,
        redacted_record: MemoryRecord,
        *,
        outbox_event: OutboxEvent | None,
        status_event: MemoryStatusEvent,
    ) -> None:
        """Atomically tombstone a record under a verified deletion receipt.

        ``status_event`` is the lifecycle evidence for the transition into
        DELETION_PENDING or DELETED; the append-only ledger must record privacy
        deletions like every other transition (ADR-024, ADR-057).
        """

    def complete_deletion(
        self,
        record_id: UUID,
        receipt_id: UUID,
        *,
        completed_at: datetime,
        actor: str = "memory.outbox-worker",
    ) -> None:
        """Mark projection erasure confirmed: DELETION_PENDING becomes DELETED.

        Appends the DELETED lifecycle event attributed to ``actor`` and marks
        the deletion receipt COMPLETE. Idempotent for an already-DELETED record.
        """
