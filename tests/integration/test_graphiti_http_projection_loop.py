# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_graphiti_http_projection_loop.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""The full projection loop against an in-process official-dialect Graphiti MCP server.

This is the strongest repo-owned proof available when no real Graphiti runtime
is reachable: a real HTTP listener speaking the Streamable-HTTP MCP framing the
production transport is written for (``initialize`` issuing ``Mcp-Session-Id``,
``notifications/initialized`` answered 202, SSE-framed JSON-RPC results, bearer
authentication) and the official tool surface (``add_memory`` keyed by
``uuid``, ``search_memory_facts``, ``search_nodes``, ``delete_episode``).

Every hop below crosses the wire: canonical write, outbox delivery, graph and
semantic retrieval that resolves back to canonical records, supersession and
maintenance withdrawing episodes, verified privacy erasure, rebuild after loss,
and an idempotent replay that projects nothing twice.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from l9_graphite_memory.adapters import GraphitiProjection, SQLiteRecordStore
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    DeletionRequest,
    DeletionStatus,
    EvidenceKind,
    EvidenceRef,
    MaintenanceOperation,
    MaintenanceRequest,
    MemoryAssertion,
    MemoryClass,
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
    WriteStatus,
)
from l9_graphite_memory.maintenance import MaintenanceService
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker
from l9_graphite_memory.transport import HttpMcpTransport

TOKEN = "loop-test-bearer"
TOOLS = ("add_memory", "search_memory_facts", "search_nodes", "delete_episode")


class FakeGraphitiState:
    """Episodes keyed by uuid, as the official server stores them."""

    def __init__(self) -> None:
        self.episodes: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []
        self.sessions: set[str] = set()
        self.lock = threading.Lock()

    def add_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        uuid = str(arguments.get("uuid") or uuid4())
        with self.lock:
            self.episodes[uuid] = {
                "uuid": uuid,
                "name": arguments.get("name"),
                "episode_body": arguments.get("episode_body", ""),
                "group_id": arguments.get("group_id"),
            }
        return {"message": f"Episode '{arguments.get('name')}' queued", "uuid": uuid}

    def delete_episode(self, arguments: dict[str, Any]) -> dict[str, Any]:
        uuid = str(arguments.get("uuid"))
        with self.lock:
            removed = self.episodes.pop(uuid, None)
        if removed is None:
            return {"error": f"Episode with UUID {uuid} not found"}
        return {"message": f"Episode with UUID {uuid} deleted successfully"}

    def search(self, arguments: dict[str, Any], *, key: str, limit_key: str) -> dict[str, Any]:
        query_terms = {term.lower() for term in str(arguments.get("query", "")).split()}
        group_ids = set(arguments.get("group_ids") or [])
        limit = int(arguments.get(limit_key, 10))
        with self.lock:
            candidates = [
                episode
                for episode in self.episodes.values()
                if not group_ids or episode["group_id"] in group_ids
            ]
        scored = []
        for episode in candidates:
            body = episode["episode_body"].lower()
            overlap = sum(1 for term in query_terms if term in body)
            if overlap:
                scored.append((overlap / max(1, len(query_terms)), episode))
        scored.sort(key=lambda item: item[0], reverse=True)
        return {
            key: [
                {"uuid": episode["uuid"], "content": episode["episode_body"], "score": score}
                for score, episode in scored[:limit]
            ]
        }


