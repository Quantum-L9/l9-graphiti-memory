# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_public_surfaces.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Graph intelligence public surfaces: MCP, SDK, capabilities, health, metrics (ADR-089)."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphOperation,
    GraphProviderNode,
    GraphProviderResult,
    GraphReceiptStatus,
)
from l9_graphite_memory.graph.ports import GraphCapability
from l9_graphite_memory.graph.service import GraphIntelligenceService
from l9_graphite_memory.mcp_tools import (
    GRAPH_OPERATION_TOOLS,
    MCPToolApplication,
    mcp_capabilities,
    tool_definitions,
)
from l9_graphite_memory.observability.graph_metrics import GraphMetrics
from l9_graphite_memory.runtime import MemoryRuntime
from l9_graphite_memory.sdk import MemorySDK
from tests.graph_fakes import FakeGraphPort, seeded_memory

SECRET_CONTENT = "falcon launch codes 7731"


def _graph_world(*, health_overrides=None, metrics=None, required=False):
    service, store, principal, write = seeded_memory()
    record = write("tenant-a", SECRET_CONTENT)

    def neighborhood(request):
        return GraphProviderResult(
            operation=request.operation,
            nodes=(
                GraphProviderNode(
                    entity_uuid=uuid4(),
                    group_id=request.group_ids[0],
                    name="Falcon",
                    supporting_episode_ids=(record,),
                ),
            ),
        )

    port = FakeGraphPort(
        {
            GraphOperation.NEIGHBORHOOD: neighborhood,
            GraphOperation.CENTRALITY: RuntimeError("bolt://db.internal refused"),
        },
        capabilities=(GraphCapability.NEIGHBORHOOD, GraphCapability.CENTRALITY),
        health_overrides=health_overrides,
    )
    from l9_graphite_memory.graph.service import GraphServiceConfig

    graph = GraphIntelligenceService(
        store,
        port,
        namespace_policy=service.namespace_policy,
        projection=service.projection,
        metrics=metrics or GraphMetrics(),
        config=GraphServiceConfig(required=required),
    )
    return service, graph, principal, record


def test_every_graph_operation_has_a_memory_owned_mcp_tool() -> None:
    tools = {item["name"]: item for item in tool_definitions()}
    for operation in GraphOperation:
        assert f"memory.{operation.value}" in tools
    assert "memory.graph.capabilities" in tools


def test_graph_tool_schemas_carry_no_scope_authority_or_query_text() -> None:
    for name in GRAPH_OPERATION_TOOLS:
        schema = next(item for item in tool_definitions() if item["name"] == name)["inputSchema"]
        properties = set(schema["properties"])
        assert schema["additionalProperties"] is False
        assert not properties & {"tenant_id", "group_id", "group_ids", "cypher", "query_text"}
        assert schema["required"] == ["namespaces"]


