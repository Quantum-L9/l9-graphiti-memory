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
from l9_graphite_memory.graph import (
    GRAPH_SCOPE_SCHEME,
    graph_group_id,
    graph_scope_digest,
)
from l9_graphite_memory.ports import ProjectionHit
from l9_graphite_memory.transport import MemoryTransport

_RECORD_ID_PATTERN = re.compile(r'"record_id"\s*:\s*"([0-9a-fA-F-]{36})"')

# Graphiti (v0.30.2) treats a caller-supplied episode uuid as "update the
# existing episode" and fails when none exists; the official MCP server queues
# that write and swallows the failure. Episodes are therefore created with a
# provider-issued uuid and located by their canonical name (ADR-090).
EPISODE_NAME_LOCATOR = "graphiti-episode-name"


def episode_name(record_id: UUID | str) -> str:
    """Canonical Graphiti episode name for a memory record."""

    return f"memory:{record_id}"


def episode_name_locator(group_id: str, record_id: UUID | str) -> str:
    """Locator naming a projected episode by provider group and canonical name."""

    return f"{EPISODE_NAME_LOCATOR}:{group_id}:{episode_name(record_id)}"


def parse_episode_name_locator(locator: str) -> tuple[str, str] | None:
    """Return ``(group_id, episode_name)`` for a name locator, else ``None``."""

    prefix = f"{EPISODE_NAME_LOCATOR}:"
    if not locator.startswith(prefix):
        return None
    group_id, separator, name = locator[len(prefix) :].partition(":")
    if not separator or not group_id or not name.startswith("memory:"):
        return None
    return group_id, name


