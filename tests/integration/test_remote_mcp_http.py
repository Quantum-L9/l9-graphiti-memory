# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_remote_mcp_http.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.7.0
#   updated: 2026-07-22

"""Remote MCP over Streamable HTTP with signed agent identity (ADR-098).

Every case drives the real FastAPI application under uvicorn on a loopback
TCP socket through an HTTP client; none calls ``MCPServer.handle`` directly.
Known-good and known-bad credentials are minted exactly as a remote agent
mints them, and each negative case names the boundary it proves.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.authz.signed_assertion import mint_assertion
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.mcp_tools import tool_definitions
from l9_graphite_memory.runtime import MemoryRuntime
from l9_graphite_memory.server import create_http_app, http_server
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.version import (
    CONTROL_PLANE_CONTRACT_VERSION,
    HTTP_MCP_PROTOCOL_VERSIONS,
    MCP_PROTOCOL_VERSION,
    REMOTE_MCP_CONTRACT_VERSION,
)
from tests.integration.remote_mcp_harness import (
    AGENT_GRANTS,
    AGENT_KEYS,
    ALLOWED_ORIGIN,
    CO_WRITER,
    FORBIDDEN_ORIGIN,
    FOREIGN_NAMESPACE,
    HOME_NAMESPACE,
    OUTSIDER,
    OUTSIDER_KEY,
    PROTOCOL_VERSION,
    READER,
    WRITER,
    credentials,
    free_port,
    identity_body,
    mcp_headers,
    rpc,
    seal,
    serve,
    server_environment,
    tool,
    tool_payload,
)
from tests.integration.remote_mcp_harness import encode as encode_identity

pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
pytest.importorskip("uvicorn", reason="HTTP transport requires the [server] extra")
httpx2 = pytest.importorskip("httpx2", reason="the HTTP proof needs an HTTP client")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _settings(**overrides: Any) -> MemorySettings:
    values: dict[str, Any] = {
        "http_auth_required": True,
        "http_auth_mode": "signed-agent",
        "http_allowed_origins": (ALLOWED_ORIGIN,),
        "local_tenant_id": "l9",
        "local_organization_id": "quantum-l9",
        "local_workspace_id": "l9-workspace",
    }
    values.update(overrides)
    return MemorySettings(**values)


def _runtime(settings: MemorySettings | None = None) -> MemoryRuntime:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    return MemoryRuntime(settings=settings or _settings(), service=service)


@pytest.fixture
def registry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The server-side key and grant registry, and a human door that must not leak."""

    for name, value in server_environment().items():
        monkeypatch.setenv(name, value)
    # A process that also holds the human door secret must still never serve
    # a remote request as the human principal.
    monkeypatch.setenv("L9_MEMORY_HUMAN_DOOR_SECRET", "local-human-door-secret")
    for name in (
        "L9_MEMORY_AGENTS_DOOR_SECRET",
        "L9_MEMORY_AGENT_ASSERTION",
        "L9_MEMORY_IDENTITY_ASSERTION_JSON",
        "L9_MEMORY_IDENTITY_ASSERTION_HMAC",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def base_url(registry_env: None) -> Iterator[str]:
    runtime = _runtime()
    try:
        with serve(create_http_app(runtime)) as url:
            yield url
    finally:
        runtime.close()


@pytest.fixture
def client(base_url: str) -> Iterator[Any]:
    with httpx2.Client(base_url=base_url, timeout=10) as http:
        yield http


def _post(
    client: Any,
    message: Any,
    *,
    agent: str | None = WRITER,
    headers: dict[str, str] | None = None,
    protocol: str | None = PROTOCOL_VERSION,
) -> Any:
    sent = mcp_headers(protocol=protocol)
    if agent is not None:
        sent.update(credentials(agent))
    sent.update(headers or {})
    body = message if isinstance(message, (bytes, str)) else json.dumps(message)
    return client.post("/mcp", content=body, headers=sent)


def _assert_refused(response: Any, status: int, *, secrets: tuple[str, ...] = ()) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert "id" not in body, "a transport refusal has no request id"
    assert isinstance(body["error"]["code"], int)
    rendered = response.text + json.dumps(dict(response.headers))
    for secret in secrets:
        assert secret not in rendered, "a credential was echoed back"
    return body


def _write(client: Any, agent: str, namespace: str, content: str) -> dict[str, Any]:
    response = _post(
        client,
        tool("memory.write_agent", {"namespace": namespace, "content": content}),
        agent=agent,
    )
    assert response.status_code == 200, response.text
    return tool_payload(response.json())


# --- 1. authenticated lifecycle ----------------------------------------------


def test_authenticated_agent_initializes_lists_tools_and_writes_and_searches(client) -> None:
    initialize = _post(
        client,
        rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "remote-proof", "version": "1"},
            },
        ),
        protocol=None,  # initialize negotiates in its body
    )
    assert initialize.status_code == 200, initialize.text
    assert initialize.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in initialize.headers, "the server is stateless"
    result = initialize.json()["result"]
    assert initialize.json()["id"] == 1
    assert result["protocolVersion"] == PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "l9-graphite-memory"
    assert result["capabilities"] == {"tools": {"listChanged": False}}

    initialized = _post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert initialized.status_code == 202
    assert initialized.content == b""

    listed = _post(client, rpc("tools/list", request_id="list-1"))
    assert listed.status_code == 200
    assert listed.json()["id"] == "list-1"
    assert listed.json()["result"]["tools"] == tool_definitions()

    health = tool_payload(_post(client, tool("memory.health", {})).json())
    assert health["status"] != "failed"
    assert health["contract_version"] == CONTROL_PLANE_CONTRACT_VERSION

    receipt = _write(client, WRITER, HOME_NAMESPACE, "falcon nests on the north tower")
    assert receipt["status"] == "admitted"
    assert receipt["record_id"]
    assert receipt["authorization"]["allowed"] is True
    assert "auth_method=" not in json.dumps(receipt["authorization"]["reasons"])

    found = tool_payload(
        _post(
            client, tool("memory.search", {"query": "falcon", "namespaces": [HOME_NAMESPACE]})
        ).json()
    )
    assert found["status"] == "complete"
    assert found["namespaces_authorized"] == [HOME_NAMESPACE]
    assert receipt["record_id"] in {item["record"]["record_id"] for item in found["hits"]}


