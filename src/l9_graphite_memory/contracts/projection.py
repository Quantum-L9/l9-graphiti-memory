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
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .receipts import AuthorizationReceipt
from .temporal import utc_now

#: Provider type recorded for a scalar-mode target and for links persisted
#: before target identity existed. Their target identity is the projection
#: name they were already keyed by (ADR-084).
LEGACY_PROVIDER_TYPE = "legacy"


class RetirementMode(str, Enum):
    """How a provider can withdraw a projection that is no longer current.

    ``NATIVE`` means the provider can deactivate a projected record while
    keeping it, so retirement is reversible at the provider.

    ``WITHDRAW`` means the provider offers only removal, so retirement removes
    the projected copy and restoring it requires re-projection from canonical
    state. Graphiti is ``WITHDRAW``: it exposes ``delete_episode`` and no
    deactivation primitive (ADR-076).
    """

    NATIVE = "native"
    WITHDRAW = "withdraw"


class ProjectionLink(BaseModel):
    """Persist the stable provider locator for one projected canonical record.

    One link is one durable provider copy, identified by
    ``(record_id, target_identity)``. A record projected into several targets
    holds one link per target, and every link is part of that record's
    mandatory erasure set (ADR-084).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID
    namespace: str = Field(min_length=1, max_length=255)
    projection_name: str = Field(min_length=1, max_length=128)
    # ``projection-name:vN:provider-type:target`` for a manifest target; the
    # projection name itself for a legacy scalar target.
    target_identity: str = Field(min_length=1, max_length=512)
    projection_version: int | None = Field(default=None, ge=1)
    provider_type: str = Field(default=LEGACY_PROVIDER_TYPE, min_length=1, max_length=64)
    locator: str = Field(min_length=1, max_length=1_024)
    manifest_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    render_contract_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def _default_legacy_target_identity(cls, data: Any) -> Any:
        # Links persisted before ADR-084 carry no target identity; they were
        # keyed by projection name, which is therefore their identity.
        if isinstance(data, dict) and not data.get("target_identity"):
            return {**data, "target_identity": data.get("projection_name")}
        return data

    @field_validator("namespace", "projection_name", "target_identity", "locator")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value cannot be blank")
        return stripped


class ProjectionRetirementReceipt(BaseModel):
    """Canonical evidence that a projection was withdrawn, and why.

    A provider whose only removal primitive is deletion cannot distinguish a
    retirement from a privacy erasure in its own logs. This receipt keeps that
    distinction in canonical state, where it does not depend on the provider
    (ADR-076).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    record_id: UUID
    namespace: str = Field(min_length=1, max_length=255)
    projection_name: str = Field(min_length=1, max_length=128)
    # The exact provider copy that was withdrawn. None only on receipts
    # written before target identity existed (ADR-084).
    target_identity: str | None = Field(default=None, max_length=512)
    provider_type: str | None = Field(default=None, max_length=64)
    retirement_mode: RetirementMode
    locator: str | None = Field(default=None, max_length=1_024)
    reason: str = Field(min_length=1, max_length=2_000)
    # Always false. Retirement never carries erasure semantics; a privacy
    # deletion produces a DeletionReceipt instead.
    erasure: bool = False
    rebuildable: bool = True
    outbox_event_id: UUID | None = None
    provider_result: dict[str, Any] = Field(default_factory=dict)
    retired_at: datetime = Field(default_factory=utc_now)

    @field_validator("erasure")
    @classmethod
    def reject_erasure_semantics(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "a retirement receipt cannot assert erasure; "
                "privacy deletion produces a DeletionReceipt"
            )
        return value


class ProjectionRebuildReceipt(BaseModel):
    """Result of re-projecting canonical records into a derivation.

    Retirement under ``WITHDRAW`` removes the projected copy. Rebuilding is how
    that is undone: active canonical records with no projection link are
    projected again, so a withdrawn projection is recoverable rather than lost
    (ADR-076).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    namespace: str = Field(min_length=1, max_length=255)
    projection_name: str = Field(min_length=1, max_length=128)
    applied: bool = False
    considered_record_count: int = Field(default=0, ge=0)
    already_projected_count: int = Field(default=0, ge=0)
    queued_record_ids: tuple[UUID, ...] = ()
    outbox_event_ids: tuple[UUID, ...] = ()
    # Targets this rebuild considered, and per target the records queued for
    # it. A record missing from one target is rebuilt there only (ADR-084).
    target_identities: tuple[str, ...] = ()
    queued_by_target: dict[str, tuple[UUID, ...]] = Field(default_factory=dict)
    authorization: AuthorizationReceipt
    reason: str = Field(min_length=1, max_length=2_000)
    actor: str = Field(min_length=1, max_length=400)
    created_at: datetime = Field(default_factory=utc_now)
