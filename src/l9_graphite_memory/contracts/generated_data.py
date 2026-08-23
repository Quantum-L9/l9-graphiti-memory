# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/generated_data.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-08-14

"""Governed generated-data ingress contracts. Cursor-Governance remains the control plane."""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_CLASSES = frozenset(
    {
        "repository_fact",
        "dependency_finding",
        "implementation_surface",
        "rejected_approach",
        "context_requirement",
        "artifact_lineage",
    }
)
VISIBILITY_TEMPLATES = {
    "campaign_local": "campaign/{campaign_id}",
    "repository_local": "repository/{repository}",
    "project_group": "project-group/{project_group}",
    "constellation_internal": "constellation/internal",
    "restricted": "restricted/{policy_id}",
}


class MemoryCandidateIngestionStatus(str, Enum):
    ADMITTED = "admitted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class MemoryReuseStatus(str, Enum):
    RECORDED = "recorded"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class SourceInvalidationStatus(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"


class GovernedCandidateSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    repository: str = Field(min_length=1)
    sha: str | None = None
    base_sha: str | None = None
    freshness_sha: str | None = None
    visibility: str | None = None
    campaign_id: str | None = None
    project_group: str | None = None
    policy_id: str | None = None

    def resolved_sha(self) -> str:
        value = self.sha or self.base_sha or self.freshness_sha
        if not value:
            raise ValueError("source SHA is required")
        return value


class GovernedCandidateKnowledge(BaseModel):
    model_config = ConfigDict(extra="allow")

    primary_class: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    observed_units: list[dict[str, Any]] = Field(default_factory=list)
    derived_units: list[dict[str, Any]] = Field(default_factory=list)
    invalidation_conditions: list[Any] = Field(default_factory=list)


class GovernedCandidateGovernance(BaseModel):
    model_config = ConfigDict(extra="allow")

    authority_class: str
    route: str
    promotion_decision: str
    visibility: str | None = None
    may_override_repository_state: bool = False
    may_override_canonical_authority: bool = False


class GovernedCandidateProvenance(BaseModel):
    model_config = ConfigDict(extra="allow")

    producer: str | None = None
    source_agent_id: str | None = None


class GovernedMemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = Field(min_length=1)
    kind: str
    candidate_id: str = Field(min_length=1)
    source: GovernedCandidateSource
    knowledge: GovernedCandidateKnowledge
    governance: GovernedCandidateGovernance
    provenance: GovernedCandidateProvenance = Field(default_factory=GovernedCandidateProvenance)

    @model_validator(mode="after")
    def validate_ingress(self) -> GovernedMemoryCandidate:
        major = self.schema_version.split(".", 1)[0]
        if major != "1":
            raise ValueError("unsupported schema major")
        if self.kind != "MemoryCandidate":
            raise ValueError("kind must be MemoryCandidate")
        if self.knowledge.primary_class not in SUPPORTED_CLASSES:
            raise ValueError(f"unsupported generated-data class: {self.knowledge.primary_class}")
        if self.governance.authority_class != "advisory":
            raise ValueError("authority_class must be advisory")
        if self.governance.route != "memory":
            raise ValueError("route must be memory")
        if self.governance.promotion_decision != "promote":
            raise ValueError("promotion_decision must be promote")
        if self.governance.may_override_repository_state:
            raise ValueError("may_override_repository_state must be false")
        if self.governance.may_override_canonical_authority:
            raise ValueError("may_override_canonical_authority must be false")
        source_sha = self.source.resolved_sha()
        freshness = (
            self.source.freshness_sha
            or (self.knowledge.model_dump().get("freshness") or {}).get("base_sha")
            or source_sha
        )
        if source_sha != freshness:
            raise ValueError("source SHA must equal freshness SHA")
        if not self.knowledge.invalidation_conditions:
            raise ValueError("invalidation conditions are required")
        units = [*self.knowledge.observed_units, *self.knowledge.derived_units]
        if units and not all(unit.get("evidence") for unit in units):
            raise ValueError("observed and derived units must include evidence")
        return self

    def namespace(self) -> str:
        visibility = self.source.visibility or self.governance.visibility
        if not visibility:
            raise ValueError("visibility is required")
        template = VISIBILITY_TEMPLATES.get(visibility)
        if template is None:
            raise ValueError(f"unknown visibility: {visibility}")
        fields = {
            "campaign_id": self.source.campaign_id,
            "repository": self.source.repository,
            "project_group": self.source.project_group,
            "policy_id": self.source.policy_id,
        }
        try:
            return template.format(**{k: v or "" for k, v in fields.items()})
        except KeyError as exc:
            raise ValueError(f"visibility {visibility} missing {exc}") from exc


class MemoryCandidateIngestionResult(BaseModel):
    status: MemoryCandidateIngestionStatus
    candidate_id: str
    namespace: str
    write_receipt_id: str | None = None
    reason: str | None = None


class MemoryReuseEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str = Field(min_length=1)
    record_id: UUID
    outcome: str = Field(min_length=1)
    body: dict[str, Any] = Field(default_factory=dict)


class MemoryReuseReceipt(BaseModel):
    status: MemoryReuseStatus
    event_id: str
    record_id: UUID
    write_receipt_id: str | None = None
    reason: str | None = None


class SourceInvalidationRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_type: str = Field(min_length=1)
    selector: dict[str, Any] = Field(default_factory=dict)
    repository: str | None = None


class SourceInvalidationReceipt(BaseModel):
    status: SourceInvalidationStatus
    event_type: str
    matched: int = 0
    write_receipt_id: str | None = None
    reason: str | None = None


class GeneratedDataCapabilityResponse(BaseModel):
    declared: bool
    store_ready: bool
    commands_registered: bool
    mcp_tools_registered: bool
    write_path: str
    ready: bool
