# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graph/evidence.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Bind projection-derived graph observations back to canonical memory (ADR-086).

A Graphiti episode UUID is the canonical ``record_id`` (ADR-084), so the
episodes that support an entity, edge, path, or score are candidate canonical
records. Each candidate is re-read from ``RecordStore`` and admitted only when
tenant, authorized namespace, lifecycle state, valid time, and transaction
time all agree with the request (GI-025). An observation with no admitted
support is an ``unsupported_projection_observation`` and is excluded from the
authoritative-facing results (GI-027). A provider item outside the authorized
provider groups is discarded outright (GI-013).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from l9_graphite_memory.contracts import MemoryState
from l9_graphite_memory.ports import RecordStore

from .contracts import (
    AUTHORITY_CLASS,
    GraphProviderEdge,
    GraphProviderNode,
    GraphProviderResult,
    GraphProviderScore,
)


@dataclass(frozen=True)
class EvidenceScope:
    tenant_id: str
    namespaces: frozenset[str]
    group_ids: frozenset[str]
    as_of: datetime | None = None
    recorded_before: datetime | None = None
    include_raw_vectors: bool = False


@dataclass
class LinkedEvidence:
    results: list[dict[str, Any]] = field(default_factory=list)
    supporting_record_ids: list[UUID] = field(default_factory=list)
    unsupported: list[dict[str, Any]] = field(default_factory=list)
    out_of_scope_dropped: int = 0
    temporal_excluded: int = 0
    rehydration_error: str | None = None


