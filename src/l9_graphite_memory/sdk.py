# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/sdk.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SDK-first interface that binds a server-derived principal once."""

from __future__ import annotations

from uuid import UUID

from l9_graphite_memory.contracts import (
    HydrationRequest,
    HydrationResult,
    MemoryPrincipal,
    MemoryRecord,
    MemorySearchRequest,
    MemoryWriteRequest,
    PhaseLockReceipt,
    PhaseLockRequest,
    SearchReceipt,
    WriteReceipt,
)
from l9_graphite_memory.lineage import LineageReplay
from l9_graphite_memory.services import MemoryService


class MemorySDK:
    """Typed per-principal façade over MemoryService."""

    def __init__(self, service: MemoryService, principal: MemoryPrincipal) -> None:
        self._service = service
        self.principal = principal

    def write(self, request: MemoryWriteRequest) -> WriteReceipt:
        return self._service.write(self.principal, request)

    def search(self, request: MemorySearchRequest) -> SearchReceipt:
        return self._service.search(self.principal, request)

    def hydrate(self, request: HydrationRequest) -> HydrationResult:
        return self._service.hydrate(self.principal, request)

    def get(self, record_id: UUID) -> MemoryRecord | None:
        return self._service.get(self.principal, record_id)

    def phase_lock(self, request: PhaseLockRequest) -> PhaseLockReceipt:
        return self._service.phase_lock(self.principal, request)

    def lineage(self, namespace: str, record_id: UUID) -> LineageReplay:
        return self._service.lineage(self.principal, namespace, record_id)
