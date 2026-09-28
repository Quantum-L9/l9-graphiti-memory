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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .receipts import AuthorizationReceipt
from .temporal import utc_now


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


# Projection-link metadata keys for legacy erasure obligations (ADR-091).
# A stale-scope re-projection (ADR-084) leaves the superseded copy in a
# retained, unreachable provider store for the rollback window. The link keeps
# a record of each such copy until an operator releases it after destroying
# that store; while any is outstanding, verified deletion stays pending.
LEGACY_COPIES_KEY = "legacy_copies"
# The live copy is gone (retired or erased) and the link survives only to
# carry legacy obligations.
LINK_WITHDRAWN_KEY = "withdrawn"
# Receipt of a verified deletion waiting only on legacy obligations.
PENDING_DELETION_RECEIPT_KEY = "pending_deletion_receipt_id"


def legacy_copies(link: ProjectionLink | None) -> list[dict[str, Any]]:
    """Outstanding legacy projection copies recorded on a link."""

    if link is None:
        return []
    copies = link.metadata.get(LEGACY_COPIES_KEY)
    return [dict(copy) for copy in copies] if isinstance(copies, list) else []


def link_withdrawn(link: ProjectionLink | None) -> bool:
    return bool(link is not None and link.metadata.get(LINK_WITHDRAWN_KEY))


class LegacyProjectionReleaseReceipt(BaseModel):
    """Operator release of legacy projection copies after their store is destroyed.

    Releasing asserts that the retained provider store holding the copies no
    longer exists (TENANT_SCOPE_MIGRATION step 7). Deletions that were waiting
    only on those copies complete; nothing else changes (ADR-091).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_id: UUID = Field(default_factory=uuid4)
    namespace: str = Field(min_length=1, max_length=255)
    projection_name: str = Field(min_length=1, max_length=128)
    applied: bool = False
    released_record_ids: tuple[UUID, ...] = ()
    released_copy_count: int = Field(default=0, ge=0)
    completed_deletion_record_ids: tuple[UUID, ...] = ()
    authorization: AuthorizationReceipt
    store_destruction_reference: str = Field(min_length=1, max_length=400)
    reason: str = Field(min_length=1, max_length=2_000)
    actor: str = Field(min_length=1, max_length=400)
    created_at: datetime = Field(default_factory=utc_now)


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
    # Records whose live link was written under an older provider scope
    # scheme and are re-projected into the current one (ADR-084). A subset of
    # ``queued_record_ids``.
    stale_scope_record_ids: tuple[UUID, ...] = ()
    outbox_event_ids: tuple[UUID, ...] = ()
    authorization: AuthorizationReceipt
    reason: str = Field(min_length=1, max_length=2_000)
    actor: str = Field(min_length=1, max_length=400)
    created_at: datetime = Field(default_factory=utc_now)
