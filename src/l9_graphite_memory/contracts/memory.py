# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/memory.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Canonical memory records and immutable assertions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION

from .enums import MemoryClass, MemoryState
from .evidence import Confidence, EvidenceRef, Provenance
from .privacy import ConsentGrant
from .temporal import TemporalCoordinates, utc_now


class MemoryAssertion(BaseModel):
    """Atomic assertion suitable for graph and lexical retrieval."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str | None = Field(default=None, max_length=500)
    predicate: str | None = Field(default=None, max_length=200)
    object: str | None = Field(default=None, max_length=2_000)

    @property
    def is_structured(self) -> bool:
        return bool(self.subject and self.predicate and self.object)


class MemoryRecord(BaseModel):
    """Content-immutable canonical memory record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID = Field(default_factory=uuid4)
    schema_version: str = MEMORY_SCHEMA_VERSION
    tenant_id: str = Field(min_length=1, max_length=200)
    namespace: str = Field(min_length=1, max_length=300)
    memory_class: MemoryClass
    content: str = Field(min_length=1, max_length=64_000)
    assertion: MemoryAssertion | None = None
    temporal: TemporalCoordinates = Field(default_factory=TemporalCoordinates)
    provenance: Provenance
    evidence: tuple[EvidenceRef, ...] = ()
    confidence: Confidence = Field(default_factory=Confidence)
    state: MemoryState = MemoryState.ACTIVE
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)
    normalized_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    original_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=300)
    supersedes: tuple[UUID, ...] = ()
    references: tuple[UUID, ...] = ()
    consent: ConsentGrant | None = None
    conflicts_with: tuple[UUID, ...] = ()
    created_by: str = Field(min_length=1, max_length=300)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({tag.strip().lower() for tag in value if tag.strip()}))


class MemoryStatusEvent(BaseModel):
    """Append-only lifecycle evidence for a memory record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    record_id: UUID
    previous_state: MemoryState | None = None
    new_state: MemoryState
    reason: str = Field(min_length=1, max_length=2_000)
    actor: str = Field(min_length=1, max_length=300)
    occurred_at: datetime = Field(default_factory=utc_now)
    receipt_id: UUID | None = None
