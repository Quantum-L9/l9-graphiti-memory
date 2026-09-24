# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_stdio_namespace_resolution.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-09-24

"""A request's namespace is an address, never a grant (ADR-006, ADR-083).

The local transport serves every request under a principal whose claims were
established before the request was read: the human door, the signed agent
door, or the Tier 3 fallback resolved from the process's repository and any
operator-configured ``local_*_namespaces``. A tools/call naming a registered
repository must not manufacture read, write, promote or maintain authority
for it (audit finding F-64-AUTHZ-001), on stdio or on auth-disabled HTTP.
Multi-root writes go through the signed Tier 2 grant map, which these tests
also prove still works end to end.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.authz.signed_assertion import mint_assertion
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.mcp_tools import MCPToolApplication
from l9_graphite_memory.runtime import MemoryRuntime, resolve_local_context
from l9_graphite_memory.server import (
    StdioPrincipalResolver,
    _stdio_principal,
    create_http_app,
)
from l9_graphite_memory.services import MemoryService

# Registered repositories in the packaged registry.
HOME_REPO = "l9-graphiti-memory"
OTHER_REPO = "cursor-governance"
THIRD_REPO = "cognitive-engine-graphs"


def _tools_call(namespace: str | None) -> dict[str, Any]:
    arguments: dict[str, Any] = {"content": "a durable fact"}
    if namespace is not None:
        arguments["namespace"] = namespace
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "memory.write_agent", "arguments": arguments},
    }


def _service() -> MemoryService:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    return service


def _write_allowed(principal: MemoryPrincipal, namespace: str) -> bool:
    receipt = MCPToolApplication(_service()).call(
        principal,
        "memory.write_agent",
        {"namespace": namespace, "content": f"a durable fact about {namespace}"},
    )
    admitted = receipt.record_id is not None
    assert admitted is receipt.authorization.allowed
    return admitted


def _granted(principal: MemoryPrincipal, namespace: str) -> dict[str, bool]:
    return {
        "read": namespace in principal.read_namespaces,
        "write": namespace in principal.write_namespaces,
        "promote": namespace in principal.promote_namespaces,
        "maintain": namespace in principal.maintain_namespaces,
    }


@pytest.fixture(autouse=True)
def _no_doors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force Tier 3. Tiers 1 and 2 read the environment, not the filesystem."""

    for name in (
        "L9_MEMORY_HUMAN_DOOR_SECRET",
        "L9_MEMORY_AGENTS_DOOR_SECRET",
        "L9_MEMORY_AGENT_ASSERTION",
        "L9_MEMORY_AGENT_SIGNING_KEYS_JSON",
        "L9_MEMORY_AGENT_GRANTS_JSON",
        "L9_MEMORY_NAMESPACE",
        "GRAPHITI_GROUP_ID",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def unresolvable_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A directory matching no registered repository: Tier 3 writes nothing."""

    monkeypatch.chdir(tmp_path)
    assert resolve_local_context(MemorySettings())[1].write_namespaces == ()
    return tmp_path


@pytest.fixture
def home_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A directory the registry resolves to HOME_REPO by path hint."""

    home = tmp_path / HOME_REPO
    home.mkdir()
    monkeypatch.chdir(home)
    assert resolve_local_context(MemorySettings())[1].write_namespaces == (HOME_REPO,)
    return home


# ---------------------------------------------------------------------------
# Tier 3: a registered namespace in the request widens nothing
# ---------------------------------------------------------------------------


def test_registered_namespace_request_does_not_widen_unconfigured_tier3(
    unresolvable_cwd: Path,
) -> None:
    resolver = StdioPrincipalResolver(MemorySettings())

    principal = resolver.for_request(_tools_call(OTHER_REPO))

    assert principal.auth_method == "stdio-local"
    assert _granted(principal, OTHER_REPO) == {
        "read": False,
        "write": False,
        "promote": False,
        "maintain": False,
    }
    assert principal.is_admin is False
    assert _write_allowed(principal, OTHER_REPO) is False


def test_tier3_principal_is_independent_of_the_request(home_cwd: Path) -> None:
    resolver = StdioPrincipalResolver(MemorySettings())

    principals = [
        resolver.for_request(_tools_call(namespace))
        for namespace in (None, HOME_REPO, OTHER_REPO, THIRD_REPO, "not-registered", "main")
    ]

    assert all(principal == principals[0] for principal in principals)
    assert principals[0] == resolver.principal == _stdio_principal(MemorySettings())


def test_tier3_stays_repository_scoped(home_cwd: Path) -> None:
    principal = StdioPrincipalResolver(MemorySettings()).for_request(_tools_call(OTHER_REPO))

    assert principal.write_namespaces == (HOME_REPO,)
    assert principal.promote_namespaces == (HOME_REPO,)
    assert principal.maintain_namespaces == (HOME_REPO,)
    assert _write_allowed(principal, HOME_REPO) is True
    assert _write_allowed(principal, OTHER_REPO) is False


def test_registered_namespace_request_does_not_widen_promote_or_maintain(
    home_cwd: Path,
) -> None:
    principal = StdioPrincipalResolver(MemorySettings()).for_request(_tools_call(OTHER_REPO))

    for namespace in (OTHER_REPO, THIRD_REPO):
        granted = _granted(principal, namespace)
        assert granted["promote"] is False
        assert granted["maintain"] is False


@pytest.mark.parametrize("namespace", ["main", "default", "test", "not-a-registered-repository"])
def test_forbidden_and_unregistered_namespaces_are_refused(namespace: str, home_cwd: Path) -> None:
    principal = StdioPrincipalResolver(MemorySettings()).for_request(_tools_call(namespace))

    assert namespace not in principal.write_namespaces
    assert _write_allowed(principal, namespace) is False


# ---------------------------------------------------------------------------
# Tier 3 with an operator-configured ACL: the ACL is the ceiling
# ---------------------------------------------------------------------------


def test_explicit_local_acl_allows_only_its_configured_namespaces(
    unresolvable_cwd: Path,
) -> None:
    settings = MemorySettings(
        local_read_namespaces=(HOME_REPO, OTHER_REPO),
        local_write_namespaces=(HOME_REPO, OTHER_REPO),
    )
    resolver = StdioPrincipalResolver(settings)

    principal = resolver.for_request(_tools_call(THIRD_REPO))

    assert principal.write_namespaces == (HOME_REPO, OTHER_REPO)
    assert principal.promote_namespaces == ()
    assert principal.maintain_namespaces == ()
    assert _write_allowed(principal, HOME_REPO) is True
    assert _write_allowed(principal, OTHER_REPO) is True
    assert _write_allowed(principal, THIRD_REPO) is False


def test_explicit_local_acl_is_not_widened_by_a_request(home_cwd: Path) -> None:
    settings = MemorySettings(
        local_read_namespaces=(HOME_REPO,),
        local_write_namespaces=(HOME_REPO,),
    )

    principal = StdioPrincipalResolver(settings).for_request(_tools_call(OTHER_REPO))

    assert principal.write_namespaces == (HOME_REPO,)
    assert _write_allowed(principal, OTHER_REPO) is False


# ---------------------------------------------------------------------------
# auth-disabled HTTP: never wider than stdio
# ---------------------------------------------------------------------------


def _post_mcp(app: Any, body: dict[str, Any]) -> dict[str, Any]:
    """Drive the /mcp route in-process; no HTTP client dependency needed."""

    from starlette.requests import Request

    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/mcp" and "POST" in getattr(route, "methods", ())
    )
    payload = json.dumps(body).encode()
    delivered = False

    async def receive() -> dict[str, Any]:
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": payload, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }
    response = asyncio.run(endpoint(Request(scope, receive)))
    return dict(json.loads(response.body))


