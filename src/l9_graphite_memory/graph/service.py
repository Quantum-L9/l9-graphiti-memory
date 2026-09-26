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

import contextvars
import hashlib
import json
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from l9_graphite_memory.authz import NamespacePolicy
from l9_graphite_memory.contracts import AuthorizationAction, MemoryPrincipal, MemoryState
from l9_graphite_memory.errors import (
    AuthorizationError,
    GraphCapabilityUnavailable,
    GraphQueryPolicyViolation,
    GraphRuntimeBudgetExceeded,
)
from l9_graphite_memory.observability.graph_metrics import GRAPH_METRICS, GraphMetrics
from l9_graphite_memory.ports import ProjectionAdapter, ProjectionHit, RecordStore

from .algorithm_policy import (
    AlgorithmPolicy,
    GraphAlgorithm,
    algorithm_identity,
    algorithm_parameters,
)
from .contracts import (
    GraphAlgorithmIdentity,
    GraphCapabilityReport,
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
from .scope import (
    GRAPH_SCOPE_SCHEME,
    GRAPH_SCOPE_SCHEME_VERSION,
    graph_group_ids,
    graph_scope_digest,
)

#: Candidate-retrieval operations served by the Graphiti projection strategies.
# Smallest budget worth starting a provider operation with; it is also the
# GraphLimits floor for max_runtime_ms.
MIN_PROVIDER_BUDGET_MS = 10

# Worker threads for projection search calls, so a stalled provider cannot
# hold a request past its deadline (ADR-091). Shared and bounded: when every
# worker is busy, a new call waits in the queue and the deadline still applies.
_SEARCH_WORKERS = 8
_search_pool: ThreadPoolExecutor | None = None
_search_pool_lock = threading.Lock()


_REQUEST_WORKERS = 16
_request_pool: ThreadPoolExecutor | None = None


def _request_executor() -> ThreadPoolExecutor:
    """Bounded pool that runs whole graph operations under a caller deadline."""

    global _request_pool
    with _search_pool_lock:
        if _request_pool is None:
            _request_pool = ThreadPoolExecutor(
                max_workers=_REQUEST_WORKERS, thread_name_prefix="l9-graph-request"
            )
        return _request_pool


def _search_executor() -> ThreadPoolExecutor:
    global _search_pool
    with _search_pool_lock:
        if _search_pool is None:
            _search_pool = ThreadPoolExecutor(
                max_workers=_SEARCH_WORKERS, thread_name_prefix="l9-graph-search"
            )
        return _search_pool


SEARCH_STRATEGIES: dict[GraphOperation, str] = {
    GraphOperation.SEARCH: "graph-search",
    GraphOperation.SEMANTIC_SEARCH: "semantic-search",
}


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


def graph_service_for(
    memory: Any,
    port: GraphIntelligencePort,
    *,
    config: GraphServiceConfig | None = None,
) -> GraphIntelligenceService:
    """Compose a graph service over a MemoryService's store, policy, projection."""

    return GraphIntelligenceService(
        memory.store,
        port,
        namespace_policy=memory.namespace_policy,
        config=config,
        projection=memory.projection,
    )


class GraphIntelligenceService:
    def __init__(
        self,
        store: RecordStore,
        port: GraphIntelligencePort,
        *,
        namespace_policy: NamespacePolicy | None = None,
        config: GraphServiceConfig | None = None,
        projection: ProjectionAdapter | None = None,
        metrics: GraphMetrics | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.metrics = metrics or GRAPH_METRICS
        self.store = store
        self.port = port
        self.projection = projection
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
        """Structural capabilities from the port plus projection search strategies."""

        served = list(self.health().capabilities)
        projection_strategies = set(self.projection.capabilities) if self.projection else set()
        served.extend(
            GraphCapability(operation.value)
            for operation, strategy in SEARCH_STRATEGIES.items()
            if strategy in projection_strategies
        )
        return tuple(served)

    def _provider_identity(self, health: GraphBackendHealth) -> GraphProviderIdentity:
        return GraphProviderIdentity(
            projection_provider=self.config.projection_provider,
            graph_backend=self.port.name,
            graphiti_version=self.config.graphiti_version,
            backend_version=health.backend_version,
            gds_version=health.analytics_version,
        )

    def capability_report(self, *, refresh: bool = False) -> GraphCapabilityReport:
        """Typed capability and health report; health dimensions stay separate."""

        backend = self.health(refresh=refresh)
        catalog_failures = getattr(self.port, "catalog_cleanup_failures", 0)
        self.metrics.set_gauge("memory_graph_gds_cleanup_failures_seen", float(catalog_failures))
        return GraphCapabilityReport(
            scope_scheme=GRAPH_SCOPE_SCHEME,
            scope_scheme_version=GRAPH_SCOPE_SCHEME_VERSION,
            capabilities=tuple(capability.value for capability in self.capabilities()),
            backend=backend.model_dump(mode="json"),
            projection_provider=self.projection.name if self.projection else None,
            projection_strategies=tuple(self.projection.capabilities) if self.projection else (),
            algorithm_maturity_ceiling=self.config.algorithm_policy.maturity_ceiling.value,
            link_prediction_enabled=self.config.algorithm_policy.link_prediction_enabled,
            required=self.config.required,
            ready=backend.healthy or not self.config.required,
            gds_catalog_cleanup_failures=int(catalog_failures),
        )

    # -- execution -----------------------------------------------------

    def execute(
        self, principal: MemoryPrincipal, request: GraphIntelligenceRequest
    ) -> GraphIntelligenceReceipt:
        """Run one operation and record its metrics and structured log line."""

        started = self._monotonic()
        budget_ms = min(request.limits.max_runtime_ms, self.config.max_runtime_ms)
        # The whole operation (health, provider, canonical evidence, GDS
        # cleanup, projection transport) runs off-thread; the caller waits at
        # most the request budget and then gets a typed refusal. Work still in
        # flight finishes against its own statement/transport timeouts and its
        # result is discarded (ADR-091).
        future = _request_executor().submit(
            contextvars.copy_context().run, self._execute, principal, request
        )
        try:
            receipt = future.result(timeout=budget_ms / 1_000)
        except FuturesTimeoutError:
            future.cancel()
            receipt = self._deadline_receipt(principal, request)
        except AuthorizationError:
            self.metrics.record_scope_denied(request.operation.value)
            raise
        self.metrics.record_operation(
            operation=request.operation.value,
            status=receipt.status.value,
            latency_ms=(self._monotonic() - started) * 1_000,
            node_count=sum(1 for item in receipt.results if item.get("kind") == "node"),
            edge_count=sum(1 for item in receipt.results if item.get("kind") == "edge"),
            unsupported_reasons=[
                str(item.get("reason", "unknown"))
                for item in receipt.unsupported_projection_observations
            ],
            failure_classes=[str(item.get("class")) for item in receipt.failures],
            provider=receipt.provider.graph_backend,
            scope_digest=receipt.scope_digest,
            algorithm=receipt.algorithm.id if receipt.algorithm else None,
            result_digest=receipt.result_digest,
        )
        return receipt

    def _deadline_receipt(
        self, principal: MemoryPrincipal, request: GraphIntelligenceRequest
    ) -> GraphIntelligenceReceipt:
        """FAILED receipt for an operation still running at its deadline.

        Built without touching the backend: provider identity comes from the
        cached health report when there is one.
        """

        limits = request.limits.model_copy(
            update={
                "max_runtime_ms": min(request.limits.max_runtime_ms, self.config.max_runtime_ms)
            }
        )
        health = self._health or GraphBackendHealth(
            name=self.port.name, enabled=True, healthy=False
        )
        return self._receipt(
            GraphReceiptStatus.FAILED,
            request.operation,
            graph_request_scope_digest(principal.tenant_id, request.namespaces),
            self._provider_identity(health),
            None,
            {**limits.model_dump(), "direction": request.direction},
            LinkedEvidence(),
            [{"class": "runtime_budget_exceeded", "stage": "request"}],
        )

    def _execute(
        self, principal: MemoryPrincipal, request: GraphIntelligenceRequest
    ) -> GraphIntelligenceReceipt:
        namespaces = request.namespaces
        for namespace in namespaces:
            self.namespace_policy.require(principal, AuthorizationAction.READ, namespace)
        # One request-wide deadline: every stage below draws on the same
        # max_runtime_ms instead of each receiving all of it (ADR-091).
        budget_ms = min(request.limits.max_runtime_ms, self.config.max_runtime_ms)
        deadline = self._monotonic() + budget_ms / 1_000

        def remaining_ms() -> int:
            return int((deadline - self._monotonic()) * 1_000)

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

        # Shared request policy runs before any operation-specific path.
        disallowed = [r for r in relationship_types if r not in self.config.relationship_allowlist]
        if disallowed:
            return refuse("relationship_type_not_allowed", "policy")
        if request.operation in SEARCH_STRATEGIES:
            # Search has no traversal: fields that would shape one are refused
            # rather than silently ignored.
            if (
                request.target is not None
                or request.relationship_types
                or request.direction != "both"
            ):
                return refuse("request_field_not_applicable", "policy")
            try:
                search_algorithm = self.config.algorithm_policy.resolve(
                    request.operation, request.algorithm
                )
            except GraphQueryPolicyViolation:
                return refuse("algorithm_not_admitted", "policy")
            return self._search(
                request,
                tenant_id,
                scope_digest,
                provider,
                limits,
                limits_applied,
                required,
                search_algorithm,
                remaining_ms,
            )
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

        budget_left = remaining_ms()
        if budget_left < MIN_PROVIDER_BUDGET_MS:
            return refuse("runtime_budget_exhausted", "limits", identity)
        provider_request = GraphProviderRequest(
            operation=request.operation,
            group_ids=group_ids,
            anchor=request.anchor,
            target=request.target,
            relationship_types=relationship_types,
            direction=request.direction,
            as_of=request.as_of,
            recorded_before=request.recorded_before,
            limits=limits.model_copy(update={"max_runtime_ms": budget_left}),
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
        except GraphRuntimeBudgetExceeded:
            return refuse("runtime_budget_exhausted", "provider", identity)
        except GraphQueryPolicyViolation:
            return refuse("query_policy_violation", "provider", identity)
        except Exception as exc:  # noqa: BLE001 - normalized; raw text never escapes
            return refuse(f"provider_error:{type(exc).__name__}", "provider", identity)
        if remaining_ms() <= 0:
            # The provider answered after the request's hard ceiling; serving
            # it would make max_runtime_ms advisory.
            return refuse("runtime_budget_exceeded", "provider", identity)

        linked = self.linker.link(
            result,
            EvidenceScope(
                tenant_id=tenant_id,
                namespaces=frozenset(namespaces),
                group_ids=frozenset(group_ids),
                as_of=request.as_of,
                recorded_before=request.recorded_before,
                include_raw_vectors=self.config.raw_vectors_allowed,
                path_direction=request.direction,
            ),
        )
        failures: list[dict[str, Any]] = []
        if linked.rehydration_error is not None:
            failures.append(
                {"class": f"rehydration_error:{linked.rehydration_error}", "stage": "evidence"}
            )
        # Caps always apply; a provider-reported truncation must not skip them.
        capped = self._apply_caps(linked, limits_applied)
        truncated = result.truncated or capped
        if truncated:
            failures.append({"class": "truncated", "stage": "limits"})
        if result.provider_metadata.get("catalog_cleanup") == "failed":
            failures.append({"class": "gds_catalog_cleanup_failed", "stage": "provider"})
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

    def _search(
        self,
        request: GraphIntelligenceRequest,
        tenant_id: str,
        scope_digest: str,
        provider: GraphProviderIdentity,
        limits: Any,
        limits_applied: dict[str, Any],
        required: bool,
        algorithm: GraphAlgorithm,
        remaining_ms: Callable[[], int],
    ) -> GraphIntelligenceReceipt:
        """graph.search / graph.semantic_search over the existing projection.

        Uses the same Graphiti strategies as ``memory.search`` (whose meaning
        is unchanged, GI-036), with the principal's tenant, and admits a hit
        only after canonical rehydration under the request's filters.
        """

        strategy = SEARCH_STRATEGIES[request.operation]
        identity = algorithm_identity(algorithm, {"strategy": strategy, "limit": limits.max_nodes})

        def fail(failure_class: str, stage: str) -> GraphIntelligenceReceipt:
            return self._receipt(
                GraphReceiptStatus.FAILED,
                request.operation,
                scope_digest,
                provider,
                identity,
                limits_applied,
                LinkedEvidence(),
                [{"class": failure_class, "stage": stage}],
            )

        if request.anchor is None or request.anchor.query is None:
            return fail("search_requires_query_anchor", "policy")
        if self.projection is None or strategy not in self.projection.capabilities:
            return fail("capability_unavailable", "capability")
        # One provider call per namespace so the request deadline is checked
        # between calls; a call that returns after the deadline is discarded.
        # A single in-flight call is bounded by the transport's own timeout.
        per_namespace = max(1, limits.max_nodes // len(request.namespaces))
        best: dict[UUID, ProjectionHit] = {}
        budget_exhausted = False
        for namespace in request.namespaces:
            if remaining_ms() <= 0:
                budget_exhausted = True
                break
            # The call runs off-thread so the request can stop waiting at its
            # deadline even when the provider stalls; an abandoned call ends
            # at its transport timeout and its result is discarded.
            future = _search_executor().submit(
                self.projection.search_strategy,
                strategy,
                request.anchor.query,
                (namespace,),
                limit=per_namespace,
                tenant_id=tenant_id,
            )
            try:
                namespace_hits = future.result(timeout=max(remaining_ms(), 0) / 1_000)
            except FuturesTimeoutError:
                future.cancel()
                budget_exhausted = True
                break
            except Exception as exc:  # noqa: BLE001 - normalized; raw text never escapes
                return fail(f"provider_error:{type(exc).__name__}", "provider")
            if remaining_ms() <= 0:
                budget_exhausted = True
                break
            for hit in namespace_hits:
                current = best.get(hit.record_id)
                if current is None or hit.score > current.score:
                    best[hit.record_id] = hit
        if budget_exhausted and not best:
            return fail("runtime_budget_exhausted", "provider")
        hits = list(best.values())
        scope = EvidenceScope(
            tenant_id=tenant_id,
            namespaces=frozenset(request.namespaces),
            group_ids=frozenset(graph_group_ids(tenant_id, request.namespaces)),
            as_of=request.as_of,
            recorded_before=request.recorded_before,
        )
        linked = LinkedEvidence()
        cache: dict[Any, bool] = {}
        try:
            for hit in sorted(hits, key=lambda h: (-h.score, str(h.record_id))):
                if self.linker.admit(hit.record_id, scope, cache):
                    linked.results.append(
                        {
                            "kind": "record_hit",
                            "record_id": str(hit.record_id),
                            "score": hit.score,
                            "strategy": strategy,
                            "supporting_record_ids": [str(hit.record_id)],
                            "authority_class": "advisory_projection",
                        }
                    )
                else:
                    # The id may name another tenant's record; never echo it.
                    linked.unsupported.append(
                        {"kind": "record_hit", "reason": "no_canonical_support"}
                    )
        except Exception as exc:  # noqa: BLE001 - reported as a rehydration failure
            return fail(f"rehydration_error:{type(exc).__name__}", "evidence")
        linked.supporting_record_ids = [
            UUID(item["record_id"]) for item in linked.results[: limits.max_nodes]
        ]
        failures: list[dict[str, Any]] = []
        if len(linked.results) > limits.max_nodes:
            linked.results = linked.results[: limits.max_nodes]
            failures.append({"class": "truncated", "stage": "limits"})
        if budget_exhausted:
            failures.append({"class": "runtime_budget_exhausted", "stage": "provider"})
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
            **algorithm_parameters(algorithm),
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
