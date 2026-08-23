# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/test_source_locator_roundtrip.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Store-conformance suite for structured source locators (ADR-078).

Every canonical backend must persist a record's provenance and evidence
locators byte-for-byte and hand them back on read, and a 2.1.0-era record —
which never carried the field — must upcast to the current schema with the
locator absent rather than fabricated.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import NullProjection
from l9_graphite_memory.contracts import (
    CsvSourceLocator,
    DocxSourceLocator,
    EvidenceRef,
    HtmlSourceLocator,
    MemoryClass,
    MemoryWriteRequest,
    NotebookSourceLocator,
    PdfSourceLocator,
    PptxSourceLocator,
    Provenance,
    SpreadsheetSourceLocator,
)
from l9_graphite_memory.contracts.enums import EvidenceKind
from l9_graphite_memory.schema import schema_registry
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION
from tests.conftest import STORE_BACKENDS, make_store

EVIDENCE_LOCATORS = (
    PdfSourceLocator(page_number=12, block_index=3),
    DocxSourceLocator(block_index=8, block_kind="table"),
    PptxSourceLocator(slide_number=2, shape_index=4),
    SpreadsheetSourceLocator(sheet="Forecast", cell_or_range="B2:F9"),
    NotebookSourceLocator(cell_index=7, cell_type="code"),
    CsvSourceLocator(row=19),
    HtmlSourceLocator(stable_node_index=311),
)


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_locators_roundtrip_through_every_canonical_backend(
    tmp_path: Path, principal, backend: str
) -> None:
    store = make_store(backend, tmp_path)
    service = MemoryService(store, NullProjection())
    service.initialize()
    try:
        request = MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.SEMANTIC,
            content="structured locator roundtrip",
            provenance=Provenance(
                source="conformance",
                source_locator=PdfSourceLocator(page_number=12, block_index=3),
            ),
            evidence=tuple(
                EvidenceRef(
                    kind=EvidenceKind.SOURCE_EXCERPT,
                    description=f"{locator.kind} coordinates",
                    source_locator=locator,
                )
                for locator in EVIDENCE_LOCATORS
            ),
        )
        receipt = service.write(principal, request)
        record = service.get(principal, receipt.record_id)
        assert record.schema_version == MEMORY_SCHEMA_VERSION
        assert record.provenance.source_locator == request.provenance.source_locator
        assert tuple(item.source_locator for item in record.evidence) == (
            EVIDENCE_LOCATORS
        )
        assert all(item.source_range is None for item in record.evidence)
    finally:
        store.close()


def test_pre_locator_record_upcasts_with_locator_absent() -> None:
    raw = {
        "record_id": "5f0f4a52-3f0f-4bcb-9c5e-2f2c8a34d5aa",
        "schema_version": "2.1.0",
        "tenant_id": "tenant-a",
        "namespace": "repo-a",
        "memory_class": "observation",
        "content": "written before locators existed",
        "assertion": None,
        "temporal": {
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": None,
            "recorded_at": "2026-01-01T00:00:00Z",
            "source_observed_at": None,
            "superseded_at": None,
        },
        "provenance": {
            "source": "legacy",
            "source_range": {"start_line": 3, "end_line": 5},
            "transformed_at": "2026-01-01T00:00:00Z",
        },
        "evidence": [
            {
                "kind": "explicit",
                "description": "legacy evidence",
                "observed_at": "2026-01-01T00:00:00Z",
            }
        ],
        "confidence": {
            "score": 1.0,
            "method": "explicit",
            "evidence_count": 1,
            "policy_version": "confidence/v1",
            "calibrated_at": "2026-01-01T00:00:00Z",
        },
        "state": "active",
        "normalized_digest": "a" * 64,
        "original_digest": "b" * 64,
        "idempotency_key": "legacy-upcast-check",
        "created_by": "tester",
        "created_at": "2026-01-01T00:00:00Z",
    }
    record = schema_registry.read_record(raw)
    assert record.schema_version == MEMORY_SCHEMA_VERSION
    assert record.provenance.source_locator is None
    assert record.provenance.source_range is not None
    assert record.evidence[0].source_locator is None
