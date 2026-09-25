# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/graph/service.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Governed graph-intelligence service (ADR-086).

``GraphIntelligenceService`` sits above ``GraphIntelligencePort``. For every
operation it:

1. authorizes each requested namespace for READ against the principal's
   server-side claims (ADR-006) — the tenant is the principal's, never a
   request field;
2. derives the exact GraphScopeKey v1 groups for those namespaces (ADR-084);
3. rejects out-of-policy requests before any provider call — relationship
   types outside the allowlist, inadmissible or over-mature algorithms,
   disabled link prediction, anchors that are not the principal's records;
4. invokes the port with a typed provider request;
5. binds every provider observation back to canonical records
   (``CanonicalEvidenceLinker``) and applies the cardinality caps
   deterministically;
6. returns a typed, deterministic ``GraphIntelligenceReceipt``.

Provider failure is ``FAILED`` (or ``PARTIAL``) with a normalized error class,
never an empty ``COMPLETE`` (GI-029). A request marked ``required`` fails
closed on any partial outcome (GI-030).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from l9_graphite_memory.authz import NamespacePolicy
from l9_graphite_memory.contracts import AuthorizationAction, MemoryPrincipal, MemoryState
from l9_graphite_memory.errors import GraphCapabilityUnavailable, GraphQueryPolicyViolation
from l9_graphite_memory.ports import RecordStore

from .algorithm_policy import AlgorithmPolicy, GraphAlgorithm, algorithm_identity
from .contracts import (
    GraphAlgorithmIdentity,
    GraphIntelligenceReceipt,
    GraphIntelligenceRequest,
    GraphOperation,
    GraphProviderIdentity,
    GraphProviderRequest,
    GraphProviderResult,
    GraphReceiptStatus,
)
from .evidence import CanonicalEvidenceLinker, EvidenceScope, LinkedEvidence
from .ports import (
    DEFAULT_RELATIONSHIP_ALLOWLIST,
    PORT_METHODS,
    GraphBackendHealth,
    GraphCapability,
    GraphIntelligencePort,
)
from .scope import GRAPH_SCOPE_SCHEME, graph_group_ids, graph_scope_digest


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def graph_request_scope_digest(tenant_id: str, namespaces: tuple[str, ...]) -> str:
    """Digest binding the tenant and the exact authorized namespace set."""

    return _canonical_digest(
        {
            "scheme": GRAPH_SCOPE_SCHEME,
            "tenant_digest": hashlib.sha256(tenant_id.encode("utf-8")).hexdigest(),
            "namespace_digests": sorted(graph_scope_digest(tenant_id, ns) for ns in namespaces),
        }
    )


@dataclass(frozen=True)
class GraphServiceConfig:
    """Service-level policy. Derived from ``MemorySettings`` by the runtime."""

    max_runtime_ms: int = 3_000
    relationship_allowlist: tuple[str, ...] = DEFAULT_RELATIONSHIP_ALLOWLIST
    algorithm_policy: AlgorithmPolicy = field(default_factory=AlgorithmPolicy)
    required: bool = False
    projection_provider: str = "graphiti"
    graphiti_version: str | None = None
    health_ttl_seconds: float = 30.0
    raw_vectors_allowed: bool = False


