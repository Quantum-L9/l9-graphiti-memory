# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_http_mcp_request_injection.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-07-28

"""Regression: the HTTP /mcp route must consume the JSON-RPC request body.

Under `from __future__ import annotations`, the route handler's `request:
Request` annotation is a string. If `Request`/`JSONResponse` are imported only
inside create_http_app(), FastAPI cannot resolve the annotation, treats
`request` as a required query parameter, and every POST /mcp returns 422 --
breaking the shared HTTP memory backend. These tests fail on that regression.
"""

from __future__ import annotations

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.config import MemorySettings, TokenPrincipalConfig
from l9_graphite_memory.runtime import MemoryRuntime
from l9_graphite_memory.server import create_http_app
from l9_graphite_memory.services import MemoryService

pytest.importorskip("fastapi", reason="HTTP transport requires the [server] extra")
pytest.importorskip("httpx", reason="fastapi TestClient requires httpx")


@pytest.fixture
def runtime() -> MemoryRuntime:
    service = MemoryService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    settings = MemorySettings(
        http_auth_required=True,
        auth_tokens={
            "test-token": TokenPrincipalConfig(
                principal_id="http-regression-client",
                tenant_id="tenant-a",
                read_namespaces=("l9-coding-memory",),
                write_namespaces=("l9-coding-memory",),
                promote_namespaces=(),
                is_admin=False,
            )
        },
    )
    return MemoryRuntime(settings=settings, service=service)


def test_http_mcp_initialize_uses_request_body(runtime: MemoryRuntime) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_http_app(runtime))
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer test-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "http-regression-test", "version": "1"},
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert "result" in body


def test_http_mcp_missing_token_returns_401_not_422(runtime: MemoryRuntime) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_http_app(runtime))
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    # The critical assertion: authentication is evaluated (401), the request is
    # not rejected by FastAPI query validation (422).
    assert response.status_code == 401, response.text
