# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/curation/procedural.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic procedural-candidate synthesis with governance review boundary."""

from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import (
    Confidence,
    ConfidenceMethod,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemoryWriteRequest,
    Provenance,
    WriteReceipt,
)
from l9_graphite_memory.ports import RecordStore, SynthesizedProcedure
from l9_graphite_memory.services import MemoryService

_WHEN = re.compile(r"^when\s+(?P<condition>.+?)(?:,|\s+then\s+)(?P<action>.+)$", re.IGNORECASE)


class ProceduralSynthesisReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str
    source_record_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    candidates: tuple[SynthesizedProcedure, ...] = ()
    write_receipts: tuple[WriteReceipt, ...] = ()
    policy_version: str = "procedural-synthesis/v1"


class PatternProceduralSynthesizer:
    """Create candidates only from at least three corroborated successful records."""

    def __init__(self, store: RecordStore, *, minimum_support: int = 3) -> None:
        if minimum_support < 2:
            raise ValueError("minimum_support must be at least 2")
        self.store = store
        self.minimum_support = minimum_support

    @staticmethod
    def _pattern(content: str, metadata: dict[str, object]) -> tuple[str, str] | None:
        condition = metadata.get("procedure_condition")
        action = metadata.get("procedure_action")
        if isinstance(condition, str) and isinstance(action, str) and condition and action:
            return condition.strip(), action.strip()
        match = _WHEN.match(content.strip().rstrip(".!"))
        if match:
            return match.group("condition").strip(), match.group("action").strip()
        return None

    @staticmethod
    def _success(record_tags: tuple[str, ...], metadata: dict[str, object]) -> bool:
        outcome = str(metadata.get("outcome", "")).casefold()
        return outcome in {"success", "passed", "approved"} or bool(
            {"success", "passed", "test-backed"} & set(record_tags)
        )

    def synthesize(self, source_record_ids: tuple[UUID, ...]) -> tuple[SynthesizedProcedure, ...]:
        grouped: dict[tuple[str, str], list[UUID]] = defaultdict(list)
        for record_id in source_record_ids:
            record = self.store.get_record(record_id)
            if record is None or not self._success(record.tags, record.metadata):
                continue
            pattern = self._pattern(record.content, record.metadata)
            if pattern is not None:
                grouped[(pattern[0].casefold(), pattern[1].casefold())].append(record_id)
        candidates: list[SynthesizedProcedure] = []
        for (condition, action), ids in grouped.items():
            unique_ids = tuple(dict.fromkeys(ids))
            if len(unique_ids) < self.minimum_support:
                continue
            confidence = min(0.99, 0.55 + 0.1 * len(unique_ids))
            candidates.append(
                SynthesizedProcedure(
                    name=f"procedure-{len(candidates) + 1}",
                    condition=condition,
                    action=action,
                    confidence=confidence,
                    source_record_ids=unique_ids,
                )
            )
        return tuple(candidates)


class ProceduralSynthesisWorker:
    """Persist reviewable META candidates; never auto-promote them to PROCEDURAL."""

    def __init__(self, service: MemoryService, synthesizer: PatternProceduralSynthesizer) -> None:
        self.service = service
        self.synthesizer = synthesizer

    def run(
        self,
        principal: MemoryPrincipal,
        *,
        namespace: str,
        source_record_ids: tuple[UUID, ...],
        dry_run: bool = False,
    ) -> ProceduralSynthesisReport:
        candidates = self.synthesizer.synthesize(source_record_ids)
        receipts: list[WriteReceipt] = []
        for candidate in candidates:
            evidence = tuple(
                EvidenceRef(
                    kind=EvidenceKind.AGGREGATION,
                    description="Successful source record supporting procedural candidate",
                    source_id=str(record_id),
                )
                for record_id in candidate.source_record_ids
            )
            receipts.append(
                self.service.write(
                    principal,
                    MemoryWriteRequest(
                        namespace=namespace,
                        memory_class=MemoryClass.META,
                        content=f"When {candidate.condition}, {candidate.action}",
                        provenance=Provenance(
                            source="procedural-synthesis",
                            source_id=str(candidate.source_record_ids[0]),
                            source_agent_id=principal.agent_id,
                            tool="ProceduralSynthesisWorker",
                            extraction_method="procedural-synthesis/v1",
                        ),
                        evidence=evidence,
                        confidence=Confidence(
                            score=candidate.confidence,
                            method=ConfidenceMethod.AGGREGATED,
                            evidence_count=len(evidence),
                            policy_version="procedural-synthesis-confidence/v1",
                        ),
                        tags=("procedural-candidate", "governance-review-required"),
                        metadata={
                            "candidate_target_class": MemoryClass.PROCEDURAL.value,
                            "procedure_condition": candidate.condition,
                            "procedure_action": candidate.action,
                            "source_record_ids": [
                                str(item) for item in candidate.source_record_ids
                            ],
                        },
                        references=candidate.source_record_ids,
                        idempotency_key=(
                            f"procedural-candidate:{namespace}:{candidate.condition}:{candidate.action}"
                        ),
                        dry_run=dry_run,
                    ),
                )
            )
        return ProceduralSynthesisReport(
            namespace=namespace,
            source_record_count=len(source_record_ids),
            candidate_count=len(candidates),
            candidates=candidates,
            write_receipts=tuple(receipts),
        )
