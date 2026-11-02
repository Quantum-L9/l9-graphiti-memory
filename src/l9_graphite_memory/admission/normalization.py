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

_PHONE_REPLACEMENT = "[PHONE_REDACTED]"
_SSN_REPLACEMENT = "[SSN_REDACTED]"

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL_REDACTED]",
    ),
    (
        "phone",
        # A North American number in every shape main redacted: E.164 or a
        # bare leading 1 (with or without separators), a parenthesized area
        # code, or a 3-3-4 grouping with at least one separator. A bare
        # unprefixed 10-digit run is deliberately absent: it is as likely an
        # epoch or an identifier, so it takes the ambiguous path below and is
        # held redacted until the caller declares what it is.
        #
        # The fully compact leading-1 form (``1`` and ten digits, no separator)
        # is excluded here and handled by the next entry, because only that
        # shape also occurs inside hex and other alphanumeric identifiers.
        re.compile(
            r"(?<!\d)(?:"
            r"(?!1\d{10}(?!\d))\+?1[\s.\-]?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}"
            r"|\(\d{3}\)[\s.\-]?\d{3}[\s.\-]?\d{4}"
            r"|\d{3}[\s.\-]\d{3}[\s.\-]?\d{4}"
            r"|\d{3}[\s.\-]?\d{3}[\s.\-]\d{4}"
            r")(?!\d)"
        ),
        _PHONE_REPLACEMENT,
    ),
    (
        "phone",
        # The compact leading-1 form only when it stands as its own token.
        # Boundaries are alphanumeric, like the ambiguous path below, so
        # ``...5b12125551212c...`` inside a hex digest or uuid is an identifier
        # and is left intact, while ``call 12125551212`` is still redacted.
        # Forms with a separator, parentheses or ``+`` stay on the entry above.
        re.compile(r"(?<![0-9A-Za-z])1\d{10}(?![0-9A-Za-z])"),
        _PHONE_REPLACEMENT,
    ),
    (
        # Any 3-2-4 grouping with at least one separator. A bare 9-digit run
        # takes the ambiguous path, never the raw-storage path.
        "ssn",
        re.compile(r"(?<!\d)\d{3}(?:[\-\s]\d{2}[\-\s]?|\d{2}[\-\s])\d{4}(?!\d)"),
        _SSN_REPLACEMENT,
    ),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "[SECRET_REDACTED]"),
    (
        "bearer",
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/=]{20,}"),
        "Bearer [SECRET_REDACTED]",
    ),
)

#: A bare 9- or 10-digit run standing as its own token. The boundaries are
#: alphanumeric, not merely numeric, so a digit run inside a hex digest or an
#: alphanumeric identifier (``...5592efd3e0327150681ba...``) is not a token.
_AMBIGUOUS_NUMERIC = re.compile(r"(?<![0-9A-Za-z])(\d{9}|\d{10})(?![0-9A-Za-z])")
_RESOLVED_NUMERIC = frozenset({"epoch", "identifier", "phone", "ssn"})
#: Normalization-context (and write-request metadata) key naming what each
#: bare 9/10-digit token is. Raw tokens are its keys: never persist it.
NUMERIC_DECLARATIONS_KEY = "numeric_declarations"
#: Undeclared ambiguous tokens are stored redacted (ADR-080: quarantine holds
#: redacted PII) and named in ``pii_types`` so automated release is blocked.
AMBIGUOUS_NUMERIC_PII_TYPE = "ambiguous_numeric"
_AMBIGUOUS_REPLACEMENT = "[AMBIGUOUS_NUMERIC_REDACTED]"
_KEPT_NUMERIC = frozenset({"epoch", "identifier"})
_DECLARED_PII_REPLACEMENT = {"phone": _PHONE_REPLACEMENT, "ssn": _SSN_REPLACEMENT}

_INJECTION_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_instructions",
        re.compile(r"(?i)ignore\s+(?:all\s+)?(?:(?:previous|prior)\s+)?(?:system\s+)?instructions"),
    ),
    (
        "reveal_prompt",
        re.compile(r"(?i)(reveal|print|show)\s+(the\s+)?(system|developer)\s+prompt"),
    ),
    (
        "credential_exfiltration",
        re.compile(r"(?i)(dump|exfiltrate|print)\s+.*(secret|token|credential|api[ _-]?key)"),
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
    unresolved_ambiguous: tuple[str, ...] = ()


def canonical_json(value: Any) -> str:
    """Stable JSON for digests and receipts."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    normalized = _ZERO_WIDTH.sub("", normalized)
    normalized = "\n".join(_WHITESPACE.sub(" ", line).rstrip() for line in normalized.splitlines())
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
    declarations = _numeric_declarations(context)
    unresolved: list[str] = []

    def _resolve(match: re.Match[str]) -> str:
        token = match.group(0)
        declared = declarations.get(token)
        if declared in _KEPT_NUMERIC:
            return token
        if declared in _DECLARED_PII_REPLACEMENT:
            pii_types.append(declared)
            return _DECLARED_PII_REPLACEMENT[declared]
        unresolved.append(token)
        pii_types.append(AMBIGUOUS_NUMERIC_PII_TYPE)
        return _AMBIGUOUS_REPLACEMENT

    # The digest is taken before undeclared tokens are masked, so two records
    # that differ only in an ambiguous value keep distinct digests. It is
    # one-way, exactly as ``original_digest`` over the raw content already is.
    digest_basis = _AMBIGUOUS_NUMERIC.sub(
        lambda match: _DECLARED_PII_REPLACEMENT.get(
            declarations.get(match.group(0), ""), match.group(0)
        ),
        redacted,
    )
    redacted = _AMBIGUOUS_NUMERIC.sub(_resolve, redacted)
    signals = tuple(name for name, pattern in _INJECTION_MARKERS if pattern.search(normalized))
    digest_payload = {"content": digest_basis, "context": context or {}}
    return NormalizationResult(
        normalized_content=normalized,
        redacted_content=redacted,
        original_digest=sha256_text(content),
        normalized_digest=sha256_text(canonical_json(digest_payload)),
        pii_types=tuple(sorted(set(pii_types))),
        safety_signals=signals,
        unresolved_ambiguous=tuple(unresolved),
    )


def _numeric_declarations(context: dict[str, Any] | None) -> dict[str, str]:
    raw = (context or {}).get(NUMERIC_DECLARATIONS_KEY)
    if not isinstance(raw, dict):
        return {}
    return {str(token): str(kind) for token, kind in raw.items() if str(kind) in _RESOLVED_NUMERIC}