@pytest.mark.parametrize(
    ("requested", "answered"),
    [
        ("2025-11-25", "2025-11-25"),
        ("2025-06-18", "2025-06-18"),
        # Revisions this transport cannot serve are answered with the newest
        # it can; the client decides whether to continue (MCP lifecycle).
        ("2025-03-26", "2025-11-25"),
        ("2024-11-05", "2025-11-25"),
        ("not-a-revision", "2025-11-25"),
    ],
)
def test_initialize_negotiates_the_protocol_revision(client, requested, answered) -> None:
    response = _post(
        client,
        rpc("initialize", {"protocolVersion": requested, "capabilities": {}}),
        protocol=None,
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["protocolVersion"] == answered


def test_each_request_is_authenticated_on_its_own_evidence(client) -> None:
    assert _post(client, rpc("tools/list")).status_code == 200
    # Nothing from the authenticated request carries over: no session, no
    # cookie, no cached principal.
    _assert_refused(_post(client, rpc("tools/list"), agent=None), 401)
    assert not client.cookies


# --- 2. two agents, one canonical service --------------------------------------


def test_a_second_authenticated_agent_reads_what_the_first_wrote(client) -> None:
    receipt = _write(client, WRITER, HOME_NAMESPACE, "osprey roosts above the east gate")
    record_id = receipt["record_id"]

    got = tool_payload(
        _post(client, tool("memory.get", {"record_id": record_id}), agent=READER).json()
    )
    assert got["found"] is True
    assert got["record"]["record_id"] == record_id
    assert got["record"]["namespace"] == HOME_NAMESPACE
    assert "osprey" in got["record"]["content"]

    found = tool_payload(
        _post(
            client,
            tool("memory.search", {"query": "osprey", "namespaces": [HOME_NAMESPACE]}),
            agent=READER,
        ).json()
    )
    assert record_id in {item["record"]["record_id"] for item in found["hits"]}

    # The reader's grant is read-only: authenticating does not let it write.
    refused = _write(client, READER, HOME_NAMESPACE, "the reader tries to write")
    assert refused["status"] == "rejected"
    assert refused["record_id"] is None
    assert refused["authorization"]["allowed"] is False


# --- 3-5. credential refusals ------------------------------------------------


def test_a_request_without_credentials_is_refused(client) -> None:
    response = _post(client, rpc("tools/list"), agent=None)
    body = _assert_refused(response, 401)
    assert body["error"]["code"] == -32001
    assert response.headers["www-authenticate"] == 'Bearer realm="l9-graphite-memory"'


@pytest.mark.parametrize(
    "missing",
    ["L9-Identity-Assertion", "L9-Identity-Assertion-HMAC", "Authorization"],
)
def test_each_credential_carrier_is_required(client, missing: str) -> None:
    headers = mcp_headers()
    headers.update(credentials(WRITER))
    del headers[missing]
    response = client.post("/mcp", content=json.dumps(rpc("tools/list")), headers=headers)
    _assert_refused(response, 401)


def test_an_expired_assertion_is_refused(client) -> None:
    expired = credentials(WRITER, ttl_seconds=-5)
    body = _assert_refused(
        _post(client, rpc("tools/list"), agent=None, headers=expired),
        401,
        secrets=(expired["Authorization"].split(" ", 1)[1],),
    )
    assert "expired" in body["error"]["message"]


def test_an_assertion_living_longer_than_the_ceiling_is_refused(client) -> None:
    long_lived = credentials(WRITER, ttl_seconds=7 * 24 * 3600)
    body = _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=long_lived), 401)
    assert "ceiling" in body["error"]["message"]


def test_a_tampered_assertion_signature_is_refused(client) -> None:
    headers = credentials(WRITER)
    token = headers["Authorization"].split(" ", 1)[1]
    flipped = token[:-1] + ("0" if token[-1] != "0" else "1")
    headers["Authorization"] = f"Bearer {flipped}"
    body = _assert_refused(
        _post(client, rpc("tools/list"), agent=None, headers=headers),
        401,
        secrets=(flipped, AGENT_KEYS[WRITER]),
    )
    assert "not valid for a registered agent" in body["error"]["message"]
    assert (
        _post(client, rpc("tools/list"), agent=None, headers=headers).headers["www-authenticate"]
        == 'Bearer realm="l9-graphite-memory", error="invalid_token"'
    )


def test_a_reexpiry_by_editing_the_token_is_refused(client) -> None:
    """Extending exp without the key breaks the HMAC: the lifetime is signed."""

    headers = credentials(WRITER, ttl_seconds=-5)
    agent_id, exp, nonce, signature = headers["Authorization"].split(" ", 1)[1].split(".")
    headers["Authorization"] = f"Bearer {agent_id}.{int(exp) + 600}.{nonce}.{signature}"
    body = _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)
    assert "not valid for a registered agent" in body["error"]["message"]


def test_a_tampered_identity_assertion_is_refused(client) -> None:
    headers = credentials(WRITER)
    sealed, _mac = seal(identity_body(WRITER), AGENT_KEYS[WRITER])
    sealed["resolved_dimensions"] = {
        **sealed["resolved_dimensions"],
        "surface_identity": "l9.surface-registry/global@1#forged-surface",
    }
    headers["L9-Identity-Assertion"] = encode_identity(sealed)
    body = _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)
    assert "digest mismatch" in body["error"]["message"]


