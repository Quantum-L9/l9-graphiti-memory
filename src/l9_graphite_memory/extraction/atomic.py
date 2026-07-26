# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/extraction/atomic.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Evidence-bound atomic memory extraction."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import (
    Confidence,
    ConfidenceMethod,
    EvidenceKind,
    EvidenceRef,
    MemoryAssertion,
    MemoryClass,
    SourceRange,
)

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_ASSERTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^(?P<subject>.+?)\s+(?:is|are|was|were)\s+(?P<object>.+)$", re.IGNORECASE),
        "is",
    ),
    (re.compile(r"^(?P<subject>.+?)\s+prefers?\s+(?P<object>.+)$", re.IGNORECASE), "prefers"),
    (re.compile(r"^(?P<subject>.+?)\s+uses?\s+(?P<object>.+)$", re.IGNORECASE), "uses"),
    (re.compile(r"^(?P<subject>.+?)\s+requires?\s+(?P<object>.+)$", re.IGNORECASE), "requires"),
)


class AtomicMemoryCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str = Field(min_length=1, max_length=8_000)
    memory_class: MemoryClass
    assertion: MemoryAssertion | None = None
    confidence: Confidence
    evidence: tuple[EvidenceRef, ...]
    source_range: SourceRange
    metadata: dict[str, Any] = Field(default_factory=dict)


class AtomicExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: str
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidates: tuple[AtomicMemoryCandidate, ...] = ()
    rejected_items: tuple[str, ...] = ()
    extractor: str


class StructuredExtractionProvider(Protocol):
    """Provider returns JSON-compatible candidate dictionaries with source lines."""

    def extract(self, text: str) -> list[dict[str, Any]]: ...


class DeterministicAtomicExtractor:
    """Extract sentence-sized candidates without inventing missing content."""

    name = "deterministic-atomic/v1"

    @staticmethod
    def _classify(sentence: str) -> MemoryClass:
        lowered = sentence.casefold()
        if any(
            token in lowered
            for token in (" prefer ", " prefers ", " preference ", " likes ")
        ):
            return MemoryClass.PREFERENCE
        if any(
            token in lowered for token in (" must ", " shall ", " never ", " required ")
        ):
            return MemoryClass.CONSTRAINT
        if any(token in lowered for token in (" decided ", " decision ", " approved ")):
            return MemoryClass.DECISION
        if lowered.startswith("when ") and any(
            token in lowered for token in (" then ", ", do ", " should ")
        ):
            return MemoryClass.PROCEDURAL
        if any(
            token in lowered for token in (" observed ", " happened ", " occurred ")
        ):
            return MemoryClass.EPISODIC
        return MemoryClass.SEMANTIC

    @staticmethod
    def _assertion(sentence: str) -> MemoryAssertion | None:
        cleaned = sentence.strip().rstrip(".!?")
        for pattern, predicate in _ASSERTION_PATTERNS:
            match = pattern.match(cleaned)
            if match:
                return MemoryAssertion(
                    subject=match.group("subject").strip(),
                    predicate=predicate,
                    object=match.group("object").strip(),
                )
        return None

    def extract(self, text: str, *, source_id: str) -> AtomicExtractionResult:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        candidates: list[AtomicMemoryCandidate] = []
        rejected: list[str] = []
        line_cursor = 1
        for raw in _SENTENCE.split(text):
            sentence = raw.strip()
            line_count = max(1, raw.count("\n") + 1)
            start_line = line_cursor
            end_line = line_cursor + line_count - 1
            line_cursor = end_line + 1
            if len(sentence) < 8:
                if sentence:
                    rejected.append(
                        f"source lines {start_line}-{end_line}: below minimum length"
                    )
                continue
            source_range = SourceRange(start_line=start_line, end_line=end_line)
            evidence = EvidenceRef(
                kind=EvidenceKind.SOURCE_EXCERPT,
                description=f"Exact source lines {start_line}-{end_line}",
                source_id=source_id,
                source_digest=digest,
                source_range=source_range,
            )
            candidates.append(
                AtomicMemoryCandidate(
                    content=sentence,
                    memory_class=self._classify(f" {sentence} "),
                    assertion=self._assertion(sentence),
                    confidence=Confidence(
                        score=0.85,
                        method=ConfidenceMethod.EXTRACTED,
                        evidence_count=1,
                        policy_version="atomic-extraction-confidence/v1",
                    ),
                    evidence=(evidence,),
                    source_range=source_range,
                    metadata={"extractor": self.name},
                )
            )
        return AtomicExtractionResult(
            source_id=source_id,
            source_digest=digest,
            candidates=tuple(candidates),
            rejected_items=tuple(rejected),
            extractor=self.name,
        )


class EvidenceBoundProviderExtractor:
    """Validate provider output and reject any candidate without exact source evidence."""

    name = "evidence-bound-provider/v1"

    def __init__(self, provider: StructuredExtractionProvider) -> None:
        self.provider = provider

    def extract(self, text: str, *, source_id: str) -> AtomicExtractionResult:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        candidates: list[AtomicMemoryCandidate] = []
        rejected: list[str] = []
        lines = text.splitlines()
        for index, item in enumerate(self.provider.extract(text), start=1):
            try:
                start_line = int(item["start_line"])
                end_line = int(item["end_line"])
                if (
                    start_line < 1
                    or end_line < start_line
                    or end_line > max(1, len(lines))
                ):
                    raise ValueError("source range is outside the input")
                content = str(item["content"]).strip()
                excerpt = "\n".join(lines[start_line - 1 : end_line]).strip()
                if not content or content.casefold() not in excerpt.casefold():
                    raise ValueError(
                        "candidate content is not grounded in the declared source range"
                    )
                memory_class = MemoryClass(str(item.get("memory_class", "semantic")))
                source_range = SourceRange(start_line=start_line, end_line=end_line)
                assertion_data = item.get("assertion")
                assertion = (
                    MemoryAssertion.model_validate(assertion_data)
                    if assertion_data
                    else None
                )
                confidence_score = float(item.get("confidence", 0.7))
                candidates.append(
                    AtomicMemoryCandidate(
                        content=content,
                        memory_class=memory_class,
                        assertion=assertion,
                        confidence=Confidence(
                            score=confidence_score,
                            method=ConfidenceMethod.EXTRACTED,
                            evidence_count=1,
                            policy_version="provider-extraction-confidence/v1",
                        ),
                        evidence=(
                            EvidenceRef(
                                kind=EvidenceKind.SOURCE_EXCERPT,
                                description=f"Provider-grounded source lines {start_line}-{end_line}",
                                source_id=source_id,
                                source_digest=digest,
                                source_range=source_range,
                            ),
                        ),
                        source_range=source_range,
                        metadata={"extractor": self.name},
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                rejected.append(f"candidate {index}: {exc}")
        return AtomicExtractionResult(
            source_id=source_id,
            source_digest=digest,
            candidates=tuple(candidates),
            rejected_items=tuple(rejected),
            extractor=self.name,
        )
