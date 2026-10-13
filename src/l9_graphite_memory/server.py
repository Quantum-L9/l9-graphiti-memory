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
    from starlette.responses import JSONResponse, Response
except ModuleNotFoundError:  # [server] extra not installed; create_http_app() will error
    Request = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]
    Response = None  # type: ignore[assignment,misc]

from l9_graphite_memory.authz import TokenAuthenticator
from l9_graphite_memory.authz.remote_agent import (
    IDENTITY_ASSERTION_HEADER,
    IDENTITY_ASSERTION_HMAC_HEADER,
    SignedAgentAuthenticator,
)
from l9_graphite_memory.authz.signed_assertion import (
    agent_grant_from_config,
    agent_principal,
    signing_keys_from_config,
    verify_assertion,
    verify_canonical_identity_assertion,
)
from l9_graphite_memory.authz.signed_assertion import (
    decode_json_object as _json_object,
)
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
)
from l9_graphite_memory.secrets import load_secrets_sync
from l9_graphite_memory.version import (
    HTTP_MCP_PROTOCOL_VERSIONS,
    MCP_PROTOCOL_VERSION,
    PACKAGE_VERSION,
)

log = get_logger("l9.memory.mcp")
JSONRPC_VERSION = "2.0"
SERVER_INFO = {
    "name": "l9-graphite-memory",
    "version": PACKAGE_VERSION,
    "description": "Contract-governed bi-temporal memory service",
}
CAPABILITIES = {"tools": {"listChanged": False}}


class MCPServer:
    """JSON-RPC dispatch shared by every MCP transport.

    ``protocol_versions`` is the transport's supported set, newest first.
    ``initialize`` echoes a requested version the set contains and otherwise
    answers with the newest. The stdio default is the single
    :data:`MCP_PROTOCOL_VERSION`, so stdio keeps answering exactly as it did.
    """

    def __init__(
        self,
        runtime: MemoryRuntime,
        *,
        protocol_versions: tuple[str, ...] = (MCP_PROTOCOL_VERSION,),
    ) -> None:
        if not protocol_versions:
            raise ValueError("an MCP transport must support at least one protocol version")
        self.runtime = runtime
        self.protocol_versions = protocol_versions
        self.tools = MCPToolApplication(runtime.service, runtime.graph_service)

    def negotiate(self, requested: Any) -> str:
        """The revision answered for a requested one (MCP lifecycle negotiation)."""

        if isinstance(requested, str) and requested in self.protocol_versions:
            return requested
        return self.protocol_versions[0]

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
                    "protocolVersion": self.negotiate(params.get("protocolVersion")),
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


def _agents_door_env(name: str) -> str:
    """A variable the agents door requires once its secret is set."""

    value = os.environ.get(name, "").strip()
    if not value:
        raise AuthenticationError(f"L9_MEMORY_AGENTS_DOOR_SECRET is set but {name} is missing")
    return value


def _human_door_principal(settings: MemorySettings) -> MemoryPrincipal | None:
    """Tier 1 — ``L9_MEMORY_HUMAN_DOOR_SECRET`` set and non-empty grants admin."""

    if not os.environ.get("L9_MEMORY_HUMAN_DOOR_SECRET", "").strip():
        return None
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


