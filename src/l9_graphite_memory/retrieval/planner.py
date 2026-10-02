# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/retrieval/planner.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Fuse canonical temporal/lexical retrieval with optional graph projections."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.contracts import (
    SEARCH_SELECTOR_CANONICALIZATION,
    MemoryRecord,
    MemorySearchRequest,
    MemoryState,
    OperationStatus,
    ProjectionStrategyEvidence,
    SearchHit,
    SearchReceipt,
)
from l9_graphite_memory.ports import ProjectionAdapter, ProjectionHit, RecordStore
from l9_graphite_memory.projections.runtime import ProjectionRuntime

from .query_classifier import QueryClassifier
from .ranking import RankingPolicy


def _matches_tags(record: MemoryRecord, tags: tuple[str, ...]) -> bool:
    """True when every requested tag is on the record (tags are a selector)."""

    if not tags:
        return True
    present = set(record.tags)
    return all(tag in present for tag in tags)


def _strategy_hits(
    adapter: ProjectionAdapter,
    strategy: str,
    query: str,
    namespaces: tuple[str, ...],
    *,
    limit: int,
) -> list[ProjectionHit]:
    strategy_search = getattr(adapter, "search_strategy", None)
    if not callable(strategy_search):
        return adapter.search(query, namespaces, limit=limit)
    # The attribute is looked up dynamically so an adapter predating per-strategy
    # search still works; the port fixes the type of what it returns.
    hits: list[ProjectionHit] = strategy_search(strategy, query, namespaces, limit=limit)
    return hits