def vector_digest(vector: Iterable[float]) -> str:
    material = json.dumps([round(float(v), 8) for v in vector], separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class CanonicalEvidenceLinker:
    """Rehydrates candidate support ids under the request's canonical filters."""

    def __init__(self, store: RecordStore) -> None:
        self.store = store

    def link(self, result: GraphProviderResult, scope: EvidenceScope) -> LinkedEvidence:
        linked = LinkedEvidence()
        admitted: dict[UUID, bool] = {}
        try:
            node_support = self._nodes(result.nodes, scope, linked, admitted)
            edge_support = self._edges(result.edges, scope, linked, admitted)
            self._paths(result, node_support, edge_support, linked)
            self._scores(result.scores, scope, node_support, linked)
        except Exception as exc:  # noqa: BLE001 - reported as a rehydration failure
            linked.rehydration_error = type(exc).__name__
            linked.results.clear()
            linked.supporting_record_ids.clear()
            return linked
        seen: dict[UUID, None] = {}
        for item in linked.results:
            for record_id in item["supporting_record_ids"]:
                seen.setdefault(UUID(record_id), None)
        linked.supporting_record_ids = sorted(seen, key=str)
        return linked

    def admit(self, record_id: UUID, scope: EvidenceScope, cache: dict[UUID, bool]) -> bool:
        """Whether one candidate id is an admitted canonical record in scope."""

        if record_id in cache:
            return cache[record_id]
        record = self.store.get_record(record_id)
        ok = (
            record is not None
            and record.tenant_id == scope.tenant_id
            and record.namespace in scope.namespaces
            and record.state is MemoryState.ACTIVE
            and (scope.as_of is None or record.temporal.is_valid_at(scope.as_of))
            and (
                scope.recorded_before is None
                or record.temporal.recorded_at <= scope.recorded_before
            )
        )
        cache[record_id] = ok
        return ok

    def _support(
        self, candidates: tuple[UUID, ...], scope: EvidenceScope, cache: dict[UUID, bool]
    ) -> list[str]:
        return sorted({str(c) for c in candidates if self.admit(c, scope, cache)})

    def _nodes(
        self,
        nodes: tuple[GraphProviderNode, ...],
        scope: EvidenceScope,
        linked: LinkedEvidence,
        cache: dict[UUID, bool],
    ) -> dict[UUID, list[str]]:
        support_by_node: dict[UUID, list[str]] = {}
        for node in sorted(nodes, key=lambda n: str(n.entity_uuid)):
            if node.group_id not in scope.group_ids:
                linked.out_of_scope_dropped += 1
                continue
            support = self._support(node.supporting_episode_ids, scope, cache)
            if not support:
                linked.unsupported.append(
                    {
                        "kind": "node",
                        "entity_uuid": str(node.entity_uuid),
                        "reason": "no_canonical_support",
                    }
                )
                continue
            support_by_node[node.entity_uuid] = support
            linked.results.append(
                {
                    "kind": "node",
                    "entity_uuid": str(node.entity_uuid),
                    "labels": list(node.labels),
                    "name": node.name,
                    "supporting_record_ids": support,
                    "authority_class": AUTHORITY_CLASS,
                }
            )
        return support_by_node

    def _edges(
        self,
        edges: tuple[GraphProviderEdge, ...],
        scope: EvidenceScope,
        linked: LinkedEvidence,
        cache: dict[UUID, bool],
    ) -> dict[UUID, list[str]]:
        """Admit edges with canonical support; return support by edge uuid."""

        edge_support: dict[UUID, list[str]] = {}
        ordered = sorted(
            edges,
            key=lambda e: (
                str(e.source_uuid),
                e.relationship_type,
                str(e.target_uuid),
                str(e.edge_uuid),
            ),
        )
        for edge in ordered:
            if edge.group_id not in scope.group_ids:
                linked.out_of_scope_dropped += 1
                continue
            if scope.as_of is not None and (
                (edge.valid_at is not None and edge.valid_at > scope.as_of)
                or (edge.invalid_at is not None and edge.invalid_at <= scope.as_of)
            ):
                linked.temporal_excluded += 1
                continue
            support = self._support(edge.supporting_episode_ids, scope, cache)
            identity = {
                "edge_uuid": str(edge.edge_uuid) if edge.edge_uuid else None,
                "source_uuid": str(edge.source_uuid),
                "target_uuid": str(edge.target_uuid),
                "relationship_type": edge.relationship_type,
            }
            if not support:
                linked.unsupported.append(
                    {"kind": "edge", **identity, "reason": "no_canonical_support"}
                )
                continue
            linked.results.append(
                {
                    "kind": "edge",
                    **identity,
                    "fact": edge.fact,
                    "valid_at": edge.valid_at.isoformat() if edge.valid_at else None,
                    "invalid_at": edge.invalid_at.isoformat() if edge.invalid_at else None,
                    "supporting_record_ids": support,
                    "authority_class": AUTHORITY_CLASS,
                }
            )
            if edge.edge_uuid is not None:
                edge_support[edge.edge_uuid] = support
        return edge_support

    @staticmethod
    def _paths(
        result: GraphProviderResult,
        node_support: dict[UUID, list[str]],
        edge_support: dict[UUID, list[str]],
        linked: LinkedEvidence,
    ) -> None:
        """Admit a path only when every node and every relationship is supported.

        Node evidence says nothing about the relationship between two nodes;
        a hop whose edge was not admitted (or cannot be identified) makes the
        path unsupported rather than borrowing its endpoints' support.
        """

        for path in result.paths:
            identity = {
                "node_uuids": [str(n) for n in path.node_uuids],
                "edge_uuids": [str(e) for e in path.edge_uuids],
                "length": path.length,
            }
            if not all(node in node_support for node in path.node_uuids):
                linked.unsupported.append({"kind": "path", **identity, "reason": "unsupported_hop"})
                continue
            if len(path.edge_uuids) != path.length or not all(
                edge in edge_support for edge in path.edge_uuids
            ):
                linked.unsupported.append(
                    {"kind": "path", **identity, "reason": "unsupported_relationship"}
                )
                continue
            support = sorted(
                {rid for node in path.node_uuids for rid in node_support[node]}
                | {rid for edge in path.edge_uuids for rid in edge_support[edge]}
            )
            linked.results.append(
                {
                    "kind": "path",
                    **identity,
                    "weight": path.weight,
                    "supporting_record_ids": support,
                    "authority_class": AUTHORITY_CLASS,
                }
            )

    @staticmethod
    def _scores(
        scores: tuple[GraphProviderScore, ...],
        scope: EvidenceScope,
        node_support: dict[UUID, list[str]],
        linked: LinkedEvidence,
    ) -> None:
        for score in scores:
            if score.group_id not in scope.group_ids:
                linked.out_of_scope_dropped += 1
                continue
            members = [score.entity_uuid] + ([score.target_uuid] if score.target_uuid else [])
            identity: dict[str, Any] = {
                "entity_uuid": str(score.entity_uuid),
                "target_uuid": str(score.target_uuid) if score.target_uuid else None,
            }
            if not all(member in node_support for member in members):
                linked.unsupported.append(
                    {"kind": "score", **identity, "reason": "unsupported_node"}
                )
                continue
            item: dict[str, Any] = {
                "kind": "score",
                **identity,
                "score": score.score,
                "community_id": score.community_id,
                "supporting_record_ids": sorted({rid for m in members for rid in node_support[m]}),
                "authority_class": AUTHORITY_CLASS,
            }
            if score.embedding is not None:
                item["embedding_digest"] = vector_digest(score.embedding)
                item["embedding_dimension"] = len(score.embedding)
                if scope.include_raw_vectors:
                    item["embedding"] = list(score.embedding)
            linked.results.append(item)
