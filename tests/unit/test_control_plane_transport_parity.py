# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_control_plane_transport_parity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-09-05

"""ADR-082: every lifecycle operation converges on MemoryService via CLI, MCP, and SDK.

The consumer of these guarantees is Cursor-Governance, which must never
reach a provider directly. The cases here are the ones its runtime binding
and control-plane client depend on: a CLI ``close`` whose exit code is a
canonical verdict, an idempotent close that yields exactly one logical close,
a capability receipt that names the contract instead of leaving the consumer
to infer it from tool presence, and a governed continuation candidate that
round-trips losslessly through the canonical store.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from l9_graphite_memory import cli
from l9_graphite_memory.contracts import (
    LIFECYCLE_OPERATIONS,
    CloseRequest,
    ControlPlaneCapabilities,
    MemorySearchRequest,
    OperationStatus,
    PhaseLockRequest,
)
from l9_graphite_memory.contracts.generated_data import (
    GovernedMemoryCandidate,
    MemoryCandidateIngestionStatus,
)
from l9_graphite_memory.mcp_tools import MCPToolApplication, tool_definitions
from l9_graphite_memory.sdk import MemorySDK
from l9_graphite_memory.services import GeneratedDataService
from l9_graphite_memory.version import CONTROL_PLANE_CONTRACT_VERSION

HEAD_SHA = "b" * 40


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolated sqlite runtime for CLI invocations; namespace is explicit."""

    monkeypatch.setenv("L9_MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("L9_MEMORY_NAMESPACE", "repo-a")
    monkeypatch.setenv("L9_MEMORY_JSON_LOGS", "0")
    for name in (
        "L9_MEMORY_CONFIG",
        "GRAPHITI_GROUP_ID",
        "CURSOR_CONVERSATION_ID",
        "L9_SESSION_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, dict[str, Any]]:
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, json.loads(out)


def continuation_candidate(*, namespace: str = "repo-a") -> dict[str, Any]:
    capsule = {
        "schema": "cursor.continuation/v2",
        "session_id": "session-42",
        "repository_identity": "Quantum-L9/Cursor-Governance",
        "task_signature": "abc123",
        "objective": "Realign memory control plane",
        "next_action": "Wire runtime binding",
        "active_files": ["ops/memory/runtime_binding.py"],
        "blockers": [],
        "decisions": ["CLI is the hook transport"],
        "unfinished_work": ["egress scanner"],
        "repository_state_digest": HEAD_SHA,
        "producer": "Cursor-Governance",
        "producer_version": "2.0.0",
        "created_at": "2026-09-05T00:00:00+00:00",
    }
    return {
        "schema_version": "1.1.0",
        "kind": "MemoryCandidate",
        "candidate_id": "cursor-continuation:session-42:deadbeef",
        "source": {
            "repository": "Quantum-L9/Cursor-Governance",
            "sha": HEAD_SHA,
            "visibility": "namespace_local",
            "namespace": namespace,
        },
        "knowledge": {
            "primary_class": "session_continuation",
            "statement": "Realign memory control plane | next: Wire runtime binding",
            "confidence": 1.0,
            "invalidation_conditions": [
                {"condition_type": "repository_state_changed", "selector": HEAD_SHA}
            ],
            "payload_schema": "cursor.continuation/v2",
            "structured_payload": capsule,
        },
        "governance": {
            "authority_class": "advisory",
            "route": "memory",
            "promotion_decision": "promote",
            "may_override_repository_state": False,
            "may_override_canonical_authority": False,
        },
        "provenance": {"producer": "Cursor-Governance", "source_agent_id": "cursor"},
    }


# ---------------------------------------------------------------------------
# CLI close
# ---------------------------------------------------------------------------


def test_cli_close_commits_and_exits_zero(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, receipt = _run(
        capsys,
        ["close", "--summary", "session finished", "--session-id", "s-1", "--capsule-digest", "d1"],
    )
    assert code == 0
    assert receipt["status"] == "complete"
    assert receipt["namespace"] == "repo-a"
    assert receipt["record_id"] is not None
    assert receipt["replayed"] is False
    assert receipt["graphiti_accepted"] is False


def test_cli_close_dry_run_is_not_reported_committed(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, receipt = _run(capsys, ["close", "--summary", "dry", "--dry-run"])
    assert code == 3
    assert receipt["status"] == "partial"
    assert receipt["record_id"] is None


def test_cli_close_rejected_namespace_exits_nonzero(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # ``main`` is a forbidden namespace: resolution yields no write grant, the
    # write is rejected, and the close must not claim success.
    code, receipt = _run(capsys, ["close", "--summary", "nope", "--group-id", "main"])
    assert code == 2
    assert receipt["status"] == "failed"
    assert receipt["record_id"] is None


def test_cli_close_replay_yields_exactly_one_logical_close(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["close", "--summary", "same close", "--idempotency-key", "close:s-2"]
    first_code, first = _run(capsys, argv)
    second_code, second = _run(capsys, argv)
    assert (first_code, second_code) == (0, 0)
    assert first["replayed"] is False
    assert second["replayed"] is True
    assert second["record_id"] == first["record_id"]

    # The store holds one close record, not two.
    search_code, hits = _run(capsys, ["search", "same close", "--memory-class", "meta"])
    assert search_code == 0
    assert len(hits["hits"]) == 1


def test_cli_close_without_key_creates_distinct_closes(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, first = _run(capsys, ["close", "--summary", "distinct"])
    _, second = _run(capsys, ["close", "--summary", "distinct"])
    assert first["record_id"] != second["record_id"]
    assert second["replayed"] is False


# ---------------------------------------------------------------------------
# Capability receipt
# ---------------------------------------------------------------------------


def test_cli_capabilities_names_contract_and_every_operation(
    cli_env: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _run(capsys, ["capabilities"])
    assert code == 0
    receipt = ControlPlaneCapabilities.model_validate(payload)
    assert receipt.contract_version == CONTROL_PLANE_CONTRACT_VERSION
    assert receipt.missing_operations() == {}
    by_transport = {surface.transport: surface.operations for surface in receipt.transports}
    assert by_transport["cli"]["close"] == "close"
    assert by_transport["cli"]["resolve"] == "resolve"
    assert by_transport["mcp"]["close"] == "memory.close"
    assert "session_continuation" in receipt.generated_data_classes
    assert "namespace_local" in receipt.candidate_visibilities
    assert receipt.exit_codes["committed"] == 0
    assert receipt.exit_codes["dry_run_not_committed"] == 3


def test_capabilities_receipt_cannot_claim_absent_surfaces() -> None:
    from l9_graphite_memory.contracts import build_capabilities

    receipt = build_capabilities(cli_commands=["health"], mcp_tools=["memory.health"])
    missing = receipt.missing_operations()
    assert "close" in missing["cli"]
    assert "close" in missing["mcp"]


def test_health_report_carries_contract_version(memory_service) -> None:
    assert memory_service.health().contract_version == CONTROL_PLANE_CONTRACT_VERSION


# ---------------------------------------------------------------------------
# MCP parity
# ---------------------------------------------------------------------------


def test_mcp_exposes_capabilities_and_idempotent_close(memory_service, principal) -> None:
    names = {item["name"] for item in tool_definitions()}
    assert "memory.capabilities" in names
    app = MCPToolApplication(memory_service)
    capabilities = app.call(principal, "memory.capabilities", {})
    assert capabilities.contract_version == CONTROL_PLANE_CONTRACT_VERSION
    assert capabilities.missing_operations() == {}

    args = {"namespace": "repo-a", "summary": "mcp close", "idempotency_key": "close:mcp-1"}
    first = app.call(principal, "memory.close", args)
    second = app.call(principal, "memory.close", args)
    assert first.status is OperationStatus.COMPLETE and first.replayed is False
    assert second.status is OperationStatus.COMPLETE and second.replayed is True
    assert second.record_id == first.record_id


def test_every_lifecycle_operation_has_a_cli_command_and_mcp_tool() -> None:
    from l9_graphite_memory.contracts import CLI_OPERATION_COMMANDS, MCP_OPERATION_TOOLS

    commands = set(cli.cli_command_names())
    tools = {item["name"] for item in tool_definitions()}
    for operation in LIFECYCLE_OPERATIONS:
        assert CLI_OPERATION_COMMANDS[operation] in commands, operation
        assert MCP_OPERATION_TOOLS[operation] in tools, operation


# ---------------------------------------------------------------------------
# SDK parity
# ---------------------------------------------------------------------------


def test_sdk_exposes_close_conflicts_verify_and_health(memory_service, principal) -> None:
    sdk = MemorySDK(memory_service, principal)
    assert sdk.health().status is OperationStatus.COMPLETE
    assert sdk.conflicts("repo-a").has_conflicts is False
    lock = sdk.phase_lock(PhaseLockRequest(namespace="repo-a", task_signature="sdk-parity-lock"))
    assert lock.granted is True
    assert sdk.verify_phase_lock("repo-a", "sdk-parity-lock").valid is True
    close = sdk.close(CloseRequest(namespace="repo-a", summary="sdk close"))
    assert close.status is OperationStatus.COMPLETE
    result = sdk.ingest_governed_candidate(continuation_candidate())
    assert result.status is MemoryCandidateIngestionStatus.ADMITTED


# ---------------------------------------------------------------------------
# Continuation candidate contract
# ---------------------------------------------------------------------------


def test_continuation_candidate_round_trips_losslessly(memory_service, principal) -> None:
    payload = continuation_candidate()
    result = GeneratedDataService(memory_service).ingest_governed_candidate(principal, payload)
    assert result.status is MemoryCandidateIngestionStatus.ADMITTED
    assert result.namespace == "repo-a"
    record = memory_service.get(principal, result.record_id)
    assert record is not None
    assert record.metadata["payload_schema"] == "cursor.continuation/v2"
    assert record.metadata["structured_payload"] == payload["knowledge"]["structured_payload"]
    assert record.metadata["producer"] == "Cursor-Governance"
    assert "session_continuation" in record.tags

    # The capsule is retrievable through the same canonical search hydration uses.
    receipt = memory_service.search(
        principal, MemorySearchRequest(query="Realign memory control plane", namespaces=("repo-a",))
    )
    assert any(hit.record.record_id == result.record_id for hit in receipt.hits)


def test_continuation_candidate_replay_is_duplicate_not_second_record(
    memory_service, principal
) -> None:
    service = GeneratedDataService(memory_service)
    first = service.ingest_governed_candidate(principal, continuation_candidate())
    second = service.ingest_governed_candidate(principal, continuation_candidate())
    assert second.status is MemoryCandidateIngestionStatus.DUPLICATE
    assert second.record_id == first.record_id


def test_namespace_local_is_a_request_not_a_grant(memory_service, principal) -> None:
    result = GeneratedDataService(memory_service).ingest_governed_candidate(
        principal, continuation_candidate(namespace="repo-b")
    )
    assert result.status is MemoryCandidateIngestionStatus.REJECTED
    assert result.record_id is None


def test_structured_payload_requires_its_schema() -> None:
    payload = continuation_candidate()
    del payload["knowledge"]["payload_schema"]
    with pytest.raises(ValidationError, match="payload_schema"):
        GovernedMemoryCandidate.model_validate(payload)


def test_namespace_local_requires_namespace() -> None:
    payload = continuation_candidate()
    del payload["source"]["namespace"]
    with pytest.raises(ValueError, match="namespace"):
        GovernedMemoryCandidate.model_validate(payload).namespace()
