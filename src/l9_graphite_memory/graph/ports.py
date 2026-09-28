# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graph/ports.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Provider-neutral structural graph-intelligence port (ADR-085).

``GraphIntelligencePort`` is a sibling of ``ProjectionAdapter``, not an
extension of it. The projection adapter owns project/retire/erase and
graph/semantic candidate retrieval through Graphiti; this port owns bounded
structural queries and analytics over the same Graphiti-managed graph. Keeping
them apart preserves projection lifecycle semantics, retrieval planner
behavior, and capability-specific limits and degradation.

Nothing here names a provider. Provider identity, versions, and schema
fingerprints travel in ``GraphBackendHealth`` and receipt metadata only.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.errors import GraphCapabilityUnavailable

from .contracts import GraphOperation, GraphProviderRequest, GraphProviderResult


class GraphCapability(str, Enum):
    """Canonical provider-neutral graph-intelligence capability names."""

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


#: Structural capabilities that need only bounded graph reads.
BASELINE_CAPABILITIES: tuple[GraphCapability, ...] = (
    GraphCapability.TRAVERSE,
    GraphCapability.PATH,
    GraphCapability.NEIGHBORHOOD,
)
#: Capabilities that need a graph-analytics engine.
ANALYTICS_CAPABILITIES: tuple[GraphCapability, ...] = (
    GraphCapability.STRUCTURAL_SIMILARITY,
    GraphCapability.COMMUNITY,
    GraphCapability.CENTRALITY,
    GraphCapability.LINK_PREDICTION,
    GraphCapability.STRUCTURAL_EMBEDDING,
)


#: Initial Graphiti relationship families a structural query may follow. New
#: provider relationship types are never admitted by wildcard.
DEFAULT_RELATIONSHIP_ALLOWLIST: tuple[str, ...] = (
    "RELATES_TO",
    "MENTIONS",
    "HAS_EPISODE",
    "NEXT_EPISODE",
    "HAS_MEMBER",
)


class GraphBackendHealth(BaseModel):
    """Typed health of a graph-intelligence backend.

    Health is not a TCP ping: reachability, schema compatibility, analytics
    availability, and scope-scheme conformance are reported as separate
    dimensions so one failing dimension never masquerades as another.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    enabled: bool
    healthy: bool
    reachable: bool = False
    database: str | None = None
    backend_version: str | None = None
    backend_edition: str | None = None
    schema_fingerprint: str | None = None
    expected_schema_fingerprint: str | None = None
    schema_compatible: bool = False
    missing_labels: tuple[str, ...] = ()
    missing_relationship_types: tuple[str, ...] = ()
    analytics_available: bool = False
    analytics_version: str | None = None
    missing_procedures: tuple[str, ...] = ()
    scope_scheme: str | None = None
    scope_scheme_conformant: bool | None = None
    supported_capabilities: tuple[GraphCapability, ...] = ()
    capabilities: tuple[GraphCapability, ...] = ()
    error_class: str | None = None
    detail: str = Field(default="", max_length=2_000)


class GraphIntelligencePort(Protocol):
    """Bounded, read-only, provider-neutral structural graph intelligence."""

    name: str

    def capabilities(self) -> tuple[GraphCapability, ...]:
        """Capabilities this backend implements and can serve right now.

        Detection is explicit: a capability absent here is unavailable, and
        callers never receive a silent substitute (GI-032).
        """
        ...

    def health(self) -> GraphBackendHealth: ...

    def close(self) -> None: ...

    # Every operation takes a typed provider request whose scope is already a
    # set of derived GraphScopeKey groups, and returns projection-derived
    # observations. No method accepts query text or mutates the graph.
    def traverse(self, request: GraphProviderRequest) -> GraphProviderResult: ...

    def path(self, request: GraphProviderRequest) -> GraphProviderResult: ...

    def neighborhood(self, request: GraphProviderRequest) -> GraphProviderResult: ...

    def structural_similarity(self, request: GraphProviderRequest) -> GraphProviderResult: ...

    def community(self, request: GraphProviderRequest) -> GraphProviderResult: ...

    def centrality(self, request: GraphProviderRequest) -> GraphProviderResult: ...

    def link_prediction(self, request: GraphProviderRequest) -> GraphProviderResult: ...

    def structural_embedding(self, request: GraphProviderRequest) -> GraphProviderResult: ...


#: Port method serving each structural operation.
PORT_METHODS: dict[GraphOperation, str] = {
    GraphOperation.TRAVERSE: "traverse",
    GraphOperation.PATH: "path",
    GraphOperation.NEIGHBORHOOD: "neighborhood",
    GraphOperation.STRUCTURAL_SIMILARITY: "structural_similarity",
    GraphOperation.COMMUNITY: "community",
    GraphOperation.CENTRALITY: "centrality",
    GraphOperation.LINK_PREDICTION: "link_prediction",
    GraphOperation.STRUCTURAL_EMBEDDING: "structural_embedding",
}


class UnservedOperations:
    """Mixin: every structural operation refuses explicitly until implemented.

    A backend that does not implement an operation raises
    ``GraphCapabilityUnavailable``; it never returns an empty result that
    would read as "no relationships found" (GI-029).
    """

    name: str

    def _unserved(self, request: GraphProviderRequest) -> GraphProviderResult:
        raise GraphCapabilityUnavailable(
            f"graph backend {self.name} does not serve {request.operation.value}"
        )

    def traverse(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)

    def path(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)

    def neighborhood(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)

    def structural_similarity(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)

    def community(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)

    def centrality(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)

    def link_prediction(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)

    def structural_embedding(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._unserved(request)
