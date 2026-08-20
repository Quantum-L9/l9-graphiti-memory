# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/maintenance.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Scheduled canonical-memory maintenance contracts.

Maintenance operates on memories that are *already canonical*. It consolidates,
refines, supersedes, and archives what the write path admitted; it is not an
ingestion surface. That boundary is structural rather than advisory: the request
model forbids unknown fields and declares no field capable of carrying content,
a transcript, a document, or any other raw source (ADR-075).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import MaintenanceOperation, MaintenanceStatus, OperationStatus
from .receipts import AuthorizationReceipt
from .temporal import utc_now

ALL_MAINTENANCE_OPERATIONS: tuple[MaintenanceOperation, ...] = tuple(
    MaintenanceOperation
)


class MaintenanceRequest(BaseModel):
    """What a maintenance run may do, and to which already-canonical records.

    There is deliberately no way to express "and also ingest this". The model
    names a namespace, a bounded set of operations, and limits. Every record it
    can touch is one the canonical store already holds.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace: str = Field(min_length=1, max_length=300)
    operations: tuple[MaintenanceOperation, ...] = ALL_MAINTENANCE_OPERATIONS
    # Only records recorded at or before the watermark are eligible. Leaving it
    # unset pins the watermark to the run's start, so writes that land while the
    # run is in flight are out of scope and cannot be half-processed.
    watermark: datetime | None = None
    max_records: int = Field(default=5_000, ge=1, le=100_000)
    max_actions: int = Field(default=500, ge=1, le=10_000)
    dry_run: bool = False
    reason: str = Field(default="scheduled maintenance", min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_operations(self) -> MaintenanceRequest:
        if not self.operations:
            raise ValueError("maintenance requires at least one operation")
        if len(set(self.operations)) != len(self.operations):
            raise ValueError("maintenance operations must be unique")
        return self


class MaintenanceAction(BaseModel):
    """One bounded transformation over records the store already holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: UUID = Field(default_factory=uuid4)
    operation: MaintenanceOperation
    # The already-canonical records this action reasons over.
    source_record_ids: tuple[UUID, ...] = ()
    # A derived record this action created, when it created one.
    result_record_id: UUID | None = None
    superseded_record_ids: tuple[UUID, ...] = ()
    archived_record_ids: tuple[UUID, ...] = ()
    reason: str = Field(min_length=1, max_length=2_000)
    # Stable digest of the action's inputs and intent. Replaying a run that
    # already produced this digest is a no-op, which is what makes a rerun
    # idempotent rather than duplicative.
    action_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    applied: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class MaintenanceRunReceipt(BaseModel):
    """Ledger entry describing exactly what one maintenance run did."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1, max_length=200)
    namespace: str = Field(min_length=1, max_length=300)
    status: OperationStatus = OperationStatus.COMPLETE
    maintenance_status: MaintenanceStatus = MaintenanceStatus.APPLIED
    applied: bool = False
    operations: tuple[MaintenanceOperation, ...] = ()
    # Upper bound on recorded_at for records this run was allowed to consider.
    watermark: datetime
    # Watermark of the previous completed run for this namespace, if any.
    previous_watermark: datetime | None = None
    considered_record_count: int = Field(default=0, ge=0)
    actions: tuple[MaintenanceAction, ...] = ()
    skipped_action_digests: tuple[str, ...] = ()
    authorization: AuthorizationReceipt
    actor: str = Field(min_length=1, max_length=400)
    reason: str = Field(min_length=1, max_length=2_000)
    failures: tuple[str, ...] = ()
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

    @property
    def applied_actions(self) -> tuple[MaintenanceAction, ...]:
        return tuple(action for action in self.actions if action.applied)
