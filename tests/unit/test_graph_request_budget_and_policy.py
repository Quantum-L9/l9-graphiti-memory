# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_request_budget_and_policy.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Request-wide runtime budget and shared search policy (ADR-091, audit findings 3-4)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)
from l9_graphite_memory.errors import GraphRuntimeBudgetExceeded
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphLimits,
    GraphOperation,
    GraphProviderRequest,
    GraphProviderResult,
    GraphReceiptStatus,
)
from l9_graphite_memory.graph.service import GraphIntelligenceService, GraphServiceConfig
from l9_graphite_memory.ports import ProjectionHit
from tests.graph_fakes import FakeGraphPort, FakeNeo4jDriver, seeded_memory

GROUP = graph_group_id("tenant-a", "shared")


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _request(**overrides) -> GraphIntelligenceRequest:
    values = {
        "operation": GraphOperation.NEIGHBORHOOD,
        "namespaces": ("shared",),
        "anchor": GraphAnchor(entity_uuid=uuid4()),
        "limits": GraphLimits(max_runtime_ms=1_000),
    }
    values.update(overrides)
    return GraphIntelligenceRequest(**values)


def _service(port, clock, projection=None):
    service, store, principal, write = seeded_memory()
    graph = GraphIntelligenceService(
        store,
        port,
        namespace_policy=service.namespace_policy,
        projection=projection,
        config=GraphServiceConfig(max_runtime_ms=5_000),
        monotonic=clock,
    )
    return graph, principal, write


# -- finding 3: one budget for the whole request -----------------------------


def test_provider_receives_only_the_budget_left_after_earlier_stages() -> None:
    clock = Clock()

    class SlowHealthPort(FakeGraphPort):
        def health(self):
            clock.advance(0.3)
            return super().health()

    port = SlowHealthPort(
        {GraphOperation.NEIGHBORHOOD: GraphProviderResult(operation="graph.neighborhood")}
    )
    graph, principal, _ = _service(port, clock)
    graph.execute(principal("tenant-a"), _request())
    assert port.requests[0].limits.max_runtime_ms == 700


def test_budget_spent_before_the_provider_refuses_without_calling_it() -> None:
    clock = Clock()

    class SlowHealthPort(FakeGraphPort):
        def health(self):
            clock.advance(1.5)
            return super().health()

    port = SlowHealthPort(
        {GraphOperation.NEIGHBORHOOD: GraphProviderResult(operation="graph.neighborhood")}
    )
    graph, principal, _ = _service(port, clock)
    receipt = graph.execute(principal("tenant-a"), _request())
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures == ({"class": "runtime_budget_exhausted", "stage": "limits"},)
    assert port.requests == []


def test_an_answer_after_the_deadline_is_not_served() -> None:
    clock = Clock()

    def slow(request):
        clock.advance(2.0)
        return GraphProviderResult(operation=request.operation)

    graph, principal, _ = _service(FakeGraphPort({GraphOperation.NEIGHBORHOOD: slow}), clock)
    receipt = graph.execute(principal("tenant-a"), _request())
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == "runtime_budget_exceeded"
    assert receipt.results == ()


def test_provider_budget_exhaustion_is_a_typed_failure() -> None:
    clock = Clock()
    port = FakeGraphPort({GraphOperation.NEIGHBORHOOD: GraphRuntimeBudgetExceeded("spent")})
    graph, principal, _ = _service(port, clock)
    receipt = graph.execute(principal("tenant-a"), _request())
    assert receipt.failures[0]["class"] == "runtime_budget_exhausted"


def _adapter(responses, clock) -> tuple[Neo4jGraphIntelligence, FakeNeo4jDriver]:
    driver = FakeNeo4jDriver(responses=responses)
    adapter = Neo4jGraphIntelligence(
        Neo4jGraphIntelligenceConfig(uri="bolt://graph.invalid:7687"),
        driver_factory=lambda: driver,
        monotonic=clock,
    )
    driver.bind(adapter)
    return adapter, driver


