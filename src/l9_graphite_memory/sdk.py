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

from typing import Any
from uuid import UUID

from l9_graphite_memory.contracts import (
    CloseReceipt,
    CloseRequest,
    ConflictReport,
    HealthReport,
    HydrationRequest,
    HydrationResult,
    MemoryPrincipal,
    MemoryRecord,
    MemorySearchRequest,
    MemoryWriteRequest,
    PhaseLockReceipt,
    PhaseLockRequest,
    PhaseLockVerification,
    SearchReceipt,
    WriteReceipt,
)
from l9_graphite_memory.contracts.generated_data import MemoryCandidateIngestionResult
from l9_graphite_memory.graph.contracts import (
    GraphCapabilityReport,
    GraphIntelligenceReceipt,
    GraphIntelligenceRequest,
)
from l9_graphite_memory.graph.service import GraphIntelligenceService, graph_service_for
from l9_graphite_memory.lineage import LineageReplay
from l9_graphite_memory.services import GeneratedDataService, MemoryService


class MemorySDK:
    """Typed per-principal façade over MemoryService.

    Every lifecycle operation the CLI and MCP transports expose is reachable
    here too (ADR-082), so an in-process consumer never has a reason to reach
    around the service.
    """

    def __init__(
        self,
        service: MemoryService,
        principal: MemoryPrincipal,
        *,
        graph: GraphIntelligenceService | None = None,
    ) -> None:
        self._service = service
        self.principal = principal
        self._graph = graph

    def _graph_service(self) -> GraphIntelligenceService:
        if self._graph is None:
            from l9_graphite_memory.adapters import NullGraphIntelligence

            # No backend configured: structural operations report unavailable;
            # graph/semantic search still run through the projection.
            self._graph = graph_service_for(self._service, NullGraphIntelligence())
        return self._graph

    def graph(self, request: GraphIntelligenceRequest) -> GraphIntelligenceReceipt:
        """Provider-neutral graph intelligence under this principal (ADR-089)."""

        return self._graph_service().execute(self.principal, request)

    def graph_capabilities(self) -> GraphCapabilityReport:
        return self._graph_service().capability_report()

    def write(self, request: MemoryWriteRequest) -> WriteReceipt:
        return self._service.write(self.principal, request)

    def write_governed(self, request: MemoryWriteRequest, *, task_signature: str) -> WriteReceipt:
        return self._service.write_governed(self.principal, request, task_signature=task_signature)

    def ingest_governed_candidate(self, payload: dict[str, Any]) -> MemoryCandidateIngestionResult:
        return GeneratedDataService(self._service).ingest_governed_candidate(
            self.principal, payload
        )

    def search(self, request: MemorySearchRequest) -> SearchReceipt:
        return self._service.search(self.principal, request)

    def hydrate(self, request: HydrationRequest) -> HydrationResult:
        return self._service.hydrate(self.principal, request)

    def get(self, record_id: UUID) -> MemoryRecord | None:
        return self._service.get(self.principal, record_id)

    def conflicts(self, namespace: str) -> ConflictReport:
        return self._service.conflicts(self.principal, namespace)

    def phase_lock(self, request: PhaseLockRequest) -> PhaseLockReceipt:
        return self._service.phase_lock(self.principal, request)

    def verify_phase_lock(self, namespace: str, task_signature: str) -> PhaseLockVerification:
        return self._service.verify_phase_lock(self.principal, namespace, task_signature)

    def close(self, request: CloseRequest) -> CloseReceipt:
        return self._service.close(self.principal, request)

    def health(self) -> HealthReport:
        return self._service.health()

    def lineage(self, namespace: str, record_id: UUID) -> LineageReplay:
        return self._service.lineage(self.principal, namespace, record_id)
