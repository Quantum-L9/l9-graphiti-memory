"""Memory-owned remote consumer of the hosted MemoryService (ADR-082, amendment 2026-10-16).

This is the client half of ``memory-remote-mcp/v1`` (ADR-098,
``docs/REMOTE_MCP_CONTRACT.md``). It speaks MCP Streamable HTTP to one hosted
``MemoryService`` as a signed agent and returns the same typed receipts the
in-process service returns, so a consumer can move from a local runtime to a
remote one without reinterpreting a single verdict.

It holds no authority of its own:

- identity is the signed agent assertion and the sealed identity assertion the
  stdio agent door already reads (``L9_MEMORY_AGENT_ASSERTION``,
  ``L9_MEMORY_IDENTITY_ASSERTION_JSON``, ``L9_MEMORY_IDENTITY_ASSERTION_HMAC``);
  only the carrier differs. No signing key, grant, role, tenant or namespace
  claim is ever sent. The server verifies every request on its own evidence;
- a namespace is an address the server authorizes, never a grant;
- there is no fallback. A refused, unreachable or non-conforming server is a
  typed :class:`RemoteMemoryError`, never a silent switch to a local store.

Only the lifecycle operations of ADR-082 and the two agent write doors are
offered. Operations whose authority cannot exist over HTTP (administrator-only
tools such as ``memory.distill`` and ``memory.bootstrap``, which ADR-098 never
serves to a signed agent and which read a path on the server's filesystem) are
refused before anything is sent: see :data:`REMOTE_BLOCKED_OPERATIONS`.
"""

from __future__ import annotations

import ipaddress
import itertools
import json
import math
import os
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, ValidationError

from l9_graphite_memory.authz.remote_agent import (
    IDENTITY_ASSERTION_HEADER,
    IDENTITY_ASSERTION_HMAC_HEADER,
    encode_identity_assertion,
)
from l9_graphite_memory.contracts import (
    CloseReceipt,
    CloseRequest,
    ConflictReport,
    HealthReport,
    HydrationRequest,
    HydrationResult,
    MemoryRecord,
    MemorySearchRequest,
    PhaseLockReceipt,
    PhaseLockRequest,
    PhaseLockVerification,
    SearchReceipt,
    WriteReceipt,
)
from l9_graphite_memory.contracts.capabilities import (
    LIFECYCLE_OPERATIONS,
    MCP_OPERATION_TOOLS,
    ControlPlaneCapabilities,
)
from l9_graphite_memory.contracts.generated_data import MemoryCandidateIngestionResult
from l9_graphite_memory.errors import L9MemoryError
from l9_graphite_memory.version import (
    CONTROL_PLANE_CONTRACT_VERSION,
    HTTP_MCP_PROTOCOL_VERSIONS,
    PACKAGE_VERSION,
    REMOTE_MCP_CONTRACT_VERSION,
)

#: Selects the remote control plane for the ``l9-memory`` CLI. Unset means the
#: local runtime; set means every command either reaches this server or is
#: refused. Nothing ever falls back from one to the other.
REMOTE_URL_ENV = "L9_MEMORY_REMOTE_URL"
REMOTE_TIMEOUT_ENV = "L9_MEMORY_REMOTE_TIMEOUT_SECONDS"
#: The client-side values the stdio agent door reads (ADR-083, ADR-098).
AGENT_ASSERTION_ENV = "L9_MEMORY_AGENT_ASSERTION"
IDENTITY_ASSERTION_JSON_ENV = "L9_MEMORY_IDENTITY_ASSERTION_JSON"
IDENTITY_ASSERTION_HMAC_ENV = "L9_MEMORY_IDENTITY_ASSERTION_HMAC"

DEFAULT_TIMEOUT_SECONDS = 30.0
#: A credential this close to expiry is refused before it is sent: it could
#: expire in flight, and a request the server refuses on expiry has spent a
#: round trip to learn what the client already knew.
EXPIRY_MARGIN_SECONDS = 5
#: Upper bound on one response body; a hydration bundle is bounded far below.
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
ACCEPT = "application/json, text/event-stream"
CLIENT_INFO = {"name": "l9-graphite-memory-remote-client", "version": PACKAGE_VERSION}

#: Tools this client calls, by operation: the ADR-082 lifecycle set plus the
#: two agent write doors (ADR-0031). Nothing else is reachable through it.
REMOTE_OPERATION_TOOLS: dict[str, str] = {
    operation: MCP_OPERATION_TOOLS[operation]
    for operation in (*LIFECYCLE_OPERATIONS, "write_agent", "write_governed")
}

