# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/extraction/distiller.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Offline evidence-preserving source distillation through canonical writes."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import (
    MemoryPrincipal,
    MemoryWriteRequest,
    OperationStatus,
    Provenance,
    WriteReceipt,
)
from l9_graphite_memory.services import MemoryService

from .atomic import AtomicExtractionResult, DeterministicAtomicExtractor


class AtomicExtractor(Protocol):
    name: str

    def extract(self, text: str, *, source_id: str) -> AtomicExtractionResult: ...


class DistillationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: OperationStatus
    source_id: str
    source_digest: str
    namespace: str
    extractor: str
    candidate_count: int = Field(ge=0)
    written_count: int = Field(ge=0)
    rejected_items: tuple[str, ...] = ()
    write_receipts: tuple[WriteReceipt, ...] = ()


class SourceDistiller:
    """Distill text into atomic candidates and submit every candidate to MemoryService."""

    def __init__(
        self,
        service: MemoryService,
        extractor: AtomicExtractor | None = None,
    ) -> None:
        self.service = service
        self.extractor = extractor or DeterministicAtomicExtractor()

    def distill_text(
        self,
        principal: MemoryPrincipal,
        text: str,
        *,
        source_id: str,
        namespace: str,
        repository: str | None = None,
        dry_run: bool = False,
    ) -> DistillationReceipt:
        result = self.extractor.extract(text, source_id=source_id)
        receipts: list[WriteReceipt] = []
        for candidate in result.candidates:
            request = MemoryWriteRequest(
                namespace=namespace,
                memory_class=candidate.memory_class,
                content=candidate.content,
                assertion=candidate.assertion,
                provenance=Provenance(
                    source="source-distillation",
                    source_id=source_id,
                    source_digest=result.source_digest,
                    source_range=candidate.source_range,
                    source_agent_id=principal.agent_id,
                    repository=repository,
                    tool="l9-memory distill",
                    extraction_method=result.extractor,
                ),
                evidence=candidate.evidence,
                confidence=candidate.confidence,
                tags=("distilled", "atomic"),
                metadata=candidate.metadata,
                idempotency_key=(
                    f"distill:{namespace}:{result.source_digest}:"
                    f"{candidate.source_range.start_line}:{candidate.source_range.end_line}:"
                    f"{candidate.content}"
                ),
                dry_run=dry_run,
            )
            receipts.append(self.service.write(principal, request))
        failed = [receipt for receipt in receipts if receipt.status.value == "rejected"]
        status = (
            OperationStatus.FAILED
            if result.candidates and len(failed) == len(result.candidates)
            else OperationStatus.PARTIAL
            if failed or result.rejected_items
            else OperationStatus.COMPLETE
        )
        return DistillationReceipt(
            status=status,
            source_id=source_id,
            source_digest=result.source_digest,
            namespace=namespace,
            extractor=result.extractor,
            candidate_count=len(result.candidates),
            written_count=sum(receipt.record_id is not None for receipt in receipts),
            rejected_items=result.rejected_items,
            write_receipts=tuple(receipts),
        )

    def distill_path(
        self,
        principal: MemoryPrincipal,
        path: str | Path,
        *,
        namespace: str,
        repository: str | None = None,
        dry_run: bool = False,
    ) -> DistillationReceipt:
        source = Path(path).expanduser().resolve()
        text = source.read_text(encoding="utf-8")
        return self.distill_text(
            principal,
            text,
            source_id=str(source),
            namespace=namespace,
            repository=repository,
            dry_run=dry_run,
        )
