# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/server.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""MCP server adapter over the canonical MemoryService."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Import the HTTP request/response types at module scope so that, under
# `from __future__ import annotations`, FastAPI can resolve the postponed
# string annotations (`request: Request`, `-> JSONResponse`) on the route
# handlers. When these types are imported only inside create_http_app(), they
# are absent from this module's globals and FastAPI misreads `request` as a
# required query parameter, making every POST /mcp return 422. Starlette is a
# hard dependency of FastAPI, so it is present whenever the [server] extra is.
try:
    from starlette.requests import Request
    from starlette.responses import JSONResponse
except ModuleNotFoundError:  # [server] extra not installed; create_http_app() will error
    Request = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]

from l9_graphite_memory.authz import TokenAuthenticator
from l9_graphite_memory.authz.signed_assertion import verify_assertion
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.errors import (
    AuthenticationError,
    ConfigurationError,
    L9MemoryError,
)
from l9_graphite_memory.mcp_tools import MCPToolApplication, tool_definitions
from l9_graphite_memory.observability import configure_logging, get_logger
from l9_graphite_memory.runtime import (
    MemoryRuntime,
    build_runtime,
    resolve_local_context,
    resolve_local_context_for_namespace,
)
from l9_graphite_memory.secrets import load_secrets_sync
from l9_graphite_memory.version import MCP_PROTOCOL_VERSION, PACKAGE_VERSION

log = get_logger("l9.memory.mcp")
JSONRPC_VERSION = "2.0"
SERVER_INFO = {
    "name": "l9-graphite-memory",
    "version": PACKAGE_VERSION,
    "description": "Contract-governed bi-temporal memory service",
}
CAPABILITIES = {"tools": {"listChanged": False}}


class MCPServer:
    def __init__(self, runtime: MemoryRuntime) -> None:
        self.runtime = runtime
        self.tools = MCPToolApplication(runtime.service)

    @staticmethod
    def response(request_id: Any, result: Any) -> dict[str, Any]:
        if hasattr(result, "model_dump"):
            result = result.model_dump(mode="json")
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}

    @staticmethod
    def error(
        request_id: Any, code: int, message: str, *, data: Any | None = None
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}

    def handle(self, request: dict[str, Any], principal: MemoryPrincipal) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "params must be an object")
        if method == "initialize":
            return self.response(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": CAPABILITIES,
                    "serverInfo": SERVER_INFO,
                },
            )
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return self.response(request_id, {"tools": tool_definitions()})
        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not name:
                return self.error(request_id, -32602, "tool name is required")
            if not isinstance(arguments, dict):
                return self.error(request_id, -32602, "tool arguments must be an object")
            try:
                result = self.tools.call(principal, name, arguments)
            except KeyError as exc:
                return self.error(request_id, -32601, str(exc))
            except AuthenticationError as exc:
                return self.error(request_id, -32001, str(exc))
            except L9MemoryError as exc:
                return self.error(request_id, -32010, str(exc), data={"type": type(exc).__name__})
            except (ValueError, TypeError) as exc:
                return self.error(request_id, -32602, str(exc))
            except Exception as exc:
                log.exception("unhandled tool failure", extra={"tool": name})
                return self.error(
                    request_id,
                    -32603,
                    "internal error",
                    data={"type": type(exc).__name__},
                )
            return self.response(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                result.model_dump(mode="json")
                                if hasattr(result, "model_dump")
                                else result,
                                indent=2,
                                default=str,
                            ),
                        }
                    ]
                },
            )
        if method == "ping":
            return self.response(request_id, {})
        return self.error(request_id, -32601, f"method not found: {method}")