def _agent_door_principal(settings: MemorySettings) -> MemoryPrincipal | None:
    """Tier 2 — a signed agent assertion verified against a configured key.

    ``L9_MEMORY_AGENTS_DOOR_SECRET`` being set makes every other variable
    mandatory, including the canonical identity assertion and its HMAC. A
    half-configured door fails loudly rather than falling through to the
    weaker local fallback, which would be a silent downgrade of the trust
    model.

    Order: verify the signed-agent token, then the canonical identity
    assertion against that agent's key, then load the grant. The identity
    assertion is evidence that the actor resolution matches the authenticated
    agent id. It does not grant roles or namespaces.
    """

    if not os.environ.get("L9_MEMORY_AGENTS_DOOR_SECRET", "").strip():
        return None

    assertion = _agents_door_env("L9_MEMORY_AGENT_ASSERTION")
    # Key material is typed before any assertion is checked against it: hmac
    # raises TypeError for a non-string key, which is not an authentication
    # outcome and would leave the door as an unhandled error.
    keys_by_agent_id = signing_keys_from_config(
        _json_object(
            _agents_door_env("L9_MEMORY_AGENT_SIGNING_KEYS_JSON"),
            "L9_MEMORY_AGENT_SIGNING_KEYS_JSON",
        )
    )
    agent_id = verify_assertion(assertion, keys_by_agent_id)
    verify_canonical_identity_assertion(
        _json_object(
            _agents_door_env("L9_MEMORY_IDENTITY_ASSERTION_JSON"),
            "L9_MEMORY_IDENTITY_ASSERTION_JSON",
        ),
        supplied_hmac=_agents_door_env("L9_MEMORY_IDENTITY_ASSERTION_HMAC"),
        agent_id=agent_id,
        signing_key=keys_by_agent_id[agent_id],
    )

    grants_map = _json_object(
        _agents_door_env("L9_MEMORY_AGENT_GRANTS_JSON"),
        "L9_MEMORY_AGENT_GRANTS_JSON",
    )
    # Typed at the trust boundary rather than coerced. Every claim below is now
    # a validated field: `is_admin` can only become True from a real boolean,
    # where `bool(grants.get("is_admin"))` made the string "false" an
    # administrator, and a malformed namespace or roles value is an error
    # instead of a silently empty grant.
    grant = agent_grant_from_config(agent_id, grants_map.get(agent_id))

    return agent_principal(settings, agent_id, grant, auth_method="stdio-agent-assertion")


def _door_principal(settings: MemorySettings) -> MemoryPrincipal | None:
    """The principal from a configured door, or ``None`` to fall through.

    Tier 1 is the human door, Tier 2 the signed agent door; each is a function
    above, because one body doing environment parsing, JSON decoding,
    signature verification and grant construction for two trust tiers is hard
    to read in exactly the place where reading it matters most.

    Both tiers read their claims from the environment, so they are resolved
    once and do not vary per request. ``None`` means Tier 3 — the local
    operator fallback, whose claims come from repository identity and are
    resolved once, server-side, by :class:`StdioPrincipalResolver`.
    """

    return _human_door_principal(settings) or _agent_door_principal(settings)


def _stdio_principal(settings: MemorySettings) -> MemoryPrincipal:
    """The stdio principal: a door principal, else the Tier 3 cwd principal.

    Every claim is established server-side, from the environment (Tiers 1/2)
    or from the repository the process runs in plus any operator-configured
    ``local_*_namespaces`` (Tier 3). No request data is consulted (ADR-006).
    """

    principal = _door_principal(settings)
    if principal is not None:
        return principal
    _, local = resolve_local_context(settings)
    return local.model_copy(update={"auth_method": "stdio-local"})


class StdioPrincipalResolver:
    """Resolve the principal a local transport serves every request under.

    Claims are fixed before the first request is read. Tiers 1 and 2 come from
    the environment and are verified eagerly, so a misconfigured door fails at
    startup. Tier 3 comes from the process's repository identity (cwd) or the
    operator-configured ``local_*_namespaces`` ceiling.

    ``for_request`` deliberately ignores the request. A requested namespace is
    an address that MemoryService checks against these claims; it must never
    produce the claim it is checked against (ADR-006, ADR-083). A registered
    repository slug is a namespace hint and grants nothing. Multi-root agent
    writes use the signed Tier 2 grant map; a multi-root local operator lists
    its roots in ``local_*_namespaces``.
    """

    def __init__(self, settings: MemorySettings) -> None:
        self._settings = settings
        self._door = _door_principal(settings)
        self._principal = self._door or _stdio_principal(settings)

    @property
    def door_principal(self) -> MemoryPrincipal | None:
        """The static Tier 1/Tier 2 principal, or ``None`` when on Tier 3."""

        return self._door

    @property
    def principal(self) -> MemoryPrincipal:
        """The one principal every request on this transport is served under."""

        return self._principal

    def for_request(self, request: dict[str, Any]) -> MemoryPrincipal:
        del request  # authority is never derived from request data
        return self._principal


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


