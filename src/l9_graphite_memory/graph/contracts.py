# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graph/contracts.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Provider-neutral graph-intelligence contracts (ADR-086).

Three layers, deliberately separate:

* ``GraphIntelligenceRequest`` — what a caller may ask. It carries namespaces
  but never a tenant, a group id, or query text for the backend; the service
  derives scope from the authenticated principal (GI-010/GI-011).
* ``GraphProviderRequest`` / ``GraphProviderResult`` — what the service hands a
  ``GraphIntelligencePort`` and what comes back. Provider results are
  projection-derived observations, never canonical memory (GI-004).
* ``GraphIntelligenceReceipt`` — what the caller receives: typed status,
  scope digest, provider identity, algorithm identity, applied limits,
  advisory results bound to canonical supporting record ids, and a digest.

The request and receipt serialize to the JSON Schemas shipped in
``resources/graph/`` (``l9.memory.graph-intelligence-request.v1`` and
``l9.memory.graph-intelligence-receipt.v1``).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .scope import is_graph_group_id

GRAPH_CONTRACT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AUTHORITY_CLASS: Literal["advisory_projection"] = "advisory_projection"
_RELATIONSHIP_TYPE = r"^[A-Z][A-Z0-9_]{0,63}$"


class GraphOperation(str, Enum):
    SEARCH = "graph.search"
    SEMANTIC_SEARCH = "graph.semantic_search"
    TRAVERSE = "graph.traverse"
    PATH = "graph.path"
    NEIGHBORHOOD = "graph.neighborhood"
    STRUCTURAL_SIMILARITY = "graph.structural_similarity"
    COMMUNITY = "graph.community"
    CENTRALITY = "graph.centrality"
    LINK_PREDICTION = "graph.link_prediction"
    STRUCTURAL_EMBEDDING = "graph.structural_embedding"


class GraphReceiptStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class GraphLimits(BaseModel):
    """Hard per-request ceilings (GI-014/GI-015). Schema maxima are absolute."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_depth: int = Field(default=2, ge=0, le=6)
    max_nodes: int = Field(default=100, ge=1, le=1_000)
    max_edges: int = Field(default=250, ge=1, le=5_000)
    max_paths: int = Field(default=10, ge=1, le=100)
    max_runtime_ms: int = Field(default=3_000, ge=10, le=30_000)


class GraphAnchor(BaseModel):
    """Exactly one of a canonical record id, an opaque entity id, or text.

    Provider-internal numeric node ids are never accepted or returned.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: UUID | None = None
    entity_uuid: UUID | None = None
    query: str | None = Field(default=None, min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def exactly_one(self) -> GraphAnchor:
        present = [v for v in (self.record_id, self.entity_uuid, self.query) if v is not None]
        if len(present) != 1:
            raise ValueError("graph anchor requires exactly one of record_id, entity_uuid, query")
        return self


class GraphIntelligenceRequest(BaseModel):
    """A caller's structural question. Scope authority is never in here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0.0"] = GRAPH_CONTRACT_SCHEMA_VERSION
    operation: GraphOperation
    namespaces: tuple[str, ...] = Field(min_length=1)
    anchor: GraphAnchor | None = None
    target: GraphAnchor | None = None
    relationship_types: tuple[str, ...] = ()
    direction: Literal["out", "in", "both"] = "both"
    as_of: datetime | None = None
    recorded_before: datetime | None = None
    algorithm: str | None = Field(default=None, max_length=100)
    required: bool = False
    profile_ref: str | None = Field(default=None, max_length=300)
    limits: GraphLimits = Field(default_factory=GraphLimits)

    @field_validator("namespaces")
    @classmethod
    def unique_namespaces(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not namespace.strip() for namespace in value):
            raise ValueError("namespaces must be non-empty strings")
        if len(set(value)) != len(value):
            raise ValueError("namespaces must be unique")
        return value

    @field_validator("relationship_types")
    @classmethod
    def relationship_tokens(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for relationship in value:
            if not re.fullmatch(_RELATIONSHIP_TYPE, relationship):
                raise ValueError(f"invalid relationship type: {relationship!r}")
        if len(set(value)) != len(value):
            raise ValueError("relationship_types must be unique")
        return value

    def contract_payload(self) -> dict[str, Any]:
        """Serialize to the ``graph-intelligence-request.schema.json`` shape."""

        return self.model_dump(mode="json", exclude_none=True)


class GraphProviderRequest(BaseModel):
    """What the service hands a port: derived groups, never a raw tenant."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: GraphOperation
    group_ids: tuple[str, ...] = Field(min_length=1)
    anchor: GraphAnchor | None = None
    target: GraphAnchor | None = None
    relationship_types: tuple[str, ...] = ()
    direction: Literal["out", "in", "both"] = "both"
    as_of: datetime | None = None
    recorded_before: datetime | None = None
    limits: GraphLimits
    algorithm_id: str | None = None
    algorithm_config: dict[str, Any] = Field(default_factory=dict)
    operation_id: str = Field(min_length=1, max_length=128)

    @field_validator("group_ids")
    @classmethod
    def scope_keys_only(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not all(is_graph_group_id(group) for group in value):
            raise ValueError("provider requests carry only GraphScopeKey v1 group ids")
        return value


class GraphProviderNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_uuid: UUID
    group_id: str
    labels: tuple[str, ...] = ()
    name: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    supporting_episode_ids: tuple[UUID, ...] = ()


class GraphProviderEdge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_uuid: UUID | None = None
    source_uuid: UUID
    target_uuid: UUID
    relationship_type: str
    group_id: str
    fact: str | None = None
    valid_at: datetime | None = None
    invalid_at: datetime | None = None
    supporting_episode_ids: tuple[UUID, ...] = ()


class GraphProviderPath(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_uuids: tuple[UUID, ...] = Field(min_length=1)
    edge_uuids: tuple[UUID, ...] = ()
    length: int = Field(ge=0)
    weight: float | None = None


class GraphProviderScore(BaseModel):
    """One analytic observation about a node, or a candidate node pair."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_uuid: UUID
    group_id: str
    score: float | None = None
    target_uuid: UUID | None = None
    community_id: int | None = None
    embedding: tuple[float, ...] | None = None


class GraphProviderResult(BaseModel):
    """Projection-derived observations. Never canonical memory (GI-004)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: GraphOperation
    nodes: tuple[GraphProviderNode, ...] = ()
    edges: tuple[GraphProviderEdge, ...] = ()
    paths: tuple[GraphProviderPath, ...] = ()
    scores: tuple[GraphProviderScore, ...] = ()
    truncated: bool = False
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class GraphProviderIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    projection_provider: str
    graph_backend: str
    graphiti_version: str | None = None
    backend_version: str | None = None
    gds_version: str | None = None


class GraphAlgorithmIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    maturity: Literal["native", "production", "beta", "alpha"]
    config_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class GraphIntelligenceReceipt(BaseModel):
    """Typed, deterministic outcome of one graph-intelligence operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0.0"] = GRAPH_CONTRACT_SCHEMA_VERSION
    status: GraphReceiptStatus
    operation: GraphOperation
    scope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    authority_class: Literal["advisory_projection"] = AUTHORITY_CLASS
    provider: GraphProviderIdentity
    algorithm: GraphAlgorithmIdentity | None = None
    limits_applied: dict[str, Any]
    results: tuple[dict[str, Any], ...] = ()
    supporting_record_ids: tuple[UUID, ...] = ()
    unsupported_projection_observations: tuple[dict[str, Any], ...] = ()
    failures: tuple[dict[str, Any], ...] = ()
    result_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("supporting_record_ids")
    @classmethod
    def unique_support(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("supporting_record_ids must be unique")
        return value

    def contract_payload(self) -> dict[str, Any]:
        """Serialize to the ``graph-intelligence-receipt.schema.json`` shape."""

        return self.model_dump(mode="json")
