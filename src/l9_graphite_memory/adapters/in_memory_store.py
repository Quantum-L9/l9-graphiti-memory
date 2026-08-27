# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/in_memory_store.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic in-memory store for tests and embedded ephemeral use."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from l9_graphite_memory.contracts import (
    ArchiveReceipt,
    DeletionReceipt,
    DeletionStatus,
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
from l9_graphite_memory.errors import PhaseLockSnapshotConflict, StoreError
from l9_graphite_memory.ports.phase_lock import PhaseLockPrecondition, snapshot_digest
from l9_graphite_memory.ports.service_capability import (
    ServiceWriteCapability,
    require_service_write_capability,
)


class InMemoryRecordStore:
    name = "memory"

    def __init__(self) -> None:
        self.records: dict[UUID, MemoryRecord] = {}
        self.receipts: dict[UUID, WriteReceipt] = {}
        self.archive_receipts: dict[UUID, ArchiveReceipt] = {}
        self.deletion_receipts: dict[UUID, DeletionReceipt] = {}
        self.idempotency: dict[tuple[str, str, str], UUID] = {}
        self.status_events: list[MemoryStatusEvent] = []
        self.outbox: dict[UUID, OutboxEvent] = {}
        self.phase_locks: dict[tuple[str, str, str], PhaseLockReceipt] = {}
        self.projection_links: dict[tuple[UUID, str], ProjectionLink] = {}
        self.maintenance_runs: list[MaintenanceRunReceipt] = []
        self.projection_retirements: list[ProjectionRetirementReceipt] = []
        self.projection_rebuilds: list[ProjectionRebuildReceipt] = []
        self.initialized = False
        self._write_lock = threading.RLock()

    def initialize(self) -> None:
        self.initialized = True

    def close(self) -> None:
        self.initialized = False

    def health(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "healthy": self.initialized,
            "records": len(self.records),
        }

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
        require_service_write_capability(capability)
        # The lock makes the snapshot re-check and the mutation one critical
        # section, so two governed writers cannot both pass the check.
        with self._write_lock:
            if expected_phase_lock is not None:
                self._require_phase_lock_snapshot(expected_phase_lock)
            if record is not None:
                key = (record.tenant_id, record.namespace, record.idempotency_key)
                existing_id = self.idempotency.get(key)
                if existing_id is not None and existing_id != record.record_id:
                    raise ValueError("duplicate idempotency key")
                self.records[record.record_id] = record
                self.idempotency[key] = record.record_id
            self.receipts[receipt.receipt_id] = receipt
            for status_event in status_events:
                self.transition_state(status_event)
            for outbox_event in outbox_events:
                self.outbox[outbox_event.event_id] = outbox_event

    def _require_phase_lock_snapshot(self, expected: PhaseLockPrecondition) -> None:
        current = snapshot_digest(
            [
                item
                for item in self.records.values()
                if item.tenant_id == expected.tenant_id
                and item.namespace == expected.namespace
                and item.state is MemoryState.ACTIVE
            ]
        )
        if current != expected.expected_snapshot_digest:
            raise PhaseLockSnapshotConflict(
                "namespace changed after phase-lock verification: "
                f"expected={expected.expected_snapshot_digest} current={current}"
            )

    def get_record(self, record_id: UUID) -> MemoryRecord | None:
        return self.records.get(record_id)

    def find_by_idempotency(
        self, tenant_id: str, namespace: str, idempotency_key: str
    ) -> MemoryRecord | None:
        record_id = self.idempotency.get((tenant_id, namespace, idempotency_key))
        return self.records.get(record_id) if record_id else None

    def search_records(
        self,
        tenant_id: str,
        request: MemorySearchRequest,
        namespaces: tuple[str, ...],
    ) -> list[MemoryRecord]:
        allowed_states = {MemoryState.ACTIVE}
        if request.include_superseded:
            allowed_states.add(MemoryState.SUPERSEDED)
        if request.include_archived:
            allowed_states.add(MemoryState.ARCHIVED)
        results: list[MemoryRecord] = []
        recorded_before = request.recorded_before or request.valid_at
        for record in self.records.values():
            if record.tenant_id != tenant_id or record.namespace not in namespaces:
                continue
            if (
                record.state not in allowed_states
                or record.confidence.score < request.min_confidence
            ):
                continue
            if request.memory_classes and record.memory_class not in request.memory_classes:
                continue
            if not record.temporal.is_valid_at(request.valid_at):
                continue
            if record.temporal.recorded_at > recorded_before:
                continue
            results.append(record)
        return sorted(results, key=lambda item: item.temporal.recorded_at, reverse=True)[
            : request.limit * 10
        ]

    def list_records(
        self,
        tenant_id: str,
        namespace: str,
        *,
        states: tuple[MemoryState, ...] = (),
        limit: int = 1_000,
    ) -> list[MemoryRecord]:
        state_set = set(states)
        records = [
            record
            for record in self.records.values()
            if record.tenant_id == tenant_id
            and record.namespace == namespace
            and (not state_set or record.state in state_set)
        ]
        return sorted(records, key=lambda item: item.temporal.recorded_at, reverse=True)[:limit]

    def transition_state(self, event: MemoryStatusEvent) -> None:
        record = self.records.get(event.record_id)
        if record is None:
            raise KeyError(f"record not found: {event.record_id}")
        temporal = record.temporal
        if event.new_state is MemoryState.SUPERSEDED:
            temporal = temporal.model_copy(update={"superseded_at": event.occurred_at})
        self.records[event.record_id] = record.model_copy(
            update={"state": event.new_state, "temporal": temporal}
        )
        self.status_events.append(event)

    def save_phase_lock(
        self, capability: ServiceWriteCapability, receipt: PhaseLockReceipt
    ) -> None:
        require_service_write_capability(capability)
        self.phase_locks[(receipt.tenant_id, receipt.namespace, receipt.task_signature)] = receipt

    def get_phase_lock(
        self, tenant_id: str, namespace: str, task_signature: str
    ) -> PhaseLockReceipt | None:
        return self.phase_locks.get((tenant_id, namespace, task_signature))

    @staticmethod
    def _is_claimable(event: OutboxEvent, now: datetime) -> bool:
        if event.status in {OutboxStatus.PENDING, OutboxStatus.RETRY}:
            return event.next_attempt_at <= now
        if event.status is OutboxStatus.PROCESSING:
            # An expired lease means the previous owner is gone.
            return event.lease_expires_at is None or event.lease_expires_at <= now
        return False

    def claim_outbox(
        self,
        *,
        limit: int,
        now: datetime,
        lease_seconds: int = 300,
        lease_owner: str = "outbox-worker",
    ) -> list[OutboxEvent]:
        candidates = [event for event in self.outbox.values() if self._is_claimable(event, now)]
        claimed: list[OutboxEvent] = []
        for event in sorted(candidates, key=lambda item: item.created_at)[:limit]:
            updated = event.model_copy(
                update={
                    "status": OutboxStatus.PROCESSING,
                    "lease_id": uuid4(),
                    "lease_owner": lease_owner,
                    "lease_expires_at": now + timedelta(seconds=lease_seconds),
                }
            )
            self.outbox[event.event_id] = updated
            claimed.append(updated)
        return claimed

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
        event = self.outbox.get(event_id)
        if event is None:
            raise StoreError(f"outbox event not found: {event_id}")
        if lease_id is not None and event.lease_id != lease_id:
            raise StoreError(
                f"outbox lease is no longer held for {event_id}; another worker owns this event"
            )
        self.outbox[event_id] = event.model_copy(
            update={
                "status": status,
                "attempts": attempts,
                "next_attempt_at": next_attempt_at,
                "last_error": last_error,
                "delivered_at": delivered_at,
                "lease_id": None,
                "lease_owner": None,
                "lease_expires_at": None,
            }
        )

    def outbox_backlog(self) -> int:
        return sum(
            1
            for event in self.outbox.values()
            if event.status not in {OutboxStatus.DELIVERED, OutboxStatus.DEAD}
        )

    def save_projection_link(self, link: ProjectionLink) -> None:
        self.projection_links[(link.record_id, link.projection_name)] = link

    def get_projection_link(
        self,
        record_id: UUID,
        projection_name: str,
    ) -> ProjectionLink | None:
        return self.projection_links.get((record_id, projection_name))

    def delete_projection_link(self, record_id: UUID, projection_name: str) -> None:
        self.projection_links.pop((record_id, projection_name), None)

    def stats(self) -> dict[str, Any]:
        by_state: dict[str, int] = {}
        by_class: dict[str, int] = {}
        for record in self.records.values():
            by_state[record.state.value] = by_state.get(record.state.value, 0) + 1
            by_class[record.memory_class.value] = by_class.get(record.memory_class.value, 0) + 1
        return {
            "records": len(self.records),
            "receipts": len(self.receipts) + len(self.archive_receipts),
            "outbox_backlog": self.outbox_backlog(),
            "by_state": by_state,
            "by_class": by_class,
        }

    def save_projection_retirement(self, receipt: ProjectionRetirementReceipt) -> None:
        self.projection_retirements.append(receipt)

    def list_unprojected_records(
        self,
        tenant_id: str,
        namespace: str,
        projection_name: str,
        *,
        limit: int = 1_000,
    ) -> list[MemoryRecord]:
        candidates = [
            record
            for record in self.records.values()
            if record.tenant_id == tenant_id
            and record.namespace == namespace
            and record.state is MemoryState.ACTIVE
            and (record.record_id, projection_name) not in self.projection_links
        ]
        candidates.sort(key=lambda item: item.temporal.recorded_at)
        return candidates[:limit]

    def commit_projection_rebuild(
        self,
        capability: ServiceWriteCapability,
        receipt: ProjectionRebuildReceipt,
        *,
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        require_service_write_capability(capability)
        if not receipt.applied:
            raise StoreError("cannot persist a non-applied rebuild receipt")
        self.projection_rebuilds.append(receipt)
        for event in outbox_events:
            self.outbox[event.event_id] = event

    def save_maintenance_run(self, receipt: MaintenanceRunReceipt) -> None:
        self.maintenance_runs.append(receipt)

    def get_maintenance_watermark(self, tenant_id: str, namespace: str) -> datetime | None:
        applied = [
            run.watermark
            for run in self.maintenance_runs
            if run.tenant_id == tenant_id and run.namespace == namespace and run.applied
        ]
        return max(applied) if applied else None

    def find_maintenance_action_digests(self, tenant_id: str, namespace: str) -> frozenset[str]:
        return frozenset(
            action.action_digest
            for run in self.maintenance_runs
            if run.tenant_id == tenant_id and run.namespace == namespace
            for action in run.actions
            if action.applied
        )

    def list_expired(
        self,
        tenant_id: str,
        namespace: str,
        *,
        before: datetime,
    ) -> list[MemoryRecord]:
        candidates = [
            record
            for record in self.records.values()
            if record.tenant_id == tenant_id
            and record.namespace == namespace
            and record.state is MemoryState.ACTIVE
            and record.temporal.valid_to is not None
            and record.temporal.valid_to <= before
        ]
        return sorted(
            candidates,
            key=lambda item: item.temporal.valid_to or item.temporal.recorded_at,
        )

    def commit_archive(
        self,
        capability: ServiceWriteCapability,
        receipt: ArchiveReceipt,
        *,
        status_events: tuple[MemoryStatusEvent, ...],
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        require_service_write_capability(capability)
        if not receipt.applied:
            raise ValueError("cannot persist a non-applied archive receipt")
        event_ids = {event.record_id for event in status_events}
        if event_ids != set(receipt.archived_record_ids):
            raise ValueError("archive receipt and status events target different records")

        updates: dict[UUID, MemoryRecord] = {}
        for event in status_events:
            record = self.records.get(event.record_id)
            if record is None:
                raise KeyError(f"record not found: {event.record_id}")
            if event.previous_state is not None and record.state is not event.previous_state:
                raise ValueError(f"record state changed before archive: {event.record_id}")
            updates[event.record_id] = record.model_copy(update={"state": event.new_state})

        self.records.update(updates)
        self.status_events.extend(status_events)
        self.archive_receipts[receipt.receipt_id] = receipt
        for outbox_event in outbox_events:
            self.outbox[outbox_event.event_id] = outbox_event

    def commit_deletion(
        self,
        capability: ServiceWriteCapability,
        receipt: DeletionReceipt,
        redacted_record: MemoryRecord,
        *,
        outbox_event: OutboxEvent | None,
    ) -> None:
        require_service_write_capability(capability)
        if redacted_record.record_id != receipt.record_id:
            raise ValueError("deletion receipt and record target differ")
        self.records[redacted_record.record_id] = redacted_record
        self.deletion_receipts[receipt.receipt_id] = receipt
        if outbox_event is not None:
            self.outbox[outbox_event.event_id] = outbox_event

    def complete_deletion(
        self,
        record_id: UUID,
        receipt_id: UUID,
        *,
        completed_at: datetime,
    ) -> None:
        record = self.records.get(record_id)
        receipt = self.deletion_receipts.get(receipt_id)
        if record is None or receipt is None:
            raise KeyError("deletion record or receipt not found")
        self.records[record_id] = record.model_copy(update={"state": MemoryState.DELETED})
        self.deletion_receipts[receipt_id] = receipt.model_copy(
            update={"status": DeletionStatus.COMPLETE, "completed_at": completed_at}
        )