def _handler(state: FakeGraphitiState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return None

        def _reply(self, status: int, body: dict[str, Any] | None, *, session: str | None) -> None:
            self.send_response(status)
            if session:
                self.send_header("mcp-session-id", session)
            if body is None:
                self.send_header("content-length", "0")
                self.end_headers()
                return
            payload = f"event: message\ndata: {json.dumps(body)}\n\n".encode()
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:
            if self.path != "/mcp":
                self._reply(404, {"error": "not found"}, session=None)
                return
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                self._reply(401, {"error": "unauthorized"}, session=None)
                return
            accept = self.headers.get("Accept", "")
            if "text/event-stream" not in accept:
                self._reply(406, {"error": "not acceptable"}, session=None)
                return
            length = int(self.headers.get("content-length", "0"))
            request = json.loads(self.rfile.read(length) or b"{}")
            method = request.get("method")
            state.calls.append(method)
            session = self.headers.get("Mcp-Session-Id")

            if method == "initialize":
                session = uuid4().hex
                state.sessions.add(session)
                self._reply(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}},
                    },
                    session=session,
                )
                return
            if not session or session not in state.sessions:
                self.send_response(400)
                body = b"Bad Request: Missing session ID"
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if method == "notifications/initialized":
                self._reply(202, None, session=session)
                return
            if method == "tools/list":
                result: dict[str, Any] = {"tools": [{"name": name} for name in TOOLS]}
            elif method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                arguments = params.get("arguments", {})
                if name == "add_memory":
                    value = state.add_memory(arguments)
                elif name == "delete_episode":
                    value = state.delete_episode(arguments)
                elif name == "search_memory_facts":
                    value = state.search(arguments, key="facts", limit_key="max_facts")
                elif name == "search_nodes":
                    value = state.search(arguments, key="nodes", limit_key="max_nodes")
                else:
                    value = {"error": f"unknown tool {name}"}
                result = {"content": [{"type": "text", "text": json.dumps(value)}]}
            else:
                self._reply(
                    200,
                    {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {"code": -32601, "message": f"method not found: {method}"},
                    },
                    session=session,
                )
                return
            self._reply(
                200, {"jsonrpc": "2.0", "id": request.get("id"), "result": result}, session=session
            )

    return Handler


@pytest.fixture
def graphiti():
    state = FakeGraphitiState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def loop(graphiti, tmp_path: Path):
    state, url = graphiti
    store = SQLiteRecordStore(tmp_path / "loop.sqlite3")
    projection = GraphitiProjection(HttpMcpTransport(url=url, token=TOKEN, timeout_seconds=5))
    service = MemoryService(store, projection)
    service.initialize()
    worker = OutboxWorker(store, projection, MemorySettings(), worker_id="loop-worker")
    try:
        yield state, store, projection, service, worker
    finally:
        store.close()


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="operator",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
        maintain_namespaces=("repo-a",),
    )


def _write(service, principal, content, **kwargs):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=kwargs.pop("memory_class", MemoryClass.OBSERVATION),
            content=content,
            provenance=Provenance(source="loop-test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
            **kwargs,
        ),
    )


def _drain(worker) -> dict[str, int]:
    totals = {"delivered": 0, "retried": 0, "dead": 0}
    for _ in range(8):
        result = worker.run_once()
        for key in totals:
            totals[key] += result[key]
        if result["claimed"] == 0:
            break
    return totals


def _search(service, principal, query: str, **kwargs):
    return service.search(
        principal, MemorySearchRequest(query=query, namespaces=("repo-a",), **kwargs)
    )


def test_transport_speaks_the_official_streamable_http_dialect(graphiti) -> None:
    state, url = graphiti
    transport = HttpMcpTransport(url=url, token=TOKEN, timeout_seconds=5)

    assert transport.list_tools() == sorted(TOOLS)
    assert state.calls == ["initialize", "notifications/initialized", "tools/list"]
    health = GraphitiProjection(transport).health()
    assert health["healthy"] is True and health["tool_count"] == 4

    unauthenticated = HttpMcpTransport(url=url, token="wrong", timeout_seconds=5)
    assert unauthenticated.health()["healthy"] is False