class RetrievalPlanner:
    """Fuse canonical retrieval with the strategies of active projection targets.

    Only active targets contribute. A shadow target is queried only when
    ``shadow_measurement`` is set, and then only to record evidence: its hits
    never reach scoring, hydration, status, or the result digest. Disabled
    targets are never queried (ADR-084).
    """

    def __init__(
        self,
        store: RecordStore,
        projection: ProjectionAdapter | ProjectionRuntime,
        *,
        ranking: RankingPolicy | None = None,
        classifier: QueryClassifier | None = None,
        projection_required: bool = False,
        shadow_measurement: bool = False,
    ) -> None:
        self.store = store
        self.projections = ProjectionRuntime.coerce(projection, required=projection_required)
        self.ranking = ranking or RankingPolicy()
        self.classifier = classifier or QueryClassifier()
        self.shadow_measurement = shadow_measurement

    def _hydrate_projection_hits(
        self,
        tenant_id: str,
        request: MemorySearchRequest,
        namespaces: tuple[str, ...],
        records: list[MemoryRecord],
        projection_scores: dict[UUID, float],
        *,
        now: datetime,
    ) -> list[MemoryRecord]:
        """Resolve projection hits into canonical records the store window missed.

        The canonical candidate set is the most recent ``limit * 20`` records.
        A graph or semantic strategy exists precisely to find the relevant
        record that recency does not surface, so a hit outside that window is
        read back from the canonical store and admitted under exactly the
        filters the store applied: tenant, authorized namespace, lifecycle
        state, class, confidence, valid time, and transaction time. The
        projection contributes identity only; the record served is canonical.
        """

        known = {record.record_id for record in records}
        allowed_states = {MemoryState.ACTIVE}
        if request.include_superseded:
            allowed_states.add(MemoryState.SUPERSEDED)
        if request.include_archived:
            allowed_states.add(MemoryState.ARCHIVED)
        recorded_before = request.recorded_before or request.valid_at or now
        hydrated = list(records)
        for record_id in projection_scores:
            if record_id in known:
                continue
            record = self.store.get_record(record_id)
            if record is None:
                continue
            if record.tenant_id != tenant_id or record.namespace not in namespaces:
                continue
            if record.state not in allowed_states:
                continue
            if request.memory_classes and record.memory_class not in request.memory_classes:
                continue
            if not _matches_tags(record, request.tags):
                continue
            if record.confidence.score < request.min_confidence:
                continue
            if not record.temporal.is_valid_at(request.valid_at):
                continue
            if record.temporal.recorded_at > recorded_before:
                continue
            hydrated.append(record)
        return hydrated

    def search(
        self,
        tenant_id: str,
        request: MemorySearchRequest,
        namespaces: tuple[str, ...],
        *,
        now: datetime,
    ) -> SearchReceipt:
        classification = self.classifier.classify(request.query)
        stores_attempted = [self.store.name]
        stores_succeeded: list[str] = []
        stores_failed: dict[str, str] = {}
        strategies_attempted = list(classification.strategies)
        strategies_succeeded: list[str] = []
        strategies_failed: dict[str, str] = {}
        try:
            records = [
                record
                for record in self.store.search_records(tenant_id, request, namespaces)
                if _matches_tags(record, request.tags)
            ]
            stores_succeeded.append(self.store.name)
            strategies_succeeded.extend(
                strategy
                for strategy in classification.strategies
                if strategy in {"lexical-ranking", "temporal-filter"}
            )
        except Exception as exc:  # noqa: BLE001
            records = []
            stores_failed[self.store.name] = str(exc)
            for strategy in classification.strategies:
                if strategy in {"lexical-ranking", "temporal-filter"}:
                    strategies_failed[strategy] = str(exc)

        projection_scores: dict[UUID, float] = {}
        # (target identity, mode, strategy, error, hit record ids)
        attempts: list[tuple[str, str, str, str | None, tuple[UUID, ...]]] = []
        projection_attempted = False
        failed_required = False
        for binding in self.projections.active_targets():
            adapter = binding.adapter
            assert adapter is not None
            for strategy in classification.strategies:
                if strategy not in adapter.capabilities:
                    continue
                projection_attempted = True
                store_label = f"{binding.identity}:{strategy}"
                stores_attempted.append(store_label)
                try:
                    strategy_hits = _strategy_hits(
                        adapter, strategy, request.query, namespaces, limit=request.limit * 2
                    )
                except Exception as exc:  # noqa: BLE001
                    # A provider failure is a failed strategy, never an empty
                    # successful one.
                    stores_failed[store_label] = str(exc)
                    strategies_failed[strategy] = str(exc)
                    failed_required = failed_required or binding.required
                    attempts.append((binding.identity, "active", strategy, str(exc), ()))
                    continue
                stores_succeeded.append(store_label)
                strategies_succeeded.append(strategy)
                for hit in strategy_hits:
                    projection_scores[hit.record_id] = max(
                        projection_scores.get(hit.record_id, 0.0),
                        hit.score,
                    )
                attempts.append(
                    (
                        binding.identity,
                        "active",
                        strategy,
                        None,
                        tuple(hit.record_id for hit in strategy_hits),
                    )
                )
        if self.shadow_measurement:
            for binding in self.projections.shadow_targets():
                adapter = binding.adapter
                assert adapter is not None
                for strategy in classification.strategies:
                    if strategy not in adapter.capabilities:
                        continue
                    try:
                        shadow_hits = _strategy_hits(
                            adapter, strategy, request.query, namespaces, limit=request.limit * 2
                        )
                    except Exception as exc:  # noqa: BLE001
                        attempts.append((binding.identity, "shadow", strategy, str(exc), ()))
                        continue
                    attempts.append(
                        (
                            binding.identity,
                            "shadow",
                            strategy,
                            None,
                            tuple(hit.record_id for hit in shadow_hits),
                        )
                    )
        if not projection_attempted:
            strategies_attempted = [
                strategy
                for strategy in strategies_attempted
                if strategy not in {"graph-search", "semantic-search"}
            ]
        if projection_scores and self.store.name not in stores_failed:
            records = self._hydrate_projection_hits(
                tenant_id, request, namespaces, records, projection_scores, now=now
            )

        if self.store.name in stores_failed or failed_required:
            status = OperationStatus.FAILED
        elif stores_failed or strategies_failed:
            status = OperationStatus.PARTIAL
        else:
            status = OperationStatus.COMPLETE

        hits: list[SearchHit] = []
        if status is not OperationStatus.FAILED:
            for record in records:
                factors = self.ranking.factors(
                    request.query,
                    record,
                    projection_score=projection_scores.get(record.record_id, 0.0),
                    pattern=classification.pattern,
                    now=now,
                )
                # A tag selector is an explicit match: a record the caller
                # selected by tag is returned even when the query text shares
                # no token with its content. Without tags, relevance decides.
                if factors.relevance <= 0 and not request.tags:
                    continue
                matched_by = ["canonical-store"]
                if factors.lexical > 0:
                    matched_by.append("lexical")
                if factors.projection > 0:
                    matched_by.append("projection")
                if request.tags:
                    matched_by.append("tag")
                matched_by.append(f"pattern:{classification.pattern.value}")
                hits.append(
                    SearchHit(
                        record=record,
                        score=self.ranking.total(factors),
                        factors=factors,
                        matched_by=tuple(matched_by),
                    )
                )
        hits.sort(
            key=lambda item: (item.score, item.record.temporal.recorded_at),
            reverse=True,
        )
        hits = hits[: request.limit]
        returned = {hit.record.record_id for hit in hits}
        projection_evidence = tuple(
            ProjectionStrategyEvidence(
                target_identity=identity,
                mode=mode,
                strategy=strategy,
                succeeded=error is None,
                error=error,
                hit_count=len(hit_ids),
                contributed=(
                    0 if mode != "active" else sum(1 for item in hit_ids if item in returned)
                ),
            )
            for identity, mode, strategy, error, hit_ids in attempts
        )
        # MEM-P2-01: identity of the request that produced these hits. Computed
        # from the EFFECTIVE request the planner filtered on, over the one
        # canonical serializer the rest of the package digests with, so a
        # consumer comparing digests is comparing the same normalization.
        request_digest = sha256_text(canonical_json(request.selector_identity()))
        digest = sha256_text(
            canonical_json(
                {
                    "query": request.query,
                    "query_pattern": classification.pattern.value,
                    "namespaces": namespaces,
                    # Binds the results to the selectors that produced them:
                    # without it two searches differing only by tag filter
                    # could share a result digest whenever their hits coincide.
                    "request_digest": request_digest,
                    "hit_ids": [str(hit.record.record_id) for hit in hits],
                    "scores": [round(hit.score, 8) for hit in hits],
                    "failures": stores_failed,
                    "strategy_failures": strategies_failed,
                }
            )
        )
        return SearchReceipt(
            status=status,
            query=request.query,
            namespaces_authorized=namespaces,
            tags=request.tags,
            memory_classes=request.memory_classes,
            limit=request.limit,
            valid_at=request.valid_at,
            recorded_before=request.recorded_before,
            include_superseded=request.include_superseded,
            include_archived=request.include_archived,
            min_confidence=request.min_confidence,
            selector_canonicalization=SEARCH_SELECTOR_CANONICALIZATION,
            request_digest=request_digest,
            hits=tuple(hits),
            query_pattern=classification.pattern,
            classification_reason=classification.reason,
            strategies_attempted=tuple(dict.fromkeys(strategies_attempted)),
            strategies_succeeded=tuple(dict.fromkeys(strategies_succeeded)),
            strategies_failed=strategies_failed,
            stores_attempted=tuple(stores_attempted),
            stores_succeeded=tuple(stores_succeeded),
            stores_failed=stores_failed,
            projection_evidence=projection_evidence,
            result_digest=digest,
        )
