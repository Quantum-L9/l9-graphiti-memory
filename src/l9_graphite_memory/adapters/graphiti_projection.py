# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/graphiti_projection.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Map canonical memory records to Graphiti/Zep transport operations."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

from l9_graphite_memory.contracts import MemoryRecord, RetirementMode
from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.ports import ProjectionHit
from l9_graphite_memory.transport import MemoryTransport

_RECORD_ID_PATTERN = re.compile(r'"record_id"\s*:\s*"([0-9a-fA-F-]{36})"')


class GraphitiProjection:
    name = "graphiti"
    capabilities: tuple[str, ...] = ("graph-search", "semantic-search")
    # Graphiti exposes delete_episode and no deactivation primitive, so
    # retirement removes the projected episode and is undone by re-projection
    # rather than by reactivating in place (ADR-076).
    retirement_mode = RetirementMode.WITHDRAW

    def __init__(self, transport: MemoryTransport) -> None:
        self.transport = transport

    def health(self) -> dict[str, Any]:
        result = self.transport.health()
        return {"name": self.name, "transport": self.transport.name, **result}

    @staticmethod
    def _projection_payload(record: MemoryRecord) -> dict[str, Any]:
        return {
            "record_id": str(record.record_id),
            "schema_version": record.schema_version,
            "namespace": record.namespace,
            "memory_class": record.memory_class.value,
            "content": record.content,
            "assertion": record.assertion.model_dump(mode="json")
            if record.assertion
            else None,
            "valid_from": record.temporal.valid_from.isoformat(),
            "valid_to": record.temporal.valid_to.isoformat()
            if record.temporal.valid_to
            else None,
            "recorded_at": record.temporal.recorded_at.isoformat(),
            "confidence": record.confidence.score,
            "tags": list(record.tags),
            "source_digest": record.provenance.source_digest,
        }

    @classmethod
    def _extract_locator(cls, result: Any) -> str | None:
        if isinstance(result, dict):
            for key in ("locator", "episode_uuid", "episode_id", "uuid", "id"):
                value = result.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
            for key in ("result", "data", "episode"):
                nested = cls._extract_locator(result.get(key))
                if nested:
                    return nested
        return None

    def project(self, record: MemoryRecord) -> dict[str, Any]:
        payload = self._projection_payload(record)
        result = self.transport.write(
            json.dumps(payload, sort_keys=True),
            record.namespace,
            kind=record.memory_class.value,
            name=f"memory:{record.record_id}",
            source="json",
            source_description="l9-memory canonical outbox projection",
            uuid=str(record.record_id),
            metadata={
                "record_id": str(record.record_id),
                "schema_version": record.schema_version,
                "memory_class": record.memory_class.value,
            },
        )
        if not isinstance(result, dict):
            result = {"result": result}
        if result.get("error"):
            raise ProjectionError(f"projection write failed: {result['error']}")
        locator = self._extract_locator(result) or str(record.record_id)
        return {**result, "locator": locator, "record_id": str(record.record_id)}

    def retire(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Withdraw a superseded or archived episode from the graph.

        Graphiti exposes no native "mark inactive" primitive, so withdrawing a
        projection means removing the projected episode with ``delete_episode``.
        That shared primitive is the only overlap with erasure: retirement
        leaves the canonical record whole, produces no deletion receipt and no
        tombstone, and the projection is rebuildable from canonical state at
        any time (ADR-074).
        """

        if not locator or not locator.strip():
            raise ProjectionError(
                f"projection locator missing for record {record_id} in namespace {namespace}"
            )
        tools = set(self.transport.list_tools())
        if "delete_episode" not in tools:
            raise ProjectionError(
                f"transport {self.transport.name} does not expose delete_episode; "
                "projection retirement cannot complete"
            )
        result = self.transport.call_tool("delete_episode", {"uuid": locator})
        if isinstance(result, dict) and result.get("error"):
            raise ProjectionError(f"projection retirement failed: {result['error']}")
        return {
            "retired": True,
            "erased": False,
            "record_id": str(record_id),
            "namespace": namespace,
            "locator": locator,
            "reason": reason,
            "provider_result": result,
        }

    def erase(
        self,
        record_id: UUID,
        namespace: str,
        *,
        locator: str | None = None,
    ) -> dict[str, Any]:
        if not locator or not locator.strip():
            raise ProjectionError(
                f"projection locator missing for record {record_id} in namespace {namespace}"
            )
        tools = set(self.transport.list_tools())
        if "delete_episode" not in tools:
            raise ProjectionError(
                f"transport {self.transport.name} does not expose delete_episode; "
                "verified projection erasure cannot complete"
            )
        result = self.transport.call_tool("delete_episode", {"uuid": locator})
        if isinstance(result, dict) and result.get("error"):
            raise ProjectionError(f"projection erasure failed: {result['error']}")
        return {
            "erased": True,
            "record_id": str(record_id),
            "namespace": namespace,
            "locator": locator,
            "provider_result": result,
        }

    @staticmethod
    def _extract_record_id(item: dict[str, Any]) -> UUID | None:
        metadata = item.get("metadata")
        containers: tuple[dict[str, Any], ...] = (
            item,
            metadata if isinstance(metadata, dict) else {},
        )
        for container in containers:
            value = container.get("record_id")
            if value:
                try:
                    return UUID(str(value))
                except ValueError:
                    pass
        for field in ("content", "body", "fact", "summary"):
            text = item.get(field)
            if isinstance(text, str):
                match = _RECORD_ID_PATTERN.search(text)
                if match:
                    return UUID(match.group(1))
        return None

    @staticmethod
    def _result_items(result: Any, strategy: str) -> list[dict[str, Any]]:
        if isinstance(result, dict):
            key = "nodes" if strategy == "graph-search" else "facts"
            values = result.get(key) or result.get("results") or []
        else:
            values = result
        if not isinstance(values, list):
            return []
        return [
            item if isinstance(item, dict) else {"content": str(item)}
            for item in values
        ]

    def search_strategy(
        self,
        strategy: str,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
    ) -> list[ProjectionHit]:
        if strategy not in self.capabilities:
            raise ProjectionError(f"unsupported projection strategy: {strategy}")
        tools = set(self.transport.list_tools())
        official_dialect = "search_memory_facts" in tools or "add_memory" in tools
        if strategy == "graph-search":
            tool = "search_nodes"
            limit_key = "max_nodes"
        else:
            tool = (
                "search_memory_facts"
                if "search_memory_facts" in tools
                else "search_facts"
            )
            limit_key = "max_facts"
        if tool not in tools:
            raise ProjectionError(
                f"transport {self.transport.name} does not expose {tool}"
            )
        hits: dict[UUID, ProjectionHit] = {}
        per_namespace = max(1, limit // max(1, len(namespaces)))
        for namespace in namespaces:
            arguments: dict[str, Any] = {"query": query, limit_key: per_namespace}
            if official_dialect:
                arguments["group_ids"] = [namespace]
            else:
                arguments["group_id"] = namespace
            result = self.transport.call_tool(tool, arguments)
            for item in self._result_items(result, strategy):
                record_id = self._extract_record_id(item)
                if record_id is None:
                    continue
                raw_score = item.get("relevance", item.get("score", 0.0))
                try:
                    score = max(0.0, min(float(raw_score), 1.0))
                except (TypeError, ValueError):
                    score = 0.0
                hit = ProjectionHit(
                    record_id=record_id,
                    score=score,
                    excerpt=str(
                        item.get("content")
                        or item.get("fact")
                        or item.get("summary")
                        or ""
                    )[:1_000],
                    metadata={
                        "namespace": namespace,
                        "transport": self.transport.name,
                        "strategy": strategy,
                        "tool": tool,
                    },
                )
                existing = hits.get(record_id)
                if existing is None or hit.score > existing.score:
                    hits[record_id] = hit
        return sorted(hits.values(), key=lambda item: item.score, reverse=True)[:limit]

    def search(
        self, query: str, namespaces: tuple[str, ...], *, limit: int
    ) -> list[ProjectionHit]:
        combined: dict[UUID, ProjectionHit] = {}
        failures: list[str] = []
        for strategy in self.capabilities:
            try:
                for hit in self.search_strategy(
                    strategy, query, namespaces, limit=limit
                ):
                    existing = combined.get(hit.record_id)
                    if existing is None or hit.score > existing.score:
                        combined[hit.record_id] = hit
            except ProjectionError as exc:
                failures.append(f"{strategy}: {exc}")
        if failures and not combined:
            raise ProjectionError("; ".join(failures))
        return sorted(combined.values(), key=lambda item: item.score, reverse=True)[
            :limit
        ]
