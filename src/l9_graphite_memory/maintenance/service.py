# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/maintenance/service.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Apply bounded maintenance plans to already-canonical memory."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from l9_graphite_memory.contracts import (
    AuthorizationAction,
    Confidence,
    ConfidenceMethod,
    ConflictItem,
    EvidenceKind,
    EvidenceRef,
    MaintenanceAction,
    MaintenanceOperation,
    MaintenanceRequest,
    MaintenanceRunReceipt,
    MaintenanceStatus,
    MemoryPrincipal,
    MemoryRecord,
    MemoryState,
    MemoryWriteRequest,
    OperationStatus,
    Provenance,
    QuarantineReviewPolicy,
    QuarantineVerdict,
    WriteStatus,
)
from l9_graphite_memory.curation import NullQuarantineReviewer, RetentionPolicy, apply_policy
from l9_graphite_memory.errors import AdmissionError, AuthorizationError, StoreError
from l9_graphite_memory.observability import get_logger
from l9_graphite_memory.ports import QuarantineReviewer
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.version import PACKAGE_VERSION

from .planner import MaintenancePlanner

log = get_logger("l9.memory.maintenance")

MAINTENANCE_SOURCE = "memory-maintenance"


class MaintenanceService:
    """Run scheduled consolidation, evolution, retention, and reconciliation.

    Maintenance only ever reads records the canonical store already holds and
    writes records derived from them. It has no ingestion surface: the request
    contract cannot carry source material, and every derived record cites the
    canonical records it was built from.
    """

    def __init__(
        self,
        service: MemoryService,
        *,
        planner: MaintenancePlanner | None = None,
        retention_policy: RetentionPolicy | None = None,
        reviewer: QuarantineReviewer | None = None,
        review_policy: QuarantineReviewPolicy | None = None,
    ) -> None:
        self.service = service
        self.store = service.store
        self.planner = planner or MaintenancePlanner(retention_policy)
        # No reviewer means every quarantined record is reported as unreviewed
        # rather than silently left in place (ADR-080).
        self.reviewer: QuarantineReviewer = reviewer or NullQuarantineReviewer()
        self.review_policy = review_policy or QuarantineReviewPolicy()

    # -- helpers --------------------------------------------------------------

    def _load(
        self, principal: MemoryPrincipal, request: MaintenanceRequest, watermark: datetime
    ) -> list[MemoryRecord]:
        states: tuple[MemoryState, ...] = (MemoryState.ACTIVE,)
        if MaintenanceOperation.REVIEW_QUARANTINE in request.operations:
            # Quarantined records are out of scope for every other operation
            # and are only loaded when the run is asked to review them.
            states = (MemoryState.ACTIVE, MemoryState.QUARANTINED)
        records = self.store.list_records(
            principal.tenant_id,
            request.namespace,
            states=states,
            limit=request.max_records,
        )
        return [record for record in records if record.temporal.recorded_at <= watermark]

    @staticmethod
    def _derived_request(
        action: MaintenanceAction,
        sources: list[MemoryRecord],
        *,
        namespace: str,
        reason: str,
        now: datetime,
    ) -> MemoryWriteRequest:
        """Build the consolidated memory an action produces.

        The derived record cites every source it was built from, both as
        ``references`` (lineage) and as ``supersedes`` (the sources stop being
        current). Its idempotency key is the action digest, so replaying the
        same action returns the existing record rather than creating a second.
        """

        ordered = sorted(sources, key=lambda item: item.temporal.recorded_at)
        primary = ordered[-1]

        valid_from = min(record.temporal.valid_from for record in ordered)
        # An open-ended source keeps the consolidation open-ended.
        valid_to: datetime | None = None
        if all(record.temporal.valid_to is not None for record in ordered):
            valid_to = max(
                record.temporal.valid_to
                for record in ordered
                if record.temporal.valid_to is not None
            )

        evidence = list(dict.fromkeys(item for record in ordered for item in record.evidence))
        evidence.append(
            EvidenceRef(
                kind=EvidenceKind.AGGREGATION,
                description=reason,
                source_id=action.action_digest,
            )
        )

        evidence_count = sum(max(record.confidence.evidence_count, 1) for record in ordered)
        score = max(record.confidence.score for record in ordered)

        source_ids = tuple(record.record_id for record in ordered)
        return MemoryWriteRequest(
            namespace=namespace,
            memory_class=primary.memory_class,
            content=primary.content,
            assertion=primary.assertion,
            provenance=Provenance(
                source=MAINTENANCE_SOURCE,
                source_id=action.action_digest,
                source_digest=primary.normalized_digest,
                tool="MaintenanceService",
                extraction_method=f"maintenance-{action.operation.value}/v1",
                transformed_at=now,
            ),
            evidence=tuple(evidence),
            confidence=Confidence(
                score=score,
                method=ConfidenceMethod.AGGREGATED,
                evidence_count=evidence_count,
                policy_version=f"maintenance/{PACKAGE_VERSION}",
            ),
            valid_from=valid_from,
            valid_to=valid_to,
            source_observed_at=primary.temporal.source_observed_at,
            tags=(
                *sorted({tag for record in ordered for tag in record.tags}),
                "consolidated",
            ),
            metadata={
                "maintenance_operation": action.operation.value,
                "maintenance_action_digest": action.action_digest,
                "consolidated_record_ids": [str(item) for item in source_ids],
                "consolidated_count": len(source_ids),
            },
            idempotency_key=f"maintenance:{action.operation.value}:{action.action_digest}",
            supersedes=source_ids,
            references=source_ids,
            consent=primary.consent,
        )

    # -- application ----------------------------------------------------------

    def _apply_consolidation(
        self,
        principal: MemoryPrincipal,
        action: MaintenanceAction,
        by_id: dict[UUID, MemoryRecord],
        *,
        namespace: str,
    ) -> MaintenanceAction:
        sources = [by_id[record_id] for record_id in action.source_record_ids if record_id in by_id]
        if len(sources) < 2:
            raise StoreError(
                f"consolidation sources are no longer available: {action.action_digest}"
            )
        request = self._derived_request(
            action,
            sources,
            namespace=namespace,
            reason=action.reason,
            now=self.service.clock.now(),
        )
        receipt = self.service._admit(principal, request, action=AuthorizationAction.MAINTAIN)
        if receipt.status is WriteStatus.DUPLICATE:
            # The same action already produced this record on an earlier run.
            return action.model_copy(
                update={
                    "applied": True,
                    "result_record_id": receipt.record_id,
                    "details": {**action.details, "already_present": True},
                }
            )
        if receipt.status is WriteStatus.QUARANTINED:
            # Admission held the derived record for review, so its sources were
            # not superseded and the consolidation did not take effect. Report
            # it rather than claiming a consolidation that did not happen.
            raise StoreError(
                "consolidation was quarantined pending review: "
                + "; ".join(receipt.warnings or receipt.admission.reasons)
            )
        # A consolidation always supersedes its sources, so admission reports
        # SUPERSEDED rather than ADMITTED; both mean the record was committed.
        if receipt.status not in {WriteStatus.ADMITTED, WriteStatus.SUPERSEDED}:
            raise StoreError(
                f"consolidation was not admitted ({receipt.status.value}): "
                + "; ".join(receipt.admission.reasons)
            )
        return action.model_copy(update={"applied": True, "result_record_id": receipt.record_id})

    def _apply_transition(
        self,
        principal: MemoryPrincipal,
        action: MaintenanceAction,
        by_id: dict[UUID, MemoryRecord],
        *,
        namespace: str,
        record_ids: tuple[UUID, ...],
        new_state: MemoryState,
    ) -> MaintenanceAction:
        """Supersede or archive through the service, never the store.

        The transition must commit together with the projection retirement it
        implies, or the provider keeps serving a fact the canonical store has
        already retired (ADR-074). ``MemoryService.transition_lifecycle`` owns
        that atomicity and the receipt; maintenance only decides which records.
        """

        targets: list[UUID] = []
        for record_id in record_ids:
            record = by_id.get(record_id)
            if record is None:
                raise StoreError(f"{new_state.value} target is unavailable: {record_id}")
            if record.state is not MemoryState.ACTIVE:
                continue
            targets.append(record_id)
        if targets:
            receipt = self.service.transition_lifecycle(
                principal,
                namespace,
                record_ids=tuple(targets),
                new_state=new_state,
                reason=action.reason,
            )
            return action.model_copy(
                update={
                    "applied": True,
                    "details": {**action.details, "lifecycle_receipt_id": str(receipt.receipt_id)},
                }
            )
        return action.model_copy(update={"applied": True})

    def _apply_reconcile(
        self,
        principal: MemoryPrincipal,
        action: MaintenanceAction,
        *,
        namespace: str,
    ) -> MaintenanceAction:
        """Make a contradiction durable without resolving it (ADR-081).

        The pair is linked on both records through the service, under a
        receipt. Resolution -- superseding or archiving one side -- is a
        governance decision; until it is taken the link keeps the conflict
        visible to phase locks and promotion without recomputation.
        """

        left_id, right_id = action.source_record_ids[0], action.source_record_ids[1]
        receipt = self.service.link_conflicts(
            principal,
            namespace,
            links=(
                ConflictItem(
                    left_record_id=left_id,
                    right_record_id=right_id,
                    subject=str(action.details.get("subject") or "") or None,
                    predicate=str(action.details.get("predicate") or "") or None,
                    reason=action.reason,
                ),
            ),
            reason=action.reason,
        )
        return action.model_copy(
            update={
                "applied": True,
                "details": {
                    **action.details,
                    "conflict_link_receipt_id": str(receipt.receipt_id),
                    "linked": bool(receipt.links),
                },
            }
        )

    def _apply_review(
        self,
        principal: MemoryPrincipal,
        action: MaintenanceAction,
        by_id: dict[UUID, MemoryRecord],
        *,
        namespace: str,
    ) -> MaintenanceAction:
        """Ask the reviewer about one quarantined record and act on the policy.

        RELEASE that clears the policy moves the record to active through the
        service, with the verdict as evidence on the lifecycle receipt.
        ESCALATE is applied without a transition: the digest is recorded so the
        reviewer is not asked again, and the record id is reported for a
        person. HOLD stays unapplied so the next run reviews it again
        (ADR-080).
        """

        record_id = action.source_record_ids[0]
        record = by_id.get(record_id)
        if record is None:
            raise StoreError(f"review target is unavailable: {record_id}")
        if record.state is not MemoryState.QUARANTINED:
            return action.model_copy(
                update={
                    "applied": True,
                    "details": {**action.details, "outcome": "not_quarantined"},
                }
            )
        verdict = apply_policy(self.reviewer.review(record), record, self.review_policy)
        details: dict[str, Any] = {
            **action.details,
            "verdict": verdict.verdict.value,
            "confidence": verdict.confidence,
            "reasons": list(verdict.reasons),
            "blockers": list(verdict.blockers),
            "reviewer": verdict.reviewer,
            "model": verdict.model,
            "review_policy_version": verdict.policy_version,
            "requires_human": verdict.requires_human,
        }
        if verdict.verdict is QuarantineVerdict.RELEASE:
            receipt = self.service.transition_lifecycle(
                principal,
                namespace,
                record_ids=(record_id,),
                new_state=MemoryState.ACTIVE,
                reason=f"released from quarantine: {verdict.summary()}"[:2_000],
                review=verdict,
            )
            details["outcome"] = "released"
            details["lifecycle_receipt_id"] = str(receipt.receipt_id)
            return action.model_copy(update={"applied": True, "details": details})
        if verdict.verdict is QuarantineVerdict.ESCALATE:
            details["outcome"] = "escalated"
            return action.model_copy(update={"applied": True, "details": details})
        details["outcome"] = "held"
        return action.model_copy(update={"details": details})

    # -- entry point ----------------------------------------------------------

    def run(self, principal: MemoryPrincipal, request: MaintenanceRequest) -> MaintenanceRunReceipt:
        """Plan and, unless this is a dry run, apply one maintenance pass."""

        authorization = self.service.namespace_policy.require(
            principal,
            AuthorizationAction.MAINTAIN,
            request.namespace,
        )
        started_at = self.service.clock.now()
        watermark = request.watermark or started_at
        if watermark > started_at:
            raise AuthorizationError(
                "maintenance watermark cannot be in the future; "
                "records that have not been recorded yet are out of scope"
            )
        previous_watermark = self.store.get_maintenance_watermark(
            principal.tenant_id, request.namespace
        )
        applied_digests = self.store.find_maintenance_action_digests(
            principal.tenant_id, request.namespace
        )

        records = self._load(principal, request, watermark)
        plan = self.planner.plan(
            records,
            tenant_id=principal.tenant_id,
            namespace=request.namespace,
            operations=request.operations,
            watermark=watermark,
            applied_digests=applied_digests,
            max_actions=request.max_actions,
            now=started_at,
        )

        if request.dry_run:
            return MaintenanceRunReceipt(
                tenant_id=principal.tenant_id,
                namespace=request.namespace,
                status=OperationStatus.COMPLETE,
                maintenance_status=MaintenanceStatus.PLANNED,
                applied=False,
                operations=tuple(request.operations),
                watermark=watermark,
                previous_watermark=previous_watermark,
                considered_record_count=plan.considered_record_count,
                actions=plan.actions,
                skipped_action_digests=plan.skipped_action_digests,
                authorization=authorization,
                actor=principal.audit_subject,
                reason=request.reason,
                started_at=started_at,
                completed_at=self.service.clock.now(),
            )

        by_id = {record.record_id: record for record in records}
        applied: list[MaintenanceAction] = []
        failures: list[str] = []
        escalated: list[UUID] = []
        reviews_performed = 0
        for action in plan.actions:
            try:
                if action.operation in {
                    MaintenanceOperation.DEDUPE,
                    MaintenanceOperation.REFINE,
                }:
                    applied.append(
                        self._apply_consolidation(
                            principal, action, by_id, namespace=request.namespace
                        )
                    )
                elif action.operation is MaintenanceOperation.SUPERSEDE:
                    applied.append(
                        self._apply_transition(
                            principal,
                            action,
                            by_id,
                            namespace=request.namespace,
                            record_ids=action.superseded_record_ids,
                            new_state=MemoryState.SUPERSEDED,
                        )
                    )
                elif action.operation is MaintenanceOperation.ARCHIVE:
                    applied.append(
                        self._apply_transition(
                            principal,
                            action,
                            by_id,
                            namespace=request.namespace,
                            record_ids=action.archived_record_ids,
                            new_state=MemoryState.ARCHIVED,
                        )
                    )
                elif action.operation is MaintenanceOperation.RECONCILE:
                    applied.append(
                        self._apply_reconcile(principal, action, namespace=request.namespace)
                    )
                elif action.operation is MaintenanceOperation.REVIEW_QUARANTINE:
                    if reviews_performed >= self.review_policy.max_reviews_per_run:
                        # Unapplied: no digest, reviewed on a later run.
                        applied.append(
                            action.model_copy(
                                update={
                                    "details": {
                                        **action.details,
                                        "outcome": "deferred",
                                        "reason": "review budget for this run is spent",
                                    }
                                }
                            )
                        )
                        continue
                    reviews_performed += 1
                    outcome = self._apply_review(
                        principal, action, by_id, namespace=request.namespace
                    )
                    applied.append(outcome)
                    if outcome.details.get("requires_human"):
                        escalated.extend(outcome.source_record_ids)
                else:
                    raise AdmissionError(f"unsupported maintenance operation {action.operation}")
            except (StoreError, AuthorizationError, AdmissionError) as exc:
                failures.append(f"{action.operation.value}: {exc}")
                log.warning(
                    "maintenance_action_failed",
                    extra={
                        "operation": action.operation.value,
                        "action_digest": action.action_digest,
                        "error": str(exc),
                    },
                )

        completed_at = self.service.clock.now()
        receipt = MaintenanceRunReceipt(
            tenant_id=principal.tenant_id,
            namespace=request.namespace,
            status=(OperationStatus.PARTIAL if failures else OperationStatus.COMPLETE),
            maintenance_status=(
                MaintenanceStatus.FAILED if failures and not applied else MaintenanceStatus.APPLIED
            ),
            applied=True,
            operations=tuple(request.operations),
            watermark=watermark,
            previous_watermark=previous_watermark,
            considered_record_count=plan.considered_record_count,
            actions=tuple(applied),
            skipped_action_digests=plan.skipped_action_digests,
            escalated_record_ids=tuple(dict.fromkeys(escalated)),
            authorization=authorization,
            actor=principal.audit_subject,
            reason=request.reason,
            failures=tuple(failures),
            started_at=started_at,
            completed_at=completed_at,
        )
        self.store.save_maintenance_run(receipt)
        return receipt
