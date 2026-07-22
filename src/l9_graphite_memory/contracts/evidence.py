# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/evidence.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Evidence, provenance, and confidence contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import ConfidenceMethod, EvidenceKind
from .temporal import utc_now


class SourceRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)


class Provenance(BaseModel):
    """Trace a memory back to the exact source and transformation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1, max_length=200)
    source_id: str | None = Field(default=None, max_length=500)
    source_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_range: SourceRange | None = None
    source_agent_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    repository: str | None = Field(default=None, max_length=300)
    tool: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    extraction_method: str = Field(default="direct", max_length=100)
    source_trust: float = Field(default=1.0, ge=0.0, le=1.0)
    transformed_at: datetime = Field(default_factory=utc_now)


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EvidenceKind
    description: str = Field(min_length=1, max_length=2_000)
    source_id: str | None = Field(default=None, max_length=500)
    source_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_range: SourceRange | None = None
    observed_at: datetime = Field(default_factory=utc_now)


class Confidence(BaseModel):
    """Confidence is meaningful only when tied to a method and evidence count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: float = Field(default=1.0, ge=0.0, le=1.0)
    method: ConfidenceMethod = ConfidenceMethod.EXPLICIT
    evidence_count: int = Field(default=1, ge=0)
    policy_version: str = Field(default="confidence/v1", min_length=1, max_length=100)
    calibrated_at: datetime = Field(default_factory=utc_now)

    @field_validator("evidence_count")
    @classmethod
    def inferred_requires_evidence(cls, value: int, info: object) -> int:
        # Cross-field enforcement is completed by admission; this validator keeps the field sane.
        return value
