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

from l9_graphite_memory.contracts import MemoryRecord


class ProjectionHit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    excerpt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectionAdapter(Protocol):
    name: str
    capabilities: tuple[str, ...]

    def health(self) -> dict[str, Any]: ...

    def project(self, record: MemoryRecord) -> dict[str, Any]: ...

    def erase(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
    ) -> dict[str, Any]: ...

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