# --- Streamable HTTP (ADR-098) ---------------------------------------------
# A stateless Streamable HTTP endpoint: one JSON-RPC message per POST, a JSON
# body for each request, 202 for each notification or client response, no
# server-initiated SSE stream and no MCP-Session-Id.

MCP_ENDPOINT_PATHS = ("/mcp", "/mcp/")
# What a server must assume when MCP-Protocol-Version is absent and nothing
# else identifies the revision. It is not in HTTP_MCP_PROTOCOL_VERSIONS, so
# such a request is refused with 400 instead of being served unversioned.
HTTP_ASSUMED_PROTOCOL_VERSION = "2025-03-26"
HTTP_MAX_BODY_BYTES = 4 * 1024 * 1024
WWW_AUTHENTICATE_REALM = 'Bearer realm="l9-graphite-memory"'
# Query parameters that look like credentials. The spec forbids tokens in the
# URI, so a request carrying one is refused before it is authenticated and is
# never echoed back.
CREDENTIAL_QUERY_PARAMETERS = frozenset(
    {
        "access_token",
        "token",
        "authorization",
        "assertion",
        "api_key",
        "apikey",
        "identity_assertion",
        "identity_assertion_hmac",
    }
)
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class _InvalidMessage(ValueError):
    """The POST body is JSON but not a valid single MCP JSON-RPC message."""


