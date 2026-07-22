# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/profiles.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Typed identity, preference, behavior, session, and domain-memory contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .evidence import Confidence, EvidenceRef, Provenance
from .privacy import ConsentGrant
from .temporal import utc_now


class ProfileFact(BaseModel):
    """One atomic profile assertion with independent evidence and validity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4_000)
    confidence: Confidence = Field(default_factory=Confidence)
    evidence: tuple[EvidenceRef, ...] = ()
    valid_from: datetime = Field(default_factory=utc_now)
    valid_to: datetime | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class IdentityProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    subject_id: str = Field(min_length=1, max_length=300)
    facts: tuple[ProfileFact, ...]
    provenance: Provenance
    consent: ConsentGrant


class PreferenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    subject_id: str = Field(min_length=1, max_length=300)
    preference: str = Field(min_length=1, max_length=4_000)
    applies_to: str = Field(default="general", min_length=1, max_length=300)
    confidence: Confidence = Field(default_factory=Confidence)
    evidence: tuple[EvidenceRef, ...] = ()
    provenance: Provenance
    consent: ConsentGrant
    valid_from: datetime = Field(default_factory=utc_now)
    valid_to: datetime | None = None


class BehaviorPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    policy_id: str = Field(min_length=1, max_length=300)
    condition: str = Field(min_length=1, max_length=4_000)
    directive: str = Field(min_length=1, max_length=4_000)
    evidence: tuple[EvidenceRef, ...] = ()
    provenance: Provenance
    valid_from: datetime = Field(default_factory=utc_now)
    valid_to: datetime | None = None


class SessionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    session_id: str = Field(min_length=1, max_length=300)
    objective: str = Field(min_length=1, max_length=8_000)
    active_constraints: tuple[str, ...] = ()
    active_decisions: tuple[str, ...] = ()
    provenance: Provenance
    expires_at: datetime | None = None


class DomainMemory(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str = Field(min_length=1, max_length=300)
    domain: str = Field(min_length=1, max_length=300)
    facts: tuple[ProfileFact, ...]
    provenance: Provenance
