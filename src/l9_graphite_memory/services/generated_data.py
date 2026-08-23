# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/services/generated_data.py
#   layer: service
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-08-14

"""Narrow generated-data operations. Durable writes go through MemoryService.write only."""

from __future__ import annotations

from typing import Any

from l9_graphite_memory.contracts import (
    Confidence,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.contracts.generated_data import (
    GeneratedDataCapabilityResponse,
    GovernedMemoryCandidate,
    MemoryCandidateIngestionResult,
    MemoryCandidateIngestionStatus,
    MemoryReuseEvent,
    MemoryReuseReceipt,
    MemoryReuseStatus,
    SourceInvalidationReceipt,
    SourceInvalidationRequest,
    SourceInvalidationStatus,
)
from l9_graphite_memory.services.memory_service import MemoryService

WRITE_PATH = "l9_graphite_memory.services.MemoryService.write"


class GeneratedDataService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory

    def ingest_governed_candidate(
        self, principal: MemoryPrincipal, payload: dict[str, Any]
    ) -> MemoryCandidateIngestionResult:
        candidate = GovernedMemoryCandidate.model_validate(payload)
        namespace = candidate.namespace()
        request = MemoryWriteRequest(
            namespace=namespace,
            memory_class=MemoryClass.SEMANTIC,
            content=candidate.knowledge.statement,
            provenance=Provenance(
                source="cursor-governance-generated-data",
                source_id=candidate.candidate_id,
                source_agent_id=candidate.provenance.source_agent_id or principal.agent_id,
                tool="generated-data.ingest",
                extraction_method="governed-candidate/v1",
            ),
            evidence=(
                EvidenceRef(
                    kind=EvidenceKind.EXPLICIT,
                    description="governed generated-data candidate",
                    source_id=candidate.candidate_id,
                ),
            ),
            confidence=Confidence(score=candidate.knowledge.confidence, evidence_count=1),
            tags=("generated-data", candidate.knowledge.primary_class),
            metadata={
                "generated_data_kind": candidate.kind,
                "primary_class": candidate.knowledge.primary_class,
                "candidate_id": candidate.candidate_id,
                "repository": candidate.source.repository,
            },
            idempotency_key=f"generated-data:{candidate.candidate_id}",
        )
        receipt = self.memory.write(principal, request)
        if receipt.status.value == "duplicate":
            status = MemoryCandidateIngestionStatus.DUPLICATE
        elif receipt.status.value not in {"rejected"}:
            status = MemoryCandidateIngestionStatus.ADMITTED
        else:
            status = MemoryCandidateIngestionStatus.REJECTED
        return MemoryCandidateIngestionResult(
            status=status,
            candidate_id=candidate.candidate_id,
            namespace=namespace,
            write_receipt_id=str(receipt.receipt_id),
            reason=None if status != MemoryCandidateIngestionStatus.REJECTED else "write rejected",
        )

    def record_reuse(
        self, principal: MemoryPrincipal, payload: dict[str, Any]
    ) -> MemoryReuseReceipt:
        event = MemoryReuseEvent.model_validate(payload)
        record = self.memory.get(principal, event.record_id)
        if record is None:
            return MemoryReuseReceipt(
                status=MemoryReuseStatus.REJECTED,
                event_id=event.event_id,
                record_id=event.record_id,
                reason="record not found",
            )
        request = MemoryWriteRequest(
            namespace=record.namespace,
            memory_class=MemoryClass.META,
            content=f"reuse:{event.outcome}:{event.record_id}",
            provenance=Provenance(
                source="cursor-governance-generated-data",
                source_id=event.event_id,
                source_agent_id=principal.agent_id,
                tool="generated-data.record-reuse",
                extraction_method="reuse-event/v1",
            ),
            evidence=(
                EvidenceRef(
                    kind=EvidenceKind.EXPLICIT,
                    description="generated-data reuse event",
                    source_id=event.event_id,
                ),
            ),
            tags=("generated-data", "reuse", event.outcome),
            metadata={
                "reuse_event_id": event.event_id,
                "referenced_record_id": str(event.record_id),
                "outcome": event.outcome,
                "body": event.body,
            },
            idempotency_key=f"generated-data-reuse:{event.event_id}",
            references=(event.record_id,),
        )
        receipt = self.memory.write(principal, request)
        if receipt.status.value == "duplicate":
            status = MemoryReuseStatus.DUPLICATE
        elif receipt.status.value not in {"rejected"}:
            status = MemoryReuseStatus.RECORDED
        else:
            status = MemoryReuseStatus.REJECTED
        return MemoryReuseReceipt(
            status=status,
            event_id=event.event_id,
            record_id=event.record_id,
            write_receipt_id=str(receipt.receipt_id),
        )

    def invalidate_by_source(
        self, principal: MemoryPrincipal, payload: dict[str, Any]
    ) -> SourceInvalidationReceipt:
        request_model = SourceInvalidationRequest.model_validate(payload)
        if request_model.repository:
            namespace = f"repository/{request_model.repository}"
        elif principal.write_namespaces:
            namespace = principal.write_namespaces[0]
        else:
            namespace = "default"
        request = MemoryWriteRequest(
            namespace=namespace,
            memory_class=MemoryClass.META,
            content=f"invalidation:{request_model.event_type}",
            provenance=Provenance(
                source="cursor-governance-generated-data",
                source_id=request_model.event_type,
                source_agent_id=principal.agent_id,
                tool="generated-data.invalidate-source",
                extraction_method="source-invalidation/v1",
            ),
            evidence=(
                EvidenceRef(
                    kind=EvidenceKind.EXPLICIT,
                    description="generated-data source invalidation",
                    source_id=request_model.event_type,
                ),
            ),
            tags=("generated-data", "invalidation", request_model.event_type),
            metadata={
                "event_type": request_model.event_type,
                "selector": request_model.selector,
                "deletion": False,
            },
            idempotency_key=(
                f"generated-data-invalidation:{request_model.event_type}:"
                f"{request_model.repository or namespace}"
            ),
        )
        receipt = self.memory.write(principal, request)
        return SourceInvalidationReceipt(
            status=SourceInvalidationStatus.APPLIED
            if receipt.status.value not in {"rejected"}
            else SourceInvalidationStatus.REJECTED,
            event_type=request_model.event_type,
            matched=0,
            write_receipt_id=str(receipt.receipt_id),
        )

    @staticmethod
    def generated_data_capabilities() -> GeneratedDataCapabilityResponse:
        return GeneratedDataCapabilityResponse(
            declared=True,
            store_ready=True,
            commands_registered=True,
            mcp_tools_registered=True,
            write_path=WRITE_PATH,
            ready=True,
        )
