# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_source_locator_contract.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Structured source-locator contract suite (ADR-078).

The locator union lets evidence keep truthful format-specific coordinates
(PDF pages, DOCX blocks, PPTX shapes, spreadsheet cells, notebook cells, CSV
rows, HTML nodes) instead of fabricating line numbers. These tests pin the
validation surface: required components, coordinate sign rules, the
dual-coordinate pairing rule, and backward compatibility of plain
``source_range`` requests.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from l9_graphite_memory.contracts import (
    CsvSourceLocator,
    DocxSourceLocator,
    EvidenceRef,
    HtmlSourceLocator,
    LineSourceLocator,
    MemoryWriteRequest,
    NotebookSourceLocator,
    PdfSourceLocator,
    PptxSourceLocator,
    Provenance,
    SourceLocator,
    SourceRange,
    SpreadsheetSourceLocator,
)
from l9_graphite_memory.contracts.enums import EvidenceKind

LOCATOR_ADAPTER: TypeAdapter[SourceLocator] = TypeAdapter(SourceLocator)

VALID_LOCATORS = (
    LineSourceLocator(start_line=3, end_line=9, start_offset=0, end_offset=120),
    PdfSourceLocator(page_number=4, block_index=2),
    DocxSourceLocator(block_index=17, block_kind="paragraph"),
    PptxSourceLocator(slide_number=6, shape_index=1),
    SpreadsheetSourceLocator(sheet="Q3", cell_or_range="B2:D14"),
    NotebookSourceLocator(cell_index=5, cell_type="code"),
    CsvSourceLocator(row=42),
    HtmlSourceLocator(stable_node_index=118),
)


@pytest.mark.parametrize("locator", VALID_LOCATORS, ids=lambda item: item.kind)
def test_each_locator_kind_roundtrips_through_the_union(locator) -> None:
    parsed = LOCATOR_ADAPTER.validate_python(locator.model_dump(mode="json"))
    assert parsed == locator


def test_unknown_locator_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LOCATOR_ADAPTER.validate_python({"kind": "microfilm", "reel": 3})


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "pdf", "page_number": 0, "block_index": 0},
        {"kind": "pdf", "page_number": -1, "block_index": 0},
        {"kind": "pptx", "slide_number": 0, "shape_index": 0},
        {"kind": "pptx", "slide_number": -3, "shape_index": 0},
        {"kind": "notebook", "cell_index": -1, "cell_type": "code"},
        {"kind": "csv", "row": -1},
        {"kind": "html", "stable_node_index": -1},
        {"kind": "docx", "block_index": -1, "block_kind": "paragraph"},
    ],
    ids=lambda item: f"{item['kind']}-negative",
)
def test_negative_coordinates_are_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        LOCATOR_ADAPTER.validate_python(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "pdf", "page_number": 1},
        {"kind": "pdf", "block_index": 0},
        {"kind": "docx", "block_index": 0},
        {"kind": "pptx", "slide_number": 1},
        {"kind": "spreadsheet", "sheet": "Q3"},
        {"kind": "spreadsheet", "cell_or_range": "A1"},
        {"kind": "notebook", "cell_index": 0},
        {"kind": "csv"},
        {"kind": "html"},
    ],
    ids=lambda item: f"{item['kind']}-missing-component",
)
def test_missing_required_locator_components_are_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        LOCATOR_ADAPTER.validate_python(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "spreadsheet", "sheet": "", "cell_or_range": "A1"},
        {"kind": "spreadsheet", "sheet": "Q3", "cell_or_range": ""},
    ],
    ids=("empty-sheet", "empty-cell-or-range"),
)
def test_empty_spreadsheet_components_are_rejected(payload: dict) -> None:
    with pytest.raises(ValidationError):
        LOCATOR_ADAPTER.validate_python(payload)


def test_extra_locator_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LOCATOR_ADAPTER.validate_python(
            {"kind": "pdf", "page_number": 1, "block_index": 0, "line": 4}
        )


@pytest.mark.parametrize("carrier", ("provenance", "evidence"))
def test_binary_locator_beside_source_range_is_rejected(carrier: str) -> None:
    source_range = SourceRange(start_line=1, end_line=2)
    locator = PdfSourceLocator(page_number=1, block_index=0)
    with pytest.raises(ValidationError, match="non-line source_locator"):
        if carrier == "provenance":
            Provenance(source="test", source_range=source_range, source_locator=locator)
        else:
            EvidenceRef(
                kind=EvidenceKind.EXPLICIT,
                description="binary evidence",
                source_range=source_range,
                source_locator=locator,
            )


@pytest.mark.parametrize("carrier", ("provenance", "evidence"))
def test_line_locator_with_equal_range_is_accepted(carrier: str) -> None:
    source_range = SourceRange(start_line=4, end_line=9, start_offset=0, end_offset=55)
    locator = LineSourceLocator(start_line=4, end_line=9, start_offset=0, end_offset=55)
    if carrier == "provenance":
        model = Provenance(
            source="test", source_range=source_range, source_locator=locator
        )
        assert model.source_locator == locator
    else:
        model = EvidenceRef(
            kind=EvidenceKind.EXPLICIT,
            description="line evidence",
            source_range=source_range,
            source_locator=locator,
        )
        assert model.source_locator == locator


@pytest.mark.parametrize("carrier", ("provenance", "evidence"))
def test_line_locator_with_diverging_range_is_rejected(carrier: str) -> None:
    source_range = SourceRange(start_line=4, end_line=9)
    locator = LineSourceLocator(start_line=4, end_line=10)
    with pytest.raises(ValidationError, match="identical coordinates"):
        if carrier == "provenance":
            Provenance(source="test", source_range=source_range, source_locator=locator)
        else:
            EvidenceRef(
                kind=EvidenceKind.EXPLICIT,
                description="diverging evidence",
                source_range=source_range,
                source_locator=locator,
            )


def test_source_range_only_requests_are_accepted_unchanged() -> None:
    request = MemoryWriteRequest(
        namespace="repo-a",
        content="pre-locator request shape",
        provenance=Provenance(source="test", source_range=SourceRange(start_line=1)),
        evidence=(
            EvidenceRef(
                kind=EvidenceKind.EXPLICIT,
                description="legacy evidence",
                source_range=SourceRange(start_line=1, end_line=3),
            ),
        ),
    )
    assert request.provenance.source_locator is None
    assert request.evidence[0].source_locator is None


def test_no_coordinates_at_all_remains_accepted() -> None:
    provenance = Provenance(source="test")
    assert provenance.source_range is None
    assert provenance.source_locator is None


def test_locator_only_requests_are_accepted() -> None:
    request = MemoryWriteRequest(
        namespace="repo-a",
        content="structured coordinates without a line range",
        provenance=Provenance(
            source="test",
            source_locator=SpreadsheetSourceLocator(sheet="Data", cell_or_range="C7"),
        ),
        evidence=(
            EvidenceRef(
                kind=EvidenceKind.EXPLICIT,
                description="cell evidence",
                source_locator=NotebookSourceLocator(
                    cell_index=2, cell_type="markdown"
                ),
            ),
        ),
    )
    assert request.provenance.source_locator.kind == "spreadsheet"
    assert request.evidence[0].source_locator.kind == "notebook"
