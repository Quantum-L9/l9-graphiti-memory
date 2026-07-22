# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/admission/normalization.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deterministic normalization, hashing, redaction, and safety signals."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_ZERO_WIDTH = re.compile("[\u200b\u200c\u200d\ufeff]")
_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL_REDACTED]",
    ),
    (
        "phone",
        re.compile(
            r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"
        ),
        "[PHONE_REDACTED]",
    ),
    ("ssn", re.compile(r"\b\d{3}[\-\s]?\d{2}[\-\s]?\d{4}\b"), "[SSN_REDACTED]"),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[SECRET_REDACTED]"),
    (
        "bearer",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{20,}"),
        "Bearer [SECRET_REDACTED]",
    ),
)

_INJECTION_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(
            r"(?i)ignore\s+(?:all\s+)?(?:(?:previous|prior)\s+)?(?:system\s+)?instructions"
        ),
    ),
    (
        "reveal_prompt",
        re.compile(r"(?i)(reveal|print|show)\s+(the\s+)?(system|developer)\s+prompt"),
    ),
    (
        "credential_exfiltration",
        re.compile(
            r"(?i)(dump|exfiltrate|print)\s+.*(secret|token|credential|api[ _-]?key)"
        ),
    ),
)


class NormalizationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    normalized_content: str
    redacted_content: str
    original_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    normalized_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    pii_types: tuple[str, ...] = ()
    safety_signals: tuple[str, ...] = ()


def canonical_json(value: Any) -> str:
    """Stable JSON for digests and receipts."""

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    )
    normalized = _ZERO_WIDTH.sub("", normalized)
    normalized = "\n".join(
        _WHITESPACE.sub(" ", line).rstrip() for line in normalized.splitlines()
    )
    return _BLANK_LINES.sub("\n\n", normalized).strip()


def normalize_candidate(
    content: str, *, context: dict[str, Any] | None = None
) -> NormalizationResult:
    normalized = normalize_text(content)
    redacted = normalized
    pii_types: list[str] = []
    for pii_type, pattern, replacement in _PII_PATTERNS:
        if pattern.search(redacted):
            pii_types.append(pii_type)
            redacted = pattern.sub(replacement, redacted)
    signals = tuple(
        name for name, pattern in _INJECTION_MARKERS if pattern.search(normalized)
    )
    digest_payload = {"content": redacted, "context": context or {}}
    return NormalizationResult(
        normalized_content=normalized,
        redacted_content=redacted,
        original_digest=sha256_text(content),
        normalized_digest=sha256_text(canonical_json(digest_payload)),
        pii_types=tuple(sorted(set(pii_types))),
        safety_signals=signals,
    )
