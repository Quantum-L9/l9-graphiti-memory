# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/zep_transport.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Zep Cloud graph transport using the current ``zep-cloud`` SDK."""

from __future__ import annotations

from typing import Any

from l9_graphite_memory.circuit_breaker import CircuitBreaker
from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.rate_limiter import RateLimiter


class ZepCloudTransport:
    """Project canonical records into Zep group graphs without owning core truth."""

    name = "zep-cloud-graph"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        rate_limiter: RateLimiter | None = None,
        client: Any | None = None,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("ZEP_API_KEY is required")
        if client is None:
            try:
                from zep_cloud.client import Zep
            except ImportError as exc:
                raise ProjectionError(
                    "zep-cloud is not installed; install l9-graphite-memory[zep]"
                ) from exc
            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            client = Zep(**kwargs)
        self.client = client
        self.circuit = circuit_breaker or CircuitBreaker()
        self.rate = rate_limiter or RateLimiter()
        self._last_connectivity_ok: bool | None = None
        self._last_error: str | None = None

    def _record_success(self) -> None:
        self._last_connectivity_ok = True
        self._last_error = None
        self.circuit.record_success()

    def _record_failure(self, exc: Exception) -> None:
        self._last_connectivity_ok = False
        self._last_error = str(exc)
        self.circuit.record_failure()

    def health(self) -> dict[str, Any]:
        graph_available = getattr(self.client, "graph", None) is not None
        verified = self._last_connectivity_ok is not None
        healthy = graph_available and self._last_connectivity_ok is True
        result: dict[str, Any] = {
            "name": self.name,
            "configured": graph_available,
            "connectivity_verified": verified,
            "healthy": healthy,
            "status": "healthy"
            if healthy
            else "unverified"
            if graph_available and not verified
            else "unhealthy",
            "circuit": self.circuit.status(),
        }
        if not graph_available:
            result["error"] = "Zep client has no graph API"
        elif self._last_error:
            result["error"] = self._last_error
        return result

    def list_tools(self) -> list[str]:
        return ["delete_episode", "graph.add", "graph.episode.delete", "graph.search"]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        if name in {"add_episode", "graph.add"}:
            return self.write(
                str(
                    args.get("episode_body")
                    or args.get("body")
                    or args.get("data")
                    or ""
                ),
                str(args.get("group_id") or args.get("graph_id") or ""),
                kind=str(args.get("kind") or "observation"),
                **{
                    key: value
                    for key, value in args.items()
                    if key
                    not in {
                        "episode_body",
                        "body",
                        "data",
                        "group_id",
                        "graph_id",
                        "kind",
                    }
                },
            )
        if name in {"search_facts", "search_nodes", "graph.search"}:
            return {
                "results": self.search(
                    str(args.get("query") or ""),
                    str(args.get("group_id") or args.get("graph_id") or ""),
                    int(
                        args.get("limit")
                        or args.get("max_facts")
                        or args.get("max_nodes")
                        or 10
                    ),
                )
            }
        if name in {"delete_episode", "graph.episode.delete"}:
            return self.delete(
                str(
                    args.get("uuid")
                    or args.get("episode_uuid")
                    or args.get("locator")
                    or ""
                )
            )
        raise ProjectionError(f"unsupported Zep transport operation: {name}")

    def write(
        self, body: str, group_id: str, kind: str = "observation", **kwargs: Any
    ) -> dict[str, Any]:
        if not group_id:
            raise ProjectionError("group_id is required for Zep graph projection")
        if not self.circuit.can_execute():
            raise ProjectionError("Zep circuit is open")
        self.rate.check_and_record()
        metadata = kwargs.pop("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {"metadata": str(metadata)}
        metadata = {
            key: value
            for key, value in metadata.items()
            if isinstance(value, (str, int, float, bool, list))
        }
        try:
            result = self.client.graph.add(
                group_id=group_id,
                data=body[:10_000],
                type="json" if body.lstrip().startswith(("{", "[")) else "text",
                source_description=str(
                    kwargs.pop("source_description", f"l9-memory/{kind}")
                )[:500],
                metadata=metadata,
            )
            self._record_success()
            return {
                "projected": True,
                "group_id": group_id,
                "episode_uuid": str(getattr(result, "uuid", "")),
            }
        except Exception as exc:
            self._record_failure(exc)
            raise ProjectionError(f"Zep graph add failed: {exc}") from exc

    def delete(self, locator: str) -> dict[str, Any]:
        if not locator:
            raise ProjectionError("episode locator is required for Zep graph deletion")
        if not self.circuit.can_execute():
            raise ProjectionError("Zep circuit is open")
        self.rate.check_and_record()
        try:
            episode_api = getattr(self.client.graph, "episode", None)
            delete_fn = getattr(episode_api, "delete", None)
            if delete_fn is None:
                raise ProjectionError("Zep client does not expose graph.episode.delete")
            result = delete_fn(uuid_=locator)
            self._record_success()
            return {"erased": True, "locator": locator, "result": result}
        except ProjectionError:
            raise
        except Exception as exc:
            self._record_failure(exc)
            raise ProjectionError(f"Zep graph episode deletion failed: {exc}") from exc

    @staticmethod
    def _result_items(response: Any) -> list[Any]:
        for attribute in ("edges", "nodes", "results"):
            value = getattr(response, attribute, None)
            if isinstance(value, list):
                return value
        if isinstance(response, list):
            return response
        return []

    def search(
        self, query: str, group_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        if not group_id:
            raise ProjectionError("group_id is required for Zep graph search")
        if not self.circuit.can_execute():
            raise ProjectionError("Zep circuit is open")
        try:
            response = self.client.graph.search(
                group_id=group_id,
                query=query,
                scope="edges",
                limit=limit,
            )
            self._record_success()
        except Exception as exc:
            self._record_failure(exc)
            raise ProjectionError(f"Zep graph search failed: {exc}") from exc
        results: list[dict[str, Any]] = []
        for item in self._result_items(response):
            attributes = getattr(item, "attributes", {}) or {}
            fact = (
                getattr(item, "fact", None)
                or getattr(item, "content", None)
                or getattr(item, "summary", None)
                or ""
            )
            score = getattr(item, "relevance", None)
            if score is None:
                score = getattr(item, "score", 0.0)
            results.append(
                {
                    "content": str(fact),
                    "score": float(score or 0.0),
                    "metadata": attributes if isinstance(attributes, dict) else {},
                    "uuid": str(getattr(item, "uuid", "")),
                }
            )
        return results