def _door_principal(settings: MemorySettings) -> MemoryPrincipal | None:
    """The principal from a configured door, or ``None`` to fall through.

    Tier 1 — Human door (admin):
        ``L9_MEMORY_HUMAN_DOOR_SECRET`` is set and its value is non-empty.
        The caller is granted admin authority (agent_id=``human``).

    Tier 2 — Agent assertion door:
        ``L9_MEMORY_AGENTS_DOOR_SECRET`` is set (non-empty).
        ``L9_MEMORY_AGENT_ASSERTION`` must be present and must verify against
        a key in ``L9_MEMORY_AGENT_SIGNING_KEYS_JSON``.
        Grants come from ``L9_MEMORY_AGENT_GRANTS_JSON``.

    Both tiers read their claims from the environment, so they are resolved
    once and do not vary per request. ``None`` means Tier 3 — the local
    operator fallback, whose claims come from repository identity and are
    therefore resolved per request by :class:`StdioPrincipalResolver`.
    """
    human_secret = os.environ.get("L9_MEMORY_HUMAN_DOOR_SECRET", "").strip()
    if human_secret:
        return MemoryPrincipal(
            principal_id="human",
            tenant_id=settings.local_tenant_id,
            organization_id=settings.local_organization_id,
            workspace_id=settings.local_workspace_id,
            user_id=settings.local_user_id or "human",
            agent_id="human",
            roles=("admin", "local-operator"),
            read_namespaces=("*",),
            write_namespaces=("*",),
            promote_namespaces=("*",),
            is_admin=True,
            auth_method="stdio-human-door",
        )

    agents_door_secret = os.environ.get("L9_MEMORY_AGENTS_DOOR_SECRET", "").strip()
    if agents_door_secret:
        assertion = os.environ.get("L9_MEMORY_AGENT_ASSERTION", "").strip()
        if not assertion:
            raise AuthenticationError(
                "L9_MEMORY_AGENTS_DOOR_SECRET is set but L9_MEMORY_AGENT_ASSERTION is missing"
            )

        raw_keys = os.environ.get("L9_MEMORY_AGENT_SIGNING_KEYS_JSON", "").strip()
        if not raw_keys:
            raise AuthenticationError(
                "L9_MEMORY_AGENTS_DOOR_SECRET is set but L9_MEMORY_AGENT_SIGNING_KEYS_JSON is missing"
            )
        try:
            keys_by_agent_id: dict[str, str] = json.loads(raw_keys)
        except json.JSONDecodeError as exc:
            raise AuthenticationError(
                f"L9_MEMORY_AGENT_SIGNING_KEYS_JSON is not valid JSON: {exc}"
            ) from exc
        if not isinstance(keys_by_agent_id, dict):
            raise AuthenticationError("L9_MEMORY_AGENT_SIGNING_KEYS_JSON must be a JSON object")

        agent_id = verify_assertion(assertion, keys_by_agent_id)

        raw_grants = os.environ.get("L9_MEMORY_AGENT_GRANTS_JSON", "").strip()
        if not raw_grants:
            raise AuthenticationError(
                "L9_MEMORY_AGENTS_DOOR_SECRET is set but L9_MEMORY_AGENT_GRANTS_JSON is missing"
            )
        try:
            grants_map: dict[str, dict] = json.loads(raw_grants)
        except json.JSONDecodeError as exc:
            raise AuthenticationError(
                f"L9_MEMORY_AGENT_GRANTS_JSON is not valid JSON: {exc}"
            ) from exc
        if not isinstance(grants_map, dict):
            raise AuthenticationError("L9_MEMORY_AGENT_GRANTS_JSON must be a JSON object")

        grants = grants_map.get(agent_id)
        if not grants or not isinstance(grants, dict):
            raise AuthenticationError(
                f"no grants configured for agent_id={agent_id!r} in L9_MEMORY_AGENT_GRANTS_JSON"
            )

        def _ns(field: str) -> tuple[str, ...]:
            raw = grants.get(field, [])
            return tuple(str(v) for v in raw) if isinstance(raw, list) else ()

        return MemoryPrincipal(
            principal_id=str(grants.get("principal_id", agent_id)),
            tenant_id=settings.local_tenant_id,
            organization_id=settings.local_organization_id,
            workspace_id=settings.local_workspace_id,
            user_id=str(grants["user_id"]) if grants.get("user_id") else None,
            agent_id=agent_id,
            roles=tuple(str(r) for r in grants.get("roles", [])),
            read_namespaces=_ns("read_namespaces"),
            write_namespaces=_ns("write_namespaces"),
            promote_namespaces=_ns("promote_namespaces"),
            is_admin=bool(grants.get("is_admin", False)),
            auth_method="stdio-agent-assertion",
        )

    return None


def _stdio_principal(settings: MemorySettings) -> MemoryPrincipal:
    """The stdio principal with no request in hand (Tier 3 resolves from cwd).

    Kept as the module's stable entry point. A transport serving requests
    should use :class:`StdioPrincipalResolver`, which resolves Tier 3 against
    the namespace each request names.
    """

    principal = _door_principal(settings)
    if principal is not None:
        return principal
    _, local = resolve_local_context(settings)
    return local.model_copy(update={"auth_method": "stdio-local"})


def _requested_namespace(request: dict[str, Any]) -> str | None:
    """The namespace a ``tools/call`` request addresses, if it names one."""

    if request.get("method") != "tools/call":
        return None
    params = request.get("params")
    if not isinstance(params, dict):
        return None
    arguments = params.get("arguments")
    if not isinstance(arguments, dict):
        return None
    namespace = arguments.get("namespace")
    return namespace if isinstance(namespace, str) else None


