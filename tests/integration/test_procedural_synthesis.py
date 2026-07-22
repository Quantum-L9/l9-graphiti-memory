# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_procedural_synthesis.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.contracts import MemoryWriteRequest, Provenance
from l9_graphite_memory.curation.procedural import (
    PatternProceduralSynthesizer,
    ProceduralSynthesisWorker,
)


def test_procedural_synthesis_emits_review_candidate_not_auto_promoted(
    memory_service,
    principal,
) -> None:
    source_ids = []
    for index in range(3):
        receipt = memory_service.write(
            principal,
            MemoryWriteRequest(
                namespace="repo-a",
                content="When validation fails, stop the release",
                provenance=Provenance(source="test", source_id=str(index)),
                tags=("success", "test-backed"),
                metadata={
                    "outcome": "success",
                    "procedure_condition": "validation fails",
                    "procedure_action": "stop the release",
                },
                idempotency_key=f"source-{index}",
            ),
        )
        source_ids.append(receipt.record_id)

    report = ProceduralSynthesisWorker(
        memory_service,
        PatternProceduralSynthesizer(memory_service.store),
    ).run(
        principal,
        namespace="repo-a",
        source_record_ids=tuple(source_ids),
    )

    assert report.candidate_count == 1
    assert len(report.write_receipts) == 1
    candidate = memory_service.get(principal, report.write_receipts[0].record_id)
    assert candidate is not None
    assert candidate.memory_class.value == "meta"
    assert "governance-review-required" in candidate.tags
    assert candidate.references == tuple(source_ids)
