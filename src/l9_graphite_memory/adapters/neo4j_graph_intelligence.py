# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/neo4j_graph_intelligence.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Bounded, read-only Neo4j/GDS graph-intelligence adapter (ADR-085).

Reads the Graphiti-managed projection that lives in Neo4j. It never writes
persistent graph state: every statement is a registered static template
(``neo4j_query_policy``), every session is opened in read access mode, and the
deployment binds a credential separate from Graphiti's writer credential.

The ``neo4j`` driver is an optional dependency (extra ``graph-intelligence``).
The package imports and runs without it; selecting this backend without the
driver installed is a configuration error, never a silent fallback.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid as uuid_module
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from types import ModuleType
from typing import Any, Protocol, cast
from uuid import UUID

from l9_graphite_memory.errors import (
    ConfigurationError,
    GraphCapabilityUnavailable,
    GraphQueryPolicyViolation,
    GraphRuntimeBudgetExceeded,
)
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphProviderEdge,
    GraphProviderNode,
    GraphProviderPath,
    GraphProviderRequest,
    GraphProviderResult,
    GraphProviderScore,
)
from l9_graphite_memory.graph.ports import (
    ANALYTICS_CAPABILITIES,
    BASELINE_CAPABILITIES,
    DEFAULT_RELATIONSHIP_ALLOWLIST,
    GraphBackendHealth,
    GraphCapability,
    UnservedOperations,
)
from l9_graphite_memory.graph.scope import GRAPH_SCOPE_SCHEME, is_graph_group_id

from .neo4j_gds_templates import GDS_TEMPLATES, GRAPH_NAME_PREFIX, project_template_name
from .neo4j_graph_templates import (
    STRUCTURAL_TEMPLATES,
    expand_template_name,
    lucene_escape,
    shortest_path_template_name,
)
from .neo4j_query_policy import QueryRegistry, QueryTemplate, TemplateKind

_neo4j_module: ModuleType | None
try:  # optional extra: graph-intelligence
    import neo4j as _imported_neo4j

    _neo4j_module = _imported_neo4j
except ImportError:  # pragma: no cover - exercised by the optional-dependency test
    _neo4j_module = None

_READ_ACCESS = "READ"

#: Graphiti v0.30.2 constructs the intelligence layer depends on. Additive
#: unknown labels/relations never widen the traversal allowlist.
REQUIRED_LABELS: tuple[str, ...] = ("Entity", "Episodic")
REQUIRED_RELATIONSHIP_TYPES: tuple[str, ...] = ("MENTIONS", "RELATES_TO")
_FINGERPRINT_PROPERTY_KEYS: frozenset[str] = frozenset(
    {
        "uuid",
        "group_id",
        "name",
        "summary",
        "fact",
        "episodes",
        "valid_at",
        "invalid_at",
        "expired_at",
        "created_at",
    }
)
REQUIRED_GDS_PROCEDURES: tuple[str, ...] = (
    "gds.graph.drop",
    "gds.graph.project",
    "gds.pageRank.stream",
    "gds.degree.stream",
    "gds.betweenness.stream",
    "gds.louvain.stream",
    "gds.leiden.stream",
    "gds.fastRP.stream",
)

HEALTH_TEMPLATES: tuple[QueryTemplate, ...] = (
    QueryTemplate(
        "dbms_components_v1",
        TemplateKind.READ,
        "CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition",
    ),
    QueryTemplate(
        "schema_labels_v1",
        TemplateKind.READ,
        "CALL db.labels() YIELD label RETURN collect(label) AS labels",
    ),
    QueryTemplate(
        "schema_relationship_types_v1",
        TemplateKind.READ,
        "CALL db.relationshipTypes() YIELD relationshipType "
        "RETURN collect(relationshipType) AS types",
    ),
    QueryTemplate(
        "schema_property_keys_v1",
        TemplateKind.READ,
        "CALL db.propertyKeys() YIELD propertyKey RETURN collect(propertyKey) AS keys",
    ),
    QueryTemplate(
        "scope_group_sample_v1",
        TemplateKind.READ,
        "MATCH (e:Episodic) WHERE e.group_id IS NOT NULL "
        "RETURN DISTINCT e.group_id AS group_id LIMIT $limit",
    ),
    QueryTemplate("gds_version_v1", TemplateKind.READ, "RETURN gds.version() AS version"),
    QueryTemplate(
        "gds_procedures_v1",
        TemplateKind.READ,
        "CALL gds.list() YIELD name RETURN collect(name) AS names",
    ),
)


