# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/requests.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Service requests. Identity is intentionally not client-writable here."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import ConfidenceMethod, EvidenceKind, MemoryClass
from .evidence import Confidence, EvidenceRef, Provenance
from .memory import MemoryAssertion
from .privacy import ConsentGrant
from .temporal import require_utc, utc_now


class MemoryWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    memory_class: MemoryClass = MemoryClass.OBSERVATION
    content: str = Field(min_length=1, max_length=64_000)
    assertion: MemoryAssertion | None = None
    provenance: Provenance
    evidence: tuple[EvidenceRef, ...] = ()
    confidence: Confidence = Field(default_factory=Confidence)
    valid_from: datetime = Field(default_factory=utc_now)
    valid_to: datetime | None = None
    source_observed_at: datetime | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Explicit operation identity. Two calls that carry the same key are the
    # same operation, so the second is a retry and dedupes. Omitting it means
    # "this is a new operation": identical content submitted twice without a
    # key is admitted twice, and semantic duplication is resolved later by
    # scheduled maintenance rather than at admission (ADR-071).
    idempotency_key: str | None = Field(default=None, max_length=300)
    supersedes: tuple[UUID, ...] = ()
    references: tuple[UUID, ...] = ()
    consent: ConsentGrant | None = None
    dry_run: bool = False

    @field_validator("valid_from", "valid_to", "source_observed_at")
    @classmethod
    def require_utc_coordinates(cls, value: datetime | None) -> datetime | None:
        return require_utc(value)

    @model_validator(mode="after")
    def validate_evidence(self) -> MemoryWriteRequest:
        if self.confidence.method in {
            ConfidenceMethod.INFERRED,
            ConfidenceMethod.AGGREGATED,
        }:
            if not self.evidence:
                raise ValueError("inferred or aggregated memory requires evidence")
            if not any(
                item.kind
                in {
                    EvidenceKind.INFERENCE,
                    EvidenceKind.AGGREGATION,
                    EvidenceKind.SOURCE_EXCERPT,
                }
                for item in self.evidence
            ):
                raise ValueError("inferred or aggregated memory requires matching evidence kind")
        return self


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=4_000)
    namespaces: tuple[str, ...] = ()
    memory_classes: tuple[MemoryClass, ...] = ()
    valid_at: datetime = Field(default_factory=utc_now)
    recorded_before: datetime | None = None
    include_superseded: bool = False
    include_archived: bool = False
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=20, ge=1, le=200)
    token_budget: int | None = Field(default=None, ge=64, le=64_000)

    @field_validator("valid_at", "recorded_before")
    @classmethod
    def require_utc_coordinates(cls, value: datetime | None) -> datetime | None:
        return require_utc(value)


class HydrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: str = Field(min_length=1, max_length=8_000)
    namespaces: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    memory_classes: tuple[MemoryClass, ...] = ()
    valid_at: datetime = Field(default_factory=utc_now)
    token_budget: int = Field(default=1_200, ge=128, le=64_000)
    max_records: int = Field(default=40, ge=1, le=200)

    @field_validator("valid_at")
    @classmethod
    def require_utc_coordinates(cls, value: datetime) -> datetime:
        normalized = require_utc(value)
        assert normalized is not None
        return normalized


class PromotionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: UUID
    target_class: MemoryClass
    explicit_confirmation: bool = False
    governance_approval: bool = False
    test_success_count: int = Field(default=0, ge=0)
    supporting_record_ids: tuple[UUID, ...] = ()
    consent: ConsentGrant | None = None
    reason: str = Field(min_length=1, max_length=2_000)


class PhaseLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    task_signature: str = Field(min_length=8, max_length=128)
    ttl_seconds: int = Field(default=1_800, ge=60, le=86_400)


class DeletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: UUID
    reason: str = Field(min_length=1, max_length=2_000)
    verification_reference: str = Field(min_length=1, max_length=500)
    dry_run: bool = False


class CloseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=8_000)
    session_id: str | None = Field(default=None, max_length=200)
    capsule_digest: str | None = Field(default=None, max_length=128)
    dry_run: bool = False
