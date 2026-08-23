# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/maintenance/planner.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Pure planning for scheduled canonical-memory maintenance.

The planner decides *what* a maintenance run should do. It reads records and
returns actions; it performs no I/O and mutates nothing, so the same inputs
always yield the same plan. Applying a plan is the service's job.

Every action is bounded and reversible in the canonical sense: consolidation
creates a new derived record and supersedes its sources, it never rewrites a
record in place. Superseded records keep their content and their history.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.contracts import (
    MaintenanceAction,
    MaintenanceOperation,
    MemoryRecord,
    MemoryState,
)
from l9_graphite_memory.curation import RetentionEngine, RetentionPolicy


def action_digest(
    operation: MaintenanceOperation,
    tenant_id: str,
    namespace: str,
    source_record_ids: Iterable[UUID],
) -> str:
    """Stable identity for one maintenance action.

    Derived from the operation and the exact set of records it consumes, so a
    rerun over unchanged state produces the same digest and is recognized as
    already applied.
    """

    return sha256_text(
        canonical_json(
            {
                "operation": operation.value,
                "tenant_id": tenant_id,
                "namespace": namespace,
                "sources": sorted(str(record_id) for record_id in source_record_ids),
            }
        )
    )


def _overlaps(left: MemoryRecord, right: MemoryRecord) -> bool:
    left_end = left.temporal.valid_to
    right_end = right.temporal.valid_to
    return (left_end is None or right.temporal.valid_from < left_end) and (
        right_end is None or left.temporal.valid_from < right_end
    )


def _assertion_key(record: MemoryRecord) -> tuple[str, str] | None:
    """Subject and predicate of a structured assertion, casefolded."""

    assertion = record.assertion
    if assertion is None or not assertion.is_structured:
        return None
    subject = (assertion.subject or "").strip().casefold()
    predicate = (assertion.predicate or "").strip().casefold()
    if not subject or not predicate:
        return None
    return subject, predicate


def _assertion_object(record: MemoryRecord) -> str:
    assertion = record.assertion
    return (assertion.object or "").strip().casefold() if assertion else ""


@dataclass(frozen=True)
class MaintenancePlan:
    actions: tuple[MaintenanceAction, ...]
    considered_record_count: int
    skipped_action_digests: tuple[str, ...]


