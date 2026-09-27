# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_health_dimensions.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Separate health dimensions the devpack names (10_OBSERVABILITY, ADR-092).

Active GDS catalog graphs, projection lag and the canonical rehydration
success rate are reported as their own fields and gauges, so no dimension
masks another.
"""

from __future__ import annotations

from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphOperation,
)
from l9_graphite_memory.graph.service import GraphIntelligenceService
from l9_graphite_memory.observability.graph_metrics import GraphMetrics
from l9_graphite_memory.ports import ProjectionEntityHit
from tests.graph_fakes import FakeGraphPort, seeded_memory


class RecordProjection:
    name = "graphiti"
    capabilities = ("graph-search", "semantic-search")

    def __init__(self) -> None:
        self.hits: list[ProjectionEntityHit] = []

    def search_entities(self, query, namespaces, *, limit, tenant_id):
        return list(self.hits)


def _graph(port=None):
    service, store, principal, write = seeded_memory()
    metrics = GraphMetrics()
    projection = RecordProjection()
    graph = GraphIntelligenceService(
        store,
        port or FakeGraphPort(),
        namespace_policy=service.namespace_policy,
        projection=projection,
        metrics=metrics,
    )
    return graph, metrics, projection, principal, write, store


def test_catalog_lag_and_rehydration_are_separate_report_fields() -> None:
    port = FakeGraphPort(health_overrides={"gds_catalog_active": 2})
    graph, metrics, _projection, *_ = _graph(port)
    report = graph.capability_report(refresh=True)
    assert report.gds_catalog_active == 2
    assert metrics.value("memory_graph_gds_catalog_active") == 2.0
    assert report.projection_lag_events == 0
    assert metrics.value("memory_graph_projection_lag_events") == 0.0
    # No graph operation has produced candidates yet: unknown, not 100 %.
    assert report.rehydration_success_rate is None


def test_projection_lag_counts_undelivered_outbox_events() -> None:
    graph, _metrics, _projection, _principal, _write, store = _graph()
    store.outbox_backlog = lambda: 7  # type: ignore[method-assign]
    assert graph.capability_report(refresh=True).projection_lag_events == 7


def test_unreadable_backlog_is_unknown_not_zero() -> None:
    graph, _metrics, _projection, _principal, _write, store = _graph()

    def broken() -> int:
        raise RuntimeError("store down")

    store.outbox_backlog = broken  # type: ignore[method-assign]
    assert graph.capability_report(refresh=True).projection_lag_events is None


def test_rehydration_success_rate_counts_admitted_and_dropped_candidates() -> None:
    graph, metrics, projection, principal, write, _store = _graph()
    own = write("tenant-a", "falcon depends on osprey")
    foreign = write("tenant-b", "bravo secret")
    projection.hits = [
        ProjectionEntityHit(record_id=own, score=0.9, namespace="shared"),
        ProjectionEntityHit(record_id=foreign, score=0.8, namespace="shared"),
    ]
    graph.execute(
        principal("tenant-a"),
        GraphIntelligenceRequest(
            operation=GraphOperation.SEARCH,
            namespaces=("shared",),
            anchor=GraphAnchor(query="falcon"),
        ),
    )
    assert metrics.value("memory_graph_rehydration_admitted_total") == 1.0
    assert graph.capability_report().rehydration_success_rate == 0.5


def test_candidates_never_attempted_do_not_lower_the_rate() -> None:
    metrics = GraphMetrics()
    metrics.inc("memory_graph_rehydration_admitted_total", 3)
    metrics.inc("memory_graph_rehydration_drop_total", reason="no_canonical_support")
    metrics.inc("memory_graph_rehydration_drop_total", 5, reason="graph_backend_unavailable")
    assert metrics.rehydration_success_rate() == 0.75