class StdioPrincipalResolver:
    """Resolve the principal for each request on a local transport.

    Tiers 1 and 2 are static for the life of the process: their claims come
    from the environment, are verified once, and do not depend on which
    namespace a request addresses. Tier 3 derives its claims from *repository
    identity*, which is a property of the namespace being addressed — so it is
    resolved per request.

    Resolving it once at spawn is what made ``memory.write_agent``'s
    ``namespace`` argument unusable for every root except the one the host
    launched the server in, while the operator CLI — which resolves per
    ``--workspace`` invocation — could address them all. The governed lane
    could not reach what the fallback could.
    """

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        # Verified eagerly: a misconfigured door must fail at startup rather
        # than on the first request that happens to need it.
        self._door = _door_principal(settings)

    @property
    def door_principal(self) -> MemoryPrincipal | None:
        """The static Tier 1/Tier 2 principal, or ``None`` when on Tier 3."""

        return self._door

    def for_request(self, request: dict[str, Any]) -> MemoryPrincipal:
        if self._door is not None:
            return self._door
        _, principal = resolve_local_context_for_namespace(
            self._settings, _requested_namespace(request)
        )
        return principal.model_copy(update={"auth_method": "stdio-local"})


def _write_json_line(obj: Any) -> None:
    """Write a JSON-RPC response line to stdout."""
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def run_stdio(runtime: MemoryRuntime) -> int:
    server = MCPServer(runtime)
    principals = StdioPrincipalResolver(runtime.settings)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as exc:
            _write_json_line(server.error(None, -32700, f"parse error: {exc}"))
            continue
        if not isinstance(decoded, dict):
            _write_json_line(server.error(None, -32600, "batch requests are not supported"))
            continue
        try:
            principal = principals.for_request(decoded)
        except AuthenticationError as exc:
            _write_json_line(server.error(decoded.get("id"), -32001, str(exc)))
            continue
        response = server.handle(decoded, principal)
        if response is not None:
            _write_json_line(response)
    return 0


def create_http_app(runtime: MemoryRuntime) -> Any:
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError(
            "HTTP server dependencies missing; install l9-graphite-memory[server]"
        ) from exc

    settings = runtime.settings
    authenticator = TokenAuthenticator(settings.auth_tokens)
    server = MCPServer(runtime)
    principals = StdioPrincipalResolver(settings)
    app = FastAPI(title="L9 Graphite Memory", version=PACKAGE_VERSION)

    def principal_for(request: Request, body: dict[str, Any]) -> MemoryPrincipal:
        if settings.http_auth_required:
            return authenticator.authenticate(request.headers.get("Authorization"))
        # Auth-disabled HTTP is the same local trust model as stdio, so it
        # resolves per request against the namespace the body names too.
        return principals.for_request(body).model_copy(update={"auth_method": "http-auth-disabled"})

    @app.post("/mcp")
    @app.post("/mcp/")
    async def mcp_endpoint(request: Request) -> JSONResponse:
        # The body is parsed first because the principal now depends on the
        # namespace the request names.
        try:
            body = await request.json()
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                status_code=400,
                content=server.error(None, -32700, f"invalid JSON: {exc}"),
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400,
                content=server.error(None, -32600, "batch requests are not supported"),
            )
        try:
            principal = principal_for(request, body)
        except AuthenticationError as exc:
            return JSONResponse(status_code=401, content=server.error(None, -32001, str(exc)))
        response = server.handle(body, principal)
        return JSONResponse(content=response or {"status": "ok"})

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        report = runtime.service.health()
        code = 200 if report.status.value != "failed" else 503
        return JSONResponse(status_code=code, content=report.model_dump(mode="json"))

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        report = runtime.service.health()
        code = 200 if report.status.value == "complete" else 503
        return JSONResponse(status_code=code, content=report.model_dump(mode="json"))

    return app


def run_http(runtime: MemoryRuntime, *, host: str, port: int) -> int:
    if runtime.settings.http_auth_required and not runtime.settings.auth_tokens:
        raise ConfigurationError(
            "HTTP authentication is required but no L9_MEMORY_AUTH_TOKENS_JSON or file is configured"
        )
    if not runtime.settings.http_auth_required and host not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ConfigurationError("authentication may only be disabled on a loopback bind address")
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is missing; install l9-graphite-memory[server]") from exc
    uvicorn.run(
        create_http_app(runtime),
        host=host,
        port=port,
        log_level=runtime.settings.log_level.lower(),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L9 Graphite Memory MCP server")
    parser.add_argument("--transport", choices=["stdio", "http", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    load_secrets_sync()
    runtime = build_runtime(args.config)
    configure_logging(runtime.settings.log_level, json_output=runtime.settings.json_logs)
    try:
        if args.transport == "stdio":
            return run_stdio(runtime)
        if args.transport == "sse":
            log.warning(
                "transport name 'sse' is retained as an HTTP compatibility alias; use --transport http"
            )
        return run_http(runtime, host=args.host, port=args.port)
    finally:
        runtime.close()


if __name__ == "__main__":
    raise SystemExit(main())
