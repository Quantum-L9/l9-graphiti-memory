# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_atomic_extraction.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.contracts import EvidenceKind, MemoryClass
from l9_graphite_memory.extraction import (
    DeterministicAtomicExtractor,
    EvidenceBoundProviderExtractor,
)


class Provider:
    def extract(self, _text: str) -> list[dict[str, object]]:
        return [
            {
                "content": "Memory writes require receipts",
                "memory_class": "constraint",
                "start_line": 1,
                "end_line": 1,
                "confidence": 0.9,
            },
            {
                "content": "Invented statement",
                "memory_class": "semantic",
                "start_line": 1,
                "end_line": 1,
            },
        ]


def test_deterministic_extractor_emits_atomic_evidence_bound_candidates() -> None:
    text = "The memory service is canonical.\nOperators prefer typed receipts."
    result = DeterministicAtomicExtractor().extract(text, source_id="source.md")

    assert len(result.candidates) == 2
    assert result.candidates[0].assertion is not None
    assert result.candidates[1].memory_class is MemoryClass.PREFERENCE
    assert result.candidates[0].evidence[0].kind is EvidenceKind.SOURCE_EXCERPT
    assert result.candidates[0].evidence[0].source_digest == result.source_digest


def test_provider_extractor_rejects_ungrounded_candidate() -> None:
    result = EvidenceBoundProviderExtractor(Provider()).extract(
        "Memory writes require receipts",
        source_id="source.md",
    )

    assert len(result.candidates) == 1
    assert len(result.rejected_items) == 1
    assert "not grounded" in result.rejected_items[0]
