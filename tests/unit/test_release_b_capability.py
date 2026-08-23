# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_release_b_capability.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-16

from __future__ import annotations

import pytest

from l9_graphite_memory.contracts.enums import OperationStatus
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.mcp_tools import ALIASES, MCPToolApplication, tool_definitions
from l9_graphite_memory.trust_boundary import model_process_trust_boundary


def test_five_canonical_operations_are_registered() -> None:
    names = {item["name"] for item in tool_definitions()}
    assert {
        "memory.search",
        "memory.hydrate",
        "memory.write_governed",
        "memory.close",
        "memory.health",
        "graphiti.query",
        "graphiti.write_governed",
    } <= names
    assert ALIASES["graphiti.query"] == "memory.search"
    assert ALIASES["graphiti.write_governed"] == "memory.write_governed"


def test_model_process_has_no_graphiti_secret_side_doors(monkeypatch) -> None:
    monkeypatch.delenv("GRAPHITI_MCP_TOKEN", raising=False)
    proof = model_process_trust_boundary()
    assert proof["model_has_graphiti_bearer"] is False
    assert proof["model_can_read_keychain_graphiti_token"] is False


def test_live_graphiti_bearer_in_the_environment_is_reported(monkeypatch) -> None:
    """A bearer in the effective process environment is held, whatever sources say.

    The static scan covers only the model-facing modules, so a token injected by
    launch configuration would otherwise leave the proof reporting False while
    the credential is present.
    """
    monkeypatch.setenv("GRAPHITI_MCP_TOKEN", "live-token-value")
    assert model_process_trust_boundary()["model_has_graphiti_bearer"] is True


def test_five_operations_terminate_at_memory_service(memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    health = app.call(principal, "memory.health", {})
    assert health.status.value in {"complete", "partial"}

    lock = app.call(
        principal,
        "memory.phase_lock",
        {"namespace": "repo-a", "task_signature": "release-b-lock"},
    )
    assert lock.granted is True

    write = app.call(
        principal,
        "memory.write_governed",
        {
            "namespace": "repo-a",
            "content": "Release B governed write",
            "task_signature": "release-b-lock",
        },
    )
    assert write.record_id is not None

    alias_hits = app.call(
        principal,
        "graphiti.query",
        {"query": "Release B", "namespaces": ["repo-a"]},
    )
    assert len(alias_hits.hits) == 1

    hydrate = app.call(
        principal,
        "memory.hydrate",
        {"task": "release B", "namespaces": ["repo-a"]},
    )
    assert hydrate.search_receipt_id is not None

    close = app.call(
        principal,
        "memory.close",
        {"namespace": "repo-a", "summary": "close after Release B write"},
    )
    assert close.graphiti_accepted is False
    assert close.record_id is not None


def test_dry_run_close_is_not_reported_as_complete(memory_service, principal) -> None:
    """A dry run skips commit_write, so it must not claim a durable close.

    Reporting COMPLETE with a record id would let a close consumer proceed as
    though session state were canonically persisted when no record exists.
    """
    app = MCPToolApplication(memory_service)
    close = app.call(
        principal,
        "memory.close",
        {
            "namespace": "repo-a",
            "summary": "dry-run close must not claim durability",
            "dry_run": True,
        },
    )
    assert close.status is OperationStatus.PARTIAL
    assert close.record_id is None


def test_write_governed_refuses_without_phase_lock(memory_service, principal) -> None:
    app = MCPToolApplication(memory_service)
    with pytest.raises(AuthorizationError, match="phase-lock"):
        app.call(
            principal,
            "graphiti.write_governed",
            {
                "namespace": "repo-a",
                "content": "must not admit",
                "task_signature": "missing-lock",
            },
        )