def _node(uuid):
    return {"uuid": str(uuid), "group_id": GROUP, "name": "n", "labels": ["Entity"]}


def test_adapter_statements_share_one_budget_and_stop_when_it_is_spent() -> None:
    clock = Clock()
    a, b = uuid4(), uuid4()

    def after(seconds, rows):
        def respond(_parameters):
            clock.advance(seconds)
            return rows

        return respond

    edge = {
        "uuid": str(uuid4()),
        "source": str(a),
        "target": str(b),
        "type": "RELATES_TO",
        "group_id": GROUP,
        "episodes": [str(uuid4())],
    }
    adapter, driver = _adapter(
        {
            "anchor_entities_v1": [{"nodes": [_node(a)], "edges": []}],
            "expand_both_d1_v1": after(0.6, [{"nodes": [_node(a), _node(b)], "edges": [edge]}]),
            "entity_supporting_episodes_v1": after(0.6, []),
            "episode_support_ids_v1": [],
        },
        clock,
    )
    request = GraphProviderRequest(
        operation=GraphOperation.NEIGHBORHOOD,
        group_ids=(GROUP,),
        anchor=GraphAnchor(entity_uuid=a),
        relationship_types=("RELATES_TO",),
        limits=GraphLimits(max_depth=1, max_runtime_ms=1_000),
        operation_id="budget",
    )
    with pytest.raises(GraphRuntimeBudgetExceeded):
        adapter.neighborhood(request)
    timeouts = [call.timeout for call in driver.calls]
    # Each statement gets what is left, not the whole request budget.
    assert timeouts[:2] == [pytest.approx(1.0), pytest.approx(1.0)]
    assert timeouts[2] == pytest.approx(0.4)
    # The third statement (edge episode mapping) never starts.
    assert [call.template for call in driver.calls] == [
        "anchor_entities_v1",
        "expand_both_d1_v1",
        "entity_supporting_episodes_v1",
    ]


def test_gds_catalog_cleanup_runs_after_the_budget_is_spent() -> None:
    from tests.unit.test_neo4j_gds_operations import _analytics_responses
    from tests.unit.test_neo4j_gds_operations import _request as gds_request

    clock = Clock()
    responses = _analytics_responses([{"uuid": str(uuid4()), "score": 1.0}])

    def slow_stream(_parameters):
        clock.advance(5.0)
        return [{"uuid": str(uuid4()), "score": 1.0}]

    responses["gds_pagerank_stream_v1"] = slow_stream
    adapter, driver = _adapter(responses, clock)
    with pytest.raises(GraphRuntimeBudgetExceeded):
        adapter.centrality(gds_request(limits=GraphLimits(max_nodes=10, max_runtime_ms=1_000)))
    assert "gds_drop_v1" in [call.template for call in driver.calls]


# -- finding 4: search goes through shared policy -----------------------------


class Projection:
    name = "graphiti"
    capabilities = ("graph-search", "semantic-search")

    def __init__(self, clock: Clock, hits: dict[str, list], step: float = 0.0) -> None:
        self.clock = clock
        self.hits = hits
        self.step = step
        self.calls: list[tuple[str, ...]] = []

    def search_strategy(self, strategy, query, namespaces, *, limit, tenant_id):
        self.calls.append(tuple(namespaces))
        self.clock.advance(self.step)
        return [hit for namespace in namespaces for hit in self.hits.get(namespace, [])]


def _search(**overrides) -> GraphIntelligenceRequest:
    values = {"operation": GraphOperation.SEARCH, "anchor": GraphAnchor(query="falcon")}
    values.update(overrides)
    return _request(**values)


