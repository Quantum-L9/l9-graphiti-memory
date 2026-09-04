# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/review.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""Automated quarantine review contracts (ADR-080).

Admission quarantines a record when a safety or PII signal fires. Nothing in
the write path can tell a benign mention of "ignore previous instructions"
from an attack, so the decision is deferred to a reviewer that reads the whole
record with the namespace in view. The reviewer's verdict is evidence, not
authority: the review policy decides what a verdict is allowed to do, and only
a RELEASE that clears the policy moves a record out of quarantine.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import QuarantineVerdict
from .temporal import coerce_utc, utc_now

QUARANTINE_REVIEW_POLICY_VERSION = "quarantine-review/v1"


class QuarantineReviewPolicy(BaseModel):
    """What an automated verdict is permitted to do.

    The defaults are deliberately asymmetric: releasing needs a confident
    reviewer, holding costs nothing but another look next run, and a finding
    that reads as a credential or an exfiltration attempt always goes to a
    person regardless of what the reviewer concluded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str = QUARANTINE_REVIEW_POLICY_VERSION
    #: A RELEASE below this confidence is treated as HOLD, never as ESCALATE:
    #: uncertainty is not a serious blocker, so it does not interrupt anyone.
    release_min_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    #: PII types (as named by admission normalization) that mean the record
    #: carried a credential. Those are escalated whatever the verdict says.
    blocker_pii_types: tuple[str, ...] = ("openai_key", "bearer")
    #: Safety signals that mean an exfiltration attempt; same treatment.
    blocker_safety_signals: tuple[str, ...] = ("credential_exfiltration",)
    #: Upper bound on reviews one maintenance run may perform.
    max_reviews_per_run: int = Field(default=200, ge=1, le=10_000)


class QuarantineReviewVerdict(BaseModel):
    """One reviewer's conclusion about one quarantined record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID
    verdict: QuarantineVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: tuple[str, ...] = Field(min_length=1)
    #: Serious findings that require a person. Non-empty forces ESCALATE.
    blockers: tuple[str, ...] = ()
    reviewer: str = Field(min_length=1, max_length=200)
    model: str | None = Field(default=None, max_length=200)
    policy_version: str = Field(min_length=1, max_length=100)
    reviewed_at: datetime = Field(default_factory=utc_now)

    @field_validator("reasons", "blockers")
    @classmethod
    def strip_and_require_text(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value)
        if any(not item for item in cleaned):
            raise ValueError("review reasons and blockers must be non-empty text")
        return cleaned

    @field_validator("reviewed_at")
    @classmethod
    def normalize_reviewed_at(cls, value: datetime) -> datetime:
        normalized = coerce_utc(value)
        assert normalized is not None
        return normalized

    @property
    def requires_human(self) -> bool:
        return self.verdict is QuarantineVerdict.ESCALATE or bool(self.blockers)

    def summary(self) -> str:
        """One line for status events and evidence descriptions."""

        model = f" ({self.model})" if self.model else ""
        reasons = "; ".join(self.reasons)
        return (
            f"quarantine review by {self.reviewer}{model}: {self.verdict.value} "
            f"at confidence {self.confidence:.2f}; {reasons}"
        )