_CENTRALITY_TEMPLATES: dict[str, str] = {
    "pagerank": "gds_pagerank_stream_v1",
    "degree": "gds_degree_stream_v1",
    "betweenness": "gds_betweenness_stream_v1",
}
_COMMUNITY_TEMPLATES: dict[str, str] = {
    "louvain": "gds_louvain_stream_v1",
    "leiden": "gds_leiden_stream_v1",
}
_ORIENTATION: dict[str, str] = {"out": "natural", "in": "reverse", "both": "undirected"}


class _Result(Protocol):
    def data(self) -> list[dict[str, Any]]: ...


class _Transaction(Protocol):
    def run(self, query: str, parameters: dict[str, Any] | None = None) -> _Result: ...


class _Session(Protocol):
    def execute_read(self, work: Callable[[_Transaction], Any]) -> Any: ...


class _Driver(Protocol):
    def session(self, **config: Any) -> AbstractContextManager[_Session]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class Neo4jGraphIntelligenceConfig:
    """Resolved adapter settings. Never part of any public memory contract."""

    uri: str
    database: str = "neo4j"
    user: str | None = None
    password: str | None = field(default=None, repr=False)
    query_timeout_ms: int = 3_000
    gds_max_nodes: int = 50_000
    relationship_allowlist: tuple[str, ...] = DEFAULT_RELATIONSHIP_ALLOWLIST
    expected_schema_fingerprint: str | None = None
    link_prediction_enabled: bool = False
    scope_group_sample_size: int = 50


# Absolute monotonic deadline of the provider operation in progress. Every
# statement an operation runs draws on one request-wide budget instead of each
# receiving the whole ``max_runtime_ms`` (ADR-091).
_REQUEST_DEADLINE: ContextVar[float | None] = ContextVar("l9_graph_request_deadline", default=None)


def _within_request_budget(
    method: Callable[[Any, GraphProviderRequest], GraphProviderResult],
) -> Callable[[Any, GraphProviderRequest], GraphProviderResult]:
    """Bind one deadline for a whole provider operation (outermost call wins)."""

    @wraps(method)
    def bounded(self: Any, request: GraphProviderRequest) -> GraphProviderResult:
        if _REQUEST_DEADLINE.get() is not None:
            return method(self, request)
        token = _REQUEST_DEADLINE.set(self._monotonic() + request.limits.max_runtime_ms / 1_000)
        try:
            return method(self, request)
        finally:
            _REQUEST_DEADLINE.reset(token)

    return bounded


