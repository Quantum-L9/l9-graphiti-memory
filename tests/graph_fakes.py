# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/graph_fakes.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Deterministic Neo4j driver double for graph-intelligence adapter tests.

Responses are keyed by registered template name, so a test states what the
backend returns for each named statement and the adapter never learns it is
talking to a fake. Every call records the session configuration and the
transaction timeout so read-only access and bounded execution are asserted,
not assumed.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

Responder = Callable[[dict[str, Any]], list[dict[str, Any]]]


@dataclass
class Call:
    template: str
    cypher: str
    parameters: dict[str, Any]
    session_config: dict[str, Any]
    timeout: float | None


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, Any]]:
        return list(self._rows)


@dataclass
class FakeNeo4jDriver:
    """Answers registered templates; raises for anything it was not told."""

    responses: dict[str, list[dict[str, Any]] | Responder | Exception] = field(default_factory=dict)
    cypher_to_template: dict[str, str] = field(default_factory=dict)
    calls: list[Call] = field(default_factory=list)
    closed: bool = False
    unreachable: Exception | None = None

    def bind(self, adapter: Any) -> FakeNeo4jDriver:
        self.cypher_to_template = {
            template.cypher: template.name for template in adapter.registry.templates()
        }
        return self

    def close(self) -> None:
        self.closed = True

    @contextmanager
    def session(self, **config: Any):
        if self.unreachable is not None:
            raise self.unreachable
        driver = self

        class _Tx:
            timeout: float | None = None

            def run(self, query: str, parameters: dict[str, Any] | None = None) -> _Result:
                name = driver.cypher_to_template.get(query, "<unregistered>")
                bound = dict(parameters or {})
                driver.calls.append(Call(name, query, bound, dict(config), self.timeout))
                response = driver.responses.get(name)
                if response is None:
                    raise AssertionError(f"no scripted response for template {name}")
                if isinstance(response, Exception):
                    raise response
                rows = response(bound) if callable(response) else response
                return _Result(rows)

        class _Session:
            def execute_read(self, work: Callable[[Any], Any]) -> Any:
                tx = _Tx()
                tx.timeout = getattr(work, "timeout", None)
                return work(tx)

            def execute_write(self, work: Callable[[Any], Any]) -> Any:  # pragma: no cover
                raise AssertionError("graph intelligence must never open a write transaction")

        yield _Session()


def healthy_graphiti_responses(
    *,
    group_ids: tuple[str, ...] = (),
    gds: bool = True,
) -> dict[str, list[dict[str, Any]] | Responder | Exception]:
    """Responses of a Graphiti v0.30.2 database with GDS 2.13 installed."""

    responses: dict[str, list[dict[str, Any]] | Responder | Exception] = {
        "dbms_components_v1": [
            {"name": "Neo4j Kernel", "versions": ["5.26.31"], "edition": "community"}
        ],
        "schema_labels_v1": [{"labels": ["Entity", "Episodic", "Community"]}],
        "schema_relationship_types_v1": [
            {"types": ["RELATES_TO", "MENTIONS", "HAS_MEMBER", "HAS_EPISODE", "NEXT_EPISODE"]}
        ],
        "schema_property_keys_v1": [
            {"keys": ["uuid", "group_id", "name", "fact", "valid_at", "invalid_at", "extra"]}
        ],
        "scope_group_sample_v1": [{"group_id": group} for group in group_ids],
    }
    if gds:
        responses["gds_version_v1"] = [{"version": "2.13.13"}]
        responses["gds_procedures_v1"] = [
            {
                "names": [
                    "gds.graph.drop",
                    "gds.graph.project",
                    "gds.pageRank.stream",
                    "gds.degree.stream",
                    "gds.betweenness.stream",
                    "gds.louvain.stream",
                    "gds.leiden.stream",
                    "gds.fastRP.stream",
                    "gds.fastRP.write",
                ]
            }
        ]
    else:
        responses["gds_version_v1"] = RuntimeError("Unknown function 'gds.version'")
        responses["gds_procedures_v1"] = RuntimeError("no procedure gds.list")
    return responses


class FakeGraphPort:
    """A GraphIntelligencePort double serving scripted provider results."""

    def __init__(
        self,
        results: dict[Any, Any] | None = None,
        *,
        capabilities: tuple[Any, ...] | None = None,
        health_overrides: dict[str, Any] | None = None,
    ) -> None:
        from l9_graphite_memory.graph.ports import BASELINE_CAPABILITIES

        self.name = "fake-graph"
        self.results = results or {}
        self._capabilities = BASELINE_CAPABILITIES if capabilities is None else capabilities
        self.health_overrides = health_overrides or {}
        self.requests: list[Any] = []
        self.health_calls = 0

    def capabilities(self):
        return self.health().capabilities

    def health(self):
        from l9_graphite_memory.graph.ports import GraphBackendHealth

        self.health_calls += 1
        values = {
            "name": self.name,
            "enabled": True,
            "healthy": True,
            "reachable": True,
            "backend_version": "5.26.31",
            "analytics_version": "2.13.13",
            "capabilities": self._capabilities,
            **self.health_overrides,
        }
        return GraphBackendHealth(**values)

    def close(self) -> None:
        return None

    def _serve(self, request):
        self.requests.append(request)
        outcome = self.results.get(request.operation)
        if outcome is None:
            raise AssertionError(f"no scripted result for {request.operation}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome(request) if callable(outcome) else outcome

    traverse = path = neighborhood = structural_similarity = _serve
    community = centrality = link_prediction = structural_embedding = _serve


def seeded_memory():
    """MemoryService with active records in two tenants that share a namespace."""

    from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
    from l9_graphite_memory.contracts import MemoryPrincipal, MemoryWriteRequest, Provenance
    from l9_graphite_memory.services import MemoryService

    store = InMemoryRecordStore()
    service = MemoryService(store, NullProjection())
    service.initialize()

    def principal(tenant: str, namespaces: tuple[str, ...] = ("shared", "other")):
        return MemoryPrincipal(
            principal_id=f"{tenant}-agent",
            tenant_id=tenant,
            read_namespaces=namespaces,
            write_namespaces=namespaces,
            maintain_namespaces=namespaces,
        )

    def write(tenant: str, content: str, namespace: str = "shared"):
        receipt = service.write(
            principal(tenant),
            MemoryWriteRequest(
                namespace=namespace, content=content, provenance=Provenance(source="graph-test")
            ),
        )
        return receipt.record_id

    return service, store, principal, write