class MaintenancePlanner:
    """Plan bounded consolidation, evolution, retention, and reconciliation."""

    def __init__(self, retention_policy: RetentionPolicy | None = None) -> None:
        self.retention_policy = retention_policy or RetentionPolicy()
        self.retention_engine = RetentionEngine(self.retention_policy)

    # -- dedupe ---------------------------------------------------------------

    def _plan_dedupe(
        self,
        records: Sequence[MemoryRecord],
        *,
        tenant_id: str,
        namespace: str,
    ) -> list[MaintenanceAction]:
        """Consolidate records whose normalized content is byte-identical.

        Identical content is the only case where consolidation is safe without
        judgement. Even then the records must share a class and their validity
        intervals must overlap: two identical statements true over disjoint
        periods describe a fact that lapsed and returned, and merging them
        would erase the gap between them.
        """

        groups: dict[tuple[str, str], list[MemoryRecord]] = {}
        for record in records:
            groups.setdefault((record.memory_class.value, record.normalized_digest), []).append(
                record
            )

        actions: list[MaintenanceAction] = []
        for (_class_value, _digest), group in sorted(groups.items(), key=lambda item: item[0]):
            if len(group) < 2:
                continue
            for cluster in self._overlapping_clusters(group):
                if len(cluster) < 2:
                    continue
                ordered = sorted(cluster, key=lambda item: item.temporal.recorded_at)
                source_ids = tuple(record.record_id for record in ordered)
                actions.append(
                    MaintenanceAction(
                        operation=MaintenanceOperation.DEDUPE,
                        source_record_ids=source_ids,
                        superseded_record_ids=source_ids,
                        reason=(
                            f"{len(ordered)} records share normalized content and "
                            "overlapping validity; consolidated into one derived memory"
                        ),
                        action_digest=action_digest(
                            MaintenanceOperation.DEDUPE,
                            tenant_id,
                            namespace,
                            source_ids,
                        ),
                        details={"observation_count": len(ordered)},
                    )
                )
        return actions

    @staticmethod
    def _overlapping_clusters(
        group: Sequence[MemoryRecord],
    ) -> list[list[MemoryRecord]]:
        """Partition records into transitively overlapping validity clusters."""

        ordered = sorted(group, key=lambda item: item.temporal.valid_from)
        clusters: list[list[MemoryRecord]] = []
        for record in ordered:
            for cluster in clusters:
                if any(_overlaps(record, member) for member in cluster):
                    cluster.append(record)
                    break
            else:
                clusters.append([record])
        return clusters

    # -- refine ---------------------------------------------------------------

    def _plan_refine(
        self,
        records: Sequence[MemoryRecord],
        *,
        tenant_id: str,
        namespace: str,
        consumed: set[UUID],
    ) -> list[MaintenanceAction]:
        """Consolidate corroborating structured assertions.

        Records that assert the same subject, predicate, and object from
        different sources are corroboration, not duplication: their wording
        differs, so dedupe cannot see them. Consolidating them produces one
        derived assertion carrying the union of the evidence.
        """

        groups: dict[tuple[str, str, str], list[MemoryRecord]] = {}
        for record in records:
            if record.record_id in consumed:
                continue
            assertion_key = _assertion_key(record)
            if assertion_key is None:
                continue
            obj = _assertion_object(record)
            if not obj:
                continue
            subject, predicate = assertion_key
            groups.setdefault((subject, predicate, obj), []).append(record)

        actions: list[MaintenanceAction] = []
        for key, group in sorted(groups.items(), key=lambda item: item[0]):
            if len(group) < 2:
                continue
            # Distinct wording only; identical content is dedupe's job.
            if len({record.normalized_digest for record in group}) < 2:
                continue
            for cluster in self._overlapping_clusters(group):
                if len(cluster) < 2:
                    continue
                ordered = sorted(cluster, key=lambda item: item.temporal.recorded_at)
                source_ids = tuple(record.record_id for record in ordered)
                actions.append(
                    MaintenanceAction(
                        operation=MaintenanceOperation.REFINE,
                        source_record_ids=source_ids,
                        superseded_record_ids=source_ids,
                        reason=(
                            f"{len(ordered)} independently worded records assert "
                            f"{key[0]} {key[1]} {key[2]}; consolidated with combined evidence"
                        ),
                        action_digest=action_digest(
                            MaintenanceOperation.REFINE,
                            tenant_id,
                            namespace,
                            source_ids,
                        ),
                        details={
                            "subject": key[0],
                            "predicate": key[1],
                            "object": key[2],
                            "corroboration_count": len(ordered),
                        },
                    )
                )
        return actions

    # -- supersede ------------------------------------------------------------

    def _plan_supersede(
        self,
        records: Sequence[MemoryRecord],
        *,
        tenant_id: str,
        namespace: str,
        consumed: set[UUID],
    ) -> list[MaintenanceAction]:
        """Close out facts a later observation replaced.

        Same subject and predicate, a different object, and a validity window
        that starts strictly later: that is the world changing, not a duplicate.
        The earlier record is superseded and keeps its content, so the history
        of what was true when stays intact.
        """

        groups: dict[tuple[str, str], list[MemoryRecord]] = {}
        for record in records:
            if record.record_id in consumed:
                continue
            key = _assertion_key(record)
            if key is None or not _assertion_object(record):
                continue
            groups.setdefault(key, []).append(record)

        actions: list[MaintenanceAction] = []
        for key, group in sorted(groups.items(), key=lambda item: item[0]):
            if len(group) < 2:
                continue
            ordered = sorted(
                group,
                key=lambda item: (item.temporal.valid_from, item.temporal.recorded_at),
            )
            latest = ordered[-1]
            for earlier in ordered[:-1]:
                if _assertion_object(earlier) == _assertion_object(latest):
                    continue
                if earlier.temporal.valid_from >= latest.temporal.valid_from:
                    continue
                # Already closed before the new fact begins: nothing to supersede.
                if (
                    earlier.temporal.valid_to is not None
                    and earlier.temporal.valid_to <= latest.temporal.valid_from
                ):
                    continue
                source_ids = (earlier.record_id, latest.record_id)
                actions.append(
                    MaintenanceAction(
                        operation=MaintenanceOperation.SUPERSEDE,
                        source_record_ids=source_ids,
                        superseded_record_ids=(earlier.record_id,),
                        reason=(
                            f"{key[0]} {key[1]} changed from "
                            f"{_assertion_object(earlier)!r} to "
                            f"{_assertion_object(latest)!r}; the earlier record is superseded"
                        ),
                        action_digest=action_digest(
                            MaintenanceOperation.SUPERSEDE,
                            tenant_id,
                            namespace,
                            source_ids,
                        ),
                        details={
                            "subject": key[0],
                            "predicate": key[1],
                            "previous_object": _assertion_object(earlier),
                            "current_object": _assertion_object(latest),
                            "superseded_by": str(latest.record_id),
                        },
                    )
                )
        return actions

    # -- archive --------------------------------------------------------------

    def _plan_archive(
        self,
        records: Sequence[MemoryRecord],
        *,
        tenant_id: str,
        namespace: str,
        consumed: set[UUID],
        now: datetime,
    ) -> list[MaintenanceAction]:
        candidates = tuple(record for record in records if record.record_id not in consumed)
        if not candidates:
            return []
        decisions = self.retention_engine.evaluate(candidates, now=now)
        archived_ids = tuple(
            decision.record_id for decision in decisions if decision.action == "archive"
        )
        if not archived_ids:
            return []
        return [
            MaintenanceAction(
                operation=MaintenanceOperation.ARCHIVE,
                source_record_ids=archived_ids,
                archived_record_ids=archived_ids,
                reason=(
                    f"{len(archived_ids)} records expired with no incoming references "
                    f"under {self.retention_policy.policy_version}"
                ),
                action_digest=action_digest(
                    MaintenanceOperation.ARCHIVE, tenant_id, namespace, archived_ids
                ),
                details={"policy_version": self.retention_policy.policy_version},
            )
        ]

    # -- reconcile ------------------------------------------------------------

    def _plan_reconcile(
        self,
        records: Sequence[MemoryRecord],
        *,
        tenant_id: str,
        namespace: str,
        consumed: set[UUID],
    ) -> list[MaintenanceAction]:
        """Report contradictions that maintenance must not resolve on its own.

        Two records asserting different objects for the same subject and
        predicate over *overlapping* validity are in genuine conflict: unlike
        the supersede case, there is no ordering that makes one the successor
        of the other. Choosing a winner needs judgement and evidence that a
        scheduled job does not have, so reconciliation reports the conflict in
        the run receipt and changes nothing.
        """

        groups: dict[tuple[str, str], list[MemoryRecord]] = {}
        for record in records:
            if record.record_id in consumed:
                continue
            key = _assertion_key(record)
            if key is None or not _assertion_object(record):
                continue
            groups.setdefault(key, []).append(record)

        actions: list[MaintenanceAction] = []
        for key, group in sorted(groups.items(), key=lambda item: item[0]):
            ordered = sorted(group, key=lambda item: item.temporal.valid_from)
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    if _assertion_object(left) == _assertion_object(right):
                        continue
                    if not _overlaps(left, right):
                        continue
                    if left.temporal.valid_from != right.temporal.valid_from:
                        # A later start makes this evolution, handled by supersede.
                        continue
                    source_ids = (left.record_id, right.record_id)
                    actions.append(
                        MaintenanceAction(
                            operation=MaintenanceOperation.RECONCILE,
                            source_record_ids=source_ids,
                            reason=(
                                f"{key[0]} {key[1]} has conflicting objects "
                                f"{_assertion_object(left)!r} and "
                                f"{_assertion_object(right)!r} over the same validity; "
                                "reported for governance, not resolved automatically"
                            ),
                            action_digest=action_digest(
                                MaintenanceOperation.RECONCILE,
                                tenant_id,
                                namespace,
                                source_ids,
                            ),
                            details={
                                "subject": key[0],
                                "predicate": key[1],
                                "objects": [
                                    _assertion_object(left),
                                    _assertion_object(right),
                                ],
                                "resolution": "requires governance decision",
                            },
                        )
                    )
        return actions

    # -- plan -----------------------------------------------------------------

    def plan(
        self,
        records: Sequence[MemoryRecord],
        *,
        tenant_id: str,
        namespace: str,
        operations: Sequence[MaintenanceOperation],
        watermark: datetime,
        applied_digests: frozenset[str] = frozenset(),
        max_actions: int = 500,
        now: datetime | None = None,
    ) -> MaintenancePlan:
        """Produce a bounded, deterministic plan over already-canonical records."""

        eligible = [
            record
            for record in records
            if record.state is MemoryState.ACTIVE and record.temporal.recorded_at <= watermark
        ]
        eligible.sort(key=lambda item: (item.temporal.recorded_at, str(item.record_id)))

        selected = set(operations)
        planned: list[MaintenanceAction] = []
        # A record consumed by an earlier operation is off limits to later ones,
        # so one run never supersedes the same record twice.
        consumed: set[UUID] = set()

        def absorb(actions: list[MaintenanceAction]) -> None:
            for action in actions:
                planned.append(action)
                consumed.update(action.superseded_record_ids)
                consumed.update(action.archived_record_ids)

        if MaintenanceOperation.DEDUPE in selected:
            absorb(self._plan_dedupe(eligible, tenant_id=tenant_id, namespace=namespace))
        if MaintenanceOperation.REFINE in selected:
            absorb(
                self._plan_refine(
                    eligible,
                    tenant_id=tenant_id,
                    namespace=namespace,
                    consumed=consumed,
                )
            )
        if MaintenanceOperation.SUPERSEDE in selected:
            absorb(
                self._plan_supersede(
                    eligible,
                    tenant_id=tenant_id,
                    namespace=namespace,
                    consumed=consumed,
                )
            )
        if MaintenanceOperation.ARCHIVE in selected:
            absorb(
                self._plan_archive(
                    eligible,
                    tenant_id=tenant_id,
                    namespace=namespace,
                    consumed=consumed,
                    now=now or watermark,
                )
            )
        if MaintenanceOperation.RECONCILE in selected:
            # Reconciliation only reports, so it does not consume records.
            planned.extend(
                self._plan_reconcile(
                    eligible,
                    tenant_id=tenant_id,
                    namespace=namespace,
                    consumed=consumed,
                )
            )

        skipped = tuple(
            action.action_digest for action in planned if action.action_digest in applied_digests
        )
        fresh = [action for action in planned if action.action_digest not in applied_digests]
        return MaintenancePlan(
            actions=tuple(fresh[:max_actions]),
            considered_record_count=len(eligible),
            skipped_action_digests=skipped,
        )