def _http_write(runtime: MemoryRuntime, namespace: str) -> dict[str, Any]:
    reply = _post_mcp(create_http_app(runtime), _tools_call(namespace))
    assert "result" in reply, reply
    return dict(json.loads(reply["result"]["content"][0]["text"]))


def test_auth_disabled_http_does_not_widen_on_a_registered_namespace(home_cwd: Path) -> None:
    pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
    runtime = MemoryRuntime(settings=MemorySettings(http_auth_required=False), service=_service())

    denied = _http_write(runtime, OTHER_REPO)
    admitted = _http_write(runtime, HOME_REPO)

    assert denied["record_id"] is None
    assert denied["authorization"]["allowed"] is False
    assert "auth_method=http-auth-disabled" in denied["authorization"]["reasons"][0]
    assert admitted["record_id"] is not None


def test_auth_disabled_http_matches_the_stdio_principal(home_cwd: Path) -> None:
    pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
    settings = MemorySettings(http_auth_required=False)
    runtime = MemoryRuntime(settings=settings, service=_service())
    stdio = StdioPrincipalResolver(settings).principal

    for namespace in (HOME_REPO, OTHER_REPO, THIRD_REPO):
        receipt = _http_write(runtime, namespace)
        assert (receipt["record_id"] is not None) is (namespace in stdio.write_namespaces)


# ---------------------------------------------------------------------------
# Tier 2: the canonical multi-root path
# ---------------------------------------------------------------------------


@pytest.fixture
def signed_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_id, key = "claude-code-desktop", "agent-signing-key"
    monkeypatch.setenv("L9_MEMORY_AGENTS_DOOR_SECRET", "open-sesame")
    monkeypatch.setenv("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", json.dumps({agent_id: key}))
    monkeypatch.setenv("L9_MEMORY_AGENT_ASSERTION", mint_assertion(agent_id, key))
    monkeypatch.setenv(
        "L9_MEMORY_AGENT_GRANTS_JSON",
        json.dumps(
            {
                agent_id: {
                    "read_namespaces": [HOME_REPO, OTHER_REPO],
                    "write_namespaces": [HOME_REPO, OTHER_REPO],
                }
            }
        ),
    )


def test_signed_tier2_writes_every_namespace_in_its_grant_map(
    signed_agent: None, unresolvable_cwd: Path
) -> None:
    resolver = StdioPrincipalResolver(MemorySettings())

    principal = resolver.for_request(_tools_call(OTHER_REPO))

    assert principal.auth_method == "stdio-agent-assertion"
    assert principal.write_namespaces == (HOME_REPO, OTHER_REPO)
    assert _write_allowed(principal, HOME_REPO) is True
    assert _write_allowed(principal, OTHER_REPO) is True
    assert _write_allowed(principal, THIRD_REPO) is False


def test_signed_tier2_is_static_across_requests(signed_agent: None, home_cwd: Path) -> None:
    resolver = StdioPrincipalResolver(MemorySettings())

    assert resolver.door_principal is not None
    first = resolver.for_request(_tools_call(HOME_REPO))
    second = resolver.for_request(_tools_call(THIRD_REPO))
    assert first == second == resolver.door_principal
    assert THIRD_REPO not in first.write_namespaces


def test_human_door_principal_is_static_across_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("L9_MEMORY_HUMAN_DOOR_SECRET", "hunter2")
    resolver = StdioPrincipalResolver(MemorySettings())

    assert resolver.door_principal is not None
    first = resolver.for_request(_tools_call(HOME_REPO))
    second = resolver.for_request(_tools_call(OTHER_REPO))
    assert first == second
    assert first.auth_method == "stdio-human-door"
