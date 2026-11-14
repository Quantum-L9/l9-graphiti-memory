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

#: A token, for the phone and SSN redactors below, is a maximal run of ASCII
#: letters and digits -- the same boundary ``_AMBIGUOUS_NUMERIC`` uses. A match
#: may neither begin nor end inside a longer token; punctuation, whitespace and
#: the ends of the string separate tokens. A phone match that opens with ``+``
#: or ``(`` already begins at a boundary.
_DIGIT_TOKEN_START = r"(?<![0-9A-Za-z])"
_PHONE_TOKEN_START = r"(?:" + _DIGIT_TOKEN_START + r"(?=\d)|(?=[+(]))"
_TOKEN_END = r"(?![0-9A-Za-z])"

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
        # The number must stand as its own token (``_PHONE_TOKEN_START`` /
        # ``_TOKEN_END``): a digit run inside a hex digest, UUID or record id
        # (``44bfc17397974647a97d...``) is an identifier, not a phone number.
        # The one letter allowed to abut the end is an ``x`` extension
        # (``212-555-1212x204``), which stays redacted.
        re.compile(
            _PHONE_TOKEN_START + r"(?:"
            r"\+?1[\s.\-]?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}"
            r"|\(\d{3}\)[\s.\-]?\d{3}[\s.\-]?\d{4}"
            r"|\d{3}[\s.\-]\d{3}[\s.\-]?\d{4}"
            r"|\d{3}[\s.\-]?\d{3}[\s.\-]\d{4}"
            r")(?:" + _TOKEN_END + r"|(?=[xX]\d{1,6}" + _TOKEN_END + r"))"
        ),
        "[PHONE_REDACTED]",
    ),
    (
        # Any 3-2-4 grouping with at least one separator. A bare 9-digit run
        # takes the ambiguous path, never the raw-storage path. Same token
        # boundary as the phone pattern: ``ab012345-6789-...`` is a UUID.
        "ssn",
        re.compile(
            _DIGIT_TOKEN_START + r"\d{3}(?:[\-\s]\d{2}[\-\s]?|\d{2}[\-\s])\d{4}" + _TOKEN_END
        ),
        "[SSN_REDACTED]",
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
_DECLARED_PII_REPLACEMENT = {"phone": "[PHONE_REDACTED]", "ssn": "[SSN_REDACTED]"}

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
