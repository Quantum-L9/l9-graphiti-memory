# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/projection.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Optional graph/semantic projection contract."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import MemoryRecord, RetirementMode


class ProjectionHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    excerpt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectionAdapter(Protocol):
    name: str
    capabilities: tuple[str, ...]
    # Whether this provider can deactivate a projected record or only remove
    # it. Declared rather than inferred, so the ceiling is machine-readable and
    # a caller can tell whether retirement is reversible at the provider
    # (ADR-076).
    retirement_mode: RetirementMode

    def health(self) -> dict[str, Any]: ...

    def project(self, record: MemoryRecord) -> dict[str, Any]: ...

    def retire(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Withdraw a projection because the record is no longer current.

        Retirement and erasure are different operations with different
        authority and different consequences. Retirement says the canonical
        record has been superseded or archived, so the derived projection must
        stop surfacing it; the canonical record keeps its content, its
        lifecycle history, and its evidence. Erasure says the content itself
        must cease to exist, and is driven by a verified deletion receipt.

        Implementations must never redact canonical state or produce deletion
        semantics here (ADR-074).
        """
        ...

    def erase(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
    ) -> dict[str, Any]:
        """Destroy the projected copy under verified privacy erasure."""
        ...

    def search_strategy(
        self,
        strategy: str,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
    ) -> list[ProjectionHit]: ...

    def search(
        self,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
    ) -> list[ProjectionHit]: ...
