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
    DeletionReceipt,
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
        limit: int = 1_000,
    ) -> list[MemoryRecord]: ...

    def transition_state(self, event: MemoryStatusEvent) -> None: ...

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

    def commit_deletion(
        self,
        capability: ServiceWriteCapability,
        receipt: DeletionReceipt,
        redacted_record: MemoryRecord,
        *,
        outbox_event: OutboxEvent | None,
    ) -> None: ...

    def complete_deletion(
        self,
        record_id: UUID,
        receipt_id: UUID,
        *,
        completed_at: datetime,
    ) -> None: ...