#: Capability-receipt fields the client binds to. Each must be present in the
#: server's own receipt; a model default is not evidence.
_CAPABILITY_BINDING_FIELDS: tuple[str, ...] = (
    "package_version",
    "contract_version",
    "remote_mcp_contract_version",
    "http_mcp_protocol_versions",
    "transports",
)

#: Operations that cannot be served remotely under existing law, with the
#: reason. They are refused locally; no request is sent.
REMOTE_BLOCKED_OPERATIONS: dict[str, str] = {
    "distill": (
        "memory.distill requires administrator authority, and ADR-098 never serves an "
        "administrator principal to a signed agent over HTTP; its source is a path on the "
        "server's filesystem, so a client's local file is not reachable. Remote distillation "
        "would need a new tool, credential class or authority, which no contract defines"
    ),
    "bootstrap": (
        "memory.bootstrap requires administrator authority and reads a repository on the "
        "server's filesystem; neither is available to a signed agent over HTTP (ADR-098)"
    ),
}


class RemoteFailureKind(str, Enum):
    """Why a remote call produced no receipt. A receipt is never a failure kind."""

    CONFIGURATION = "configuration"
    CREDENTIAL_EXPIRED = "credential_expired"
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    PROTOCOL = "protocol"
    CONTRACT_MISMATCH = "contract_mismatch"
    INVALID_REQUEST = "invalid_request"
    TOOL_FAILURE = "tool_failure"
    UNSUPPORTED_REMOTELY = "unsupported_remotely"


#: The exception type a local runtime raises for the same outcome, so a
#: consumer that classifies ``l9-memory`` failures by type classifies a remote
#: one identically. Tool failures carry the server's own type instead.
_PARITY_TYPES: dict[RemoteFailureKind, str] = {
    RemoteFailureKind.CONFIGURATION: "ConfigurationError",
    RemoteFailureKind.CREDENTIAL_EXPIRED: "AuthenticationError",
    RemoteFailureKind.UNREACHABLE: "ConnectionError",
    RemoteFailureKind.TIMEOUT: "TimeoutError",
    RemoteFailureKind.AUTHENTICATION: "AuthenticationError",
    RemoteFailureKind.AUTHORIZATION: "AuthorizationError",
    RemoteFailureKind.PROTOCOL: "RemoteProtocolError",
    RemoteFailureKind.CONTRACT_MISMATCH: "RemoteContractMismatch",
    RemoteFailureKind.INVALID_REQUEST: "ValueError",
    RemoteFailureKind.TOOL_FAILURE: "RemoteToolError",
    RemoteFailureKind.UNSUPPORTED_REMOTELY: "RemoteOperationUnsupported",
}


class RemoteMemoryError(L9MemoryError):
    """A remote call that produced no receipt, classified.

    ``error_type`` is the exception type a local runtime raises for the same
    outcome (or the server's own type for a tool failure). No credential is
    ever part of the message.
    """

    def __init__(
        self,
        kind: RemoteFailureKind,
        message: str,
        *,
        http_status: int | None = None,
        rpc_code: int | None = None,
        remote_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status
        self.rpc_code = rpc_code
        self.remote_type = remote_type

    @property
    def error_type(self) -> str:
        if self.kind is RemoteFailureKind.TOOL_FAILURE and self.remote_type:
            return self.remote_type
        return _PARITY_TYPES[self.kind]

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": self.error_type,
            "message": str(self),
            "remote": {
                "failure_kind": self.kind.value,
                "http_status": self.http_status,
                "rpc_code": self.rpc_code,
                "remote_type": self.remote_type,
            },
        }


def _configuration(message: str) -> RemoteMemoryError:
    return RemoteMemoryError(RemoteFailureKind.CONFIGURATION, message)


def _header_safe(value: str, name: str) -> str:
    """A credential value fit for an HTTP header; never echoed on refusal."""

    if not value or not value.isascii() or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise _configuration(f"{name} must be a non-empty single-line ASCII value")
    return value


@dataclass(frozen=True)
class AgentCredentials:
    """The three per-request credentials of a signed agent (ADR-098 §2).

    Only the minted assertion and the sealed identity evidence are held; the
    signing key never reaches this object. ``repr`` omits every value.
    """

    agent_assertion: str = field(repr=False)
    identity_assertion: Mapping[str, Any] = field(repr=False)
    identity_assertion_hmac: str = field(repr=False)

    def __post_init__(self) -> None:
        _header_safe(self.agent_assertion, AGENT_ASSERTION_ENV)
        _header_safe(self.identity_assertion_hmac, IDENTITY_ASSERTION_HMAC_ENV)
        parts = self.agent_assertion.split(".")
        if len(parts) != 4 or not parts[0] or not (parts[1].isdigit() and len(parts[1]) <= 12):
            raise _configuration(
                f"{AGENT_ASSERTION_ENV} is not an agent assertion (agent_id.exp.nonce.hmac)"
            )
        if not isinstance(self.identity_assertion, Mapping) or not self.identity_assertion.get(
            "assertion_digest"
        ):
            raise _configuration(
                f"{IDENTITY_ASSERTION_JSON_ENV} must be a sealed identity assertion object"
            )

    @property
    def agent_id(self) -> str:
        return self.agent_assertion.split(".", 1)[0]

    @property
    def expires_at(self) -> int:
        return int(self.agent_assertion.split(".")[1])

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> AgentCredentials:
        env = os.environ if environ is None else environ
        missing = [
            name
            for name in (
                AGENT_ASSERTION_ENV,
                IDENTITY_ASSERTION_JSON_ENV,
                IDENTITY_ASSERTION_HMAC_ENV,
            )
            if not env.get(name, "").strip()
        ]
        if missing:
            raise _configuration(
                "the remote control plane needs a signed agent identity; missing "
                + ", ".join(missing)
            )
        try:
            identity = json.loads(env[IDENTITY_ASSERTION_JSON_ENV])
        except ValueError:
            raise _configuration(f"{IDENTITY_ASSERTION_JSON_ENV} is not valid JSON") from None
        if not isinstance(identity, dict):
            raise _configuration(f"{IDENTITY_ASSERTION_JSON_ENV} must be a JSON object")
        return cls(
            agent_assertion=env[AGENT_ASSERTION_ENV].strip(),
            identity_assertion=identity,
            identity_assertion_hmac=env[IDENTITY_ASSERTION_HMAC_ENV].strip(),
        )

    def headers(self, *, now: float) -> dict[str, str]:
        """The credential headers, refused locally once the assertion is spent."""

        if self.expires_at <= now + EXPIRY_MARGIN_SECONDS:
            raise RemoteMemoryError(
                RemoteFailureKind.CREDENTIAL_EXPIRED,
                f"agent assertion for agent_id={self.agent_id!r} has expired; mint a new one",
            )
        return {
            "Authorization": f"Bearer {self.agent_assertion}",
            IDENTITY_ASSERTION_HEADER: encode_identity_assertion(self.identity_assertion),
            IDENTITY_ASSERTION_HMAC_HEADER: self.identity_assertion_hmac,
        }