def test_a_forged_identity_hmac_is_refused(client) -> None:
    headers = credentials(WRITER)
    headers["L9-Identity-Assertion-HMAC"] = "0" * 64
    body = _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)
    assert "HMAC mismatch" in body["error"]["message"]


@pytest.mark.parametrize("value", ["%%%not-base64%%%", "bm90IGpzb24", "WzEsMiwzXQ"])
def test_a_malformed_identity_carrier_is_refused(client, value: str) -> None:
    # not base64url / base64url of "not json" / base64url of a JSON array
    headers = credentials(WRITER)
    headers["L9-Identity-Assertion"] = value
    _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)


def test_identity_evidence_naming_another_actor_is_refused(client) -> None:
    """The writer's own key seals evidence that names the reader."""

    headers = credentials(WRITER, body=identity_body(WRITER, actor=READER))
    body = _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)
    assert "does not match the authenticated agent_id" in body["error"]["message"]


def test_another_agents_genuine_identity_evidence_is_refused(client) -> None:
    """The reader's genuine, reader-sealed evidence presented with the writer's token."""

    stolen = credentials(READER)
    headers = credentials(WRITER)
    headers["L9-Identity-Assertion"] = stolen["L9-Identity-Assertion"]
    headers["L9-Identity-Assertion-HMAC"] = stolen["L9-Identity-Assertion-HMAC"]
    _assert_refused(
        _post(client, rpc("tools/list"), agent=None, headers=headers),
        401,
        secrets=(AGENT_KEYS[READER], AGENT_KEYS[WRITER]),
    )


def test_an_agent_the_server_never_registered_is_refused(client) -> None:
    headers = credentials(OUTSIDER, key=OUTSIDER_KEY)
    body = _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)
    assert "not valid for a registered agent" in body["error"]["message"]


def test_a_static_bearer_token_is_not_an_agent_identity(client) -> None:
    """A long-lived shared secret is not accepted in place of the signed assertion."""

    headers = credentials(WRITER)
    headers["Authorization"] = f"Bearer {AGENT_KEYS[WRITER]}"
    _assert_refused(
        _post(client, rpc("tools/list"), agent=None, headers=headers),
        401,
        secrets=(AGENT_KEYS[WRITER],),
    )


def test_credentials_in_the_url_are_refused_and_not_echoed(client) -> None:
    token = credentials(WRITER)["Authorization"].split(" ", 1)[1]
    response = client.post(
        "/mcp",
        params={"access_token": token},
        content=json.dumps(rpc("tools/list")),
        headers={**mcp_headers(), **credentials(WRITER)},
    )
    _assert_refused(response, 400, secrets=(token,))


def test_a_credential_in_the_url_never_reaches_the_access_log(registry_env: None) -> None:
    """The refused URL credential is not written to uvicorn's access log either.

    Runs the production ``http_server`` builder, so the filter under test is
    the one ``run_http`` installs, on a real loopback socket.
    """

    token = credentials(WRITER)["Authorization"].split(" ", 1)[1]
    runtime = _runtime()
    server = http_server(runtime, host="127.0.0.1", port=free_port())
    thread = threading.Thread(target=server.run, name="access-log-server", daemon=True)
    # uvicorn's access logger does not propagate, so capture on it directly;
    # logger filters run before any handler sees the record.
    access_logger = logging.getLogger("uvicorn.access")
    captured: list[logging.LogRecord] = []
    capture = logging.Handler(level=logging.INFO)
    capture.emit = captured.append  # type: ignore[method-assign]
    access_logger.addHandler(capture)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "uvicorn did not start"
            time.sleep(0.02)
        with httpx2.Client(base_url=f"http://127.0.0.1:{server.config.port}", timeout=10) as http:
            response = http.post(
                "/mcp",
                params={"access_token": token},
                content=json.dumps(rpc("tools/list")),
                headers={**mcp_headers(), **credentials(WRITER)},
            )
        _assert_refused(response, 400, secrets=(token,))
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        access_logger.removeHandler(capture)
        runtime.close()
    access = [record.getMessage() for record in captured]
    assert any('"POST /mcp HTTP/' in line and " 400" in line for line in access), access
    assert not any(token in line or "access_token" in line for line in access), access


def test_the_human_door_is_unreachable_over_http(client) -> None:
    """``L9_MEMORY_HUMAN_DOOR_SECRET`` is set in the server process (fixture)."""

    response = _post(client, tool("memory.health", {}), agent=None)
    _assert_refused(response, 401, secrets=("local-human-door-secret",))
    # And the authenticated agent is the agent, not the human administrator.
    receipt = _write(client, WRITER, HOME_NAMESPACE, "the agent writes as itself")
    assert receipt["authorization"]["principal_id"] == WRITER


# --- 6. authorization is server-side ---------------------------------------


def test_a_namespace_outside_the_grant_is_denied(client) -> None:
    receipt = _write(client, WRITER, FOREIGN_NAMESPACE, "a fact for a namespace never granted")
    assert receipt["status"] == "rejected"
    assert receipt["record_id"] is None
    assert receipt["authorization"]["allowed"] is False

    response = _post(
        client, tool("memory.search", {"query": "fact", "namespaces": [FOREIGN_NAMESPACE]})
    )
    assert response.status_code == 200
    error = response.json()["error"]
    assert error["code"] == -32010
    assert error["data"] == {"type": "AuthorizationError"}


