# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graphiti_error_transport.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 1.0.0
#   updated: 2026-10-27

"""Graphiti isError, breaker classification, and phantom-link refusal."""

from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

import pytest

from l9_graphite_memory.adapters import GraphitiProjection
from l9_graphite_memory.adapters.graphiti_projection import inventory_phantom_links
from l9_graphite_memory.circuit_breaker import CircuitBreaker, CircuitState
from l9_graphite_memory.contracts import ProjectionLink
from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.transport import HttpMcpTransport, rpc_error_is_availability
from tests.graph_fakes import seeded_memory


def _record():
    _service, store, _principal, write = seeded_memory()
    return store.get_record(write("tenant-a", "falcon migration plan"))


def _transport(breaker: CircuitBreaker | None = None) -> HttpMcpTransport:
    transport = HttpMcpTransport(
        url="http://127.0.0.1:9",
        circuit_breaker=breaker or CircuitBreaker(),
    )
    transport._session_id = "session-1"
    return transport


def test_graphiti_isError_text_and_json() -> None:
    transport = _transport()
    transport._rpc_once = lambda payload, timeout, retry_on_session_error: {  # type: ignore[method-assign]
        "result": {
            "isError": True,
            "content": [{"type": "text", "text": "Error: provider rejected the episode"}],
        }
    }
    with pytest.raises(ProjectionError, match="isError"):
        transport.call_tool("add_memory", {"name": "memory:1"})
    assert transport.circuit.snapshot().failure_count == 0


def test_error_text_does_not_synthesize_a_locator() -> None:
    record = _record()

    class Transport:
        def write(self, body: str, group_id: str, kind: str = "observation", **kwargs: Any) -> str:
            return "Error: provider rejected the episode"

    with pytest.raises(ProjectionError, match="not accepted"):
        GraphitiProjection(Transport()).project(record)


def test_queued_acceptance_keeps_a_pending_name_locator() -> None:
    record = _record()

    class Transport:
        def write(self, body: str, group_id: str, kind: str = "observation", **kwargs: Any) -> dict:
            return {"message": "Episode 'memory:1' queued for processing in group"}

    result = GraphitiProjection(Transport()).project(record)
    assert result["pending_ingest"] is True
    assert result["locator"].startswith("graphiti-episode-name:")


def test_provider_uuid_is_accepted_without_pending_ingest() -> None:
    record = _record()

    class Transport:
        def write(self, body: str, group_id: str, kind: str = "observation", **kwargs: Any) -> dict:
            return {"episode_uuid": "provider-7"}

    result = GraphitiProjection(Transport()).project(record)
    assert result["locator"] == "provider-7"
    assert result["pending_ingest"] is False


def test_graphiti_add_memory_signature_translates_metadata() -> None:
    transport = _transport()
    captured: dict[str, Any] = {}

    def list_tools() -> list[str]:
        return ["add_memory"]

    def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        captured["name"] = name
        captured["arguments"] = arguments
        return {"message": "Episode 'memory:1' queued for processing in group"}

    transport.list_tools = list_tools  # type: ignore[method-assign]
    transport.call_tool = call_tool  # type: ignore[method-assign]
    transport.write("body", "group-1", metadata={"record_id": "abc"}, name="memory:abc")
    assert captured["arguments"].keys() == {
        "name",
        "episode_body",
        "source",
        "source_description",
        "group_id",
    }
    assert "metadata" not in captured["arguments"]
    assert "[metadata translated]" in captured["arguments"]["source_description"]
    with pytest.raises(ProjectionError, match="unsupported arguments"):
        transport.write("body", "group-1", uuid="not-a-create")


def test_breaker_error_class_matrix() -> None:
    assert rpc_error_is_availability({"code": -32602, "message": "invalid params"}) is False
    assert rpc_error_is_availability({"code": -32000, "message": "server error"}) is True
    transport = _transport()

    def invalid(payload: dict, timeout: int | None, retry_on_session_error: bool) -> dict:
        return {"error": {"code": -32602, "message": "invalid params"}}

    transport._rpc_once = invalid  # type: ignore[method-assign]
    for _ in range(5):
        with pytest.raises(ProjectionError):
            transport._rpc("tools/call", {"name": "add_memory"})
    assert transport.circuit.snapshot().failure_count == 0
    assert transport.circuit.snapshot().state is CircuitState.CLOSED

    def unavailable(payload: dict, timeout: int | None, retry_on_session_error: bool) -> dict:
        return {"error": {"code": -32000, "message": "unavailable"}}

    transport._rpc_once = unavailable  # type: ignore[method-assign]
    with pytest.raises(ProjectionError):
        transport._rpc("tools/call", {"name": "add_memory"})
    assert transport.circuit.snapshot().failure_count == 1


def test_breaker_half_open_rearm() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10, clock=lambda: now[0])
    breaker.record_failure()
    now[0] = 10
    assert breaker.can_execute() is True
    assert breaker.snapshot().state is CircuitState.HALF_OPEN
    assert breaker.can_execute() is False
    now[0] = 20
    assert breaker.can_execute() is True
    assert breaker.can_execute() is False


def test_concurrent_single_probe() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10, clock=lambda: now[0])
    breaker.record_failure()
    now[0] = 10
    barrier = threading.Barrier(2)
    results: list[bool] = []

    def probe() -> None:
        barrier.wait()
        results.append(breaker.can_execute())

    threads = [threading.Thread(target=probe) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [False, True]


def test_session_rehandshake_breaker_failure() -> None:
    now = [0.0]
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10, clock=lambda: now[0])
    breaker.record_failure()
    now[0] = 10
    transport = HttpMcpTransport(url="http://127.0.0.1:9", circuit_breaker=breaker)

    def fail(**kwargs: Any) -> None:
        raise ProjectionError("initialize failed")

    transport._ensure_session = fail  # type: ignore[method-assign]
    with pytest.raises(ProjectionError, match="initialize failed"):
        transport._rpc("tools/list", {})
    snapshot = breaker.snapshot()
    assert snapshot.state is CircuitState.OPEN
    assert snapshot.failure_count == 2
    assert breaker.can_execute() is False
    now[0] = 20
    assert breaker.can_execute() is True


def test_phantom_link_reconciliation_dry_run() -> None:
    record_id = uuid4()
    name_link = ProjectionLink(
        record_id=record_id,
        namespace="repo-a",
        projection_name="graphiti",
        target_identity="graphiti",
        locator=f"graphiti-episode-name:group-1:memory:{record_id}",
    )
    uuid_link = ProjectionLink(
        record_id=uuid4(),
        namespace="repo-a",
        projection_name="graphiti",
        target_identity="graphiti",
        locator="provider-7",
    )
    receipt = inventory_phantom_links([name_link, uuid_link])
    assert receipt["action"] == "inventory_only"
    assert receipt["provider_absence_proved"] is False
    assert receipt["candidate_count"] == 1
    assert receipt["candidates"][0]["provider_confirmed"] is False
    assert receipt["candidates"][0]["locator"] == name_link.locator
    assert name_link.locator.startswith("graphiti-episode-name:")