class GraphitiProjection:
    name = "graphiti"
    capabilities: tuple[str, ...] = ("graph-search", "semantic-search")
    # Graphiti exposes delete_episode and no deactivation primitive, so
    # retirement removes the projected episode and is undone by re-projection
    # rather than by reactivating in place (ADR-076).
    retirement_mode = RetirementMode.WITHDRAW
    # Provider group identity scheme (ADR-084). Persisted on each projection
    # link so a rebuild can find records projected under an older scheme.
    scope_scheme: str = GRAPH_SCOPE_SCHEME

    def __init__(self, transport: MemoryTransport, *, episode_lookup_limit: int = 1000) -> None:
        if episode_lookup_limit < 1:
            raise ValueError("episode_lookup_limit must be positive")
        self.transport = transport
        # Upper bound on episodes listed per group when resolving a name
        # locator; a miss fails closed rather than reporting a false removal.
        self.episode_lookup_limit = episode_lookup_limit

    def health(self) -> dict[str, Any]:
        result = self.transport.health()
        return {"name": self.name, "transport": self.transport.name, **result}

    @staticmethod
    def _projection_payload(record: MemoryRecord) -> dict[str, Any]:
        return {
            "record_id": str(record.record_id),
            "schema_version": record.schema_version,
            "namespace": record.namespace,
            # Scope binding is carried as a digest only; the raw tenant id is
            # never written into the provider graph (ADR-084).
            "scope_scheme": GRAPH_SCOPE_SCHEME,
            "scope_digest": graph_scope_digest(record.tenant_id, record.namespace),
            "memory_class": record.memory_class.value,
            "content": record.content,
            "assertion": record.assertion.model_dump(mode="json") if record.assertion else None,
            "valid_from": record.temporal.valid_from.isoformat(),
            "valid_to": record.temporal.valid_to.isoformat() if record.temporal.valid_to else None,
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
        group_id = graph_group_id(record.tenant_id, record.namespace)
        # No ``uuid`` argument: Graphiti would treat it as an update of an
        # existing episode (ADR-090). The canonical name carries the mapping.
        result = self.transport.write(
            json.dumps(payload, sort_keys=True),
            group_id,
            kind=record.memory_class.value,
            name=episode_name(record.record_id),
            source="json",
            source_description="l9-memory canonical outbox projection",
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
        locator = self._extract_locator(result) or episode_name_locator(group_id, record.record_id)
        return {
            **result,
            "locator": locator,
            "record_id": str(record.record_id),
            "scope_scheme": GRAPH_SCOPE_SCHEME,
        }

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
        result = self._delete_projected(locator, action="retirement")
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
        result = self._delete_projected(locator, action="erasure")
        return {
            "erased": True,
            "record_id": str(record_id),
            "namespace": namespace,
            "locator": locator,
            "provider_result": result,
        }

    def _resolve_episode_uuids(self, group_id: str, name: str, *, action: str) -> list[str]:
        """Resolve a name locator to the provider's episode uuids in one group."""

        if "get_episodes" not in set(self.transport.list_tools()):
            raise ProjectionError(
                f"transport {self.transport.name} does not expose get_episodes; "
                f"projection {action} cannot resolve episode {name}"
            )
        listing = self.transport.call_tool(
            "get_episodes",
            {"group_ids": [group_id], "max_episodes": self.episode_lookup_limit},
        )
        if isinstance(listing, dict) and listing.get("error"):
            raise ProjectionError(f"projection {action} lookup failed: {listing['error']}")
        episodes = listing.get("episodes") if isinstance(listing, dict) else listing
        matches = sorted(
            {
                str(item["uuid"])
                for item in episodes or []
                if isinstance(item, dict)
                and item.get("uuid")
                and item.get("name") == name
                and item.get("group_id", group_id) == group_id
            }
        )
        if not matches:
            # Not yet ingested (Graphiti ingests asynchronously), never
            # ingested, or outside the lookup window: none of these proves the
            # episode is absent, so the operation fails closed and is retried.
            raise ProjectionError(
                f"projected episode {name} not found in its graph scope within "
                f"{self.episode_lookup_limit} episodes; projection {action} cannot be verified"
            )
        return matches

    def _episode_records(self, group_id: str) -> dict[str, UUID]:
        """Provider episode uuid -> record id for one group, from episode names.

        Best effort and bounded by ``episode_lookup_limit``: an episode outside
        the window or a failed listing contributes no hit. Hits are advisory;
        canonical rehydration decides what is served.
        """

        listing = self.transport.call_tool(
            "get_episodes",
            {"group_ids": [group_id], "max_episodes": self.episode_lookup_limit},
        )
        if isinstance(listing, dict) and listing.get("error"):
            return {}
        episodes = listing.get("episodes") if isinstance(listing, dict) else listing
        mapping: dict[str, UUID] = {}
        for item in episodes or []:
            if not isinstance(item, dict) or item.get("group_id", group_id) != group_id:
                continue
            name = str(item.get("name") or "")
            if not name.startswith("memory:") or not item.get("uuid"):
                continue
            try:
                mapping[str(item["uuid"])] = UUID(name.removeprefix("memory:"))
            except ValueError:
                continue
        return mapping

    def _delete_projected(self, locator: str, *, action: str) -> Any:
        tools = set(self.transport.list_tools())
        if "delete_episode" not in tools:
            raise ProjectionError(
                f"transport {self.transport.name} does not expose delete_episode; "
                f"projection {action} cannot complete"
            )
        parsed = parse_episode_name_locator(locator)
        episode_uuids = (
            self._resolve_episode_uuids(parsed[0], parsed[1], action=action)
            if parsed
            else [locator]
        )
        results: list[Any] = []
        for episode_uuid in episode_uuids:
            result = self.transport.call_tool("delete_episode", {"uuid": episode_uuid})
            if isinstance(result, dict) and result.get("error"):
                raise ProjectionError(f"projection {action} failed: {result['error']}")
            results.append(result)
        if not parsed:
            return results[0]
        return {"deleted_episode_uuids": episode_uuids, "results": results}

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
        return [item if isinstance(item, dict) else {"content": str(item)} for item in values]

    def search_strategy(
        self,
        strategy: str,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
        tenant_id: str,
    ) -> list[ProjectionHit]:
        if strategy not in self.capabilities:
            raise ProjectionError(f"unsupported projection strategy: {strategy}")
        tools = set(self.transport.list_tools())
        official_dialect = "search_memory_facts" in tools or "add_memory" in tools
        if strategy == "graph-search":
            tool = "search_nodes"
            limit_key = "max_nodes"
        else:
            tool = "search_memory_facts" if "search_memory_facts" in tools else "search_facts"
            limit_key = "max_facts"
        if tool not in tools:
            raise ProjectionError(f"transport {self.transport.name} does not expose {tool}")
        hits: dict[UUID, ProjectionHit] = {}
        per_namespace = max(1, limit // max(1, len(namespaces)))
        for namespace in namespaces:
            # Each authorized namespace maps to exactly one tenant-bound group;
            # no request field can widen or replace it (ADR-084).
            group_id = graph_group_id(tenant_id, namespace)
            arguments: dict[str, Any] = {"query": query, limit_key: per_namespace}
            if official_dialect:
                arguments["group_ids"] = [group_id]
            else:
                arguments["group_id"] = group_id
            result = self.transport.call_tool(tool, arguments)
            episode_records: dict[str, UUID] | None = None
            for item in self._result_items(result, strategy):
                record_ids: list[UUID] = []
                record_id = self._extract_record_id(item)
                if record_id is not None:
                    record_ids.append(record_id)
                elif item.get("episodes") and "get_episodes" in tools:
                    # Graphiti facts cite provider episode uuids, not record
                    # ids; the episode name carries the mapping (ADR-090).
                    if episode_records is None:
                        episode_records = self._episode_records(group_id)
                    record_ids.extend(
                        episode_records[str(episode)]
                        for episode in item["episodes"]
                        if str(episode) in episode_records
                    )
                raw_score = item.get("relevance", item.get("score", 0.0))
                try:
                    score = max(0.0, min(float(raw_score), 1.0))
                except (TypeError, ValueError):
                    score = 0.0
                for record_id in dict.fromkeys(record_ids):
                    hit = ProjectionHit(
                        record_id=record_id,
                        score=score,
                        excerpt=str(
                            item.get("content") or item.get("fact") or item.get("summary") or ""
                        )[:1_000],
                        metadata={
                            "namespace": namespace,
                            "scope_scheme": GRAPH_SCOPE_SCHEME,
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
        self,
        query: str,
        namespaces: tuple[str, ...],
        *,
        limit: int,
        tenant_id: str,
    ) -> list[ProjectionHit]:
        combined: dict[UUID, ProjectionHit] = {}
        failures: list[str] = []
        for strategy in self.capabilities:
            try:
                for hit in self.search_strategy(
                    strategy, query, namespaces, limit=limit, tenant_id=tenant_id
                ):
                    existing = combined.get(hit.record_id)
                    if existing is None or hit.score > existing.score:
                        combined[hit.record_id] = hit
            except ProjectionError as exc:
                failures.append(f"{strategy}: {exc}")
        if failures and not combined:
            raise ProjectionError("; ".join(failures))
        return sorted(combined.values(), key=lambda item: item.score, reverse=True)[:limit]