@pytest.mark.parametrize(
    ("overrides", "failure"),
    [
        ({"algorithm": "not-an-algorithm"}, "algorithm_not_admitted"),
        ({"relationship_types": ("DROP_EVERYTHING",)}, "relationship_type_not_allowed"),
        ({"relationship_types": ("RELATES_TO",)}, "request_field_not_applicable"),
        ({"target": GraphAnchor(entity_uuid=uuid4())}, "request_field_not_applicable"),
        ({"direction": "out"}, "request_field_not_applicable"),
    ],
)
def test_search_refuses_out_of_policy_requests_with_a_typed_receipt(overrides, failure) -> None:
    clock = Clock()
    projection = Projection(clock, {})
    graph, principal, _ = _service(FakeGraphPort(), clock, projection)
    receipt = graph.execute(principal("tenant-a"), _search(**overrides))
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == failure
    assert projection.calls == []


def test_multi_namespace_search_stops_at_the_deadline_and_reports_partial() -> None:
    clock = Clock()
    graph, principal, write = _service(FakeGraphPort(), clock)
    shared = write("tenant-a", "falcon shared")
    other = write("tenant-a", "falcon other", namespace="other")
    projection = Projection(
        clock,
        {
            "shared": [ProjectionHit(record_id=shared, score=0.9)],
            "other": [ProjectionHit(record_id=other, score=0.8)],
        },
        step=0.6,
    )
    graph.projection = projection
    receipt = graph.execute(principal("tenant-a"), _search(namespaces=("shared", "other")))
    assert projection.calls == [("shared",), ("other",)]
    # "other" answered after the deadline, so only "shared" is served.
    assert receipt.status is GraphReceiptStatus.PARTIAL
    assert receipt.supporting_record_ids == (shared,)
    assert {"class": "runtime_budget_exhausted", "stage": "provider"} in receipt.failures


def test_search_within_budget_is_complete() -> None:
    clock = Clock()
    graph, principal, write = _service(FakeGraphPort(), clock)
    shared = write("tenant-a", "falcon shared")
    graph.projection = Projection(clock, {"shared": [ProjectionHit(record_id=shared, score=0.9)]})
    receipt = graph.execute(principal("tenant-a"), _search())
    assert receipt.status is GraphReceiptStatus.COMPLETE
    assert receipt.supporting_record_ids == (shared,)


def test_a_stalled_provider_search_is_abandoned_at_the_deadline() -> None:
    """Codex review: the in-flight projection call must not outlive the budget."""

    import threading
    import time

    release = threading.Event()

    class StalledProjection(Projection):
        def search_strategy(self, strategy, query, namespaces, *, limit, tenant_id):
            release.wait(5)
            return []

    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store,
        FakeGraphPort(),
        namespace_policy=service.namespace_policy,
        projection=StalledProjection(Clock(), {}),
    )
    started = time.monotonic()
    try:
        receipt = graph.execute(
            principal("tenant-a"), _search(limits=GraphLimits(max_runtime_ms=100))
        )
    finally:
        release.set()
    assert time.monotonic() - started < 1.0
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == "runtime_budget_exhausted"


# -- audit F-03: the budget bounds the caller's wall-clock time -------------

_BUDGET = GraphLimits(max_runtime_ms=150)
_CEILING_S = 0.6  # budget plus scheduling slack; every stall below is 5 s


def _timed(graph, principal, request):
    import time

    started = time.monotonic()
    receipt = graph.execute(principal, request)
    return receipt, time.monotonic() - started


def _assert_bounded(receipt, elapsed) -> None:
    assert elapsed < _CEILING_S, f"request took {elapsed:.2f}s against a 150 ms budget"
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == "runtime_budget_exceeded"
    assert receipt.results == ()


def test_slow_backend_health_is_bounded_by_the_request_budget() -> None:
    import threading

    release = threading.Event()

    class SlowHealthPort(FakeGraphPort):
        def health(self):
            release.wait(5)
            return super().health()

    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store,
        SlowHealthPort(
            {GraphOperation.NEIGHBORHOOD: GraphProviderResult(operation="graph.neighborhood")}
        ),
        namespace_policy=service.namespace_policy,
    )
    try:
        receipt, elapsed = _timed(graph, principal("tenant-a"), _request(limits=_BUDGET))
    finally:
        release.set()
    _assert_bounded(receipt, elapsed)