def test_claims_smuggled_into_identity_evidence_do_not_widen_the_grant(client) -> None:
    body = identity_body(WRITER)
    body.update(
        {
            "roles": ["admin"],
            "is_admin": True,
            "write_namespaces": ["*"],
            "read_namespaces": ["*"],
        }
    )
    headers = credentials(WRITER, body=body)  # genuinely sealed by the writer
    response = _post(
        client,
        tool("memory.write_agent", {"namespace": FOREIGN_NAMESPACE, "content": "smuggled"}),
        agent=None,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    receipt = tool_payload(response.json())
    assert receipt["status"] == "rejected"
    assert receipt["record_id"] is None


def test_claims_in_request_headers_are_ignored(client) -> None:
    receipt_response = _post(
        client,
        tool("memory.write_agent", {"namespace": FOREIGN_NAMESPACE, "content": "header claims"}),
        headers={"X-L9-Roles": "admin", "X-L9-Namespaces": "*", "X-Tenant-Id": "other"},
    )
    receipt = tool_payload(receipt_response.json())
    assert receipt["status"] == "rejected"


# --- 7. Origin ---------------------------------------------------------------


def test_a_forbidden_origin_is_refused_before_authentication(client) -> None:
    # No credentials: a 403 rather than a 401 proves Origin is decided first.
    response = _post(client, rpc("tools/list"), agent=None, headers={"Origin": FORBIDDEN_ORIGIN})
    _assert_refused(response, 403)
    response = _post(client, rpc("tools/list"), headers={"Origin": FORBIDDEN_ORIGIN})
    _assert_refused(response, 403)
    get = client.get("/mcp", headers={"Origin": FORBIDDEN_ORIGIN})
    _assert_refused(get, 403)


def test_an_allowed_origin_and_an_absent_origin_are_served(client) -> None:
    assert _post(client, rpc("tools/list"), headers={"Origin": ALLOWED_ORIGIN}).status_code == 200
    assert _post(client, rpc("tools/list")).status_code == 200


# --- 8. malformed requests and protocol versions ------------------------------


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (b"{not json", 400, -32700),
        (b"\xff\xfe", 400, -32700),
        (json.dumps([rpc("tools/list")]), 400, -32600),  # batching removed in 2025-06-18
        (json.dumps({"id": 1, "method": "tools/list"}), 400, -32600),  # no jsonrpc
        (json.dumps({"jsonrpc": "1.0", "id": 1, "method": "tools/list"}), 400, -32600),
        (json.dumps({"jsonrpc": "2.0", "id": None, "method": "tools/list"}), 400, -32600),
        (json.dumps({"jsonrpc": "2.0", "id": True, "method": "tools/list"}), 400, -32600),
        (json.dumps({"jsonrpc": "2.0", "id": 1, "method": ""}), 400, -32600),
        (json.dumps({"jsonrpc": "2.0", "id": 1}), 400, -32600),
        (
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "notifications/initialized"}),
            400,
            -32600,
        ),
    ],
)
def test_malformed_messages_are_refused(client, payload, status: int, code: int) -> None:
    body = _assert_refused(_post(client, payload), status)
    assert body["error"]["code"] == code


def test_json_rpc_level_errors_keep_the_request_id(client) -> None:
    unknown = _post(client, rpc("no/such/method", request_id=7))
    assert unknown.status_code == 200
    assert unknown.json()["id"] == 7
    assert unknown.json()["error"]["code"] == -32601
    bad_params = _post(client, {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": []})
    assert bad_params.json()["error"]["code"] == -32602
    unknown_tool = _post(client, tool("memory.no_such_tool", {}, request_id=9))
    assert unknown_tool.json()["error"]["code"] == -32601


def test_an_unsupported_protocol_version_header_is_refused(client) -> None:
    body = _assert_refused(_post(client, rpc("tools/list"), protocol="2024-11-05"), 400)
    assert body["error"]["data"] == {
        "supported": list(HTTP_MCP_PROTOCOL_VERSIONS),
        "requested": "2024-11-05",
    }
    # On initialize too, when the client names one.
    _assert_refused(
        _post(client, rpc("initialize", {"protocolVersion": "2025-11-25"}), protocol="1999-01-01"),
        400,
    )


def test_a_missing_protocol_version_header_assumes_2025_03_26_and_is_refused(client) -> None:
    body = _assert_refused(_post(client, rpc("tools/list"), protocol=None), 400)
    assert body["error"]["data"]["requested"] == "2025-03-26"
    assert _post(client, rpc("tools/list"), protocol="2025-06-18").status_code == 200


def test_content_type_and_accept_are_enforced(client) -> None:
    headers = {**mcp_headers(), **credentials(WRITER), "Content-Type": "text/plain"}
    _assert_refused(client.post("/mcp", content=json.dumps(rpc("ping")), headers=headers), 415)
    for accept in (
        "application/json",
        "text/event-stream",
        "text/html",
        "application/json, text/event-stream;q=0",
    ):
        headers = {**mcp_headers(), **credentials(WRITER), "Accept": accept}
        _assert_refused(client.post("/mcp", content=json.dumps(rpc("ping")), headers=headers), 406)
    headers = {**mcp_headers(), **credentials(WRITER), "Accept": "*/*"}
    assert client.post("/mcp", content=json.dumps(rpc("ping")), headers=headers).status_code == 200


def test_an_oversized_body_is_refused(client) -> None:
    from l9_graphite_memory.server import HTTP_MAX_BODY_BYTES

    padding = "x" * (HTTP_MAX_BODY_BYTES + 1)
    message = tool("memory.write_agent", {"namespace": HOME_NAMESPACE, "content": padding})
    _assert_refused(_post(client, message), 413)


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_get_and_delete_are_not_allowed(client, method: str) -> None:
    response = client.request(method, "/mcp", headers={**mcp_headers(), **credentials(WRITER)})
    _assert_refused(response, 405)
    assert response.headers["allow"] == "POST"


# --- 9. notifications and client responses ------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 3}},
        {"jsonrpc": "2.0", "id": "srv-1", "result": {}},
        {"jsonrpc": "2.0", "id": "srv-2", "error": {"code": -32601, "message": "no"}},
    ],
)
def test_notifications_and_client_responses_get_an_empty_202(client, message) -> None:
    response = _post(client, message)
    assert response.status_code == 202
    assert response.content == b""


