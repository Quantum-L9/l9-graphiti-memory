"""A KeyError from a tool is a missing argument only when the caller left one out.

The JSON-RPC layer maps a tool KeyError to -32602 "invalid params: missing
<key>". A KeyError raised by server code (a stored payload, an internal table)
is a server fault: it must surface as -32603 and never blame the caller.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.mcp_tools import MCPToolApplication
from l9_graphite_memory.server import MCPServer
from l9_graphite_memory.services import MemoryService

PRINCIPAL = MemoryPrincipal(
    principal_id="agent",
    tenant_id="tenant",
    auth_method="signed-agent",
    write_namespaces=("repo",),
)


def _broken_service() -> MemoryService:
    service = MemoryService(InMemoryRecordStore(), NullProjection())

    def broken_health(*_args: Any, **_kwargs: Any) -> Any:
        internal: dict[str, str] = {"status": "ok"}
        return internal["state"]

    service.health = broken_health  # type: ignore[method-assign]
    return service


def _call(server: MCPServer, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        PRINCIPAL,
    )
    assert response is not None
    return response


def test_an_internal_key_error_is_an_internal_error_not_a_missing_argument() -> None:
    server = MCPServer(SimpleNamespace(service=_broken_service(), graph_service=None))  # type: ignore[arg-type]
    error = _call(server, "memory.health", {})["error"]
    assert error["code"] == -32603
    assert "missing" not in error["message"]


def test_an_internal_key_error_does_not_escape_as_a_key_error() -> None:
    tools = MCPToolApplication(_broken_service())
    with pytest.raises(RuntimeError, match="internal error in memory.health"):
        tools.call(PRINCIPAL, "memory.health", {})


def test_a_missing_declared_argument_is_still_invalid_params() -> None:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    server = MCPServer(SimpleNamespace(service=service, graph_service=None))  # type: ignore[arg-type]
    error = _call(server, "memory.write_agent", {"content": "no namespace"})["error"]
    assert error == {"code": -32602, "message": "invalid params: missing namespace"}
