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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_naive(value: datetime) -> bool:
    return value.tzinfo is None or value.tzinfo.utcoffset(value) is None


def require_utc(value: datetime | None) -> datetime | None:
    """Normalize an ingress datetime to UTC and refuse naive values (ADR-029).

    Every temporal coordinate is compared across records and across store
    backends. SQLite compares the stored ISO text lexically and the in-memory
    store compares Python datetimes, so a naive value or a non-UTC offset would
    either sort wrongly or raise ``TypeError`` deep inside retrieval. Request
    contracts therefore fail closed: a caller that omits the offset gets a
    validation error naming the field rather than a silently mis-filed record.
    """

    if value is None:
        return None
    if _is_naive(value):
        raise ValueError("datetime must be timezone-aware; ADR-029 requires UTC coordinates")
    return value.astimezone(timezone.utc)


def coerce_utc(value: datetime | None) -> datetime | None:
    """Normalize a persisted datetime to UTC, reading a naive value as UTC.

    Persisted contracts are read back from rows written by earlier releases,
    some of which accepted naive values. Refusing them would make those rows
    unreadable, so at rest the missing offset is interpreted as UTC -- the only
    zone this system ever wrote -- and the value is normalized so that every
    reader compares like with like. New input never reaches here naive: the
    request contracts apply :func:`require_utc` first.
    """

    if value is None:
        return None
    if _is_naive(value):
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class TemporalCoordinates(BaseModel):
    """Coordinates that distinguish when a fact is true from when it was recorded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    valid_from: datetime = Field(default_factory=utc_now)
    valid_to: datetime | None = None
    recorded_at: datetime = Field(default_factory=utc_now)
    source_observed_at: datetime | None = None
    superseded_at: datetime | None = None

    @field_validator("valid_from", "valid_to", "recorded_at", "source_observed_at", "superseded_at")
    @classmethod
    def normalize_utc(cls, value: datetime | None) -> datetime | None:
        return coerce_utc(value)

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