def test_a_notification_still_requires_credentials(client) -> None:
    _assert_refused(
        _post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, agent=None), 401
    )


# --- 11. capability and receipt compatibility ----------------------------------


def test_capability_and_lifecycle_receipts_keep_their_control_plane_shapes(client) -> None:
    capabilities = tool_payload(_post(client, tool("memory.capabilities", {})).json())
    assert capabilities["contract_version"] == CONTROL_PLANE_CONTRACT_VERSION
    assert capabilities["mcp_protocol_version"] == MCP_PROTOCOL_VERSION
    assert capabilities["http_mcp_protocol_versions"] == list(HTTP_MCP_PROTOCOL_VERSIONS)
    assert capabilities["remote_mcp_contract_version"] == REMOTE_MCP_CONTRACT_VERSION
    mcp = next(t for t in capabilities["transports"] if t["transport"] == "mcp")
    for operation in ("write_agent", "write_governed", "search", "hydrate", "close", "phase_lock"):
        assert operation in mcp["operations"]

    write = _write(client, WRITER, HOME_NAMESPACE, "kestrel hunts over the west field")
    assert {"receipt_id", "status", "namespace", "record_id"} <= set(write)

    lock = tool_payload(
        _post(
            client,
            tool(
                "memory.phase_lock", {"namespace": HOME_NAMESPACE, "task_signature": "remote-proof"}
            ),
        ).json()
    )
    assert {"lock_id", "namespace", "task_signature", "granted", "expires_at"} <= set(lock)
    assert lock["granted"] is True
    governed = tool_payload(
        _post(
            client,
            tool(
                "memory.write_governed",
                {
                    "namespace": HOME_NAMESPACE,
                    "content": "merlin perches on the south wall",
                    "task_signature": "remote-proof",
                },
            ),
        ).json()
    )
    assert governed["status"] == "admitted", governed

    search = tool_payload(
        _post(
            client, tool("memory.search", {"query": "kestrel", "namespaces": [HOME_NAMESPACE]})
        ).json()
    )
    assert {"receipt_id", "status", "query", "namespaces_authorized"} <= set(search)
    hydrate = tool_payload(
        _post(
            client, tool("memory.hydrate", {"task": "birds", "namespaces": [HOME_NAMESPACE]})
        ).json()
    )
    assert hydrate["status"] in {"complete", "partial"}

    close = tool_payload(
        _post(
            client,
            tool(
                "memory.close",
                {
                    "namespace": HOME_NAMESPACE,
                    "summary": "remote proof session closed",
                    "idempotency_key": "remote-proof-close",
                },
            ),
        ).json()
    )
    assert close["status"] == "complete", close
    assert close["record_id"]
    assert close["write_receipt_id"]


# --- startup configuration fails closed -----------------------------------------


def test_signed_agent_mode_refuses_to_start_without_a_registry(monkeypatch) -> None:
    monkeypatch.delenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", raising=False)
    monkeypatch.delenv("L9_MEMORY_AGENT_GRANTS_JSON", raising=False)
    runtime = _runtime()
    with pytest.raises(ConfigurationError, match="L9_MEMORY_AGENT_SIGNING_KEYS_JSON"):
        create_http_app(runtime)


def test_signed_agent_mode_refuses_a_malformed_grant_at_startup(monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", json.dumps(AGENT_KEYS))
    # The door has never granted maintain authority; a grant carrying it is
    # malformed trusted configuration, not a silently dropped key.
    grants = {**AGENT_GRANTS, READER: {**AGENT_GRANTS[READER], "maintain_namespaces": ["*"]}}
    monkeypatch.setenv("L9_MEMORY_AGENT_GRANTS_JSON", json.dumps(grants))
    runtime = _runtime()
    with pytest.raises(ConfigurationError, match="malformed signed-agent grant"):
        create_http_app(runtime)
    monkeypatch.setenv("L9_MEMORY_AGENT_GRANTS_JSON", json.dumps({WRITER: AGENT_GRANTS[WRITER]}))
    with pytest.raises(ConfigurationError, match="no grants configured"):
        create_http_app(runtime)


def test_signed_agent_mode_refuses_to_register_the_human_door(monkeypatch) -> None:
    monkeypatch.setenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", json.dumps({"human": "k" * 32}))
    monkeypatch.setenv("L9_MEMORY_AGENT_GRANTS_JSON", json.dumps({"human": {"is_admin": True}}))
    runtime = _runtime()
    with pytest.raises(ConfigurationError, match="reserved agent id"):
        create_http_app(runtime)


@pytest.mark.parametrize("is_admin", [True, "true", 1])
def test_signed_agent_mode_refuses_an_administrator_grant_at_startup(
    registry_env, monkeypatch, is_admin: object
) -> None:
    """A server-side agent grant is never a route to tenant administrator over HTTP.

    Every value Pydantic parses as ``True`` is refused, and the otherwise
    identical non-administrator registry still starts and serves its agents.
    """

    grants = {**AGENT_GRANTS, READER: {**AGENT_GRANTS[READER], "is_admin": is_admin}}
    monkeypatch.setenv("L9_MEMORY_AGENT_GRANTS_JSON", json.dumps(grants))
    runtime = _runtime()
    try:
        with pytest.raises(ConfigurationError, match=rf"is_admin to agent_id='{READER}'"):
            create_http_app(runtime)
        monkeypatch.setenv("L9_MEMORY_AGENT_GRANTS_JSON", json.dumps(AGENT_GRANTS))
        with serve(create_http_app(runtime)) as url, httpx2.Client(base_url=url) as http:
            receipt = _write(http, WRITER, HOME_NAMESPACE, "a non-admin grant still writes")
            assert receipt["status"] == "admitted", receipt
            assert receipt["authorization"]["principal_id"] == WRITER
    finally:
        runtime.close()


def test_auth_disabled_http_refuses_an_administrator_agent_door(registry_env, monkeypatch) -> None:
    """Loopback HTTP serves the signed agent door, so it refuses the same grant.

    The stdio agent door for the same configuration is unchanged, and the
    human door stays the local administrator tier.
    """

    from l9_graphite_memory.server import _agent_door_principal, _stdio_principal

    grants = {**AGENT_GRANTS, WRITER: {**AGENT_GRANTS[WRITER], "is_admin": True}}
    monkeypatch.setenv("L9_MEMORY_AGENT_GRANTS_JSON", json.dumps(grants))
    sealed, mac = seal(identity_body(WRITER), AGENT_KEYS[WRITER])
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "door")
    monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", mint_assertion(WRITER, AGENT_KEYS[WRITER]))
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_JSON", json.dumps(sealed))
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_HMAC", mac)
    settings = _settings(http_auth_required=False, http_auth_mode="bearer")
    runtime = _runtime(settings)
    try:
        with pytest.raises(ConfigurationError, match=rf"is_admin to agent_id='{WRITER}'"):
            create_http_app(runtime)
    finally:
        runtime.close()
    stdio_agent = _agent_door_principal(settings)
    assert stdio_agent is not None
    assert (stdio_agent.auth_method, stdio_agent.is_admin) == ("stdio-agent-assertion", True)
    human = _stdio_principal(settings)  # the fixture also sets the human door secret
    assert (human.principal_id, human.is_admin, human.auth_method) == (
        "human",
        True,
        "stdio-human-door",
    )


