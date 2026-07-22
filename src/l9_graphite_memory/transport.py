# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/transport.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Explicit Graphiti MCP transport used only as an optional projection adapter."""

from __future__ import annotations

import json
import ssl
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

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        if not self.circuit.can_execute():
            raise ProjectionError("Graphiti MCP circuit is open")
        payload = {
            "jsonrpc": "2.0",
            "id": "l9-memory",
            "method": method,
            "params": params or {},
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout or self.timeout_seconds,
                context=ssl.create_default_context(),
            ) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.circuit.record_failure()
            detail = exc.read().decode("utf-8", errors="replace")[:1_000]
            raise ProjectionError(f"Graphiti MCP HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            self.circuit.record_failure()
            raise ProjectionError(f"Graphiti MCP unreachable: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.circuit.record_failure()
            raise ProjectionError(f"Graphiti MCP returned invalid JSON: {exc}") from exc
        if "error" in decoded:
            self.circuit.record_failure()
            raise ProjectionError(json.dumps(decoded["error"], sort_keys=True))
        self.circuit.record_success()
        result = decoded.get("result", decoded)
        if not isinstance(result, dict):
            return {"value": result}
        return result

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
