# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/temporal.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Bi-temporal coordinates for valid time and transaction time."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TemporalCoordinates(BaseModel):
    """Coordinates that distinguish when a fact is true from when it was recorded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valid_from: datetime = Field(default_factory=utc_now)
    valid_to: datetime | None = None
    recorded_at: datetime = Field(default_factory=utc_now)
    source_observed_at: datetime | None = None
    superseded_at: datetime | None = None

    @model_validator(mode="after")
    def validate_coordinates(self) -> TemporalCoordinates:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")
        if self.superseded_at is not None and self.superseded_at < self.recorded_at:
            raise ValueError("superseded_at cannot precede recorded_at")
        return self

    def is_valid_at(self, at: datetime) -> bool:
        """Return whether the fact is valid at a valid-time coordinate."""

        return self.valid_from <= at and (self.valid_to is None or at < self.valid_to)
