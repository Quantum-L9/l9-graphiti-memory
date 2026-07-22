# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_mcp_harvest_tools.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from l9_graphite_memory.contracts import MemoryWriteRequest, Provenance
from l9_graphite_memory.mcp_tools import MCPToolApplication, tool_definitions


def test_mcp_inventory_contains_recursive_harvest_tools() -> None:
    names = {item["name"] for item in tool_definitions()}
    assert {
        "memory.verify_phase_lock",
        "memory.lineage",
        "memory.retention",
        "memory.distill",
        "memory.synthesize_procedures",
    } <= names


def test_mcp_lineage_and_retention_delegate_to_canonical_service(
    memory_service, principal
) -> None:
    receipt = memory_service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            content="lineage root",
            provenance=Provenance(source="test"),
        ),
    )
    app = MCPToolApplication(memory_service)

    lineage = app.call(
        principal,
        "memory.lineage",
        {"namespace": "repo-a", "record_id": str(receipt.record_id)},
    )
    retention = app.call(
        principal,
        "memory.retention",
        {"namespace": "repo-a", "apply": False},
    )

    assert lineage.root_record_id == receipt.record_id
    assert retention.namespace == "repo-a"
