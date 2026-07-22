# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_http_transport_dialect.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.transport import HttpMcpTransport


class FakeHttpTransport(HttpMcpTransport):
    def __init__(self) -> None:
        super().__init__(url="https://graphiti.example")
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[str]:
        return ["add_memory", "search_memory_facts", "search_nodes", "delete_episode"]

    def call_tool(self, name: str, arguments: dict | None = None):
        self.calls.append((name, arguments or {}))
        if name == "add_memory":
            return {"message": "queued"}
        if name == "search_memory_facts":
            return {"facts": []}
        if name == "search_nodes":
            return {"nodes": []}
        return {"message": "deleted"}


def test_http_transport_prefers_official_add_memory_tool() -> None:
    transport = FakeHttpTransport()
    transport.write("{}", "repo-a", uuid="00000000-0000-0000-0000-000000000001")
    assert transport.calls[0][0] == "add_memory"
    assert transport.calls[0][1]["group_id"] == "repo-a"


def test_http_transport_uses_official_group_ids_search_shape() -> None:
    transport = FakeHttpTransport()
    assert transport.search("memory", "repo-a") == []
    assert transport.calls[0][0] == "search_memory_facts"
    assert transport.calls[0][1]["group_ids"] == ["repo-a"]
