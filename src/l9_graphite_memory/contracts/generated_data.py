# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/generated_data.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 1.2.0
#   updated: 2026-10-02

"""Governed generated-data ingress contracts. Cursor-Governance remains control plane."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .memory import MemoryRecord

SUPPORTED_CLASSES = frozenset(
    {
        "repository_fact",
        "dependency_finding",
        "implementation_surface",
        "rejected_approach",
        "context_requirement",
        "artifact_lineage",
        # A Cursor-Governance session continuation capsule: the structured
        # successor of the provider-only PICKUP episode (ADR-082). The capsule
        # rides in ``knowledge.structured_payload`` losslessly; the statement
        # is its human-readable summary for retrieval.
        "session_continuation",
    }
)
VISIBILITY_TEMPLATES = {
    "campaign_local": "campaign/{campaign_id}",
    "repository_local": "repository/{repository}",
    "project_group": "project-group/{project_group}",
    "constellation_internal": "constellation/internal",
    "restricted": "restricted/{policy_id}",
    # The candidate names the exact namespace it requests. This is a request,
    # never a grant: MemoryService authorizes the principal against it like
    # any other write (INV-07). It exists so a session artifact lands in the
    # repository namespace hydration reads, not a derived ``repository/…`` one.
    "namespace_local": "{namespace}",
}
VISIBILITY_REQUIRED_FIELDS = {
    "campaign_local": ("campaign_id",),
    "repository_local": ("repository",),
    "project_group": ("project_group",),
    "constellation_internal": (),
    "restricted": ("policy_id",),
    "namespace_local": ("namespace",),
}


class MemoryCandidateIngestionStatus(str, Enum):
    ADMITTED = "admitted"
    DUPLICATE = "duplicate"
    QUARANTINED = "quarantined"
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
    # Requested namespace for ``namespace_local`` visibility (ADR-082).
    namespace: str | None = Field(default=None, min_length=1, max_length=300)

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
    # A structured artifact carried losslessly beside the statement, named by
    # the producer-owned schema it conforms to (for example
    # ``cursor.continuation/v2``). Memory stores it under record metadata and
    # never interprets it; the producer owns the schema (ADR-082).
    payload_schema: str | None = Field(default=None, min_length=1, max_length=200)
    structured_payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_structured_payload(self) -> GovernedCandidateKnowledge:
        if (self.structured_payload is None) != (self.payload_schema is None):
            raise ValueError("payload_schema and structured_payload must be supplied together")
        return self


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
    # Canonical supersession reference (ADR-082 amendment, audit P1-03): the
    # records this candidate replaces once admitted. Memory validates every
    # target (same tenant, authorized namespace, exists, lifecycle transition
    # legal) and applies the transition transactionally; a producer that
    # refines a continuation names the prior record here instead of leaving
    # two ACTIVE continuations behind. A refused supersession rejects the
    # candidate and leaves the targets untouched.
    supersedes: list[UUID] = Field(default_factory=list)

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
        knowledge = self.knowledge.model_dump()
        freshness = (
            self.source.freshness_sha
            or (knowledge.get("freshness") or {}).get("base_sha")
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
            "namespace": self.source.namespace,
        }
        missing = [
            field for field in VISIBILITY_REQUIRED_FIELDS[visibility] if not fields.get(field)
        ]
        if missing:
            raise ValueError(
                f"visibility {visibility} missing required fields: {', '.join(missing)}"
            )
        return template.format(**{key: value or "" for key, value in fields.items()})


class MemoryCandidateIngestionResult(BaseModel):
    status: MemoryCandidateIngestionStatus
    candidate_id: str
    namespace: str
    record_id: UUID | None = None
    write_receipt_id: str | None = None
    storage_committed: bool = False
    memory_state: str | None = None
    reason: str | None = None
    # Records this admission superseded (empty unless the candidate named
    # targets and memory applied the transition).
    superseded_record_ids: list[UUID] = Field(default_factory=list)


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


#: Provenance source every governed generated-data candidate is admitted under.
GENERATED_DATA_SOURCE = "cursor-governance-generated-data"

#: Change kinds the deployed Cursor-Governance repository event bridge emits
#: (``repository_event_bridge.ChangeKind``).
SourceChangeKind = Literal["added", "modified", "deleted", "renamed", "type_changed"]


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SourceInvalidationSelector(BaseModel):
    """One structured source selector of an invalidation request (ADR-086).

    The canonical fields are ``selector_id``, ``selector_type`` and
    ``selector_value``. The deployed Cursor-Governance bridge spells the same
    two values ``condition_type`` and ``selector`` and adds ``change_kind`` and
    ``previous_path``; those spellings are modeled explicitly and normalized
    here, never accepted through ``extra``. Supplying both spellings of one
    value is ambiguous and rejected. Unknown fields fail closed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    selector_id: str = Field(min_length=1, max_length=200)
    selector_type: str = Field(min_length=1, max_length=200)
    selector_value: str = Field(min_length=1, max_length=4_000)
    change_kind: SourceChangeKind | None = None
    previous_path: str | None = Field(default=None, min_length=1, max_length=4_000)

    @model_validator(mode="before")
    @classmethod
    def normalize_deployed_spelling(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for canonical, deployed in (
            ("selector_type", "condition_type"),
            ("selector_value", "selector"),
        ):
            if deployed in data:
                if canonical in data:
                    raise ValueError(
                        f"selector supplies both {canonical!r} and its deployed "
                        f"spelling {deployed!r}; send exactly one"
                    )
                data[canonical] = data.pop(deployed)
        if not data.get("selector_id") and data.get("selector_type") and data.get("selector_value"):
            data["selector_id"] = (
                "selector-"
                + _canonical_digest(
                    {
                        "selector_type": data.get("selector_type"),
                        "selector_value": data.get("selector_value"),
                        "change_kind": data.get("change_kind"),
                        "previous_path": data.get("previous_path"),
                    }
                )[:32]
            )
        return data


class SourceInvalidationRequest(BaseModel):
    """Structured source invalidation under memory-control-plane/v1 (ADR-086).

    Canonical form: ``event_id``, ``event_type``, ``repository``,
    ``from_sha``, ``to_sha``, ``selectors[]`` and ``delete_memory=false``.

    The singular ``selector`` is the explicit compatibility form of earlier
    v1 clients: it is normalized into a one-element ``selectors`` and may omit
    ``event_id`` and ``repository``. Supplying both forms, or neither, is
    rejected. ``schema_version``, ``kind``, ``create_replacement_record`` and
    ``metadata`` are modeled because the deployed Cursor-Governance bridge
    sends them; every other field fails closed.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str | None = Field(default=None, min_length=1, max_length=300)
    event_type: str = Field(min_length=1, max_length=200)
    repository: str | None = Field(default=None, min_length=1, max_length=300)
    from_sha: str | None = Field(default=None, max_length=200)
    to_sha: str | None = Field(default=None, max_length=200)
    selectors: tuple[SourceInvalidationSelector, ...] | None = None
    delete_memory: Literal[False] = False
    # Legacy singular compatibility form.
    selector: SourceInvalidationSelector | None = None
    # Envelope fields of the deployed producer (repository_event_bridge).
    schema_version: str = Field(default="1.0.0", min_length=1, max_length=50)
    kind: Literal["SourceInvalidationRequest"] = "SourceInvalidationRequest"
    create_replacement_record: Literal[False] = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_selector_form(self) -> SourceInvalidationRequest:
        if self.schema_version.split(".", 1)[0] != "1":
            raise ValueError("unsupported invalidation schema major")
        if self.selector is not None and self.selectors is not None:
            raise ValueError("selector and selectors are mutually exclusive; send selectors")
        if self.selector is None and not self.selectors:
            raise ValueError("source invalidation requires structured selectors")
        if self.selectors is not None:
            if self.event_id is None:
                raise ValueError("canonical invalidation requests require event_id")
            if self.repository is None:
                raise ValueError("canonical invalidation requests require repository")
        return self

    @property
    def compatibility_form(self) -> Literal["canonical", "legacy_selector"]:
        return "canonical" if self.selectors is not None else "legacy_selector"

    def normalized_selectors(self) -> tuple[SourceInvalidationSelector, ...]:
        if self.selectors is not None:
            return self.selectors
        assert self.selector is not None  # guaranteed by validate_selector_form
        return (self.selector,)

    def request_digest(self) -> str:
        """Digest of the normalized canonical request body, never its identity.

        Envelope fields (``schema_version``, ``kind``, ``metadata``) carry no
        invalidation semantics and are excluded, as is ``event_id``: a body is
        compared under an identity, it does not define one.
        """

        return _canonical_digest(
            {
                "event_type": self.event_type,
                "repository": self.repository,
                "from_sha": self.from_sha,
                "to_sha": self.to_sha,
                "selectors": sorted(
                    (item.model_dump(mode="json") for item in self.normalized_selectors()),
                    key=lambda item: json.dumps(item, sort_keys=True),
                ),
                "delete_memory": False,
            }
        )

    def operation_id(self) -> str:
        """The retry identity: ``event_id``, or a digest-derived legacy identity."""

        if self.event_id is not None:
            return self.event_id
        return f"legacy-invalidation-{self.request_digest()[:32]}"


class SourceInvalidationReceipt(BaseModel):
    """Outcome of one atomic source invalidation (ADR-086).

    ``status`` stays ``applied`` / ``rejected``; there is no partial success.
    ``deleted`` is always false. A zero-match ``applied`` receipt is a valid
    outcome but never proof that invalidation took effect.
    """

    status: SourceInvalidationStatus
    event_type: str
    matched: int = 0
    write_receipt_id: str | None = None
    reason: str | None = None
    event_id: str | None = None
    transitioned: int = 0
    record_ids: list[UUID] = Field(default_factory=list)
    lifecycle_receipt_ids: list[UUID] = Field(default_factory=list)
    revalidation_requirement_ids: list[UUID] = Field(default_factory=list)
    deleted: Literal[False] = False


class SourceSelectorRecord(BaseModel):
    """Durable structured source selector owned by one canonical record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selector_id: str = Field(min_length=1, max_length=200)
    record_id: UUID
    repository: str = Field(min_length=1)
    selector_type: str = Field(min_length=1)
    selector_value: str = Field(min_length=1)
    active: bool = True
    created_at: datetime
    deactivated_at: datetime | None = None


class RevalidationRequirement(BaseModel):
    """Durable obligation to revalidate a record a source invalidation archived."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requirement_id: UUID = Field(default_factory=uuid4)
    tenant_id: str = Field(min_length=1)
    namespace: str = Field(min_length=1)
    record_id: UUID
    invalidation_event_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2_000)
    status: Literal["open"] = "open"
    created_at: datetime


class SourceInvalidationEvent(BaseModel):
    """Durable record of one applied source invalidation operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    request_digest: str = Field(min_length=1)
    compatibility_form: Literal["canonical", "legacy_selector"]
    event_type: str = Field(min_length=1)
    repository: str | None = None
    from_sha: str | None = None
    to_sha: str | None = None
    selectors: tuple[SourceInvalidationSelector, ...]
    namespaces: tuple[str, ...] = ()
    matched: int = 0
    transitioned: int = 0
    record_ids: tuple[UUID, ...] = ()
    lifecycle_receipt_ids: tuple[UUID, ...] = ()
    revalidation_requirement_ids: tuple[UUID, ...] = ()
    actor: str = Field(min_length=1)
    created_at: datetime


def source_selectors_for_record(record: MemoryRecord) -> tuple[SourceSelectorRecord, ...]:
    """Structured selectors a governed generated-data record carries, or none.

    The single mapping used both at admission and by the store backfill, so a
    backfilled selector is exactly the selector admission would have written.
    It reads only the structured ``invalidation_conditions`` and
    ``repository`` metadata of a governed candidate, never statement text or
    provider content. The mapping is all-or-nothing: unless every condition is
    an object of exactly ``condition_type`` and ``selector`` strings, the
    record has no selectors, because a partial mapping would silently drop an
    invalidation condition.
    """

    metadata = record.metadata or {}
    if record.provenance.source != GENERATED_DATA_SOURCE:
        return ()
    if metadata.get("generated_data_kind") != "MemoryCandidate":
        return ()
    repository = metadata.get("repository")
    conditions = metadata.get("invalidation_conditions")
    if not isinstance(repository, str) or not repository:
        return ()
    if not isinstance(conditions, list) or not conditions:
        return ()
    selectors: dict[str, SourceSelectorRecord] = {}
    for condition in conditions:
        if not isinstance(condition, dict) or set(condition) != {"condition_type", "selector"}:
            return ()
        selector_type = condition["condition_type"]
        selector_value = condition["selector"]
        if not isinstance(selector_type, str) or not selector_type:
            return ()
        if not isinstance(selector_value, str) or not selector_value:
            return ()
        selector_id = (
            "srcsel-"
            + _canonical_digest([str(record.record_id), selector_type, selector_value])[:40]
        )
        selectors[selector_id] = SourceSelectorRecord(
            selector_id=selector_id,
            record_id=record.record_id,
            repository=repository,
            selector_type=selector_type,
            selector_value=selector_value,
            created_at=record.created_at,
        )
    return tuple(selectors.values())


class GeneratedDataCapabilityResponse(BaseModel):
    declared: bool
    store_ready: bool
    commands_registered: bool
    mcp_tools_registered: bool
    write_path: str
    ready: bool
