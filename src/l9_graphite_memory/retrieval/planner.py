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
    MemoryRecord,
    MemorySearchRequest,
    MemoryState,
    OperationStatus,
    SearchHit,
    SearchReceipt,
)
from l9_graphite_memory.ports import ProjectionAdapter, RecordStore

from .query_classifier import QueryClassifier
from .ranking import RankingPolicy


class RetrievalPlanner:
    def __init__(
        self,
        store: RecordStore,
        projection: ProjectionAdapter,
        *,
        ranking: RankingPolicy | None = None,
        classifier: QueryClassifier | None = None,
        projection_required: bool = False,
    ) -> None:
        self.store = store
        self.projection = projection
        self.ranking = ranking or RankingPolicy()
        self.classifier = classifier or QueryClassifier()
        self.projection_required = projection_required

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
            records = self.store.search_records(tenant_id, request, namespaces)
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
        projection_strategies = tuple(
            strategy
            for strategy in classification.strategies
            if strategy in self.projection.capabilities
        )
        projection_attempted = False
        for strategy in projection_strategies:
            projection_attempted = True
            store_label = f"{self.projection.name}:{strategy}"
            stores_attempted.append(store_label)
            try:
                strategy_search = getattr(self.projection, "search_strategy", None)
                if strategy_search is None:
                    strategy_hits = self.projection.search(
                        request.query,
                        namespaces,
                        limit=request.limit * 2,
                    )
                else:
                    strategy_hits = strategy_search(
                        strategy,
                        request.query,
                        namespaces,
                        limit=request.limit * 2,
                    )
                stores_succeeded.append(store_label)
                strategies_succeeded.append(strategy)
                for hit in strategy_hits:
                    projection_scores[hit.record_id] = max(
                        projection_scores.get(hit.record_id, 0.0),
                        hit.score,
                    )
            except Exception as exc:  # noqa: BLE001
                stores_failed[store_label] = str(exc)
                strategies_failed[strategy] = str(exc)
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

        if (
            self.store.name in stores_failed
            or self.projection_required
            and any(key.startswith(f"{self.projection.name}:") for key in stores_failed)
        ):
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
                if factors.relevance <= 0:
                    continue
                matched_by = ["canonical-store"]
                if factors.lexical > 0:
                    matched_by.append("lexical")
                if factors.projection > 0:
                    matched_by.append("projection")
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
        digest = sha256_text(
            canonical_json(
                {
                    "query": request.query,
                    "query_pattern": classification.pattern.value,
                    "namespaces": namespaces,
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
            hits=tuple(hits),
            query_pattern=classification.pattern,
            classification_reason=classification.reason,
            strategies_attempted=tuple(dict.fromkeys(strategies_attempted)),
            strategies_succeeded=tuple(dict.fromkeys(strategies_succeeded)),
            strategies_failed=strategies_failed,
            stores_attempted=tuple(stores_attempted),
            stores_succeeded=tuple(stores_succeeded),
            stores_failed=stores_failed,
            result_digest=digest,
        )