def test_slow_canonical_evidence_rehydration_is_bounded() -> None:
    import threading

    from l9_graphite_memory.graph.contracts import GraphProviderNode

    release = threading.Event()
    service, store, principal, write = seeded_memory()
    record = write("tenant-a", "falcon")
    real_get = store.get_record

    def slow_get(record_id):
        release.wait(5)
        return real_get(record_id)

    def result(request):
        return GraphProviderResult(
            operation=request.operation,
            nodes=(
                GraphProviderNode(
                    entity_uuid=uuid4(),
                    group_id=request.group_ids[0],
                    name="falcon",
                    supporting_episode_ids=(record,),
                ),
            ),
        )

    graph = GraphIntelligenceService(
        store,
        FakeGraphPort({GraphOperation.NEIGHBORHOOD: result}),
        namespace_policy=service.namespace_policy,
    )
    store.get_record = slow_get  # evidence rehydration reads canonical records
    try:
        receipt, elapsed = _timed(graph, principal("tenant-a"), _request(limits=_BUDGET))
    finally:
        release.set()
    _assert_bounded(receipt, elapsed)


def test_slow_gds_catalog_cleanup_is_bounded_and_still_runs() -> None:
    import threading

    from tests.unit.test_neo4j_gds_operations import _analytics_responses

    release, dropped = threading.Event(), threading.Event()
    responses = _analytics_responses([{"uuid": str(uuid4()), "score": 1.0}])

    def slow_drop(_parameters):
        release.wait(5)
        dropped.set()
        return [{"graphName": "x"}]

    responses["gds_drop_v1"] = slow_drop
    driver = FakeNeo4jDriver(responses={**responses, **_health_rows()})
    adapter = Neo4jGraphIntelligence(
        Neo4jGraphIntelligenceConfig(uri="bolt://graph.invalid:7687"), driver_factory=lambda: driver
    )
    driver.bind(adapter)
    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(store, adapter, namespace_policy=service.namespace_policy)
    try:
        receipt, elapsed = _timed(
            graph,
            principal("tenant-a"),
            _request(operation=GraphOperation.CENTRALITY, anchor=None, limits=_BUDGET),
        )
    finally:
        release.set()
    _assert_bounded(receipt, elapsed)
    # Cleanup is not abandoned: it completes after the caller was answered.
    assert dropped.wait(5)


def _health_rows():
    from tests.graph_fakes import healthy_graphiti_responses

    return healthy_graphiti_responses(group_ids=(GROUP,))


def test_stalled_projection_transport_is_bounded_on_every_search_strategy() -> None:
    import threading

    release = threading.Event()

    class StalledProjection(Projection):
        def search_strategy(self, strategy, query, namespaces, *, limit, tenant_id):
            release.wait(5)
            return []

    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store,
        FakeGraphPort(),
        namespace_policy=service.namespace_policy,
        projection=StalledProjection(Clock(), {}),
    )
    try:
        for operation in (GraphOperation.SEARCH, GraphOperation.SEMANTIC_SEARCH):
            receipt, elapsed = _timed(
                graph, principal("tenant-a"), _search(operation=operation, limits=_BUDGET)
            )
            assert elapsed < _CEILING_S
            assert receipt.status is GraphReceiptStatus.FAILED
    finally:
        release.set()


def test_graph_requests_beyond_pool_capacity_are_refused_immediately(monkeypatch) -> None:
    """Codex review on #73: admission is bounded instead of queueing without limit."""

    import threading

    from l9_graphite_memory.graph import service as service_module

    monkeypatch.setattr(
        service_module, "_REQUEST_POOL", service_module._BoundedPool(1, 0, "test-graph")
    )
    release = threading.Event()

    class HungPort(FakeGraphPort):
        def health(self):
            release.wait(5)
            return super().health()

    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store,
        HungPort(
            {GraphOperation.NEIGHBORHOOD: GraphProviderResult(operation="graph.neighborhood")}
        ),
        namespace_policy=service.namespace_policy,
    )
    try:
        first, _ = _timed(graph, principal("tenant-a"), _request(limits=_BUDGET))
        second, elapsed = _timed(graph, principal("tenant-a"), _request(limits=_BUDGET))
    finally:
        release.set()
    assert first.failures[0]["class"] == "runtime_budget_exceeded"
    assert second.failures == ({"class": "graph_capacity_exhausted", "stage": "admission"},)
    assert elapsed < 0.1  # refused at admission, not after waiting out the budget


