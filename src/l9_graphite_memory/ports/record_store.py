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
    GraphCutoverReceipt,
    LegacyProjectionReleaseReceipt,
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

    def save_projection_link(self, link: ProjectionLink) -> None:
        """Upsert the link for ``(link.record_id, link.target_identity)``.

        A record holds one link per target it is projected into; saving a link
        for one target never replaces another target's link (ADR-084).
        """

    def save_projection_link_if_active(
        self, link: ProjectionLink, *, expected_previous: ProjectionLink | None
    ) -> bool:
        """Persist ``link`` only while its record is ACTIVE, in one atomic step.

        Returns ``False`` (and writes nothing) when the record is missing or
        no longer ACTIVE. The outbox worker uses this after a provider write,
        so a deletion, retirement or release that lands between its lifecycle
        check and the link write can never be followed by a live link
        (ADR-092).

        ``expected_previous`` is the link the replacement was derived from
        (``None`` when there was none). If the current link differs, for
        example because a legacy release cleared its obligations in the
        meantime, nothing is written and ``ProjectionLinkConflict`` is raised
        so the caller can re-derive from the current link.
        """
        ...

    def get_projection_link(
        self,
        record_id: UUID,
        target_identity: str,
    ) -> ProjectionLink | None: ...

    def list_projection_links(self, record_id: UUID) -> list[ProjectionLink]:
        """Every durable provider copy canonical state knows for this record.

        This, not the currently configured targets, is the erasure set of a
        privacy deletion (ADR-084).
        """

    def list_projection_target_identities(self) -> tuple[str, ...]:
        """Every target identity canonical state still owes lifecycle work to.

        The distinct identities of all persisted projection links plus those
        named by outbox events that are still pending, retrying, or leased. A
        runtime that cannot address one of them would strand that copy or
        event, so composition checks this set before activating (ADR-084).
        """

    def delete_projection_link(self, record_id: UUID, target_identity: str) -> None:
        """Remove one target's link; a link that does not exist is not an error."""

    def save_projection_retirement(self, receipt: ProjectionRetirementReceipt) -> None:
        """Record that a projection was withdrawn, and why, in canonical state."""
        ...

    def list_unprojected_records(
        self,
        tenant_id: str,
        namespace: str,
        target_identity: str,
        *,
        limit: int = 1_000,
    ) -> list[MemoryRecord]:
        """Active records with no live projection link for this target."""
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

    def commit_legacy_projection_release(
        self,
        capability: ServiceWriteCapability,
        receipt: LegacyProjectionReleaseReceipt,
        *,
        link_updates: tuple[ProjectionLink, ...] = (),
        link_removals: tuple[tuple[UUID, str], ...] = (),
        deletion_completions: tuple[tuple[UUID, UUID], ...] = (),
        expected_links: tuple[ProjectionLink, ...] = (),
    ) -> None:
        """Atomically record a legacy-copy release and apply its effects (ADR-092).

        One transaction persists the receipt, rewrites or removes the affected
        projection links, and completes each ``(record_id, deletion_receipt_id)``
        deletion that was waiting only on the released copies. Every link in
        ``expected_links`` (the state the release was planned from) must still
        be current, or nothing is applied: a concurrent outbox erasure cannot be
        overwritten by a stale plan. A canonical mutation, so it requires the
        service-issued capability (ADR-036).
        """
        ...

    def list_legacy_projection_releases(
        self, namespace: str
    ) -> list[LegacyProjectionReleaseReceipt]:
        """Applied legacy-copy releases for one namespace, oldest first."""
        ...

    def commit_graph_cutover(
        self, capability: ServiceWriteCapability, receipt: GraphCutoverReceipt
    ) -> None:
        """Append one applied graph cutover receipt to the operation ledger.

        Append-only: a later cutover supersedes an earlier one for the same
        namespace, and neither is ever updated or deleted. A canonical
        mutation, so it requires the service-issued capability (ADR-036, ADR-093).
        """
        ...

    def list_graph_cutovers(self, tenant_id: str, namespace: str) -> list[GraphCutoverReceipt]:
        """Applied graph cutovers for one tenant's namespace, oldest first."""
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
        outbox_event: OutboxEvent | None = None,
        outbox_events: tuple[OutboxEvent, ...] = (),
        status_event: MemoryStatusEvent,
    ) -> None:
        """Atomically tombstone a record under a verified deletion receipt.

        ``status_event`` is the lifecycle evidence for the transition into
        DELETION_PENDING or DELETED; the append-only ledger must record privacy
        deletions like every other transition (ADR-024, ADR-057). The erase
        events, one per provider copy, commit in the same transaction
        (ADR-084); ``outbox_event`` is the single-event form.
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
        Must raise ``StoreError`` while any projection link for the record
        remains: a deletion is complete only once every durable provider copy
        is erased (ADR-084).
        """