def test_mcp_graph_operation_returns_a_typed_receipt() -> None:
    service, graph, principal, record = _graph_world()
    app = MCPToolApplication(service, graph)
    receipt = app.call(
        principal("tenant-a"),
        "memory.graph.neighborhood",
        {"namespaces": ["shared"], "anchor": {"entity_uuid": str(uuid4())}},
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE
    assert receipt.supporting_record_ids == (record,)


@pytest.mark.parametrize(
    "smuggled", [{"tenant_id": "tenant-b"}, {"cypher": "MATCH (n) DETACH DELETE n"}]
)
def test_mcp_graph_operation_rejects_smuggled_scope_or_cypher(smuggled) -> None:
    service, graph, principal, _record = _graph_world()
    app = MCPToolApplication(service, graph)
    with pytest.raises(ValueError, match="invalid memory.graph.neighborhood"):
        app.call(
            principal("tenant-a"),
            "memory.graph.neighborhood",
            {"namespaces": ["shared"], "anchor": {"entity_uuid": str(uuid4())}, **smuggled},
        )


def test_mcp_capability_report_separates_dimensions() -> None:
    service, graph, principal, _ = _graph_world()
    report = MCPToolApplication(service, graph).call(
        principal("tenant-a"), "memory.graph.capabilities", {}
    )
    assert report.scope_scheme == "l9g-v1" and report.scope_scheme_version == 1
    assert set(report.capabilities) == {"graph.neighborhood", "graph.centrality"}
    assert report.backend["backend_version"] == "5.26.31"
    assert report.algorithm_maturity_ceiling == "production"
    assert report.link_prediction_enabled is False
    assert report.ready is True


def test_capability_receipt_reports_graph_tools_without_breaking_cli_parity() -> None:
    receipt = mcp_capabilities()
    mcp = next(surface for surface in receipt.transports if surface.transport == "mcp")
    assert mcp.operations["graph.path"] == "memory.graph.path"
    assert mcp.operations["graph.capabilities"] == "memory.graph.capabilities"
    assert receipt.missing_operations() == {}


def test_sdk_default_graph_backend_is_explicitly_unavailable(memory_service, principal) -> None:
    sdk = MemorySDK(memory_service, principal)
    receipt = sdk.graph(
        GraphIntelligenceRequest(
            operation=GraphOperation.TRAVERSE,
            namespaces=("repo-a",),
            anchor=GraphAnchor(entity_uuid=uuid4()),
        )
    )
    assert receipt.status is GraphReceiptStatus.FAILED
    assert receipt.failures[0]["class"] == "capability_unavailable"
    assert sdk.graph_capabilities().capabilities == ()


def test_sdk_uses_an_injected_graph_service() -> None:
    service, graph, principal, record = _graph_world()
    sdk = MemorySDK(service, principal("tenant-a"), graph=graph)
    receipt = sdk.graph(
        GraphIntelligenceRequest(
            operation=GraphOperation.NEIGHBORHOOD,
            namespaces=("shared",),
            anchor=GraphAnchor(entity_uuid=uuid4()),
        )
    )
    assert receipt.supporting_record_ids == (record,)


def test_metrics_count_operations_failures_and_denials_without_content(caplog) -> None:
    metrics = GraphMetrics()
    _service, graph, principal, _ = _graph_world(metrics=metrics)
    request = GraphIntelligenceRequest(
        operation=GraphOperation.NEIGHBORHOOD,
        namespaces=("shared",),
        anchor=GraphAnchor(entity_uuid=uuid4()),
    )
    with caplog.at_level(logging.INFO, logger="l9_graphite_memory.graph"):
        graph.execute(principal("tenant-a"), request)
        graph.execute(
            principal("tenant-a"),
            request.model_copy(update={"operation": GraphOperation.CENTRALITY, "anchor": None}),
        )
        with pytest.raises(AuthorizationError):
            graph.execute(
                principal("tenant-a", namespaces=("other",)),
                request.model_copy(update={"namespaces": ("shared",)}),
            )
    assert (
        metrics.value("memory_graph_query_total", operation="graph.neighborhood", status="COMPLETE")
        == 1
    )
    assert (
        metrics.value("memory_graph_query_total", operation="graph.centrality", status="FAILED")
        == 1
    )
    assert (
        metrics.value(
            "memory_graph_provider_failure_total",
            provider="fake-graph",
            operation="graph.centrality",
        )
        == 1
    )
    assert metrics.value("memory_graph_scope_denied_total") == 1
    assert (
        metrics.summary("memory_graph_query_latency_ms", operation="graph.neighborhood")["count"]
        == 1
    )
    logged = " ".join(record.getMessage() + str(record.__dict__) for record in caplog.records)
    assert "graph_intelligence_operation" in logged
    assert SECRET_CONTENT not in logged
    assert "db.internal" not in logged
    assert "tenant-a" not in logged


@pytest.mark.parametrize(
    ("required", "healthy", "expected"),
    [(True, False, 503), (False, False, 200), (True, True, 200)],
)
def test_readiness_gates_on_graph_only_when_required(required, healthy, expected) -> None:
    from fastapi.testclient import TestClient

    from l9_graphite_memory.server import create_http_app

    service, graph, _principal, _ = _graph_world(
        health_overrides={"healthy": healthy}, required=required
    )
    runtime = MemoryRuntime(settings=MemorySettings(), service=service, graph_service=graph)
    client = TestClient(create_http_app(runtime))
    response = client.get("/readyz")
    assert response.status_code == expected
    assert response.json()["graph"]["ready"] is (healthy or not required)