def test_search_beyond_pool_capacity_is_refused(monkeypatch) -> None:
    from l9_graphite_memory.graph import service as service_module

    class FullPool:
        def try_submit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(service_module, "_SEARCH_POOL", FullPool())
    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store,
        FakeGraphPort(),
        namespace_policy=service.namespace_policy,
        projection=Projection(Clock(), {}),
    )
    receipt = graph.execute(principal("tenant-a"), _search())
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == "graph_capacity_exhausted"


def test_bounded_pool_releases_slots_when_work_finishes() -> None:
    from l9_graphite_memory.graph.service import _BoundedPool

    pool = _BoundedPool(1, 0, "test-slots")
    first = pool.try_submit(lambda: 1)
    assert first is not None and first.result(1) == 1
    second = pool.try_submit(lambda: 2)
    assert second is not None and second.result(1) == 2


# -- third audit F-02: authorization precedes admission and deadlines ------


def _unauthorized(principal):
    # Holds READ on "other" only; every request below targets "shared".
    return principal("tenant-a", namespaces=("other",))


def test_unauthorized_caller_is_refused_even_when_the_request_pool_is_full(monkeypatch) -> None:
    from l9_graphite_memory.errors import AuthorizationError
    from l9_graphite_memory.graph import service as service_module

    class FullPool:
        submitted = 0

        def try_submit(self, *args, **kwargs):
            FullPool.submitted += 1

    monkeypatch.setattr(service_module, "_REQUEST_POOL", FullPool())
    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store, FakeGraphPort(), namespace_policy=service.namespace_policy
    )
    with pytest.raises(AuthorizationError):
        graph.execute(_unauthorized(principal), _request(limits=_BUDGET))
    assert FullPool.submitted == 0  # never reached admission; no receipt produced


def test_unauthorized_caller_is_refused_before_queueing_or_deadline(monkeypatch) -> None:
    import threading
    import time

    from l9_graphite_memory.errors import AuthorizationError
    from l9_graphite_memory.graph import service as service_module

    monkeypatch.setattr(
        service_module, "_REQUEST_POOL", service_module._BoundedPool(1, 1, "test-authz")
    )
    release = threading.Event()

    class HungPort(FakeGraphPort):
        def health(self):
            release.wait(5)
            return super().health()

    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store,
        HungPort(
            {GraphOperation.NEIGHBORHOOD: GraphProviderResult(operation="graph.neighborhood")}
        ),
        namespace_policy=service.namespace_policy,
    )
    try:
        # Occupy the only worker so the next accepted request would queue and
        # then hit its deadline.
        occupied = graph.execute(principal("tenant-a"), _request(limits=_BUDGET))
        assert occupied.failures[0]["class"] == "runtime_budget_exceeded"
        started = time.monotonic()
        with pytest.raises(AuthorizationError):
            graph.execute(_unauthorized(principal), _request(limits=_BUDGET))
        assert time.monotonic() - started < 0.1  # decided before queueing or waiting
    finally:
        release.set()


def test_scope_denial_is_counted_once_when_refused_before_admission(monkeypatch) -> None:
    from l9_graphite_memory.errors import AuthorizationError
    from l9_graphite_memory.observability.graph_metrics import GraphMetrics

    metrics = GraphMetrics()
    service, store, principal, _ = seeded_memory()
    graph = GraphIntelligenceService(
        store, FakeGraphPort(), namespace_policy=service.namespace_policy, metrics=metrics
    )
    with pytest.raises(AuthorizationError):
        graph.execute(_unauthorized(principal), _request())
    assert metrics.value("memory_graph_scope_denied_total") == 1
