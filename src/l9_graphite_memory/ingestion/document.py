# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ingestion/document.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Conservative document-to-memory importer with exact source line evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import (
    Confidence,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    Provenance,
    SourceRange,
)


class IngestedChunk(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class DocumentIngestor:
    """Create atomic candidates from paragraphs without inventing summaries."""

    @staticmethod
    def _digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def _text_from_path(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".json":
            parsed = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(parsed, indent=2, sort_keys=True)
        if suffix in {".yaml", ".yml"}:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
            return str(yaml.safe_dump(parsed, sort_keys=True))
        return path.read_text(encoding="utf-8")

    @staticmethod
    def chunks(text: str, *, max_chars: int = 4_000) -> tuple[IngestedChunk, ...]:
        lines = text.splitlines()
        chunks: list[IngestedChunk] = []
        buffer: list[str] = []
        start_line = 1

        def flush(end_line: int) -> None:
            nonlocal buffer, start_line
            content = "\n".join(buffer).strip()
            if content:
                chunks.append(
                    IngestedChunk(
                        content=content, start_line=start_line, end_line=end_line
                    )
                )
            buffer = []

        for index, line in enumerate(lines, start=1):
            stripped = line.rstrip()
            if not buffer:
                start_line = index
            candidate = "\n".join([*buffer, stripped]).strip()
            boundary = not stripped and buffer
            if len(candidate) > max_chars and buffer:
                flush(index - 1)
                start_line = index
            if stripped or buffer:
                buffer.append(stripped)
            if boundary:
                flush(index)
        if buffer:
            flush(len(lines) or 1)
        return tuple(chunks)

    def requests(
        self,
        path: str | Path,
        *,
        namespace: str,
        memory_class: MemoryClass = MemoryClass.OBSERVATION,
        repository: str | None = None,
        tags: tuple[str, ...] = (),
        dry_run: bool = False,
    ) -> tuple[MemoryWriteRequest, ...]:
        source_path = Path(path).expanduser().resolve()
        raw = source_path.read_bytes()
        text = self._text_from_path(source_path)
        digest = self._digest(raw)
        requests: list[MemoryWriteRequest] = []
        for chunk in self.chunks(text):
            source_range = SourceRange(
                start_line=chunk.start_line, end_line=chunk.end_line
            )
            requests.append(
                MemoryWriteRequest(
                    namespace=namespace,
                    memory_class=memory_class,
                    content=chunk.content,
                    provenance=Provenance(
                        source="document-import",
                        source_id=str(source_path),
                        source_digest=digest,
                        source_range=source_range,
                        repository=repository,
                        tool="l9-memory import",
                        extraction_method="paragraph-preserving/v1",
                    ),
                    evidence=(
                        EvidenceRef(
                            kind=EvidenceKind.SOURCE_EXCERPT,
                            description=f"Source lines {chunk.start_line}-{chunk.end_line}",
                            source_id=str(source_path),
                            source_digest=digest,
                            source_range=source_range,
                        ),
                    ),
                    confidence=Confidence(score=1.0, evidence_count=1),
                    tags=tuple({*tags, "imported"}),
                    idempotency_key=(
                        f"document:{namespace}:{digest}:{chunk.start_line}:{chunk.end_line}"
                    ),
                    dry_run=dry_run,
                )
            )
        return tuple(requests)