def test_signed_agent_mode_requires_authentication(registry_env) -> None:
    runtime = _runtime(_settings(http_auth_required=False))
    with pytest.raises(ConfigurationError, match="requires http_auth_required=true"):
        create_http_app(runtime)


def test_bearer_mode_is_unchanged_and_never_reads_the_agent_registry(registry_env) -> None:
    from l9_graphite_memory.config import TokenPrincipalConfig

    settings = _settings(
        http_auth_mode="bearer",
        auth_tokens={
            "service-token-for-tests": TokenPrincipalConfig(
                principal_id="service",
                tenant_id="l9",
                read_namespaces=(HOME_NAMESPACE,),
                write_namespaces=(HOME_NAMESPACE,),
            )
        },
    )
    runtime = _runtime(settings)
    try:
        with serve(create_http_app(runtime)) as url, httpx2.Client(base_url=url) as http:
            ok = http.post(
                "/mcp",
                content=json.dumps(tool("memory.health", {})),
                headers={**mcp_headers(), "Authorization": "Bearer service-token-for-tests"},
            )
            assert ok.status_code == 200, ok.text
            # A signed agent credential is not a bearer service token.
            refused = http.post(
                "/mcp",
                content=json.dumps(rpc("tools/list")),
                headers={**mcp_headers(), **credentials(WRITER)},
            )
            _assert_refused(refused, 401)
    finally:
        runtime.close()


# --- 10. stdio is unchanged ------------------------------------------------------


def test_stdio_still_answers_its_own_revision_and_the_same_tools(tmp_path: Path) -> None:
    """The installed stdio client contract: 2024-11-05 whatever is requested."""

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("L9_MEMORY_") and key != "PYTHONPATH"
    }
    env.update(
        {
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "HOME": str(tmp_path / "home"),
            "L9_MEMORY_DATA_DIR": str(tmp_path / "data"),
            "L9_MEMORY_STATE_DIR": str(tmp_path / "state"),
            "L9_MEMORY_PROJECTION_BACKEND": "none",
        }
    )
    lines = [
        rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}}, request_id=1),
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        rpc("tools/list", request_id=2),
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "l9_graphite_memory.server", "--transport", "stdio"],
        input="".join(json.dumps(line) + "\n" for line in lines),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    replies = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    assert [reply["id"] for reply in replies] == [1, 2], "a notification gets no stdio reply"
    assert replies[0]["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION == "2024-11-05"
    assert replies[1]["result"]["tools"] == tool_definitions()


def test_the_stdio_agent_door_and_the_http_door_build_the_same_principal(
    registry_env, monkeypatch
) -> None:
    """One grant, two transports: the remote agent holds exactly the local claims."""

    from l9_graphite_memory.authz.remote_agent import SignedAgentAuthenticator
    from l9_graphite_memory.server import _agent_door_principal

    settings = _settings()
    headers = credentials(WRITER)
    remote = SignedAgentAuthenticator.from_environment(settings).authenticate(
        authorization=headers["Authorization"],
        identity_assertion=headers["L9-Identity-Assertion"],
        identity_assertion_hmac=headers["L9-Identity-Assertion-HMAC"],
    )
    sealed, mac = seal(identity_body(WRITER), AGENT_KEYS[WRITER])
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "door")
    monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", mint_assertion(WRITER, AGENT_KEYS[WRITER]))
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_JSON", json.dumps(sealed))
    monkeypatch.setenv("L9_MEMORY_IDENTITY_ASSERTION_HMAC", mac)
    local = _agent_door_principal(settings)
    assert local is not None
    assert remote.auth_method == "http-agent-assertion"
    assert local.auth_method == "stdio-agent-assertion"
    assert remote.model_copy(update={"auth_method": local.auth_method}) == local


# --- review regressions: hostile inputs are 4xx, never 500 ----------------------


def _future_exp() -> int:
    import time

    return int(time.time()) + 300


