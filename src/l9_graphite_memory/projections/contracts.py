# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/projections/contracts.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-26
"""Immutable projection-manifest and compiler contracts."""

from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class StrictFrozenModel(BaseModel):
    """Common strict immutable model configuration."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        use_enum_values=True,
    )


class ProjectionStatus(str, Enum):
    SHADOW = "shadow"
    ACTIVE = "active"
    RETIRED = "retired"


class ProviderType(str, Enum):
    GRAPHITI_MCP = "graphiti_mcp"
    ZEP = "zep"


class DistanceMetric(str, Enum):
    COSINE = "cosine"
    DOT_PRODUCT = "dot_product"
    EUCLIDEAN = "euclidean"


class ProjectionMetadata(StrictFrozenModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,61}$")
    version: int = Field(ge=1)
    status: ProjectionStatus = ProjectionStatus.SHADOW


class ProviderTarget(StrictFrozenModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,61}$")
    type: ProviderType
    target: str = Field(pattern=r"^[a-z][a-z0-9-]{0,126}$")
    required: bool = False


class ProjectionSource(StrictFrozenModel):
    event_types: tuple[str, ...] = Field(
        
        min_length=1,
    )
    minimum_schema_version: str = Field(
        
        pattern=r"^\d+\.\d+\.\d+$",
    )

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value)
        if any(not item for item in cleaned):
            raise ValueError("source event types cannot be blank")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("source event types must be unique")
        return cleaned


class ProjectionAuthority(StrictFrozenModel):
    record_store: str = Field(pattern=r"^canonical$")
    vector_is_authoritative: bool = Field()

    @model_validator(mode="after")
    def reject_authoritative_vector_state(self) -> ProjectionAuthority:
        if self.vector_is_authoritative:
            raise ValueError("vector state cannot be authoritative")
        return self


class RenderContract(StrictFrozenModel):
    template: str = Field(pattern=r"^[a-z][a-z0-9.-]{1,126}$")
    fields: tuple[str, ...] = Field(min_length=1)
    normalization: str = Field(pattern=r"^unicode-nfc$")
    chunk_policy: str = Field(
        
        pattern=r"^atomic-record-v1$",
    )

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value)
        if any(not item for item in cleaned):
            raise ValueError("render fields cannot be blank")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("render fields must be unique")
        required = {"record_id", "tenant_id", "namespace", "content"}
        missing = required - set(cleaned)
        if missing:
            raise ValueError(
                "render fields are missing required canonical fields: "
                + ", ".join(sorted(missing))
            )
        return cleaned


class EmbeddingContract(StrictFrozenModel):
    ownership: str = Field(pattern=r"^provider$")
    model: str = Field(min_length=3, max_length=300)
    dimensions: int = Field(ge=1, le=65536)
    distance: DistanceMetric
    similarity_space: str = Field(
        
        pattern=r"^[a-z][a-z0-9-]{1,126}$",
    )
    cache_policy: str = Field(
        
        pattern=r"^(none|content-addressed-v1)$",
    )

    @field_validator("model")
    @classmethod
    def require_pinned_model_revision(cls, value: str) -> str:
        model_name, separator, revision = value.partition("@")
        if not separator or not model_name.strip() or not revision.strip():
            raise ValueError(
                "embedding model must include a non-empty pinned revision "
                "using model@revision"
            )
        return value


class ScopeContract(StrictFrozenModel):
    required: tuple[str, ...] = Field(min_length=1)
    fail_closed: bool = Field()

    @model_validator(mode="after")
    def validate_scope(self) -> ScopeContract:
        if not self.fail_closed:
            raise ValueError("projection scope must fail closed")
        required = set(self.required)
        missing = {"tenant_id", "namespace"} - required
        if missing:
            raise ValueError(
                "projection scope is missing: " + ", ".join(sorted(missing))
            )
        if len(required) != len(self.required):
            raise ValueError("projection scope fields must be unique")
        return self


class ReplayContract(StrictFrozenModel):
    ordering: str = Field(pattern=r"^tenant-subject-stream-sequence$")
    strategy: str = Field(pattern=r"^(full|incremental|partitioned)$")
    partition_key: str = Field(
        
        pattern=r"^tenant_id$",
    )
    side_effects: str = Field(
        
        pattern=r"^prohibited$",
    )


class DeterminismContract(StrictFrozenModel):
    structural: str = Field(pattern=r"^exact$")
    render: str = Field(pattern=r"^exact$")
    embedding_mode: str = Field(
        
        pattern=r"^provider-managed$",
    )
    retrieval_mode: str = Field(
        
        pattern=r"^bounded-equivalence$",
    )


class DeletionContract(StrictFrozenModel):
    propagation: tuple[str, ...] = Field(min_length=4)
    attestation_required: bool = Field()

    @model_validator(mode="after")
    def validate_deletion(self) -> DeletionContract:
        required = {"projection", "vector_index", "cache", "summary"}
        actual = set(self.propagation)
        missing = required - actual
        if missing:
            raise ValueError(
                "deletion propagation is missing: " + ", ".join(sorted(missing))
            )
        if len(actual) != len(self.propagation):
            raise ValueError("deletion propagation entries must be unique")
        if not self.attestation_required:
            raise ValueError("deletion attestation must be required")
        return self


class ProjectionSlo(StrictFrozenModel):
    incremental_lag_warning_seconds: int = Field(
        
        ge=0,
    )
    incremental_lag_critical_seconds: int = Field(
        
        ge=1,
    )
    query_p95_milliseconds: int = Field(
        
        ge=1,
    )
    query_p99_milliseconds: int = Field(
        
        ge=1,
    )
    rebuild_maximum_seconds: int = Field(
        
        ge=1,
    )
    deletion_attestation_deadline_seconds: int = Field(
        
        ge=1,
    )
    dead_letter_maximum_count: int = Field(
        
        ge=0,
    )

    @model_validator(mode="after")
    def validate_thresholds(self) -> ProjectionSlo:
        if (
            self.incremental_lag_critical_seconds
            <= self.incremental_lag_warning_seconds
        ):
            raise ValueError(
                "critical projection lag must exceed warning projection lag"
            )
        if self.query_p99_milliseconds < self.query_p95_milliseconds:
            raise ValueError("query p99 must be greater than or equal to p95")
        return self


class ProjectionSpec(StrictFrozenModel):
    providers: tuple[ProviderTarget, ...] = Field(min_length=1)
    source: ProjectionSource
    authority: ProjectionAuthority
    render: RenderContract
    embedding: EmbeddingContract
    scope: ScopeContract
    replay: ReplayContract
    determinism: DeterminismContract
    deletion: DeletionContract
    slo: ProjectionSlo

    @field_validator("providers")
    @classmethod
    def validate_provider_targets(
        cls,
        value: tuple[ProviderTarget, ...],
    ) -> tuple[ProviderTarget, ...]:
        ids = [item.id for item in value]
        identities = [(str(item.type), item.target) for item in value]
        if len(set(ids)) != len(ids):
            raise ValueError("provider ids must be unique")
        if len(set(identities)) != len(identities):
            raise ValueError(
                "provider type and target identities must be unique"
            )
        return value


class ProjectionManifest(StrictFrozenModel):
    api_version: str = Field(
        
        pattern=r"^memory\.quantum-l9\.dev/v1$",
    )
    kind: str = Field(pattern=r"^Projection$")
    metadata: ProjectionMetadata
    spec: ProjectionSpec


class CompiledProjectionTarget(StrictFrozenModel):
    identity: str
    provider_id: str
    provider_type: ProviderType
    target: str
    required: bool


class CompiledProjection(StrictFrozenModel):
    name: str
    version: int
    status: ProjectionStatus
    source_event_types: tuple[str, ...]
    minimum_schema_version: str
    targets: tuple[CompiledProjectionTarget, ...]
    render: RenderContract
    embedding: EmbeddingContract
    scope: ScopeContract
    replay: ReplayContract
    deletion: DeletionContract
    slo: ProjectionSlo
    manifest_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    render_contract_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    compiled_artifact_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
