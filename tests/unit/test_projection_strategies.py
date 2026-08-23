# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_projection_strategies.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from uuid import uuid4

from l9_graphite_memory.adapters import GraphitiProjection, InMemoryRecordStore
from l9_graphite_memory.contracts import (
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.services import MemoryService


class StrategyTransport:
    name = "strategy-transport"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.record_id = uuid4()

    def health(self):
        return {"healthy": True}

    def list_tools(self):
        return ["search_facts", "search_nodes", "add_episode", "delete_episode"]

    def call_tool(self, name, arguments=None):
        self.calls.append(name)
        if name == "search_facts":
            return {"facts": [{"record_id": str(self.record_id), "fact": "semantic", "score": 0.8}]}
        if name == "search_nodes":
            return {"nodes": [{"record_id": str(self.record_id), "content": "graph", "score": 0.9}]}
        if name == "delete_episode":
            return {"message": "deleted", "uuid": arguments["uuid"]}
        return {}

    def search(self, query, group_id, limit=10):
        raise AssertionError("combined transport search must not replace strategy-specific calls")

    def write(self, body, group_id, kind="observation", **kwargs):
        return {"projected": True, "uuid": kwargs.get("uuid")}


def test_graphiti_projection_executes_graph_and_semantic_strategies_independently() -> None:
    transport = StrategyTransport()
    projection = GraphitiProjection(transport)

    graph_hits = projection.search_strategy("graph-search", "memory", ("repo-a",), limit=10)
    semantic_hits = projection.search_strategy("semantic-search", "memory", ("repo-a",), limit=10)

    assert transport.calls == ["search_nodes", "search_facts"]
    assert graph_hits[0].metadata["strategy"] == "graph-search"
    assert semantic_hits[0].metadata["strategy"] == "semantic-search"


def test_retrieval_receipt_reports_only_executed_projection_strategies() -> None:
    transport = StrategyTransport()
    projection = GraphitiProjection(transport)
    store = InMemoryRecordStore()
    principal = MemoryPrincipal(
        principal_id="p",
        tenant_id="t",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
    )
    service = MemoryService(store, projection)
    service.initialize()
    write = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            content="identity preference context",
            provenance=Provenance(source="test"),
        ),
    )
    transport.record_id = write.record_id

    receipt = service.search(
        principal,
        MemorySearchRequest(query="identity preference context", namespaces=("repo-a",)),
    )

    assert "graph-search" in receipt.strategies_succeeded
    assert "semantic-search" in receipt.strategies_succeeded
    assert "graphiti:graph-search" in receipt.stores_succeeded
    assert "graphiti:semantic-search" in receipt.stores_succeeded


def test_graphiti_projection_erases_using_persisted_locator() -> None:
    transport = StrategyTransport()
    projection = GraphitiProjection(transport)
    result = projection.erase(transport.record_id, "repo-a", locator=str(transport.record_id))
    assert result["erased"] is True
    assert result["locator"] == str(transport.record_id)
    assert transport.calls == ["delete_episode"]


class OfficialStrategyTransport(StrategyTransport):
    name = "official-graphiti"

    def __init__(self) -> None:
        super().__init__()
        self.arguments: list[dict] = []

    def list_tools(self):
        return ["add_memory", "search_memory_facts", "search_nodes", "delete_episode"]

    def call_tool(self, name, arguments=None):
        self.calls.append(name)
        self.arguments.append(arguments or {})
        if name == "search_memory_facts":
            return {"facts": [{"record_id": str(self.record_id), "fact": "semantic", "score": 0.8}]}
        if name == "search_nodes":
            return {"nodes": [{"record_id": str(self.record_id), "content": "graph", "score": 0.9}]}
        if name == "delete_episode":
            return {"message": "deleted"}
        return {"message": "queued"}


def test_official_graphiti_dialect_uses_current_tool_names_and_group_ids() -> None:
    transport = OfficialStrategyTransport()
    projection = GraphitiProjection(transport)
    projection.search_strategy("semantic-search", "memory", ("repo-a",), limit=10)
    projection.search_strategy("graph-search", "memory", ("repo-a",), limit=10)
    assert transport.calls == ["search_memory_facts", "search_nodes"]
    assert transport.arguments[0]["group_ids"] == ["repo-a"]
    assert transport.arguments[1]["group_ids"] == ["repo-a"]
