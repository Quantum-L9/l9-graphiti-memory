# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/projection.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Projection-link contracts for rebuildable external indexes."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .temporal import utc_now


class ProjectionLink(BaseModel):
    """Persist the stable provider locator for one projected canonical record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID
    namespace: str = Field(min_length=1, max_length=255)
    projection_name: str = Field(min_length=1, max_length=128)
    locator: str = Field(min_length=1, max_length=1_024)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("namespace", "projection_name", "locator")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped
