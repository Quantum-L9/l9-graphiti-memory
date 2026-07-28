# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/transport.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-28

"""Explicit Graphiti MCP transport used only as an optional projection adapter."""

from __future__ import annotations

import email.message
import json
import ssl
import threading
import urllib.error
import urllib.request
from typing import Any, Protocol

from l9_graphite_memory.circuit_breaker import CircuitBreaker
from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.rate_limiter import RateLimiter


class MemoryTransport(Protocol):
    name: str

    def health(self) -> dict[str, Any]: ...

    def search(
        self, query: str, group_id: str, limit: int = 10
    ) -> list[dict[str, Any]]: ...

    def write(
        self, body: str, group_id: str, kind: str = "observation", **kwargs: Any
    ) -> dict[str, Any]: ...

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any: ...

    def list_tools(self) -> list[str]: ...


class HttpMcpTransport:
    """JSON-RPC transport to the official Graphiti MCP server tool surface."""

    name = "graphiti-http-mcp"

    def __init__(
        self,
        *,
        url: str,
        token: str | None = None,
        timeout_seconds: int = 30,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        normalized = url.rstrip("/")
        if not normalized:
            raise ValueError("Graphiti MCP URL cannot be empty")
        self.url = normalized if normalized.endswith("/mcp") else f"{normalized}/mcp"
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.circuit = circuit_breaker or CircuitBreaker()
        self.rate = rate_limiter or RateLimiter()
        self._session_id: str | None = None
        self._session_lock = threading.Lock()

    def _headers(self) -> dict[str, str]:
        # The MCP Streamable-HTTP transport requires the client to accept
        # both response encodings the server may choose between; sending
        # "application/json" alone causes the server to reject the request
        # with 406 Not Acceptable.
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    @staticmethod
    def _parse_body(content_type: str, raw: bytes) -> dict[str, Any]:
        text = raw.decode("utf-8")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type == "text/event-stream":
            # SSE framing: one or more "event: ...\ndata: {...}\n\n" blocks.
            # The JSON-RPC response is the data payload of the last event.
            events = [block for block in text.split("\n\n") if block.strip()]
            if not events:
                raise json.JSONDecodeError("empty SSE stream", text, 0)
            data_lines = [
                line[len("data:") :].strip()
                for line in events[-1].splitlines()
                if line.startswith("data:")
            ]
            if not data_lines:
                raise json.JSONDecodeError("no data field in SSE event", text, 0)
            parsed = json.loads("".join(data_lines))
        elif media_type == "application/json":
            parsed = json.loads(text)
        else:
            raise ProjectionError(
                f"Graphiti MCP returned unsupported Content-Type: {content_type!r}"
            )
        if not isinstance(parsed, dict):
            raise ProjectionError(
                f"Graphiti MCP returned a non-object JSON-RPC response: {parsed!r}"
            )
        return parsed

    def _post(
        self, payload: dict[str, Any], *, timeout: int | None = None
    ) -> tuple[email.message.Message, bytes]:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=timeout or self.timeout_seconds,
            context=ssl.create_default_context(),
        ) as response:
            # response.headers (http.client.HTTPMessage) does case-insensitive
            # lookups; a plain dict would not, and this server sends lowercase
            # header names ("content-type", "mcp-session-id").
            return response.headers, response.read()

    def _ensure_session(self, *, timeout: int | None = None) -> None:
        """Establish an MCP session if one is not already active.

        The Streamable-HTTP transport is stateful: every RPC after the first
        must carry the `Mcp-Session-Id` the server issued during
        `initialize`. Calling any other method beforehand fails with
        `400 Bad Request: Missing session ID`.
        """
        with self._session_lock:
            if self._session_id:
                return
            init_payload = {
                "jsonrpc": "2.0",
                "id": "l9-memory-init",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "l9-graphite-memory", "version": "2.2.0"},
                },
            }
            try:
                headers, _ = self._post(init_payload, timeout=timeout)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1_000]
                raise ProjectionError(
                    f"Graphiti MCP session initialize failed HTTP {exc.code}: {detail}"
                ) from exc
            except urllib.error.URLError as exc:
                raise ProjectionError(
                    f"Graphiti MCP unreachable during initialize: {exc.reason}"
                ) from exc
            session_id = headers.get("Mcp-Session-Id")
            if not session_id:
                raise ProjectionError(
                    "Graphiti MCP initialize response carried no Mcp-Session-Id header"
                )
            self._session_id = session_id
            # Complete the handshake; the server expects this notification
            # before treating the session as fully initialized.
            try:
                self._post(
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    timeout=timeout,
                )
            except (urllib.error.HTTPError, urllib.error.URLError) as exc:
                self._session_id = None
                raise ProjectionError(
                    f"Graphiti MCP notifications/initialized failed: {exc}"
                ) from exc

    def _rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        if not self.circuit.can_execute():
            raise ProjectionError("Graphiti MCP circuit is open")
        if method != "initialize":
            self._ensure_session(timeout=timeout)
        payload = {
            "jsonrpc": "2.0",
            "id": "l9-memory",
            "method": method,
            "params": params or {},
        }
        decoded = self._rpc_once(payload, timeout=timeout, retry_on_session_error=True)
        if "error" in decoded:
            self.circuit.record_failure()
            raise ProjectionError(json.dumps(decoded["error"], sort_keys=True))
        self.circuit.record_success()
        result = decoded.get("result", decoded)
        if not isinstance(result, dict):
            return {"value": result}
        return result

    def _rpc_once(
        self,
        payload: dict[str, Any],
        *,
        timeout: int | None,
        retry_on_session_error: bool,
    ) -> dict[str, Any]:
        try:
            headers, raw = self._post(payload, timeout=timeout)
            return self._parse_body(headers.get("Content-Type", ""), raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1_000]
            if (
                retry_on_session_error
                and exc.code in (400, 404)
                and "session" in detail.lower()
            ):
                # The server-side session expired or the process restarted;
                # re-handshake once and retry this exact call.
                self._session_id = None
                self._ensure_session(timeout=timeout)
                return self._rpc_once(
                    payload, timeout=timeout, retry_on_session_error=False
                )
            self.circuit.record_failure()
            raise ProjectionError(f"Graphiti MCP HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            self.circuit.record_failure()
            raise ProjectionError(f"Graphiti MCP unreachable: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.circuit.record_failure()
            raise ProjectionError(f"Graphiti MCP returned invalid JSON: {exc}") from exc

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            text = content[0].get("text")
            if isinstance(text, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return result

    def list_tools(self) -> list[str]:
        result = self._rpc("tools/list", {}, timeout=10)
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            return []
        return sorted(
            str(item.get("name", ""))
            for item in tools
            if isinstance(item, dict) and item.get("name")
        )

    def health(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "healthy": False,
            "circuit": self.circuit.status(),
        }
        try:
            tools = self.list_tools()
            result.update({"healthy": True, "tool_count": len(tools), "tools": tools})
        except ProjectionError as exc:
            result["error"] = str(exc)
        result["circuit"] = self.circuit.status()
        return result

    def search(
        self, query: str, group_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        tools = set(self.list_tools())
        official_dialect = "search_memory_facts" in tools or "add_memory" in tools
        candidates = [
            ("search_memory_facts", "max_facts")
            if "search_memory_facts" in tools
            else ("search_facts", "max_facts"),
            ("search_nodes", "max_nodes"),
        ]
        failures: list[str] = []
        attempted = False
        for tool, limit_key in candidates:
            if tool not in tools:
                continue
            attempted = True
            arguments: dict[str, Any] = {"query": query, limit_key: limit}
            if official_dialect:
                arguments["group_ids"] = [group_id]
            else:
                arguments["group_id"] = group_id
            try:
                result = self.call_tool(tool, arguments)
                if isinstance(result, dict):
                    if result.get("error"):
                        raise ProjectionError(str(result["error"]))
                    values = (
                        result.get("facts")
                        or result.get("nodes")
                        or result.get("results")
                        or []
                    )
                else:
                    values = result
                if isinstance(values, list) and values:
                    return [
                        item if isinstance(item, dict) else {"content": str(item)}
                        for item in values
                    ]
            except ProjectionError as exc:
                failures.append(f"{tool}: {exc}")
        if failures:
            raise ProjectionError("; ".join(failures))
        if not attempted:
            raise ProjectionError("Graphiti MCP exposes no supported search tool")
        return []

    def write(
        self, body: str, group_id: str, kind: str = "observation", **kwargs: Any
    ) -> dict[str, Any]:
        self.rate.check_and_record()
        tools = set(self.list_tools())
        tool = (
            "add_memory"
            if "add_memory" in tools
            else "add_episode"
            if "add_episode" in tools
            else ""
        )
        if not tool:
            raise ProjectionError(
                "Graphiti MCP exposes neither add_memory nor add_episode"
            )
        arguments: dict[str, Any] = {
            "name": str(kwargs.pop("name", f"{kind}:{body[:80]}")),
            "episode_body": body,
            "source": str(kwargs.pop("source", "json")),
            "source_description": str(
                kwargs.pop("source_description", f"l9-memory/{kind}")
            ),
            "group_id": group_id,
            **kwargs,
        }
        result = self.call_tool(tool, arguments)
        if isinstance(result, dict) and result.get("error"):
            raise ProjectionError(str(result["error"]))
        return result if isinstance(result, dict) else {"result": result}