def test_write_project_search_supersede_erase_rebuild_loop(loop, maintainer, admin_principal):
    state, store, _projection, service, worker = loop

    # -- write and project --------------------------------------------------
    first = _write(
        service,
        maintainer,
        "the billing service owner is the payments team",
        assertion=MemoryAssertion(subject="billing", predicate="owner", object="payments"),
    )
    assert first.status is WriteStatus.ADMITTED
    assert _drain(worker)["delivered"] == 1
    link = store.get_projection_link(first.record_id, "graphiti")
    assert link is not None and link.locator == str(first.record_id)
    assert str(first.record_id) in state.episodes
    assert json.loads(state.episodes[str(first.record_id)]["episode_body"])["record_id"] == str(
        first.record_id
    )

    # -- retrieval crosses the wire and resolves to the canonical record ----
    receipt = _search(service, maintainer, "who is the billing owner")
    assert [hit.record.record_id for hit in receipt.hits] == [first.record_id]
    assert any(name.startswith("graphiti:") for name in receipt.stores_succeeded)

    # -- idempotent replay projects nothing twice ---------------------------
    keyed = _write(service, maintainer, "deploys happen on tuesdays", idempotency_key="op-1")
    replay = _write(service, maintainer, "deploys happen on tuesdays", idempotency_key="op-1")
    assert replay.status is WriteStatus.DUPLICATE and replay.record_id == keyed.record_id
    _drain(worker)
    assert state.calls.count("tools/call") >= 2
    assert len(state.episodes) == 2

    # -- supersession withdraws the old episode, keeps canonical history ----
    second = _write(
        service,
        maintainer,
        "the billing service owner is the platform team",
        assertion=MemoryAssertion(subject="billing", predicate="owner", object="platform"),
        supersedes=(first.record_id,),
    )
    _drain(worker)
    assert str(first.record_id) not in state.episodes
    assert str(second.record_id) in state.episodes
    assert store.get_record(first.record_id).state is MemoryState.SUPERSEDED
    assert store.get_projection_link(first.record_id, "graphiti") is None
    current = _search(service, maintainer, "who is the billing owner")
    assert [hit.record.record_id for hit in current.hits] == [second.record_id]

    # -- maintenance archives an expired record through the same path ------
    now = datetime.now(timezone.utc)
    expired = _write(
        service,
        maintainer,
        "temporary freeze on deploys",
        valid_from=now - timedelta(days=3),
        valid_to=now - timedelta(days=2),
    )
    _drain(worker)
    assert str(expired.record_id) in state.episodes
    maintenance = MaintenanceService(service).run(
        maintainer,
        MaintenanceRequest(namespace="repo-a", operations=(MaintenanceOperation.ARCHIVE,)),
    )
    assert maintenance.failures == ()
    _drain(worker)
    assert store.get_record(expired.record_id).state is MemoryState.ARCHIVED
    assert str(expired.record_id) not in state.episodes

    # -- verified privacy erasure removes the episode and completes -------
    deletion = service.delete(
        admin_principal,
        DeletionRequest(
            record_id=second.record_id, reason="subject request", verification_reference="t-1"
        ),
    )
    assert deletion.status is DeletionStatus.PENDING_PROJECTION
    totals = _drain(worker)
    assert totals["dead"] == 0
    assert str(second.record_id) not in state.episodes
    assert store.get_record(second.record_id).state is MemoryState.DELETED
    assert store.get_record(second.record_id).content.startswith("[deleted:")
    assert _search(service, maintainer, "who is the billing owner").hits == ()

    # -- rebuild recovers a projection the provider lost -------------------
    state.episodes.pop(str(keyed.record_id))
    store.delete_projection_link(keyed.record_id, "graphiti")
    rebuild = service.rebuild_projection(maintainer, "repo-a", apply=True)
    assert rebuild.queued_record_ids == (keyed.record_id,)
    _drain(worker)
    assert str(keyed.record_id) in state.episodes
    assert store.get_projection_link(keyed.record_id, "graphiti") is not None

    # Only current truth is projected at the end of the loop.
    assert set(state.episodes) == {str(keyed.record_id)}


def test_a_restarted_provider_session_is_transparently_reestablished(loop, maintainer):
    state, _store, _projection, service, worker = loop
    written = _write(service, maintainer, "session survives restarts")
    _drain(worker)
    assert str(written.record_id) in state.episodes

    # The provider restarts: every issued session id is forgotten.
    state.sessions.clear()
    later = _write(service, maintainer, "written after the restart")
    assert _drain(worker)["delivered"] == 1
    assert str(later.record_id) in state.episodes
    assert state.calls.count("initialize") == 2
