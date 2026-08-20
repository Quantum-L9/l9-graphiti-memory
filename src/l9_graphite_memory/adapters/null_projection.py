# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/null_projection.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""No-op projection used when graph projection is intentionally disabled."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from l9_graphite_memory.contracts import MemoryRecord
from l9_graphite_memory.ports import ProjectionHit


class NullProjection:
    name = "none"
    capabilities: tuple[str, ...] = ()

    def health(self) -> dict[str, Any]:
        return {"name": self.name, "healthy": True, "enabled": False}

    def project(self, record: MemoryRecord) -> dict[str, Any]:
        return {
            "projected": False,
            "reason": "projection disabled",
            "record_id": str(record.record_id),
        }

    def retire(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        return {
            "retired": True,
            "erased": False,
            "reason": reason or "projection disabled; nothing to withdraw",
            "record_id": str(record_id),
            "namespace": namespace,
            "locator": locator,
        }

    def erase(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
    ) -> dict[str, Any]:
        return {
            "erased": True,
            "reason": "projection disabled; no external copy exists",
            "record_id": str(record_id),
            "namespace": namespace,
            "locator": locator,
        }

    def search_strategy(
        self,
        strategy: str,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
    ) -> list[ProjectionHit]:
        return []

    def search(
        self, query: str, namespaces: tuple[str, ...], *, limit: int
    ) -> list[ProjectionHit]:
        return []