def schema_fingerprint(
    labels: tuple[str, ...] | list[str],
    relationship_types: tuple[str, ...] | list[str],
    property_keys: tuple[str, ...] | list[str],
) -> str:
    """Deterministic digest of the Graphiti constructs this layer relies on."""

    material = {
        "labels": sorted(set(labels)),
        "relationship_types": sorted(set(relationship_types)),
        "property_keys": sorted(set(property_keys) & _FINGERPRINT_PROPERTY_KEYS),
        "scope_scheme": GRAPH_SCOPE_SCHEME,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _unit_of_work(timeout_seconds: float) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    if _neo4j_module is not None:
        decorator: Callable[[Callable[..., Any]], Callable[..., Any]] = _neo4j_module.unit_of_work(
            timeout=timeout_seconds
        )
        return decorator

    def attach(function: Callable[..., Any]) -> Callable[..., Any]:
        function.__dict__["timeout"] = timeout_seconds
        return function

    return attach


class Neo4jGraphIntelligence(UnservedOperations):
    """Read-only structural intelligence over a Graphiti Neo4j projection."""

    name = "neo4j"
    #: Structural operations this adapter implements. Supported-by-backend and
    #: implemented are reported separately; only their intersection is served.
    implemented_capabilities: tuple[GraphCapability, ...] = (
        GraphCapability.TRAVERSE,
        GraphCapability.PATH,
        GraphCapability.NEIGHBORHOOD,
        GraphCapability.STRUCTURAL_SIMILARITY,
        GraphCapability.COMMUNITY,
        GraphCapability.CENTRALITY,
        GraphCapability.LINK_PREDICTION,
        GraphCapability.STRUCTURAL_EMBEDDING,
    )
    #: Canonical support ids collected per entity or edge.
    support_limit = 50
    #: Entities a record or text anchor may resolve to.
    anchor_resolution_limit = 10

    def __init__(
        self,
        config: Neo4jGraphIntelligenceConfig,
        *,
        driver_factory: Callable[[], _Driver] | None = None,
        templates: tuple[QueryTemplate, ...] = (),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not config.uri.strip():
            raise ConfigurationError("graph intelligence neo4j backend requires a URI")
        if driver_factory is None and _neo4j_module is None:
            raise ConfigurationError(
                "graph intelligence backend 'neo4j' requires the optional driver: "
                "install l9-graphite-memory[graph-intelligence]"
            )
        self.config = config
        self._driver_factory = driver_factory or self._default_driver_factory
        self._driver: _Driver | None = None
        self.registry = QueryRegistry(
            (*HEALTH_TEMPLATES, *STRUCTURAL_TEMPLATES, *GDS_TEMPLATES, *templates)
        )
        self.catalog_cleanup_failures = 0
        self._monotonic = monotonic

    def _default_driver_factory(self) -> _Driver:
        assert _neo4j_module is not None
        auth = (self.config.user, self.config.password or "") if self.config.user else None
        budget_seconds = self.config.query_timeout_ms / 1_000
        driver = _neo4j_module.GraphDatabase.driver(
            self.config.uri,
            auth=auth,
            # An unreachable backend must fail inside the query budget rather
            # than behind the driver's default 30 s managed-transaction retry.
            max_transaction_retry_time=budget_seconds,
            connection_timeout=budget_seconds,
            connection_acquisition_timeout=budget_seconds,
            # Server notifications can echo query text; never log them.
            notifications_min_severity="OFF",
            user_agent="l9-graphite-memory/graph-intelligence",
        )
        return cast("_Driver", driver)

    def _driver_instance(self) -> _Driver:
        if self._driver is None:
            self._driver = self._driver_factory()
        return self._driver

    def _read(
        self,
        template_name: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        timeout_ms: int | None = None,
        budgeted: bool = True,
    ) -> list[dict[str, Any]]:
        """Run one registered template in a read transaction. No text by value.

        Inside a provider operation the statement gets at most what is left of
        the request-wide budget, and none is started once it is spent.
        ``budgeted=False`` is reserved for cleanup that must run regardless.
        """

        template = self.registry.get(template_name)
        bound = dict(parameters or {})
        timeout = (timeout_ms or self.config.query_timeout_ms) / 1_000
        deadline = _REQUEST_DEADLINE.get()
        if budgeted and deadline is not None:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise GraphRuntimeBudgetExceeded(
                    f"request runtime budget spent before {template_name}"
                )
            timeout = min(timeout, remaining)

        def work(tx: _Transaction) -> list[dict[str, Any]]:
            return tx.run(template.cypher, bound).data()

        with self._driver_instance().session(
            database=self.config.database, default_access_mode=_READ_ACCESS
        ) as session:
            rows: list[dict[str, Any]] = session.execute_read(_unit_of_work(timeout)(work))
        return rows

    def _single(self, template_name: str, key: str) -> Any:
        rows = self._read(template_name)
        return rows[0].get(key) if rows else None

    def _probe_analytics(self) -> tuple[str | None, tuple[str, ...]]:
        try:
            version = self._single("gds_version_v1", "version")
            names = set(self._single("gds_procedures_v1", "names") or ())
        except Exception:  # noqa: BLE001 - absence of GDS is a reported state
            return None, REQUIRED_GDS_PROCEDURES
        missing = tuple(name for name in REQUIRED_GDS_PROCEDURES if name not in names)
        return (str(version) if version is not None else None), missing

    def health(self) -> GraphBackendHealth:
        try:
            components = self._read("dbms_components_v1")
            labels = list(self._single("schema_labels_v1", "labels") or ())
            relationship_types = list(self._single("schema_relationship_types_v1", "types") or ())
            property_keys = list(self._single("schema_property_keys_v1", "keys") or ())
            sample = self._read(
                "scope_group_sample_v1", {"limit": self.config.scope_group_sample_size}
            )
        except Exception as exc:  # noqa: BLE001 - unreachable is a reported state
            return GraphBackendHealth(
                name=self.name,
                enabled=True,
                healthy=False,
                reachable=False,
                database=self.config.database,
                scope_scheme=GRAPH_SCOPE_SCHEME,
                error_class=type(exc).__name__,
                detail="graph backend unreachable or probe failed",
            )
        kernel = next(
            (row for row in components if row.get("name") == "Neo4j Kernel"),
            components[0] if components else {},
        )
        versions = kernel.get("versions") or []
        fingerprint = schema_fingerprint(labels, relationship_types, property_keys)
        missing_labels = tuple(label for label in REQUIRED_LABELS if label not in labels)
        missing_types = tuple(
            rel for rel in REQUIRED_RELATIONSHIP_TYPES if rel not in relationship_types
        )
        expected = self.config.expected_schema_fingerprint
        schema_compatible = (
            not missing_labels
            and not missing_types
            and (expected is None or expected == fingerprint)
        )
        groups = [str(row.get("group_id")) for row in sample if row.get("group_id") is not None]
        conformant = all(is_graph_group_id(group) for group in groups) if groups else None
        analytics_version, missing_procedures = self._probe_analytics()
        analytics_available = analytics_version is not None and not missing_procedures

        supported: list[GraphCapability] = []
        if schema_compatible and conformant is not False:
            supported.extend(BASELINE_CAPABILITIES)
            if analytics_available:
                supported.extend(
                    capability
                    for capability in ANALYTICS_CAPABILITIES
                    if capability is not GraphCapability.LINK_PREDICTION
                    or self.config.link_prediction_enabled
                )
        served = tuple(c for c in supported if c in self.implemented_capabilities)
        problems: list[str] = []
        if missing_labels or missing_types:
            problems.append("required Graphiti constructs missing")
        if expected is not None and expected != fingerprint:
            problems.append("schema fingerprint differs from the qualified binding")
        if conformant is False:
            problems.append("projection groups do not use the GraphScopeKey v1 scheme")
        return GraphBackendHealth(
            name=self.name,
            enabled=True,
            healthy=schema_compatible and conformant is not False,
            reachable=True,
            database=self.config.database,
            backend_version=str(versions[0]) if versions else None,
            backend_edition=str(kernel.get("edition")) if kernel.get("edition") else None,
            schema_fingerprint=fingerprint,
            expected_schema_fingerprint=expected,
            schema_compatible=schema_compatible,
            missing_labels=missing_labels,
            missing_relationship_types=missing_types,
            analytics_available=analytics_available,
            analytics_version=analytics_version,
            missing_procedures=missing_procedures,
            scope_scheme=GRAPH_SCOPE_SCHEME,
            scope_scheme_conformant=conformant,
            supported_capabilities=tuple(supported),
            capabilities=served,
            detail="; ".join(problems),
        )

    def capabilities(self) -> tuple[GraphCapability, ...]:
        return self.health().capabilities

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    # -- structural operations (ADR-087) ---------------------------------

    def _base_parameters(self, request: GraphProviderRequest) -> dict[str, Any]:
        return {
            "group_ids": list(request.group_ids),
            "relationship_types": list(request.relationship_types),
            "as_of": request.as_of,
            "recorded_before": request.recorded_before,
            "support_limit": self.support_limit,
        }

    def _resolve_anchor(
        self, anchor: GraphAnchor | None, request: GraphProviderRequest
    ) -> list[str]:
        if anchor is None:
            raise GraphQueryPolicyViolation(f"{request.operation.value} requires an anchor")
        group_ids = list(request.group_ids)
        if anchor.entity_uuid is not None:
            return [str(anchor.entity_uuid)]
        if anchor.record_id is not None:
            rows = self._read(
                "episode_entities_v1",
                {
                    "record_id": str(anchor.record_id),
                    "episode_name": f"memory:{anchor.record_id}",
                    "group_ids": group_ids,
                    "limit": self.anchor_resolution_limit,
                },
                timeout_ms=request.limits.max_runtime_ms,
            )
        else:
            rows = self._read(
                "entity_lookup_v1",
                {
                    "query": lucene_escape(anchor.query or ""),
                    "group_ids": group_ids,
                    "scan_limit": self.anchor_resolution_limit * 10,
                    "limit": self.anchor_resolution_limit,
                },
                timeout_ms=request.limits.max_runtime_ms,
            )
        return [str(row["uuid"]) for row in rows if row.get("uuid")]

    def _expand(self, request: GraphProviderRequest, direction: str) -> GraphProviderResult:
        anchors = self._resolve_anchor(request.anchor, request)
        parameters = {**self._base_parameters(request), "anchor_uuids": anchors}
        limits = request.limits
        budget = limits.max_edges + 1
        rows = self._read("anchor_entities_v1", parameters, timeout_ms=limits.max_runtime_ms)
        path_rows: list[dict[str, Any]] = []
        if anchors and limits.max_depth > 0:
            path_rows = self._read(
                expand_template_name(direction, limits.max_depth),
                {**parameters, "path_budget": budget},
                timeout_ms=limits.max_runtime_ms,
            )
        return self._assemble(request, [*rows, *path_rows], len(path_rows) >= budget)

    @_within_request_budget
    def traverse(self, request: GraphProviderRequest) -> GraphProviderResult:
        return self._expand(request, request.direction)

    @_within_request_budget
    def neighborhood(self, request: GraphProviderRequest) -> GraphProviderResult:
        # A neighborhood is direction-agnostic by definition.
        return self._expand(request, "both")

    @_within_request_budget
    def path(self, request: GraphProviderRequest) -> GraphProviderResult:
        if request.limits.max_depth < 1:
            raise GraphQueryPolicyViolation("graph.path requires max_depth >= 1")
        sources = self._resolve_anchor(request.anchor, request)
        targets = self._resolve_anchor(request.target, request)
        if not sources or not targets:
            return GraphProviderResult(operation=request.operation)
        budget = request.limits.max_paths + 1
        rows = self._read(
            shortest_path_template_name(request.direction, request.limits.max_depth),
            {
                **self._base_parameters(request),
                "anchor_uuids": sources,
                "target_uuids": targets,
                "path_budget": budget,
            },
            timeout_ms=request.limits.max_runtime_ms,
        )
        return self._assemble(request, rows, len(rows) >= budget, as_paths=True)

    def _assemble(
        self,
        request: GraphProviderRequest,
        rows: list[dict[str, Any]],
        truncated: bool,
        *,
        as_paths: bool = False,
    ) -> GraphProviderResult:
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        paths: list[GraphProviderPath] = []
        for row in rows:
            row_nodes = [n for n in row.get("nodes") or [] if n and n.get("uuid")]
            row_edges = [e for e in row.get("edges") or [] if e and e.get("source")]
            for node in row_nodes:
                nodes.setdefault(str(node["uuid"]), node)
            for edge in row_edges:
                key = str(edge.get("uuid") or (edge["source"], edge["type"], edge["target"]))
                edges.setdefault(key, edge)
            if as_paths and row_nodes:
                paths.append(
                    GraphProviderPath(
                        node_uuids=tuple(UUID(str(n["uuid"])) for n in row_nodes),
                        edge_uuids=tuple(UUID(str(e["uuid"])) for e in row_edges if e.get("uuid")),
                        length=len(row_edges),
                    )
                )
        limits = request.limits
        if len(nodes) > limits.max_nodes or len(edges) > limits.max_edges:
            truncated = True
        support = self._entity_support(request, list(nodes)) if nodes else {}
        edge_support = self._episode_support(
            request, [str(e) for edge in edges.values() for e in edge.get("episodes") or ()]
        )
        provider_nodes = tuple(
            GraphProviderNode(
                entity_uuid=UUID(uuid),
                group_id=str(node.get("group_id")),
                labels=tuple(sorted(str(label) for label in node.get("labels") or ())),
                name=node.get("name"),
                supporting_episode_ids=support.get(uuid, ()),
            )
            for uuid, node in sorted(nodes.items())
        )
        provider_edges = tuple(
            GraphProviderEdge(
                edge_uuid=UUID(str(edge["uuid"])) if edge.get("uuid") else None,
                source_uuid=UUID(str(edge["source"])),
                target_uuid=UUID(str(edge["target"])),
                relationship_type=str(edge.get("type")),
                group_id=str(edge.get("group_id")),
                fact=edge.get("fact"),
                valid_at=_as_datetime(edge.get("valid_at")),
                invalid_at=_as_datetime(edge.get("invalid_at")),
                supporting_episode_ids=_uuids(
                    edge_support.get(str(e), str(e)) for e in edge.get("episodes") or ()
                ),
            )
            for _, edge in sorted(edges.items())
        )
        return GraphProviderResult(
            operation=request.operation,
            nodes=provider_nodes,
            edges=provider_edges,
            paths=tuple(paths),
            truncated=truncated,
            provider_metadata={"backend": self.name, "database": self.config.database},
        )

    # -- GDS analytics (ADR-088), stream mode only --------------------------

    def _projected(
        self,
        request: GraphProviderRequest,
        stream: Callable[[str], list[dict[str, Any]]],
        *,
        undirected: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Project the authorized scope, stream one analytic, always drop."""

        base = self._base_parameters(request)
        timeout = request.limits.max_runtime_ms
        size_rows = self._read("gds_scope_size_v1", base, timeout_ms=timeout)
        nodes = int(size_rows[0].get("nodes") or 0) if size_rows else 0
        relationships = int(size_rows[0].get("rels") or 0) if size_rows else 0
        if nodes > self.config.gds_max_nodes:
            raise GraphQueryPolicyViolation(
                f"analytics scope has {nodes} nodes; the ceiling is {self.config.gds_max_nodes}"
            )
        metadata: dict[str, Any] = {
            "backend": self.name,
            "database": self.config.database,
            "scope_nodes": nodes,
            "scope_relationships": relationships,
            "gds_mode": "stream",
        }
        if relationships == 0:
            return [], metadata
        max_relationships = self.config.gds_max_nodes * 20
        orientation = "undirected" if undirected else _ORIENTATION[request.direction]
        # Catalog names carry the operation digest and a random suffix only:
        # never a tenant or namespace (GI-018).
        graph_name = (
            f"{GRAPH_NAME_PREFIX}{request.operation_id[:16]}_{uuid_module.uuid4().hex[:12]}"
        )
        try:
            projected = self._read(
                project_template_name(orientation),
                {**base, "graph_name": graph_name, "max_relationships": max_relationships},
                timeout_ms=timeout,
            )
            rows = stream(graph_name)
        finally:
            metadata["catalog_cleanup"] = self._drop_catalog_graph(graph_name, timeout)
        if projected:
            metadata["projected_nodes"] = projected[0].get("node_count")
            metadata["projected_relationships"] = projected[0].get("relationship_count")
        metadata["projection_truncated"] = relationships > max_relationships
        return rows, metadata

    def _drop_catalog_graph(self, graph_name: str, timeout_ms: int) -> str:
        try:
            # Cleanup runs even when the request budget is spent.
            self._read(
                "gds_drop_v1", {"graph_name": graph_name}, timeout_ms=timeout_ms, budgeted=False
            )
        except Exception:  # noqa: BLE001 - reported, and swept by cleanup_stale_catalog
            self.catalog_cleanup_failures += 1
            return "failed"
        return "dropped"

    def cleanup_stale_catalog(self) -> int:
        """Drop every graph-intelligence catalog entry left by a crash."""

        rows = self._read("gds_catalog_list_v1", {"prefix": GRAPH_NAME_PREFIX})
        names = list(rows[0].get("names") or ()) if rows else []
        dropped = 0
        for name in names:
            if self._drop_catalog_graph(str(name), self.config.query_timeout_ms) == "dropped":
                dropped += 1
        return dropped

    def _nodes_for(
        self, request: GraphProviderRequest, entity_uuids: list[str]
    ) -> tuple[GraphProviderNode, ...]:
        if not entity_uuids:
            return ()
        rows = self._read(
            "anchor_entities_v1",
            {"anchor_uuids": entity_uuids, "group_ids": list(request.group_ids)},
            timeout_ms=request.limits.max_runtime_ms,
        )
        found = {
            str(node["uuid"]): node
            for row in rows
            for node in row.get("nodes") or []
            if node and node.get("uuid")
        }
        support = self._entity_support(request, list(found))
        return tuple(
            GraphProviderNode(
                entity_uuid=UUID(uuid),
                group_id=str(node.get("group_id")),
                labels=tuple(sorted(str(label) for label in node.get("labels") or ())),
                name=node.get("name"),
                supporting_episode_ids=support.get(uuid, ()),
            )
            for uuid, node in sorted(found.items())
        )

    def _analytic_result(
        self,
        request: GraphProviderRequest,
        scores: list[GraphProviderScore],
        metadata: dict[str, Any],
        *,
        truncated: bool = False,
    ) -> GraphProviderResult:
        members = {str(s.entity_uuid) for s in scores} | {
            str(s.target_uuid) for s in scores if s.target_uuid
        }
        return GraphProviderResult(
            operation=request.operation,
            nodes=self._nodes_for(request, sorted(members)),
            scores=tuple(scores),
            truncated=truncated or bool(metadata.get("projection_truncated")),
            provider_metadata=metadata,
        )

    @_within_request_budget
    def centrality(self, request: GraphProviderRequest) -> GraphProviderResult:
        template = _CENTRALITY_TEMPLATES.get(request.algorithm_id or "")
        if template is None:
            raise GraphQueryPolicyViolation(f"unsupported centrality {request.algorithm_id!r}")
        limit = request.limits.max_nodes
        rows, metadata = self._projected(
            request,
            lambda name: self._read(
                template,
                {"graph_name": name, "limit": limit + 1},
                timeout_ms=request.limits.max_runtime_ms,
            ),
        )
        scores = [
            GraphProviderScore(
                entity_uuid=UUID(str(row["uuid"])),
                group_id=str(row.get("group_id")),
                score=float(row.get("score") or 0.0),
            )
            for row in rows[:limit]
        ]
        return self._analytic_result(request, scores, metadata, truncated=len(rows) > limit)

    @_within_request_budget
    def community(self, request: GraphProviderRequest) -> GraphProviderResult:
        algorithm = request.algorithm_id or ""
        template = _COMMUNITY_TEMPLATES.get(algorithm)
        if template is None:
            raise GraphQueryPolicyViolation(f"unsupported community algorithm {algorithm!r}")
        if algorithm == "leiden" and request.direction != "both":
            raise GraphQueryPolicyViolation("leiden requires an undirected projection")
        limit = request.limits.max_nodes
        rows, metadata = self._projected(
            request,
            lambda name: self._read(
                template,
                {
                    "graph_name": name,
                    "limit": limit + 1,
                    "random_seed": int(request.algorithm_config.get("random_seed", 42)),
                },
                timeout_ms=request.limits.max_runtime_ms,
            ),
            undirected=algorithm == "leiden",
        )
        scores = [
            GraphProviderScore(
                entity_uuid=UUID(str(row["uuid"])),
                group_id=str(row.get("group_id")),
                community_id=int(row["community_id"]),
            )
            for row in rows[:limit]
        ]
        return self._analytic_result(request, scores, metadata, truncated=len(rows) > limit)

    def _embeddings(
        self, request: GraphProviderRequest, limit: int
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        config = request.algorithm_config
        return self._projected(
            request,
            lambda name: self._read(
                "gds_fastrp_stream_v1",
                {
                    "graph_name": name,
                    "limit": limit,
                    "embedding_dimension": int(config.get("embedding_dimension", 64)),
                    "random_seed": int(config.get("random_seed", 42)),
                },
                timeout_ms=request.limits.max_runtime_ms,
            ),
        )

    @_within_request_budget
    def structural_embedding(self, request: GraphProviderRequest) -> GraphProviderResult:
        anchors = set(self._resolve_anchor(request.anchor, request)) if request.anchor else None
        limit = request.limits.max_nodes
        rows, metadata = self._embeddings(
            request, self.config.gds_max_nodes if anchors is not None else limit + 1
        )
        if anchors is not None:
            rows = [row for row in rows if str(row["uuid"]) in anchors]
        scores = [
            GraphProviderScore(
                entity_uuid=UUID(str(row["uuid"])),
                group_id=str(row.get("group_id")),
                embedding=tuple(float(v) for v in row.get("embedding") or ()),
            )
            for row in rows[:limit]
        ]
        return self._analytic_result(request, scores, metadata, truncated=len(rows) > limit)

    @_within_request_budget
    def structural_similarity(self, request: GraphProviderRequest) -> GraphProviderResult:
        anchors = self._resolve_anchor(request.anchor, request)
        if not anchors:
            return GraphProviderResult(operation=request.operation)
        anchor = anchors[0]
        rows, metadata = self._embeddings(request, self.config.gds_max_nodes)
        vectors = {
            str(row["uuid"]): (row.get("group_id"), row.get("embedding") or []) for row in rows
        }
        if anchor not in vectors:
            return self._analytic_result(request, [], metadata)
        anchor_vector = vectors[anchor][1]
        ranked = sorted(
            (
                (_cosine(anchor_vector, vector), uuid, group)
                for uuid, (group, vector) in vectors.items()
                if uuid != anchor
            ),
            key=lambda item: (-item[0], item[1]),
        )
        limit = request.limits.max_nodes
        scores = [
            GraphProviderScore(
                entity_uuid=UUID(uuid),
                group_id=str(group),
                target_uuid=UUID(anchor),
                score=similarity,
            )
            for similarity, uuid, group in ranked[:limit]
        ]
        metadata["similarity"] = "cosine over streamed FastRP vectors"
        return self._analytic_result(request, scores, metadata, truncated=len(ranked) > limit)

    @_within_request_budget
    def link_prediction(self, request: GraphProviderRequest) -> GraphProviderResult:
        # Feature-gated at the adapter too, not only by the service policy.
        if not self.config.link_prediction_enabled:
            raise GraphCapabilityUnavailable("link prediction is disabled for this backend")
        anchors = self._resolve_anchor(request.anchor, request)
        if not anchors:
            return GraphProviderResult(operation=request.operation)
        anchor = anchors[0]
        limit = request.limits.max_nodes
        rows = self._read(
            "link_candidates_v1",
            {
                **self._base_parameters(request),
                "anchor_uuid": anchor,
                "candidate_budget": limit * 20,
            },
            timeout_ms=request.limits.max_runtime_ms,
        )
        score_of = _LINK_SCORES.get(request.algorithm_id or "")
        if score_of is None:
            raise GraphQueryPolicyViolation(f"unsupported link predictor {request.algorithm_id!r}")
        ranked = sorted(
            (
                (score_of([int(d) for d in row.get("common_degrees") or ()]), str(row["uuid"]))
                for row in rows
                if row.get("uuid")
            ),
            key=lambda item: (-item[0], item[1]),
        )
        anchor_group = next(iter(request.group_ids))
        groups = {str(row["uuid"]): str(row.get("group_id")) for row in rows}
        scores = [
            GraphProviderScore(
                entity_uuid=UUID(anchor),
                group_id=groups.get(uuid, anchor_group),
                target_uuid=UUID(uuid),
                score=score,
            )
            for score, uuid in ranked[:limit]
        ]
        metadata = {
            "backend": self.name,
            "database": self.config.database,
            "link_prediction": "in-scope topological score; candidates are never materialized",
        }
        return self._analytic_result(request, scores, metadata, truncated=len(ranked) > limit)

    def _entity_support(
        self, request: GraphProviderRequest, entity_uuids: list[str]
    ) -> dict[str, tuple[UUID, ...]]:
        rows = self._read(
            "entity_supporting_episodes_v1",
            {
                "entity_uuids": entity_uuids,
                "group_ids": list(request.group_ids),
                "support_limit": self.support_limit,
            },
            timeout_ms=request.limits.max_runtime_ms,
        )
        return {str(row["uuid"]): _uuids(row.get("episodes")) for row in rows}

    def _episode_support(
        self, request: GraphProviderRequest, episode_uuids: list[str]
    ) -> dict[str, str]:
        """Map edge episode uuids to canonical support ids (ADR-090).

        Ids that name no in-scope episode are returned unchanged; the evidence
        linker admits only ids that rehydrate to canonical records.
        """

        unique = sorted(set(episode_uuids))
        if not unique:
            return {}
        rows = self._read(
            "episode_support_ids_v1",
            {"episode_uuids": unique, "group_ids": list(request.group_ids)},
            timeout_ms=request.limits.max_runtime_ms,
        )
        return {str(row["uuid"]): str(row["support"]) for row in rows if row.get("support")}

    def template_names(self) -> Iterator[str]:
        """Audit hook: every statement this adapter can execute, by name."""

        yield from self.registry.names()


def _uuids(values: Any) -> tuple[UUID, ...]:
    """Parse provider id lists; anything that is not a UUID is not evidence."""

    if isinstance(values, str):
        values = [part for part in values.split(",") if part]
    parsed: list[UUID] = []
    for value in values or ():
        try:
            parsed.append(UUID(str(value)))
        except ValueError:
            continue
    return tuple(parsed)


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        native = to_native()
        return native if isinstance(native, datetime) else None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _adamic_adar(degrees: list[int]) -> float:
    return sum(1.0 / math.log(d) for d in degrees if d > 1)


def _resource_allocation(degrees: list[int]) -> float:
    return sum(1.0 / d for d in degrees if d > 0)


_LINK_SCORES: dict[str, Callable[[list[int]], float]] = {
    "adamic-adar": _adamic_adar,
    "common-neighbors": lambda degrees: float(len(degrees)),
    "resource-allocation": _resource_allocation,
}