CredentialSource = AgentCredentials | Callable[[], AgentCredentials]


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_endpoint(url: str) -> str:
    """The ``/mcp`` endpoint for ``url``, or a configuration refusal.

    Plain HTTP is accepted only to a loopback host: a remote deployment
    terminates TLS in front of the server (ADR-098), and a bearer-equivalent
    credential must not cross a network in clear text. A URL carrying user
    information, a query or a fragment is refused, because credentials never
    travel in a URL.
    """

    try:
        parts = urlsplit(url.strip())
        parts.port  # noqa: B018 -- raises ValueError on an invalid port
    except ValueError:
        raise _configuration("remote memory URL is not a valid URL") from None
    host = parts.hostname or ""
    if parts.scheme not in {"https", "http"} or not host:
        raise _configuration("remote memory URL must be an absolute https:// URL")
    if parts.username is not None or parts.password is not None:
        raise _configuration("remote memory URL must not carry credentials")
    if parts.query or parts.fragment:
        raise _configuration("remote memory URL must not carry a query or fragment")
    if parts.scheme == "http" and not _is_loopback(host):
        raise _configuration(
            "plain http:// is accepted only for a loopback host; a remote memory "
            "server is reached over https://"
        )
    path = parts.path.rstrip("/")
    if not path.endswith("/mcp"):
        path = f"{path}/mcp"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """A redirect would replay the credential headers to another location."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_Model = TypeVar("_Model", bound=BaseModel)


class RemoteMemoryClient:
    """A signed agent's client for one hosted ``MemoryService``.

    Construct it with the server URL and either fixed credentials or a
    callable that returns current ones; the callable is consulted on every
    request, so a long-lived consumer can mint fresh assertions before they
    expire. ``connect`` negotiates the protocol and binds the server's
    capability receipt; every operation connects first if needed.
    """

    def __init__(
        self,
        url: str,
        credentials: CredentialSource,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        ssl_context: ssl.SSLContext | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise _configuration("remote timeout must be a positive, finite number of seconds")
        self.endpoint = normalize_endpoint(url)
        self._credentials = credentials
        self._timeout = timeout_seconds
        self._clock = clock
        host = urlsplit(self.endpoint).hostname or ""
        handlers: list[Any] = [_RefuseRedirects()]
        if _is_loopback(host):
            handlers.append(urllib.request.ProxyHandler({}))
        if self.endpoint.startswith("https://"):
            handlers.append(
                urllib.request.HTTPSHandler(context=ssl_context or ssl.create_default_context())
            )
        self._opener = urllib.request.build_opener(*handlers)
        self._ids = itertools.count(1)
        self.protocol_version: str | None = None
        self.server_capabilities: ControlPlaneCapabilities | None = None

    @classmethod
    def from_environment(
        cls,
        url: str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> RemoteMemoryClient:
        env = os.environ if environ is None else environ
        selected = (url or env.get(REMOTE_URL_ENV, "")).strip()
        if not selected:
            raise _configuration(f"{REMOTE_URL_ENV} is not set")
        raw_timeout = env.get(REMOTE_TIMEOUT_ENV, "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            raise _configuration(f"{REMOTE_TIMEOUT_ENV} must be a number of seconds") from None
        return cls(
            selected,
            AgentCredentials.from_environment(env),
            timeout_seconds=timeout,
            ssl_context=ssl_context,
        )

    # -- transport ---------------------------------------------------------

    def _current_credentials(self) -> AgentCredentials:
        source = self._credentials
        credentials = source() if callable(source) else source
        if not isinstance(credentials, AgentCredentials):
            raise _configuration("credential provider must return AgentCredentials")
        return credentials

    def _send(self, message: dict[str, Any]) -> tuple[int, str, bytes]:
        credentials = self._current_credentials()
        headers = {
            "Content-Type": "application/json",
            "Accept": ACCEPT,
            "User-Agent": f"l9-graphite-memory/{PACKAGE_VERSION} remote-client",
            **credentials.headers(now=self._clock()),
        }
        if self.protocol_version is not None:
            headers["MCP-Protocol-Version"] = self.protocol_version
        body = json.dumps(message, separators=(",", ":"), default=str).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                return (
                    int(response.status),
                    response.headers.get("Content-Type", ""),
                    payload,
                )
        except urllib.error.HTTPError as exc:
            try:
                payload = exc.read(MAX_RESPONSE_BYTES + 1)
            finally:
                exc.close()
            raise self._http_refusal(exc.code, payload) from None
        except TimeoutError:
            raise RemoteMemoryError(
                RemoteFailureKind.TIMEOUT,
                f"remote memory server did not answer within {self._timeout:g}s",
            ) from None
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise RemoteMemoryError(
                    RemoteFailureKind.TIMEOUT,
                    f"remote memory server did not answer within {self._timeout:g}s",
                ) from None
            if isinstance(reason, ssl.SSLError):
                raise RemoteMemoryError(
                    RemoteFailureKind.UNREACHABLE,
                    f"TLS to the remote memory server failed: {type(reason).__name__}",
                ) from None
            raise RemoteMemoryError(
                RemoteFailureKind.UNREACHABLE,
                f"remote memory server is unreachable: {type(reason).__name__}",
            ) from None
        except OSError as exc:
            raise RemoteMemoryError(
                RemoteFailureKind.UNREACHABLE,
                f"remote memory server is unreachable: {type(exc).__name__}",
            ) from None

    @staticmethod
    def _refusal_message(payload: bytes) -> str | None:
        try:
            decoded = json.loads(payload[:65_536])
        except ValueError:
            return None
        if isinstance(decoded, dict) and isinstance(decoded.get("error"), dict):
            message = decoded["error"].get("message")
            return str(message) if message else None
        return None

    def _http_refusal(self, status: int, payload: bytes) -> RemoteMemoryError:
        detail = self._refusal_message(payload) or f"HTTP {status}"
        if status == 401:
            kind = RemoteFailureKind.AUTHENTICATION
        elif 300 <= status < 400:
            kind = RemoteFailureKind.PROTOCOL
            detail = f"redirect refused (HTTP {status}); credentials are sent to one endpoint only"
        elif status >= 500 or status in {404, 408, 429}:
            kind = RemoteFailureKind.UNREACHABLE
        else:  # 400, 403, 405, 406, 413, 415: the request did not conform
            kind = RemoteFailureKind.PROTOCOL
        return RemoteMemoryError(
            kind, f"remote memory refused the request: {detail}", http_status=status
        )

    def _exchange(self, message: dict[str, Any]) -> tuple[int, str, bytes]:
        try:
            return self._send(message)
        except RemoteMemoryError as exc:
            # A provider may have minted fresh credentials since this request
            # was built; an authentication refusal means nothing was served,
            # so one retry with the new evidence is safe.
            if exc.kind is RemoteFailureKind.AUTHENTICATION and callable(self._credentials):
                return self._send(message)
            raise

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        request_id = next(self._ids)
        status, content_type, payload = self._exchange(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        if status != 200:
            raise RemoteMemoryError(
                RemoteFailureKind.PROTOCOL,
                f"remote memory answered {method} with HTTP {status}, not 200",
                http_status=status,
            )
        if len(payload) > MAX_RESPONSE_BYTES:
            raise RemoteMemoryError(RemoteFailureKind.PROTOCOL, "remote response is too large")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            raise RemoteMemoryError(
                RemoteFailureKind.PROTOCOL,
                f"remote memory answered with {content_type or 'no Content-Type'}; "
                "memory-remote-mcp/v1 responses are application/json",
            )
        try:
            response = json.loads(payload)
        except ValueError:
            raise RemoteMemoryError(
                RemoteFailureKind.PROTOCOL, "remote response is not JSON"
            ) from None
        if (
            not isinstance(response, dict)
            or response.get("jsonrpc") != "2.0"
            or response.get("id") != request_id
        ):
            raise RemoteMemoryError(
                RemoteFailureKind.PROTOCOL,
                "remote response is not the JSON-RPC response to this request",
            )
        if "error" in response:
            raise self._rpc_failure(method, response["error"])
        if "result" not in response:
            raise RemoteMemoryError(RemoteFailureKind.PROTOCOL, "remote response has no result")
        return response["result"]

    @staticmethod
    def _rpc_failure(method: str, error: Any) -> RemoteMemoryError:
        if not isinstance(error, dict):
            return RemoteMemoryError(RemoteFailureKind.PROTOCOL, "malformed JSON-RPC error")
        code = error.get("code")
        message = str(error.get("message", "remote error"))
        raw_data = error.get("data")
        data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
        remote_type = str(data["type"]) if data.get("type") else None
        if code == -32001:
            kind = RemoteFailureKind.AUTHENTICATION
        elif code == -32010 and remote_type == "AuthorizationError":
            kind = RemoteFailureKind.AUTHORIZATION
        elif code == -32010:
            kind = RemoteFailureKind.TOOL_FAILURE
        elif code == -32602:
            kind = RemoteFailureKind.INVALID_REQUEST
        elif code == -32601:
            kind = RemoteFailureKind.CONTRACT_MISMATCH
            message = f"remote memory does not serve {method}: {message}"
        else:
            kind = RemoteFailureKind.TOOL_FAILURE
            remote_type = remote_type or "RemoteToolError"
        return RemoteMemoryError(
            kind,
            message,
            rpc_code=code if isinstance(code, int) else None,
            remote_type=remote_type,
        )

    def _notify(self, method: str) -> None:
        status, _, _ = self._exchange({"jsonrpc": "2.0", "method": method})
        if status != 202:
            raise RemoteMemoryError(
                RemoteFailureKind.PROTOCOL,
                f"remote memory answered the {method} notification with HTTP {status}, not 202",
                http_status=status,
            )

    # -- binding -----------------------------------------------------------

    def connect(self) -> ControlPlaneCapabilities:
        """Negotiate the protocol and bind the server's capability receipt.

        The client binds the contract, not tool presence (ADR-082): the
        receipt must name ``memory-control-plane/v1`` and
        ``memory-remote-mcp/v1``, the negotiated revision, and every lifecycle
        operation on the MCP transport.
        """

        if self.server_capabilities is not None:
            return self.server_capabilities
        self.protocol_version = None
        result = self._request(
            "initialize",
            {
                "protocolVersion": HTTP_MCP_PROTOCOL_VERSIONS[0],
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )
        negotiated = result.get("protocolVersion") if isinstance(result, dict) else None
        if negotiated not in HTTP_MCP_PROTOCOL_VERSIONS:
            raise RemoteMemoryError(
                RemoteFailureKind.CONTRACT_MISMATCH,
                f"remote memory negotiated MCP revision {negotiated!r}; this client speaks "
                f"{', '.join(HTTP_MCP_PROTOCOL_VERSIONS)}",
            )
        self.protocol_version = str(negotiated)
        self._notify("notifications/initialized")
        raw = self._tool_payload(REMOTE_OPERATION_TOOLS["capabilities"], {})
        # The model defaults these to this client's own values, so a receipt
        # that omits them would bind on evidence the server never gave.
        absent = sorted(
            name
            for name in _CAPABILITY_BINDING_FIELDS
            if not isinstance(raw, dict) or name not in raw
        )
        if absent:
            raise RemoteMemoryError(
                RemoteFailureKind.CONTRACT_MISMATCH,
                "remote capability receipt omits " + ", ".join(absent),
            )
        capabilities = self._typed(ControlPlaneCapabilities, raw)
        problems: list[str] = []
        if capabilities.contract_version != CONTROL_PLANE_CONTRACT_VERSION:
            problems.append(
                f"contract_version {capabilities.contract_version!r} != "
                f"{CONTROL_PLANE_CONTRACT_VERSION!r}"
            )
        if capabilities.remote_mcp_contract_version != REMOTE_MCP_CONTRACT_VERSION:
            problems.append(
                f"remote_mcp_contract_version {capabilities.remote_mcp_contract_version!r} != "
                f"{REMOTE_MCP_CONTRACT_VERSION!r}"
            )
        if self.protocol_version not in capabilities.http_mcp_protocol_versions:
            problems.append(f"negotiated revision {self.protocol_version} is not advertised")
        mcp = next((t for t in capabilities.transports if t.transport == "mcp"), None)
        missing = sorted(
            operation
            for operation, tool_name in REMOTE_OPERATION_TOOLS.items()
            if mcp is None or mcp.operations.get(operation) != tool_name
        )
        if missing:
            problems.append(f"MCP transport lacks {', '.join(missing)}")
        if problems:
            raise RemoteMemoryError(
                RemoteFailureKind.CONTRACT_MISMATCH,
                "remote memory is not bound to this client's contract: " + "; ".join(problems),
            )
        self.server_capabilities = capabilities
        return capabilities

    def _tool_payload(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        result = self._request("tools/call", {"name": tool_name, "arguments": arguments})
        try:
            content = result["content"]
            text = next(
                item["text"]
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
            return json.loads(text)
        except (KeyError, TypeError, StopIteration, ValueError):
            raise RemoteMemoryError(
                RemoteFailureKind.PROTOCOL,
                f"{tool_name} returned no JSON text content",
            ) from None

    @staticmethod
    def _typed(model: type[_Model], payload: Any) -> _Model:
        try:
            return model.model_validate(payload)
        except ValidationError as exc:
            raise RemoteMemoryError(
                RemoteFailureKind.CONTRACT_MISMATCH,
                f"remote receipt does not match {model.__name__}: "
                f"{exc.error_count()} validation error(s)",
            ) from None

    def call(self, operation: str, arguments: dict[str, Any]) -> Any:
        """Call one supported operation and return its decoded tool payload."""

        if operation in REMOTE_BLOCKED_OPERATIONS:
            raise RemoteMemoryError(
                RemoteFailureKind.UNSUPPORTED_REMOTELY, REMOTE_BLOCKED_OPERATIONS[operation]
            )
        tool_name = REMOTE_OPERATION_TOOLS.get(operation)
        if tool_name is None:
            raise RemoteMemoryError(
                RemoteFailureKind.UNSUPPORTED_REMOTELY,
                f"{operation!r} is not a remote control-plane operation",
            )
        self.connect()
        return self._tool_payload(tool_name, arguments)

    # -- typed lifecycle operations ---------------------------------------

    def capabilities(self) -> ControlPlaneCapabilities:
        return self.connect()

    def health(self) -> HealthReport:
        return self._typed(HealthReport, self.call("health", {}))

    def search(self, request: MemorySearchRequest) -> SearchReceipt:
        if request.token_budget is not None:
            raise RemoteMemoryError(
                RemoteFailureKind.INVALID_REQUEST,
                "memory.search defines no token_budget; it is not sent rather than dropped",
            )
        arguments: dict[str, Any] = {
            "query": request.query,
            "namespaces": list(request.namespaces),
            "memory_classes": [item.value for item in request.memory_classes],
            "valid_at": request.valid_at.isoformat(),
            "include_superseded": request.include_superseded,
            "include_archived": request.include_archived,
            "min_confidence": request.min_confidence,
            "limit": request.limit,
            "tags": list(request.tags),
        }
        if request.recorded_before is not None:
            arguments["recorded_before"] = request.recorded_before.isoformat()
        return self._typed(SearchReceipt, self.call("search", arguments))

    def hydrate(self, request: HydrationRequest) -> HydrationResult:
        if "valid_at" in request.model_fields_set:
            raise RemoteMemoryError(
                RemoteFailureKind.INVALID_REQUEST,
                "memory.hydrate defines no valid_at; the server hydrates as of now",
            )
        arguments = {
            "task": request.task,
            "namespaces": list(request.namespaces),
            "entities": list(request.entities),
            "topics": list(request.topics),
            "memory_classes": [item.value for item in request.memory_classes],
            "token_budget": request.token_budget,
            "max_records": request.max_records,
            "tags": list(request.tags),
        }
        return self._typed(HydrationResult, self.call("hydrate", arguments))

    def get(self, record_id: UUID) -> MemoryRecord | None:
        payload = self.call("get", {"record_id": str(record_id)})
        if not isinstance(payload, dict) or "found" not in payload:
            raise RemoteMemoryError(
                RemoteFailureKind.CONTRACT_MISMATCH, "memory.get returned no found flag"
            )
        if not payload["found"]:
            return None
        return self._typed(MemoryRecord, payload.get("record"))

    def conflicts(self, namespace: str) -> ConflictReport:
        return self._typed(ConflictReport, self.call("conflicts", {"namespace": namespace}))

    def phase_lock(self, request: PhaseLockRequest) -> PhaseLockReceipt:
        return self._typed(
            PhaseLockReceipt,
            self.call("phase_lock", request.model_dump(mode="json")),
        )

    def verify_phase_lock(self, namespace: str, task_signature: str) -> PhaseLockVerification:
        return self._typed(
            PhaseLockVerification,
            self.call(
                "verify_phase_lock", {"namespace": namespace, "task_signature": task_signature}
            ),
        )

    def close(self, request: CloseRequest) -> CloseReceipt:
        arguments = {
            key: value
            for key, value in request.model_dump(mode="json").items()
            if value is not None
        }
        return self._typed(CloseReceipt, self.call("close", arguments))

    def ingest_governed_candidate(self, payload: dict[str, Any]) -> MemoryCandidateIngestionResult:
        return self._typed(
            MemoryCandidateIngestionResult,
            self.call("ingest_governed_candidate", {"candidate": payload}),
        )

    def ingest(self, arguments: dict[str, Any]) -> WriteReceipt:
        """``memory.ingest``: provenance is server-derived from the verified agent."""

        return self._typed(WriteReceipt, self.call("ingest", arguments))

    def write_agent(self, arguments: dict[str, Any]) -> WriteReceipt:
        return self._typed(WriteReceipt, self.call("write_agent", arguments))

    def write_governed(self, arguments: dict[str, Any]) -> WriteReceipt:
        return self._typed(WriteReceipt, self.call("write_governed", arguments))


def remote_url_from_environment(environ: Mapping[str, str] | None = None) -> str | None:
    env = os.environ if environ is None else environ
    value = env.get(REMOTE_URL_ENV, "").strip()
    return value or None


__all__ = [
    "AGENT_ASSERTION_ENV",
    "IDENTITY_ASSERTION_HMAC_ENV",
    "IDENTITY_ASSERTION_JSON_ENV",
    "REMOTE_BLOCKED_OPERATIONS",
    "REMOTE_OPERATION_TOOLS",
    "REMOTE_TIMEOUT_ENV",
    "REMOTE_URL_ENV",
    "AgentCredentials",
    "RemoteFailureKind",
    "RemoteMemoryClient",
    "RemoteMemoryError",
    "normalize_endpoint",
    "remote_url_from_environment",
]
