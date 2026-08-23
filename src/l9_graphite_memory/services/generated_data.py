# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/services/generated_data.py
#   layer: service
#   owner: memory-control-plane
#   status: active
#   version: 1.1.0
#   updated: 2026-08-23

"""Narrow generated-data operations. Durable writes use MemoryService.write only."""

from __future__ import annotations

from typing import Any

from l9_graphite_memory.contracts import (
    Confidence,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemorySearchRequest,
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
        knowledge = candidate.knowledge.model_dump(mode="json")
        source = candidate.source.model_dump(mode="json")
        request = MemoryWriteRequest(
            namespace=namespace,
            memory_class=MemoryClass.SEMANTIC,
            content=candidate.knowledge.statement,
            provenance=Provenance(
                source="cursor-governance-generated-data",
                source_id=candidate.candidate_id,
                source_agent_id=candidate.provenance.source_agent_id
                or principal.agent_id,
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
            confidence=Confidence(
                score=candidate.knowledge.confidence,
                evidence_count=max(
                    1,
                    len(
                        payload.get("provenance", {}).get("source_evidence", [])
                        if isinstance(payload.get("provenance"), dict)
                        else []
                    ),
                ),
            ),
            tags=("generated-data", candidate.knowledge.primary_class),
            metadata={
                "generated_data_kind": candidate.kind,
                "primary_class": candidate.knowledge.primary_class,
                "candidate_id": candidate.candidate_id,
                "repository": candidate.source.repository,
                "campaign_id": candidate.source.campaign_id,
                "source_sha": candidate.source.resolved_sha(),
                "scope": knowledge.get("scope") or {},
                "epistemic_status": knowledge.get("epistemic_status", "observed"),
                "invalidation_conditions": candidate.knowledge.invalidation_conditions,
                "visibility": candidate.source.visibility
                or candidate.governance.visibility,
                "authority_class": candidate.governance.authority_class,
                "source": source,
            },
            idempotency_key=f"generated-data:{candidate.candidate_id}",
        )
        receipt = self.memory.write(principal, request)
        raw_status = receipt.status.value
        if raw_status == "duplicate":
            status = MemoryCandidateIngestionStatus.DUPLICATE
        elif raw_status == "quarantined":
            status = MemoryCandidateIngestionStatus.QUARANTINED
        elif raw_status == "rejected":
            status = MemoryCandidateIngestionStatus.REJECTED
        else:
            status = MemoryCandidateIngestionStatus.ADMITTED
        return MemoryCandidateIngestionResult(
            status=status,
            candidate_id=candidate.candidate_id,
            namespace=namespace,
            record_id=receipt.record_id,
            write_receipt_id=str(receipt.receipt_id),
            storage_committed=raw_status != "rejected",
            memory_state=(
                "quarantined"
                if status is MemoryCandidateIngestionStatus.QUARANTINED
                else "active"
                if status is MemoryCandidateIngestionStatus.ADMITTED
                else "existing"
                if status is MemoryCandidateIngestionStatus.DUPLICATE
                else "rejected"
            ),
            reason=(
                "write rejected"
                if status is MemoryCandidateIngestionStatus.REJECTED
                else "admission quarantined candidate"
                if status is MemoryCandidateIngestionStatus.QUARANTINED
                else None
            ),
        )

    @staticmethod
    def _context_candidate(hit: Any, *, repository: str) -> dict[str, Any]:
        record = hit.record
        metadata = dict(record.metadata or {})
        scope = metadata.get("scope") if isinstance(metadata.get("scope"), dict) else {}
        confidence = getattr(record.confidence, "score", record.confidence)
        state = getattr(record.state, "value", str(record.state))
        return {
            "record_id": str(record.record_id),
            "text": record.content,
            "score": float(hit.score),
            "confidence": float(confidence),
            "state": str(state),
            "authority_class": str(metadata.get("authority_class", "advisory")),
            "visibility": str(metadata.get("visibility", "repository_local")),
            "repository": str(metadata.get("repository", repository)),
            "source_sha": metadata.get("source_sha"),
            "paths": list(scope.get("paths") or []),
            "task_types": list(scope.get("task_types") or []),
            "roles": list(scope.get("roles") or []),
            "epistemic_status": str(metadata.get("epistemic_status", "observed")),
            "invalidated": str(state) in {
                "archived",
                "deleted",
                "deletion_pending",
                "superseded",
                "rejected",
            },
            "metadata": metadata,
        }

    def search_context(
        self, principal: MemoryPrincipal, payload: dict[str, Any]
    ) -> dict[str, Any]:
        repository = str(payload.get("repository") or "").strip()
        namespace = str(payload.get("namespace") or "").strip()
        if not namespace:
            if not repository:
                raise ValueError("repository or namespace is required")
            namespace = f"repository/{repository}"
        receipt = self.memory.search(
            principal,
            MemorySearchRequest(
                query=str(payload.get("query") or payload.get("task") or "generated data"),
                namespaces=(namespace,),
                min_confidence=float(payload.get("minimum_confidence", 0.0)),
                limit=max(1, int(payload.get("max_items", payload.get("limit", 12)))),
                token_budget=(
                    max(1, int(payload["max_characters"]) // 4)
                    if payload.get("max_characters") is not None
                    else None
                ),
                include_superseded=bool(payload.get("include_historical", False)),
                include_archived=bool(payload.get("include_invalidated", False)),
            ),
        )
        candidates = [
            self._context_candidate(hit, repository=repository)
            for hit in receipt.hits
        ]
        return {
            "schema_version": "1.0.0",
            "available": receipt.status.value != "failed",
            "source": "l9-graphiti-memory",
            "request_id": str(receipt.receipt_id),
            "candidates": candidates,
            "result_digest": receipt.result_digest,
            "status": receipt.status.value,
        }

    def hydrate_context(
        self, principal: MemoryPrincipal, payload: dict[str, Any]
    ) -> dict[str, Any]:
        result = self.search_context(principal, payload)
        result["kind"] = "GeneratedDataHydrationResult"
        result["records"] = list(result["candidates"])
        return result

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
