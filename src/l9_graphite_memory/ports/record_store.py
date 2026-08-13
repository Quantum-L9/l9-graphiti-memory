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
    MemoryRecord,
    MemorySearchRequest,
    MemoryState,
    MemoryStatusEvent,
    OutboxEvent,
    OutboxStatus,
    PhaseLockReceipt,
    ProjectionLink,
    WriteReceipt,
)

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
    ) -> None: ...

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

    def claim_outbox(self, *, limit: int, now: datetime) -> list[OutboxEvent]: ...

    def update_outbox(
        self,
        event_id: UUID,
        *,
        status: OutboxStatus,
        attempts: int,
        next_attempt_at: datetime,
        last_error: str | None,
        delivered_at: datetime | None = None,
    ) -> None: ...

    def outbox_backlog(self) -> int: ...

    def save_projection_link(self, link: ProjectionLink) -> None: ...

    def get_projection_link(
        self,
        record_id: UUID,
        projection_name: str,
    ) -> ProjectionLink | None: ...

    def delete_projection_link(self, record_id: UUID, projection_name: str) -> None: ...

    def stats(self) -> dict[str, Any]: ...

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
