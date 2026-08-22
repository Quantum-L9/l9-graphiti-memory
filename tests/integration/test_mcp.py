# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_mcp.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from l9_graphite_memory.mcp_tools import MCPToolApplication, tool_definitions


def test_tool_inventory_contains_canonical_and_compatibility_names() -> None:
    names = {item["name"] for item in tool_definitions()}
    assert {
        "memory.ingest",
        "memory.search",
        "memory.write_governed",
        "memory.close",
        "write",
        "search",
        "graphiti.query",
        "phase_lock",
    } <= names


def test_compatibility_write_alias_uses_canonical_service(
    memory_service, principal
) -> None:
    app = MCPToolApplication(memory_service)
    receipt = app.call(
        principal,
        "write",
        {"namespace": "repo-a", "content": "MCP memory", "memory_class": "observation"},
    )
    assert receipt.record_id is not None
    result = app.call(principal, "search", {"query": "MCP", "namespaces": ["repo-a"]})
    assert len(result.hits) == 1
