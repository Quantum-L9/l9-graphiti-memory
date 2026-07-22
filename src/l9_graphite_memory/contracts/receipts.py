# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/receipts.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Evidence-bearing outcomes for every public memory operation."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.version import (
    ADMISSION_POLICY_VERSION,
    AUTHORIZATION_POLICY_VERSION,
    PHASE_LOCK_POLICY_VERSION,
    RANKING_POLICY_VERSION,
    RETENTION_POLICY_VERSION,
)

from .enums import (
    AuthorizationAction,
    DeletionStatus,
    MemoryClass,
    OperationStatus,
    OutboxStatus,
    QueryPattern,
    WriteStatus,
)
from .memory import MemoryRecord
from .temporal import utc_now


class AuthorizationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    principal_id: str
    action: AuthorizationAction
    namespace: str
    allowed: bool
    reasons: tuple[str, ...] = ()
    policy_version: str = AUTHORIZATION_POLICY_VERSION
    evaluated_at: datetime = Field(default_factory=utc_now)


class AdmissionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: UUID = Field(default_factory=uuid4)
    status: WriteStatus
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    policy_version: str = ADMISSION_POLICY_VERSION
    candidate_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime = Field(default_factory=utc_now)


class WriteReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    status: WriteStatus
    record_id: UUID | None = None
    namespace: str
    schema_version: str
    normalized_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str
    admission: AdmissionDecision
    authorization: AuthorizationReceipt
    outbox_event_ids: tuple[UUID, ...] = ()
    superseded_record_ids: tuple[UUID, ...] = ()
    warnings: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)


class ArchiveReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    status: OperationStatus = OperationStatus.COMPLETE
    namespace: str
    applied: bool
    archived_record_ids: tuple[UUID, ...] = ()
    authorization: AuthorizationReceipt
    reason: str
    actor: str
    created_at: datetime = Field(default_factory=utc_now)


class DeletionReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    tombstone_id: UUID = Field(default_factory=uuid4)
    record_id: UUID
    namespace: str
    status: DeletionStatus
    tombstone_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorization: AuthorizationReceipt
    reason: str
    verification_reference: str
    projection_event_id: UUID | None = None
    requested_by: str
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class ScoreFactors(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lexical: float = Field(default=0.0, ge=0.0, le=1.0)
    projection: float = Field(default=0.0, ge=0.0, le=1.0)
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    trust: float = Field(default=0.0, ge=0.0, le=1.0)
    importance: float = Field(default=0.0, ge=0.0, le=1.0)
    recency: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record: MemoryRecord
    score: float = Field(ge=0.0, le=1.0)
    factors: ScoreFactors
    matched_by: tuple[str, ...] = ()


class SearchReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    status: OperationStatus
    query: str
    namespaces_authorized: tuple[str, ...]
    hits: tuple[SearchHit, ...] = ()
    query_pattern: QueryPattern = QueryPattern.DEFAULT
    classification_reason: str = ""
    strategies_attempted: tuple[str, ...] = ()
    strategies_succeeded: tuple[str, ...] = ()
    strategies_failed: dict[str, str] = Field(default_factory=dict)
    stores_attempted: tuple[str, ...] = ()
    stores_succeeded: tuple[str, ...] = ()
    stores_failed: dict[str, str] = Field(default_factory=dict)
    ranking_policy_version: str = RANKING_POLICY_VERSION
    result_digest: str
    created_at: datetime = Field(default_factory=utc_now)


class ContextSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    memory_class: MemoryClass
    content: str
    record_ids: tuple[UUID, ...]
    tokens_estimated: int = Field(ge=0)
    highest_score: float = Field(ge=0.0, le=1.0)


class HydrationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    status: OperationStatus
    task: str
    sections: tuple[ContextSection, ...] = ()
    token_budget: int
    tokens_used: int
    search_receipt_id: UUID
    result_digest: str
    warnings: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)


class ConflictItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left_record_id: UUID
    right_record_id: UUID
    subject: str | None = None
    predicate: str | None = None
    reason: str


class ConflictReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str
    status: OperationStatus = OperationStatus.COMPLETE
    conflicts: tuple[ConflictItem, ...] = ()
    checked_record_count: int = Field(default=0, ge=0)
    snapshot_digest: str = Field(default="0" * 64, pattern=r"^[a-f0-9]{64}$")
    policy_version: str = PHASE_LOCK_POLICY_VERSION
    checked_at: datetime = Field(default_factory=utc_now)

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


class PhaseLockReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lock_id: UUID = Field(default_factory=uuid4)
    namespace: str
    task_signature: str
    granted: bool
    conflict_report: ConflictReport
    snapshot_digest: str = Field(default="0" * 64, pattern=r"^[a-f0-9]{64}$")
    expires_at: datetime
    principal_id: str
    policy_version: str = PHASE_LOCK_POLICY_VERSION
    created_at: datetime = Field(default_factory=utc_now)


class PhaseLockVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lock_id: UUID | None = None
    namespace: str
    task_signature: str
    valid: bool
    reasons: tuple[str, ...]
    current_snapshot_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    verified_at: datetime = Field(default_factory=utc_now)


class RetentionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID
    action: str
    reason: str
    reference_count: int = Field(default=0, ge=0)
    decay_score: float = Field(default=1.0, ge=0.0, le=1.0)


class RetentionReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    namespace: str
    applied: bool
    decisions: tuple[RetentionDecision, ...]
    archive_receipt: ArchiveReceipt
    policy_version: str = RETENTION_POLICY_VERSION
    created_at: datetime = Field(default_factory=utc_now)


class OutboxEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    aggregate_id: UUID
    namespace: str
    payload: dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    next_attempt_at: datetime = Field(default_factory=utc_now)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    delivered_at: datetime | None = None


class HealthReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: OperationStatus
    package_version: str
    schema_version: str
    store: dict[str, Any]
    projection: dict[str, Any]
    outbox_backlog: int = Field(ge=0)
    degraded_reasons: tuple[str, ...] = ()
    checked_at: datetime = Field(default_factory=utc_now)
