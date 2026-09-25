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
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Protocol, cast

from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.graph.ports import (
    ANALYTICS_CAPABILITIES,
    BASELINE_CAPABILITIES,
    DEFAULT_RELATIONSHIP_ALLOWLIST,
    GraphBackendHealth,
    GraphCapability,
)
from l9_graphite_memory.graph.scope import GRAPH_SCOPE_SCHEME, is_graph_group_id

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


class Neo4jGraphIntelligence:
    """Read-only structural intelligence over a Graphiti Neo4j projection."""

    name = "neo4j"
    #: Structural operations this adapter implements. Supported-by-backend and
    #: implemented are reported separately; only their intersection is served.
    implemented_capabilities: tuple[GraphCapability, ...] = ()

    def __init__(
        self,
        config: Neo4jGraphIntelligenceConfig,
        *,
        driver_factory: Callable[[], _Driver] | None = None,
        templates: tuple[QueryTemplate, ...] = (),
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
        self.registry = QueryRegistry((*HEALTH_TEMPLATES, *templates))

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
    ) -> list[dict[str, Any]]:
        """Run one registered template in a read transaction. No text by value."""

        template = self.registry.get(template_name)
        bound = dict(parameters or {})
        timeout = (timeout_ms or self.config.query_timeout_ms) / 1_000

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

    def template_names(self) -> Iterator[str]:
        """Audit hook: every statement this adapter can execute, by name."""

        yield from self.registry.names()