def test_registered_and_unregistered_agents_are_refused_identically(client) -> None:
    """No agent-id enumeration: a bad signature on a registered id and any
    signature on an unregistered id produce the same refusal."""

    exp = _future_exp()
    registered = f"Bearer {WRITER}.{exp}.{'ab' * 16}.{'0' * 64}"
    unregistered = f"Bearer nobody.{exp}.{'ab' * 16}.{'0' * 64}"
    bodies = []
    for authorization in (registered, unregistered):
        headers = {**credentials(WRITER), "Authorization": authorization}
        bodies.append(
            _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)
        )
    assert bodies[0] == bodies[1]


@pytest.mark.parametrize(
    "signature",
    [
        "\u00e9" * 64,  # non-ASCII: hmac.compare_digest would raise TypeError
        "0" * 63,
        "G" * 64,
        "0" * 65,
    ],
    ids=["non-ascii", "short", "non-hex", "long"],
)
def test_a_malformed_signature_is_refused_without_a_key(client, signature: str) -> None:
    exp = _future_exp()
    headers = {"Authorization": f"Bearer {WRITER}.{exp}.{'ab' * 16}.{signature}"}
    raw_headers = {**mcp_headers(), **headers}
    response = client.post(
        "/mcp",
        content=json.dumps(rpc("tools/list")),
        headers={key: value.encode("latin-1") for key, value in raw_headers.items()},
    )
    _assert_refused(response, 401)


@pytest.mark.parametrize(
    "exp",
    ["1" + "0" * 400, "-5", "+300", "1_700", "", "12345678901234"],
    ids=["huge", "negative", "signed", "underscored", "empty", "13-digits"],
)
def test_an_out_of_shape_expiry_is_refused(client, exp: str) -> None:
    from l9_graphite_memory.authz.signed_assertion import mint_assertion as _mint

    token = _mint(WRITER, AGENT_KEYS[WRITER])
    agent_id, _exp, nonce, signature = token.split(".")
    headers = {
        **credentials(WRITER),
        "Authorization": f"Bearer {agent_id}.{exp}.{nonce}.{signature}",
    }
    body = _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)
    assert "malformed" in body["error"]["message"]


def test_a_correctly_signed_absurd_expiry_is_refused_not_overflowed(client) -> None:
    """A key holder signs exp=10**400: the shape check refuses it before arithmetic."""

    import hashlib
    import hmac

    exp, nonce = "1" + "0" * 400, "ab" * 16
    payload = f"{WRITER}|{exp}|{nonce}".encode()
    signature = hmac.new(AGENT_KEYS[WRITER].encode(), payload, hashlib.sha256).hexdigest()
    headers = {**credentials(WRITER), "Authorization": f"Bearer {WRITER}.{exp}.{nonce}.{signature}"}
    _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)


@pytest.mark.parametrize(
    "mac", ["\u00e9" * 64, "\u00e9" + "0" * 63], ids=["non-ascii", "non-ascii-prefix"]
)
def test_a_non_ascii_identity_hmac_is_refused(client, mac: str) -> None:
    headers = {**mcp_headers(), **credentials(WRITER), "L9-Identity-Assertion-HMAC": mac}
    response = client.post(
        "/mcp",
        content=json.dumps(rpc("tools/list")),
        headers={key: value.encode("latin-1") for key, value in headers.items()},
    )
    _assert_refused(response, 401)


def test_a_non_ascii_assertion_digest_is_refused(client) -> None:
    sealed, mac = seal(identity_body(WRITER), AGENT_KEYS[WRITER])
    sealed["assertion_digest"] = "\u00e9" * len(sealed["assertion_digest"])
    headers = {**credentials(WRITER), "L9-Identity-Assertion": encode_identity(sealed)}
    headers["L9-Identity-Assertion-HMAC"] = mac
    _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)


@pytest.mark.parametrize(
    "payload",
    [
        "[" * 12_000,  # RecursionError in json.loads
        '{"n": ' + "9" * 5_000 + "}",  # int digit limit -> ValueError
    ],
    ids=["deep-nesting", "huge-integer"],
)
def test_an_undecodable_identity_assertion_is_refused(client, payload: str) -> None:
    import base64

    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    headers = {**credentials(WRITER), "L9-Identity-Assertion": encoded}
    _assert_refused(_post(client, rpc("tools/list"), agent=None, headers=headers), 401)


@pytest.mark.parametrize(
    "payload",
    [
        b"[" * 200_000,
        b'{"jsonrpc": "2.0", "id": ' + b"9" * 5_000 + b', "method": "ping"}',
    ],
    ids=["deep-nesting", "huge-integer"],
)
def test_an_undecodable_body_is_a_parse_error(client, payload: bytes) -> None:
    body = _assert_refused(_post(client, payload), 400)
    assert body["error"]["code"] == -32700


def test_a_chunked_oversized_body_is_refused_at_the_limit(client) -> None:
    from l9_graphite_memory.server import HTTP_MAX_BODY_BYTES

    def chunks():
        block = b"x" * 65_536
        sent = 0
        while sent <= HTTP_MAX_BODY_BYTES:
            sent += len(block)
            yield block

    headers = {**mcp_headers(), **credentials(WRITER)}
    response = client.post("/mcp", content=chunks(), headers=headers)
    assert "content-length" not in {key.lower() for key in response.request.headers}
    _assert_refused(response, 413)


def test_auth_disabled_http_never_serves_the_human_door(monkeypatch) -> None:
    """Pre-existing gap closed with ADR-098: any local process reaching a
    loopback port is not the human administrator."""

    monkeypatch.setenv("L9_MEMORY_HUMAN_DOOR_SECRET", "local-human-door-secret")
    for name in ("L9_MEMORY_AGENTS_DOOR_SECRET",):
        monkeypatch.delenv(name, raising=False)
    runtime = _runtime(_settings(http_auth_required=False, http_auth_mode="bearer"))
    try:
        with serve(create_http_app(runtime)) as url, httpx2.Client(base_url=url) as http:
            response = http.post(
                "/mcp",
                content=json.dumps(
                    tool("memory.write_agent", {"namespace": FOREIGN_NAMESPACE, "content": "x y z"})
                ),
                headers=mcp_headers(),
            )
            receipt = tool_payload(response.json())
            assert receipt["status"] == "rejected"
            assert receipt["authorization"]["principal_id"] != "human"
            assert "stdio-human-door" not in json.dumps(receipt)
    finally:
        runtime.close()


