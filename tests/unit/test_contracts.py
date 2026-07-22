# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_contracts.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.contracts import (
    Confidence,
    ConfidenceMethod,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    Provenance,
    TemporalCoordinates,
)


def test_temporal_rejects_inverted_validity() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="valid_to"):
        TemporalCoordinates(valid_from=now, valid_to=now - timedelta(seconds=1))


def test_inferred_request_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires evidence"):
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.INSIGHT,
            content="inferred content",
            provenance=Provenance(source="test"),
            confidence=Confidence(method=ConfidenceMethod.INFERRED, evidence_count=0),
        )


def test_inferred_request_accepts_matching_evidence() -> None:
    request = MemoryWriteRequest(
        namespace="repo-a",
        memory_class=MemoryClass.INSIGHT,
        content="inferred content",
        provenance=Provenance(source="test"),
        evidence=(
            EvidenceRef(
                kind=EvidenceKind.INFERENCE,
                description="derived from three observations",
            ),
        ),
        confidence=Confidence(method=ConfidenceMethod.INFERRED, evidence_count=1),
    )
    assert request.memory_class is MemoryClass.INSIGHT
