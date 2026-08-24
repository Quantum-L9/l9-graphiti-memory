# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/evidence.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Evidence, provenance, and confidence contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import ConfidenceMethod, EvidenceKind
from .temporal import utc_now


class SourceRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)


class LineSourceLocator(BaseModel):
    """Line/offset coordinates, structurally equal to ``SourceRange``.

    This is the only locator kind that may accompany a legacy ``source_range``,
    and only when both carry identical coordinates — the pairing rule lives on
    ``Provenance`` and ``EvidenceRef`` because it spans two fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["line"] = "line"
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)

    def matches_range(self, source_range: SourceRange) -> bool:
        return (
            self.start_line == source_range.start_line
            and self.end_line == source_range.end_line
            and self.start_offset == source_range.start_offset
            and self.end_offset == source_range.end_offset
        )


class PdfSourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pdf"] = "pdf"
    page_number: int = Field(ge=1)
    block_index: int = Field(ge=0)


class DocxSourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["docx"] = "docx"
    block_index: int = Field(ge=0)
    block_kind: str = Field(min_length=1, max_length=100)


class PptxSourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pptx"] = "pptx"
    slide_number: int = Field(ge=1)
    shape_index: int = Field(ge=0)


class SpreadsheetSourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["spreadsheet"] = "spreadsheet"
    sheet: str = Field(min_length=1, max_length=300)
    cell_or_range: str = Field(min_length=1, max_length=100)


class NotebookSourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["notebook"] = "notebook"
    cell_index: int = Field(ge=0)
    cell_type: str = Field(min_length=1, max_length=100)


class CsvSourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["csv"] = "csv"
    #: Zero-based row index into the parsed file, header row included.
    row: int = Field(ge=0)


class HtmlSourceLocator(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["html"] = "html"
    #: Index into a stable document-order enumeration of element nodes.
    stable_node_index: int = Field(ge=0)


#: Format-aware source coordinates (ADR-078). ``SourceRange`` keeps carrying
#: line/offset coordinates for text sources exactly as before; this union lets
#: producers preserve truthful PDF/DOCX/PPTX/spreadsheet/notebook/CSV/HTML
#: coordinates instead of fabricating line numbers that never existed.
SourceLocator = Annotated[
    LineSourceLocator
    | PdfSourceLocator
    | DocxSourceLocator
    | PptxSourceLocator
    | SpreadsheetSourceLocator
    | NotebookSourceLocator
    | CsvSourceLocator
    | HtmlSourceLocator,
    Field(discriminator="kind"),
]


def _check_locator_range_pairing(
    source_range: SourceRange | None,
    source_locator: object,
) -> None:
    """Enforce the dual-coordinate rule shared by Provenance and EvidenceRef.

    A record may carry the legacy ``source_range``, a structured
    ``source_locator``, or neither. Carrying both is allowed only when the
    locator is the ``line`` kind and repeats the range exactly — anything else
    would let one evidence row assert two different source positions, and a
    binary locator beside a line range is precisely the fabricated-line-number
    shape this contract exists to prevent.
    """
    if source_range is None or source_locator is None:
        return
    if isinstance(source_locator, LineSourceLocator):
        if not source_locator.matches_range(source_range):
            raise ValueError(
                "source_range and line source_locator must carry identical coordinates"
            )
        return
    # ValueError, not TypeError: this runs inside pydantic model validators,
    # which convert only ValueError into a field ValidationError.
    raise ValueError(
        "source_range cannot accompany a non-line source_locator; "
        "binary coordinates must not be doubled with line coordinates"
    )


class Provenance(BaseModel):
    """Trace a memory back to the exact source and transformation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1, max_length=200)
    source_id: str | None = Field(default=None, max_length=500)
    source_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_range: SourceRange | None = None
    source_locator: SourceLocator | None = None
    source_agent_id: str | None = Field(default=None, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    repository: str | None = Field(default=None, max_length=300)
    tool: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    extraction_method: str = Field(default="direct", max_length=100)
    source_trust: float = Field(default=1.0, ge=0.0, le=1.0)
    transformed_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_locator_pairing(self) -> Provenance:
        _check_locator_range_pairing(self.source_range, self.source_locator)
        return self


class EvidenceRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EvidenceKind
    description: str = Field(min_length=1, max_length=2_000)
    source_id: str | None = Field(default=None, max_length=500)
    source_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_range: SourceRange | None = None
    source_locator: SourceLocator | None = None
    observed_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_locator_pairing(self) -> EvidenceRef:
        _check_locator_range_pairing(self.source_range, self.source_locator)
        return self


class Confidence(BaseModel):
    """Confidence is meaningful only when tied to a method and evidence count."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: float = Field(default=1.0, ge=0.0, le=1.0)
    method: ConfidenceMethod = ConfidenceMethod.EXPLICIT
    evidence_count: int = Field(default=1, ge=0)
    policy_version: str = Field(default="confidence/v1", min_length=1, max_length=100)
    calibrated_at: datetime = Field(default_factory=utc_now)

    @field_validator("evidence_count")
    @classmethod
    def inferred_requires_evidence(cls, value: int, info: object) -> int:
        # Cross-field enforcement is completed by admission; this validator keeps the field sane.
        return value
