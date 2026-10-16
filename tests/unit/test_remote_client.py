"""Unit contract of the remote consumer client (ADR-082, amendment 2026-10-16): no network.

The transport is replaced at ``_send``, so every case here pins what the
client does with a given wire answer: how it classifies a refusal, what it
refuses to send, and what it binds to.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from l9_graphite_memory.contracts import MemorySearchRequest
from l9_graphite_memory.contracts.capabilities import build_capabilities
from l9_graphite_memory.mcp_tools import canonical_tool_names
from l9_graphite_memory.remote_client import (
    AGENT_ASSERTION_ENV,
    IDENTITY_ASSERTION_HMAC_ENV,
    IDENTITY_ASSERTION_JSON_ENV,
    REMOTE_BLOCKED_OPERATIONS,
    REMOTE_OPERATION_TOOLS,
    AgentCredentials,
    RemoteFailureKind,
    RemoteMemoryClient,
    RemoteMemoryError,
    normalize_endpoint,
)

NOW = 1_800_000_000
ASSERTION = f"cursor.{NOW + 600}.{'ab' * 16}.{'cd' * 32}"
IDENTITY = {"schema": "l9.identity-assertion/v1", "assertion_digest": "sha256:" + "e" * 64}
HMAC = "f" * 64


def credentials(**overrides: Any) -> AgentCredentials:
    values: dict[str, Any] = {
        "agent_assertion": ASSERTION,
        "identity_assertion": IDENTITY,
        "identity_assertion_hmac": HMAC,
    }
    values.update(overrides)
    return AgentCredentials(**values)


# -- endpoint policy ---------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "endpoint"),
    [
        ("https://memory.example", "https://memory.example/mcp"),
        ("https://memory.example/", "https://memory.example/mcp"),
        ("https://memory.example/mcp/", "https://memory.example/mcp"),
        ("https://memory.example:8443/l9/mcp", "https://memory.example:8443/l9/mcp"),
        ("http://127.0.0.1:9000", "http://127.0.0.1:9000/mcp"),
        ("http://localhost:9000/mcp", "http://localhost:9000/mcp"),
        ("http://[::1]:9000", "http://[::1]:9000/mcp"),
    ],
)
def test_endpoint_normalization(url: str, endpoint: str) -> None:
    assert normalize_endpoint(url) == endpoint


@pytest.mark.parametrize(
    "url",
    [
        "http://memory.example",  # clear text to a remote host
        "http://10.0.0.5:9000",
        "ftp://memory.example",
        "memory.example",
        "https://user:pass@memory.example",
        "https://memory.example/mcp?token=abc",
        "https://memory.example/mcp#frag",
        "https://memory.example:99999",
        "",
    ],
)
def test_endpoint_refusals(url: str) -> None:
    with pytest.raises(RemoteMemoryError) as caught:
        normalize_endpoint(url)
    assert caught.value.kind is RemoteFailureKind.CONFIGURATION
    assert caught.value.error_type == "ConfigurationError"
    assert "abc" not in str(caught.value)
    assert "pass" not in str(caught.value)


# -- credentials -------------------------------------------------------------


def test_credentials_expose_identity_but_never_values() -> None:
    held = credentials()
    assert held.agent_id == "cursor"
    assert held.expires_at == NOW + 600
    assert ASSERTION not in repr(held)
    assert HMAC not in repr(held)
    headers = held.headers(now=NOW)
    assert headers["Authorization"] == f"Bearer {ASSERTION}"
    assert headers["L9-Identity-Assertion-HMAC"] == HMAC
    assert set(headers) == {"Authorization", "L9-Identity-Assertion", "L9-Identity-Assertion-HMAC"}


def test_expired_and_nearly_expired_credentials_are_refused_locally() -> None:
    held = credentials()
    for now in (NOW + 600, NOW + 596, NOW + 10_000):
        with pytest.raises(RemoteMemoryError) as caught:
            held.headers(now=now)
        assert caught.value.kind is RemoteFailureKind.CREDENTIAL_EXPIRED
        assert caught.value.error_type == "AuthenticationError"
        assert ASSERTION not in str(caught.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"agent_assertion": "not-an-assertion"},
        {"agent_assertion": "cursor.soon.nonce.sig"},
        {"agent_assertion": f"cursor.{'9' * 13}.n.s"},
        {"agent_assertion": ASSERTION + "\r\nX-Injected: 1"},
        {"identity_assertion_hmac": "ab cd"},
        {"identity_assertion": {"schema": "unsealed"}},
    ],
)
def test_malformed_credentials_are_configuration_failures(overrides: dict[str, Any]) -> None:
    with pytest.raises(RemoteMemoryError) as caught:
        credentials(**overrides)
    assert caught.value.kind is RemoteFailureKind.CONFIGURATION


def test_credentials_from_environment() -> None:
    env = {
        AGENT_ASSERTION_ENV: ASSERTION,
        IDENTITY_ASSERTION_JSON_ENV: json.dumps(IDENTITY),
        IDENTITY_ASSERTION_HMAC_ENV: HMAC,
    }
    assert AgentCredentials.from_environment(env).agent_id == "cursor"
    with pytest.raises(RemoteMemoryError, match=IDENTITY_ASSERTION_HMAC_ENV):
        AgentCredentials.from_environment({**env, IDENTITY_ASSERTION_HMAC_ENV: ""})
    with pytest.raises(RemoteMemoryError, match="not valid JSON"):
        AgentCredentials.from_environment({**env, IDENTITY_ASSERTION_JSON_ENV: "{"})


# -- the client against scripted wire answers -------------------------------


def _capabilities(**overrides: Any) -> dict[str, Any]:
    receipt = build_capabilities(cli_commands=(), mcp_tools=canonical_tool_names()).model_dump(
        mode="json"
    )
    receipt.update(overrides)
    return receipt


class ScriptedClient(RemoteMemoryClient):
    """A client whose wire answers are scripted; records what it would send."""

    def __init__(self, answers: Iterator[Any], **kwargs: Any) -> None:
        super().__init__("https://memory.example", credentials(), clock=lambda: NOW, **kwargs)
        self.answers = answers
        self.sent: list[dict[str, Any]] = []

    def _send(self, message: dict[str, Any]) -> tuple[int, str, bytes]:
        self.sent.append(message)
        answer = next(self.answers)
        if isinstance(answer, BaseException):
            raise answer
        if answer == 202:
            return 202, "", b""
        if callable(answer):
            answer = answer(message)
        return 200, "application/json", json.dumps(answer).encode("utf-8")


def result(payload: Any) -> Any:
    def build(message: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": message["id"],
            "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
        }

    return build


def rpc_error(code: int, message: str, data: dict[str, Any] | None = None) -> Any:
    def build(request: dict[str, Any]) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request["id"], "error": error}

    return build


def initialize(version: str = "2025-11-25") -> Any:
    def build(message: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": version}}

    return build


def handshake(**capability_overrides: Any) -> list[Any]:
    return [initialize(), 202, result(_capabilities(**capability_overrides))]


def test_connect_binds_the_contract_and_carries_the_negotiated_revision() -> None:
    client = ScriptedClient(iter(handshake()))
    capabilities = client.connect()
    assert capabilities.remote_mcp_contract_version == "memory-remote-mcp/v1"
    initialize_message, notification, capability_call = client.sent
    assert initialize_message["method"] == "initialize"
    assert "id" not in notification
    assert notification["method"] == "notifications/initialized"
    assert capability_call["params"]["name"] == "memory.capabilities"
    assert client.protocol_version == "2025-11-25"
    assert client.connect() is capabilities  # bound once
    assert len(client.sent) == 3


@pytest.mark.parametrize(
    "overrides",
    [
        {"contract_version": "memory-control-plane/v2"},
        {"remote_mcp_contract_version": "memory-remote-mcp/v2"},
        {"http_mcp_protocol_versions": ["2025-06-18"]},
        {"transports": []},
        {"unexpected_field": True},
    ],
)
def test_a_server_outside_the_contract_is_refused(overrides: dict[str, Any]) -> None:
    client = ScriptedClient(iter(handshake(**overrides)))
    with pytest.raises(RemoteMemoryError) as caught:
        client.connect()
    assert caught.value.kind is RemoteFailureKind.CONTRACT_MISMATCH


def test_an_unspeakable_negotiated_revision_is_refused() -> None:
    client = ScriptedClient(iter([initialize("2026-07-28")]))
    with pytest.raises(RemoteMemoryError) as caught:
        client.connect()
    assert caught.value.kind is RemoteFailureKind.CONTRACT_MISMATCH


@pytest.mark.parametrize(
    ("answer", "kind", "error_type"),
    [
        (rpc_error(-32001, "bad agent"), RemoteFailureKind.AUTHENTICATION, "AuthenticationError"),
        (
            rpc_error(-32010, "not granted", {"type": "AuthorizationError"}),
            RemoteFailureKind.AUTHORIZATION,
            "AuthorizationError",
        ),
        (
            rpc_error(-32010, "store down", {"type": "StoreError"}),
            RemoteFailureKind.TOOL_FAILURE,
            "StoreError",
        ),
        (rpc_error(-32602, "bad args"), RemoteFailureKind.INVALID_REQUEST, "ValueError"),
        (
            rpc_error(-32601, "unknown tool"),
            RemoteFailureKind.CONTRACT_MISMATCH,
            "RemoteContractMismatch",
        ),
        (
            rpc_error(-32603, "internal error", {"type": "KeyError"}),
            RemoteFailureKind.TOOL_FAILURE,
            "KeyError",
        ),
        (
            lambda m: {"jsonrpc": "2.0", "id": m["id"] + 1, "result": {}},
            RemoteFailureKind.PROTOCOL,
            "RemoteProtocolError",
        ),
        (
            lambda m: {"jsonrpc": "2.0", "id": m["id"], "result": {"content": []}},
            RemoteFailureKind.PROTOCOL,
            "RemoteProtocolError",
        ),
        (
            result({"status": "complete"}),
            RemoteFailureKind.CONTRACT_MISMATCH,
            "RemoteContractMismatch",
        ),
    ],
)
def test_tool_outcomes_are_classified(
    answer: Any, kind: RemoteFailureKind, error_type: str
) -> None:
    client = ScriptedClient(iter([*handshake(), answer]))
    with pytest.raises(RemoteMemoryError) as caught:
        client.health()
    assert caught.value.kind is kind
    assert caught.value.error_type == error_type
    assert caught.value.as_dict()["remote"]["failure_kind"] == kind.value


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (400, RemoteFailureKind.PROTOCOL),
        (401, RemoteFailureKind.AUTHENTICATION),
        (403, RemoteFailureKind.PROTOCOL),
        (406, RemoteFailureKind.PROTOCOL),
        (307, RemoteFailureKind.PROTOCOL),
        (404, RemoteFailureKind.UNREACHABLE),
        (502, RemoteFailureKind.UNREACHABLE),
        (503, RemoteFailureKind.UNREACHABLE),
    ],
)
def test_http_refusals_are_classified(status: int, kind: RemoteFailureKind) -> None:
    body = json.dumps({"jsonrpc": "2.0", "error": {"code": -32600, "message": "refused"}})
    refusal = RemoteMemoryClient._http_refusal(
        RemoteMemoryClient.__new__(RemoteMemoryClient), status, body.encode()
    )
    assert refusal.kind is kind
    assert refusal.http_status == status


@pytest.mark.parametrize("operation", sorted(REMOTE_BLOCKED_OPERATIONS))
def test_blocked_operations_send_nothing(operation: str) -> None:
    client = ScriptedClient(iter([]))
    with pytest.raises(RemoteMemoryError) as caught:
        client.call(operation, {"namespace": "repo-a", "path": "/etc/passwd"})
    assert caught.value.kind is RemoteFailureKind.UNSUPPORTED_REMOTELY
    assert "administrator" in str(caught.value)
    assert client.sent == []


def test_only_lifecycle_and_agent_write_tools_are_reachable() -> None:
    assert set(REMOTE_OPERATION_TOOLS.values()) == {
        "memory.health",
        "memory.capabilities",
        "memory.hydrate",
        "memory.search",
        "memory.get",
        "memory.ingest",
        "memory.ingest_governed_candidate",
        "memory.close",
        "memory.conflicts",
        "memory.phase_lock",
        "memory.verify_phase_lock",
        "memory.write_agent",
        "memory.write_governed",
    }
    client = ScriptedClient(iter([]))
    for operation in ("delete", "promote", "retention", "lineage", "graph.search"):
        with pytest.raises(RemoteMemoryError) as caught:
            client.call(operation, {})
        assert caught.value.kind is RemoteFailureKind.UNSUPPORTED_REMOTELY
    assert client.sent == []


def test_a_search_field_the_tool_lacks_is_refused_not_dropped() -> None:
    client = ScriptedClient(iter([]))
    request = MemorySearchRequest(query="x", namespaces=("repo-a",), token_budget=256)
    with pytest.raises(RemoteMemoryError) as caught:
        client.search(request)
    assert caught.value.kind is RemoteFailureKind.INVALID_REQUEST
    assert client.sent == []


def test_a_nonpositive_timeout_is_a_configuration_failure() -> None:
    held = credentials()
    with pytest.raises(RemoteMemoryError):
        RemoteMemoryClient("https://memory.example", held, timeout_seconds=0)