class GraphIntelligenceService:
    def __init__(
        self,
        store: RecordStore,
        port: GraphIntelligencePort,
        *,
        namespace_policy: NamespacePolicy | None = None,
        config: GraphServiceConfig | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.port = port
        self.namespace_policy = namespace_policy or NamespacePolicy()
        self.config = config or GraphServiceConfig()
        self.linker = CanonicalEvidenceLinker(store)
        self._monotonic = monotonic
        self._health: GraphBackendHealth | None = None
        self._health_at = 0.0

    # -- backend state -------------------------------------------------

    def health(self, *, refresh: bool = False) -> GraphBackendHealth:
        now = self._monotonic()
        if (
            refresh
            or self._health is None
            or now - self._health_at >= self.config.health_ttl_seconds
        ):
            self._health = self.port.health()
            self._health_at = now
        return self._health

    def capabilities(self) -> tuple[GraphCapability, ...]:
        return self.health().capabilities

    def _provider_identity(self, health: GraphBackendHealth) -> GraphProviderIdentity:
        return GraphProviderIdentity(
            projection_provider=self.config.projection_provider,
            graph_backend=self.port.name,
            graphiti_version=self.config.graphiti_version,
            backend_version=health.backend_version,
            gds_version=health.analytics_version,
        )

    # -- execution -----------------------------------------------------

    def execute(
        self, principal: MemoryPrincipal, request: GraphIntelligenceRequest
    ) -> GraphIntelligenceReceipt:
        namespaces = request.namespaces
        for namespace in namespaces:
            self.namespace_policy.require(principal, AuthorizationAction.READ, namespace)
        tenant_id = principal.tenant_id
        group_ids = graph_group_ids(tenant_id, namespaces)
        scope_digest = graph_request_scope_digest(tenant_id, namespaces)
        required = request.required or self.config.required
        relationship_types = request.relationship_types or self.config.relationship_allowlist
        limits = request.limits.model_copy(
            update={
                "max_runtime_ms": min(request.limits.max_runtime_ms, self.config.max_runtime_ms)
            }
        )
        limits_applied: dict[str, Any] = {
            **limits.model_dump(),
            "relationship_types": list(relationship_types),
            "direction": request.direction,
            "as_of": request.as_of.isoformat() if request.as_of else None,
            "recorded_before": request.recorded_before.isoformat()
            if request.recorded_before
            else None,
        }
        health = self.health()
        provider = self._provider_identity(health)

        def refuse(
            failure_class: str, stage: str, algorithm: GraphAlgorithmIdentity | None = None
        ) -> GraphIntelligenceReceipt:
            return self._receipt(
                GraphReceiptStatus.FAILED,
                request.operation,
                scope_digest,
                provider,
                algorithm,
                limits_applied,
                LinkedEvidence(),
                [{"class": failure_class, "stage": stage}],
            )

        disallowed = [r for r in relationship_types if r not in self.config.relationship_allowlist]
        if disallowed:
            return refuse("relationship_type_not_allowed", "policy")
        method_name = PORT_METHODS.get(request.operation)
        if (
            method_name is None
            or GraphCapability(request.operation.value) not in health.capabilities
        ):
            return refuse("capability_unavailable", "capability")
        try:
            algorithm = self.config.algorithm_policy.resolve(request.operation, request.algorithm)
        except GraphQueryPolicyViolation:
            return refuse("algorithm_not_admitted", "policy")
        algorithm_config = self._algorithm_config(algorithm, limits_applied)
        identity = algorithm_identity(algorithm, algorithm_config)
        for anchor in (request.anchor, request.target):
            if anchor is not None and anchor.record_id is not None:
                record = self.store.get_record(anchor.record_id)
                if (
                    record is None
                    or record.tenant_id != tenant_id
                    or record.namespace not in namespaces
                    or record.state is not MemoryState.ACTIVE
                ):
                    # Same answer whether the record is absent or foreign.
                    return refuse("anchor_not_in_scope", "anchor", identity)

        provider_request = GraphProviderRequest(
            operation=request.operation,
            group_ids=group_ids,
            anchor=request.anchor,
            target=request.target,
            relationship_types=relationship_types,
            direction=request.direction,
            as_of=request.as_of,
            limits=limits,
            algorithm_id=algorithm.id,
            algorithm_config=algorithm_config,
            operation_id=_canonical_digest(
                {"scope": scope_digest, "request": request.contract_payload()}
            )[:32],
        )
        try:
            result: GraphProviderResult = getattr(self.port, method_name)(provider_request)
        except GraphCapabilityUnavailable:
            return refuse("capability_unavailable", "provider", identity)
        except GraphQueryPolicyViolation:
            return refuse("query_policy_violation", "provider", identity)
        except Exception as exc:  # noqa: BLE001 - normalized; raw text never escapes
            return refuse(f"provider_error:{type(exc).__name__}", "provider", identity)

        linked = self.linker.link(
            result,
            EvidenceScope(
                tenant_id=tenant_id,
                namespaces=frozenset(namespaces),
                group_ids=frozenset(group_ids),
                as_of=request.as_of,
                recorded_before=request.recorded_before,
                include_raw_vectors=self.config.raw_vectors_allowed,
            ),
        )
        failures: list[dict[str, Any]] = []
        if linked.rehydration_error is not None:
            failures.append(
                {"class": f"rehydration_error:{linked.rehydration_error}", "stage": "evidence"}
            )
        truncated = result.truncated or self._apply_caps(linked, limits_applied)
        if truncated:
            failures.append({"class": "truncated", "stage": "limits"})
        if linked.out_of_scope_dropped:
            failures.append(
                {
                    "class": "out_of_scope_dropped",
                    "stage": "evidence",
                    "count": linked.out_of_scope_dropped,
                }
            )
        status = GraphReceiptStatus.COMPLETE
        if failures:
            status = GraphReceiptStatus.FAILED if required else GraphReceiptStatus.PARTIAL
        if status is GraphReceiptStatus.FAILED:
            linked = LinkedEvidence()
        return self._receipt(
            status,
            request.operation,
            scope_digest,
            provider,
            identity,
            limits_applied,
            linked,
            failures,
        )

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _algorithm_config(algorithm: GraphAlgorithm, limits: dict[str, Any]) -> dict[str, Any]:
        return {
            "algorithm": algorithm.id,
            "max_depth": limits["max_depth"],
            "max_nodes": limits["max_nodes"],
            "max_edges": limits["max_edges"],
            "max_paths": limits["max_paths"],
            "relationship_types": limits["relationship_types"],
            "direction": limits["direction"],
        }

    @staticmethod
    def _apply_caps(linked: LinkedEvidence, limits: dict[str, Any]) -> bool:
        caps = {
            "node": limits["max_nodes"],
            "edge": limits["max_edges"],
            "path": limits["max_paths"],
            "score": limits["max_nodes"],
        }
        kept: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        truncated = False
        for item in linked.results:
            kind = item["kind"]
            counts[kind] = counts.get(kind, 0) + 1
            if counts[kind] > caps.get(kind, limits["max_nodes"]):
                truncated = True
                continue
            kept.append(item)
        if truncated:
            linked.results = kept
            support = {rid for item in kept for rid in item["supporting_record_ids"]}
            linked.supporting_record_ids = [
                r for r in linked.supporting_record_ids if str(r) in support
            ]
        return truncated

    @staticmethod
    def _receipt(
        status: GraphReceiptStatus,
        operation: GraphOperation,
        scope_digest: str,
        provider: GraphProviderIdentity,
        algorithm: GraphAlgorithmIdentity | None,
        limits_applied: dict[str, Any],
        linked: LinkedEvidence,
        failures: list[dict[str, Any]],
    ) -> GraphIntelligenceReceipt:
        body = {
            "status": status.value,
            "operation": operation.value,
            "scope_digest": scope_digest,
            "algorithm": algorithm.model_dump() if algorithm else None,
            "results": linked.results,
            "supporting_record_ids": [str(r) for r in linked.supporting_record_ids],
            "unsupported": linked.unsupported,
            "failures": failures,
        }
        return GraphIntelligenceReceipt(
            status=status,
            operation=operation,
            scope_digest=scope_digest,
            provider=provider,
            algorithm=algorithm,
            limits_applied=limits_applied,
            results=tuple(linked.results),
            supporting_record_ids=tuple(linked.supporting_record_ids),
            unsupported_projection_observations=tuple(linked.unsupported),
            failures=tuple(failures),
            result_digest=_canonical_digest(body),
        )