def test_bearer_mode_refuses_a_non_ascii_token(registry_env) -> None:
    from l9_graphite_memory.config import TokenPrincipalConfig

    settings = _settings(
        http_auth_mode="bearer",
        auth_tokens={"service-token": TokenPrincipalConfig(principal_id="svc", tenant_id="l9")},
    )
    runtime = _runtime(settings)
    try:
        with serve(create_http_app(runtime)) as url, httpx2.Client(base_url=url) as http:
            response = http.post(
                "/mcp",
                content=json.dumps(rpc("tools/list")),
                headers={
                    **{key: value.encode() for key, value in mcp_headers().items()},
                    "Authorization": "Bearer \u00e9\u00e9\u00e9".encode("latin-1"),
                },
            )
            _assert_refused(response, 401)
    finally:
        runtime.close()


# --- tenant isolation and idempotency over HTTP ----------------------------------


def _call(http: Any, agent: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = http.post(
        "/mcp",
        content=json.dumps(tool(name, arguments)),
        headers={**mcp_headers(), **credentials(agent)},
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_tenant_isolation_holds_between_two_deployments_of_one_service(registry_env) -> None:
    """The tenant is a deployment coordinate (server settings), never an agent claim.

    Two HTTP deployments share one MemoryService and one agent registry but
    run as different tenants. The same agents, with the same grants, cannot
    see or touch the other tenant's records.
    """

    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    tenant_a = MemoryRuntime(settings=_settings(local_tenant_id="tenant-a"), service=service)
    tenant_b = MemoryRuntime(settings=_settings(local_tenant_id="tenant-b"), service=service)
    content = "a falcon nests on the tenant-a tower"
    with (
        serve(create_http_app(tenant_a)) as url_a,
        serve(create_http_app(tenant_b)) as url_b,
        httpx2.Client(base_url=url_a, timeout=10) as http_a,
        httpx2.Client(base_url=url_b, timeout=10) as http_b,
    ):
        written = tool_payload(
            _call(
                http_a,
                WRITER,
                "memory.write_agent",
                {"namespace": HOME_NAMESPACE, "content": content, "idempotency_key": "tenant-key"},
            )
        )
        assert written["status"] == "admitted"
        record_id = written["record_id"]

        # Known good: the tenant-a reader sees it.
        own = tool_payload(_call(http_a, READER, "memory.get", {"record_id": record_id}))
        assert own["found"] is True
        assert own["record"]["tenant_id"] == "tenant-a"

        # Denied: the same reader, through the tenant-b deployment, cannot read it.
        foreign_get = _call(http_b, READER, "memory.get", {"record_id": record_id})
        assert foreign_get["error"]["code"] == -32010
        assert foreign_get["error"]["data"] == {"type": "AuthorizationError"}
        foreign_search = tool_payload(
            _call(
                http_b, READER, "memory.search", {"query": "falcon", "namespaces": [HOME_NAMESPACE]}
            )
        )
        assert foreign_search["hits"] == []

        # A tenant-b write under the same namespace and key is its own record;
        # it neither replays nor overwrites the tenant-a record.
        other = tool_payload(
            _call(
                http_b,
                WRITER,
                "memory.write_agent",
                {"namespace": HOME_NAMESPACE, "content": content, "idempotency_key": "tenant-key"},
            )
        )
        assert other["status"] == "admitted"
        assert other["record_id"] != record_id
        back = _call(http_a, READER, "memory.get", {"record_id": other["record_id"]})
        assert back["error"]["data"] == {"type": "AuthorizationError"}
        unchanged = tool_payload(_call(http_a, READER, "memory.get", {"record_id": record_id}))
        assert unchanged["record"]["content"] == own["record"]["content"]
    tenant_a.close()
    tenant_b.close()


def test_repeated_writes_keep_the_existing_idempotency_guarantees(client) -> None:
    """Over HTTP, a replayed key yields the original record; a second agent
    reusing the key cannot overwrite it or take its attribution (ADR-008)."""

    arguments = {
        "namespace": HOME_NAMESPACE,
        "content": "a kite circles the quarry at dusk",
        "idempotency_key": "remote-idempotency-1",
    }
    first = tool_payload(_post(client, tool("memory.write_agent", arguments)).json())
    replay = tool_payload(_post(client, tool("memory.write_agent", arguments)).json())
    assert first["status"] == "admitted"
    assert replay["status"] == "duplicate"
    assert replay["record_id"] == first["record_id"]

    hijack = tool_payload(
        _post(
            client,
            tool("memory.write_agent", {**arguments, "content": "the kite was never there"}),
            agent=CO_WRITER,
        ).json()
    )
    assert hijack["status"] == "duplicate"
    assert hijack["record_id"] == first["record_id"]
    assert any("original record remains authoritative" in w for w in hijack["warnings"])

    stored = tool_payload(
        _post(client, tool("memory.get", {"record_id": first["record_id"]})).json()
    )
    assert stored["record"]["content"] == arguments["content"]
    assert stored["record"]["provenance"]["source_agent_id"] == WRITER
    found = tool_payload(
        _post(
            client, tool("memory.search", {"query": "kite", "namespaces": [HOME_NAMESPACE]})
        ).json()
    )
    assert [hit["record"]["record_id"] for hit in found["hits"]].count(first["record_id"]) == 1
    assert len(found["hits"]) == 1