def _transport_error(
    status: int,
    code: int,
    message: str,
    *,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """An HTTP error whose body is a JSON-RPC error response without an ``id``."""

    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JSONResponse(
        status_code=status,
        content={"jsonrpc": JSONRPC_VERSION, "error": error},
        headers=headers,
    )


def _accepted_media_types(header: str | None) -> set[str]:
    """Media ranges an Accept header admits; a range with ``q=0`` is refused."""

    admitted: set[str] = set()
    for item in (header or "").split(","):
        media, *parameters = item.split(";")
        media = media.strip().lower()
        if not media:
            continue
        refused = False
        for parameter in parameters:
            name, _, value = parameter.partition("=")
            if name.strip().lower() == "q":
                try:
                    refused = float(value.strip()) <= 0
                except ValueError:
                    refused = True
        if not refused:
            admitted.add(media)
    return admitted


def _admits(admitted: set[str], media_type: str) -> bool:
    family = media_type.split("/", 1)[0]
    return bool(admitted & {media_type, f"{family}/*", "*/*"})


def _classify_message(message: dict[str, Any]) -> str:
    """``request``, ``notification`` or ``response``; raise for anything else."""

    if message.get("jsonrpc") != JSONRPC_VERSION:
        raise _InvalidMessage('jsonrpc must be "2.0"')
    has_id = "id" in message
    if has_id:
        message_id = message["id"]
        if isinstance(message_id, bool) or not isinstance(message_id, (str, int)):
            raise _InvalidMessage("id must be a string or an integer")
    if "method" in message:
        method = message["method"]
        if not isinstance(method, str) or not method:
            raise _InvalidMessage("method must be a non-empty string")
        if not has_id:
            return "notification"
        if method.startswith("notifications/"):
            raise _InvalidMessage("a notification must not carry an id")
        return "request"
    if has_id and (("result" in message) != ("error" in message)):
        return "response"
    raise _InvalidMessage("message is neither a request, a notification, nor a response")


def _origin_allowed(origin: str | None, allowed: tuple[str, ...]) -> bool:
    if origin is None:
        return True
    return origin.strip().rstrip("/").lower() in {
        item.strip().rstrip("/").lower() for item in allowed
    }


def create_http_app(runtime: MemoryRuntime) -> Any:
    try:
        from fastapi import FastAPI
    except ImportError as exc:
        raise RuntimeError(
            "HTTP server dependencies missing; install l9-graphite-memory[server]"
        ) from exc

    settings = runtime.settings
    if settings.http_auth_mode == "signed-agent" and not settings.http_auth_required:
        raise ConfigurationError(
            "http_auth_mode=signed-agent requires http_auth_required=true; "
            "an unauthenticated transport cannot establish an agent identity"
        )
    authenticator = TokenAuthenticator(settings.auth_tokens)
    # Signed-agent mode loads the agent key and grant registry once, so a
    # missing or malformed registry stops the server before it serves.
    agent_authenticator = (
        SignedAgentAuthenticator.from_environment(settings)
        if settings.http_auth_required and settings.http_auth_mode == "signed-agent"
        else None
    )
    server = MCPServer(runtime, protocol_versions=HTTP_MCP_PROTOCOL_VERSIONS)
    # Auth-disabled HTTP is the local trust model: exactly the stdio principal,
    # established server-side before any body is read. Never wider than stdio.
    local_principal = (
        None
        if settings.http_auth_required
        else StdioPrincipalResolver(settings).principal.model_copy(
            update={"auth_method": "http-auth-disabled"}
        )
    )
    app = FastAPI(title="L9 Graphite Memory", version=PACKAGE_VERSION)

    def principal_for(request: Request) -> MemoryPrincipal:
        """Authenticate this request on its own evidence; nothing carries over."""

        if local_principal is not None:
            return local_principal
        if agent_authenticator is not None:
            return agent_authenticator.authenticate(
                authorization=request.headers.get("Authorization"),
                identity_assertion=request.headers.get(IDENTITY_ASSERTION_HEADER),
                identity_assertion_hmac=request.headers.get(IDENTITY_ASSERTION_HMAC_HEADER),
            )
        return authenticator.authenticate(request.headers.get("Authorization"))

    def refuse_origin(request: Request) -> Any | None:
        if _origin_allowed(request.headers.get("Origin"), settings.http_allowed_origins):
            return None
        return _transport_error(403, -32600, "forbidden Origin")

    def protocol_refusal(request: Request, message: dict[str, Any], kind: str) -> Any | None:
        header = request.headers.get("MCP-Protocol-Version")
        if header is None and kind == "request" and message["method"] == "initialize":
            return None  # initialize negotiates the revision in its body
        requested = HTTP_ASSUMED_PROTOCOL_VERSION if header is None else header.strip()
        if requested in HTTP_MCP_PROTOCOL_VERSIONS:
            return None
        reason = (
            "MCP-Protocol-Version header is missing; assumed "
            f"{HTTP_ASSUMED_PROTOCOL_VERSION}, which this server does not support"
            if header is None
            else "unsupported MCP-Protocol-Version"
        )
        return _transport_error(
            400,
            -32600,
            reason,
            data={"supported": list(HTTP_MCP_PROTOCOL_VERSIONS), "requested": requested},
        )

    def method_not_allowed(request: Request) -> Any:
        refused = refuse_origin(request)
        if refused is not None:
            return refused
        # No standalone server-to-client SSE stream and no session to delete.
        return _transport_error(
            405, -32600, "method not allowed; use POST", headers={"Allow": "POST"}
        )

    async def mcp_endpoint(request: Request) -> Any:
        refused = refuse_origin(request)
        if refused is not None:
            return refused
        if CREDENTIAL_QUERY_PARAMETERS & {key.lower() for key in request.query_params}:
            return _transport_error(400, -32600, "credentials must not be sent in the URL")
        try:
            principal = principal_for(request)
        except AuthenticationError as exc:
            challenge = WWW_AUTHENTICATE_REALM
            if request.headers.get("Authorization"):
                challenge += ', error="invalid_token"'
            return _transport_error(401, -32001, str(exc), headers={"WWW-Authenticate": challenge})
        content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            return _transport_error(415, -32600, "Content-Type must be application/json")
        admitted = _accepted_media_types(request.headers.get("Accept"))
        if not (_admits(admitted, "application/json") and _admits(admitted, "text/event-stream")):
            return _transport_error(
                406, -32600, "Accept must list both application/json and text/event-stream"
            )
        declared_length = request.headers.get("Content-Length", "")
        if declared_length.isdigit() and int(declared_length) > HTTP_MAX_BODY_BYTES:
            return _transport_error(413, -32600, "request body is too large")
        raw = await request.body()
        if len(raw) > HTTP_MAX_BODY_BYTES:
            return _transport_error(413, -32600, "request body is too large")
        try:
            body = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return _transport_error(400, -32700, f"parse error: {exc}")
        if not isinstance(body, dict):
            return _transport_error(400, -32600, "the body must be one JSON-RPC message")
        try:
            kind = _classify_message(body)
        except _InvalidMessage as exc:
            return _transport_error(400, -32600, f"invalid request: {exc}")
        refused = protocol_refusal(request, body, kind)
        if refused is not None:
            return refused
        if kind != "request":
            # A stateless server has nothing to update for a notification or
            # a client response; accepting it is the whole contract.
            return Response(status_code=202)
        return JSONResponse(content=server.handle(body, principal))

    for path in MCP_ENDPOINT_PATHS:
        app.add_api_route(path, mcp_endpoint, methods=["POST"])
        app.add_api_route(path, method_not_allowed, methods=["GET", "DELETE"])

    @app.get("/healthz")
    async def healthz() -> JSONResponse:
        report = runtime.service.health()
        code = 200 if report.status.value != "failed" else 503
        return JSONResponse(status_code=code, content=report.model_dump(mode="json"))

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        # Every capability family is probed on its own evidence (ADR-097):
        # canonical and an enabled projection always gate; graph and active
        # memory gate only when the deployment marks them required.
        readiness = await runtime.readiness()
        content = runtime.service.health().model_dump(mode="json")
        if runtime.graph_service is not None:
            content["graph"] = readiness.family("graph").detail
        content["active_memory"] = {
            "store": readiness.family("active_store").model_dump(mode="json"),
            "bus": readiness.family("awareness_bus").model_dump(mode="json"),
        }
        content["readiness"] = readiness.model_dump(mode="json")
        return JSONResponse(status_code=200 if readiness.ready else 503, content=content)

    return app


def run_http(runtime: MemoryRuntime, *, host: str, port: int) -> int:
    settings = runtime.settings
    if settings.http_auth_required and settings.http_auth_mode == "bearer":
        if not settings.auth_tokens:
            raise ConfigurationError(
                "HTTP authentication is required but no L9_MEMORY_AUTH_TOKENS_JSON or file is configured"
            )
        log.info(
            "HTTP bearer mode serves configured service principals; remote agent "
            "identity requires L9_MEMORY_HTTP_AUTH_MODE=signed-agent (ADR-098)"
        )
    if not settings.http_auth_required and host not in _LOOPBACK_HOSTS:
        raise ConfigurationError("authentication may only be disabled on a loopback bind address")
    if host not in _LOOPBACK_HOSTS:
        log.warning(
            "serving MCP on a non-loopback address: terminate TLS in front of it; "
            "the remote credentials are bearer-equivalent until they expire"
        )
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is missing; install l9-graphite-memory[server]") from exc
    uvicorn.run(
        create_http_app(runtime),
        host=host,
        port=port,
        log_level=settings.log_level.lower(),
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
