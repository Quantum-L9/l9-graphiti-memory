# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/services/memory_service.py
#   layer: service
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Single canonical service for reads, writes, hydration, locks, and curation."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from l9_graphite_memory.admission import AdmissionEngine, normalize_candidate
from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.authz import NamespacePolicy
from l9_graphite_memory.contracts import (
    ArchiveReceipt,
    AuthorizationAction,
    Confidence,
    ConflictItem,
    ConflictReport,
    DeletionReceipt,
    DeletionRequest,
    DeletionStatus,
    EvidenceKind,
    EvidenceRef,
    HealthReport,
    HydrationRequest,
    HydrationResult,
    MemoryPrincipal,
    MemoryRecord,
    MemorySearchRequest,
    MemoryState,
    MemoryStatusEvent,
    MemoryWriteRequest,
    OperationStatus,
    OutboxEvent,
    PhaseLockReceipt,
    PhaseLockRequest,
    PhaseLockVerification,
    PromotionRequest,
    Provenance,
    RetentionReceipt,
    SearchReceipt,
    TemporalCoordinates,
    WriteReceipt,
    WriteStatus,
)
from l9_graphite_memory.curation import (
    PromotionPolicy,
    RetentionEngine,
    RetentionPolicy,
)
from l9_graphite_memory.errors import AuthorizationError, StoreError
from l9_graphite_memory.lineage import LineageReplay, LineageReplayer
from l9_graphite_memory.ports import Clock, ProjectionAdapter, RecordStore, SystemClock
from l9_graphite_memory.retrieval import ContextBudgetAllocator, RetrievalPlanner
from l9_graphite_memory.version import MEMORY_SCHEMA_VERSION, PACKAGE_VERSION


class MemoryService:
    """The only production-authorized path into canonical memory state."""

    def __init__(
        self,
        store: RecordStore,
        projection: ProjectionAdapter,
        *,
        namespace_policy: NamespacePolicy | None = None,
        admission: AdmissionEngine | None = None,
        clock: Clock | None = None,
        retrieval: RetrievalPlanner | None = None,
        budget_allocator: ContextBudgetAllocator | None = None,
        promotion_policy: PromotionPolicy | None = None,
        retention_policy: RetentionPolicy | None = None,
        retention_engine: RetentionEngine | None = None,
        projection_required: bool = False,
    ) -> None:
        self.store = store
        self.projection = projection
        self.namespace_policy = namespace_policy or NamespacePolicy()
        self.admission = admission or AdmissionEngine()
        self.clock = clock or SystemClock()
        self.retrieval = retrieval or RetrievalPlanner(
            store,
            projection,
            projection_required=projection_required,
        )
        self.budget_allocator = budget_allocator or ContextBudgetAllocator()
        self.promotion_policy = promotion_policy or PromotionPolicy()
        self.retention_policy = retention_policy or RetentionPolicy()
        self.retention_engine = retention_engine or RetentionEngine(
            self.retention_policy
        )
        self.lineage_replayer = LineageReplayer(store)

    def initialize(self) -> None:
        self.store.initialize()

    @staticmethod
    def _operation_identity(request: MemoryWriteRequest) -> str:
        """Resolve the retry identity of this write, never its meaning.

        An explicit ``idempotency_key`` names the operation, so a retry of that
        operation collapses onto the same record. Without one, each call is a
        distinct operation and is admitted on its own merits even when another
        record already holds identical content. The semantic digest is recorded
        on the record as a maintenance candidate signal and never governs
        admission (ADR-071).
        """

        return request.idempotency_key or f"operation:{request.namespace}:{uuid4()}"

    def write(
        self, principal: MemoryPrincipal, request: MemoryWriteRequest
    ) -> WriteReceipt:
        """Admit a new memory under the caller's WRITE grant."""

        return self._admit(principal, request, action=AuthorizationAction.WRITE)

    def _admit(
        self,
        principal: MemoryPrincipal,
        request: MemoryWriteRequest,
        *,
        action: AuthorizationAction,
    ) -> WriteReceipt:
        """Single admission implementation behind an explicit authority gate.

        ``action`` names which grant admits this record. Ingestion uses WRITE.
        Scheduled maintenance uses MAINTAIN, so a nightly principal can derive
        consolidated memories from records the store already holds without
        gaining the authority to ingest new source material (ADR-075).
        """

        authorization = self.namespace_policy.evaluate(
            principal,
            action,
            request.namespace,
        )
        normalization = normalize_candidate(
            request.content,
            context={
                "namespace": request.namespace,
                "memory_class": request.memory_class.value,
                "assertion": request.assertion.model_dump(mode="json")
                if request.assertion
                else None,
                "consent_id": str(request.consent.consent_id)
                if request.consent
                else None,
            },
        )
        idempotency_key = self._operation_identity(request)
        existing = (
            self.store.find_by_idempotency(
                principal.tenant_id,
                request.namespace,
                idempotency_key,
            )
            if request.idempotency_key
            else None
        )
        admission = self.admission.evaluate(
            request,
            normalization,
            authorization,
            duplicate_record_exists=existing is not None,
        )

        if admission.status is WriteStatus.DUPLICATE:
            if existing is None:
                raise StoreError(
                    "admission reported duplicate but store returned no record"
                )
            receipt = WriteReceipt(
                status=WriteStatus.DUPLICATE,
                record_id=existing.record_id,
                namespace=request.namespace,
                schema_version=existing.schema_version,
                normalized_digest=normalization.normalized_digest,
                original_digest=normalization.original_digest,
                idempotency_key=idempotency_key,
                idempotency_key_supplied=request.idempotency_key is not None,
                admission=admission,
                authorization=authorization,
                warnings=admission.warnings,
            )
            if not request.dry_run:
                self.store.commit_write(None, receipt)
            return receipt

        if admission.status is WriteStatus.REJECTED:
            receipt = WriteReceipt(
                status=WriteStatus.REJECTED,
                namespace=request.namespace,
                schema_version=MEMORY_SCHEMA_VERSION,
                normalized_digest=normalization.normalized_digest,
                original_digest=normalization.original_digest,
                idempotency_key=idempotency_key,
                idempotency_key_supplied=request.idempotency_key is not None,
                admission=admission,
                authorization=authorization,
                warnings=admission.warnings,
            )
            if not request.dry_run:
                self.store.commit_write(None, receipt)
            return receipt

        now = self.clock.now()
        state = (
            MemoryState.QUARANTINED
            if admission.status is WriteStatus.QUARANTINED
            else MemoryState.ACTIVE
        )
        temporal = TemporalCoordinates(
            valid_from=request.valid_from,
            valid_to=request.valid_to,
            recorded_at=now,
            source_observed_at=request.source_observed_at,
        )
        record = MemoryRecord(
            tenant_id=principal.tenant_id,
            namespace=request.namespace,
            memory_class=request.memory_class,
            content=normalization.redacted_content,
            assertion=request.assertion,
            temporal=temporal,
            provenance=request.provenance,
            evidence=request.evidence,
            confidence=request.confidence,
            state=state,
            tags=request.tags,
            metadata={
                **request.metadata,
                "pii_redacted": bool(normalization.pii_types),
                "safety_signals": list(normalization.safety_signals),
            },
            normalized_digest=normalization.normalized_digest,
            original_digest=normalization.original_digest,
            idempotency_key=idempotency_key,
            supersedes=request.supersedes,
            references=request.references,
            consent=request.consent,
            created_by=principal.audit_subject,
            created_at=now,
        )
        warnings = list(admission.warnings)
        effective_supersedes = request.supersedes if state is MemoryState.ACTIVE else ()
        if request.supersedes and state is MemoryState.QUARANTINED:
            warnings.append(
                "supersession deferred until the quarantined candidate is approved"
            )

        status_events: list[MemoryStatusEvent] = []
        for record_id in effective_supersedes:
            prior = self.store.get_record(record_id)
            if prior is None:
                raise StoreError(f"superseded record does not exist: {record_id}")
            if (
                prior.tenant_id != principal.tenant_id
                or prior.namespace != request.namespace
            ):
                raise AuthorizationError(
                    "cannot supersede a record outside the authorized tenant and namespace"
                )
            status_events.append(
                MemoryStatusEvent(
                    record_id=record_id,
                    previous_state=prior.state,
                    new_state=MemoryState.SUPERSEDED,
                    reason=f"superseded by {record.record_id}",
                    actor=principal.audit_subject,
                    occurred_at=now,
                )
            )

        outbox_events: tuple[OutboxEvent, ...] = ()
        if state is MemoryState.ACTIVE and self.projection.name != "none":
            events = [
                OutboxEvent(
                    event_type="memory.record.project",
                    aggregate_id=record.record_id,
                    namespace=record.namespace,
                    payload={
                        "record_id": str(record.record_id),
                        "schema_version": record.schema_version,
                    },
                    created_at=now,
                    next_attempt_at=now,
                )
            ]
            # A superseded record must stop being projected, or retrieval keeps
            # surfacing truth the canonical store has already replaced. The
            # retirement intent commits in the same transaction as the
            # supersession itself, so the two cannot diverge (ADR-074).
            events.extend(
                OutboxEvent(
                    event_type="memory.record.retire",
                    aggregate_id=superseded_id,
                    namespace=record.namespace,
                    payload={
                        "record_id": str(superseded_id),
                        "reason": f"superseded by {record.record_id}",
                        "superseded_by": str(record.record_id),
                    },
                    created_at=now,
                    next_attempt_at=now,
                )
                for superseded_id in effective_supersedes
            )
            outbox_events = tuple(events)

        receipt = WriteReceipt(
            status=admission.status,
            record_id=record.record_id,
            namespace=record.namespace,
            schema_version=record.schema_version,
            normalized_digest=record.normalized_digest,
            original_digest=record.original_digest,
            idempotency_key=record.idempotency_key,
            idempotency_key_supplied=request.idempotency_key is not None,
            admission=admission,
            authorization=authorization,
            outbox_event_ids=tuple(event.event_id for event in outbox_events),
            superseded_record_ids=effective_supersedes,
            warnings=tuple(warnings),
            created_at=now,
        )
        initial_reason = (
            "record quarantined by admission policy"
            if state is MemoryState.QUARANTINED
            else "record admitted and supersedes prior records"
            if effective_supersedes
            else "record admitted by admission policy"
        )
        initial_event = MemoryStatusEvent(
            record_id=record.record_id,
            previous_state=None,
            new_state=state,
            reason=initial_reason,
            actor=principal.audit_subject,
            occurred_at=now,
            receipt_id=receipt.receipt_id,
        )
        status_events = [
            initial_event,
            *(
                event.model_copy(update={"receipt_id": receipt.receipt_id})
                for event in status_events
            ),
        ]
        if not request.dry_run:
            self.store.commit_write(
                record,
                receipt,
                outbox_events=outbox_events,
                status_events=tuple(status_events),
            )
        return receipt

    def get(self, principal: MemoryPrincipal, record_id: UUID) -> MemoryRecord | None:
        record = self.store.get_record(record_id)
        if record is None:
            return None
        if record.tenant_id != principal.tenant_id and not principal.is_admin:
            raise AuthorizationError("record belongs to a different tenant")
        self.namespace_policy.require(
            principal, AuthorizationAction.READ, record.namespace
        )
        if record.state is MemoryState.QUARANTINED and not principal.is_admin:
            raise AuthorizationError(
                "quarantined records require administrator authority"
            )
        if (
            record.state in {MemoryState.DELETION_PENDING, MemoryState.DELETED}
            and not principal.is_admin
        ):
            raise AuthorizationError("deleted records require administrator authority")
        return record

    @staticmethod
    def _concrete_namespaces(patterns: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            pattern
            for pattern in patterns
            if not any(character in pattern for character in "*?[]")
        )

    def _authorized_search_namespaces(
        self,
        principal: MemoryPrincipal,
        requested: tuple[str, ...],
    ) -> tuple[str, ...]:
        namespaces = requested or self._concrete_namespaces(principal.read_namespaces)
        if not namespaces:
            raise AuthorizationError(
                "explicit namespace is required when read grants contain only wildcards"
            )
        for namespace in namespaces:
            self.namespace_policy.require(
                principal, AuthorizationAction.READ, namespace
            )
        return tuple(dict.fromkeys(namespaces))

    def search(
        self, principal: MemoryPrincipal, request: MemorySearchRequest
    ) -> SearchReceipt:
        namespaces = self._authorized_search_namespaces(principal, request.namespaces)
        now = self.clock.now()
        effective_request = (
            request
            if request.recorded_before is not None
            else request.model_copy(update={"recorded_before": now})
        )
        return self.retrieval.search(
            principal.tenant_id,
            effective_request,
            namespaces,
            now=now,
        )

    def hydrate(
        self, principal: MemoryPrincipal, request: HydrationRequest
    ) -> HydrationResult:
        query_parts = [request.task, *request.entities, *request.topics]
        search_request = MemorySearchRequest(
            query=" ".join(part for part in query_parts if part),
            namespaces=request.namespaces,
            memory_classes=request.memory_classes,
            valid_at=request.valid_at,
            limit=request.max_records,
            token_budget=request.token_budget,
        )
        search = self.search(principal, search_request)
        return self.budget_allocator.allocate(
            search, task=request.task, token_budget=request.token_budget
        )

    @staticmethod
    def _overlaps(left: MemoryRecord, right: MemoryRecord) -> bool:
        left_end = left.temporal.valid_to
        right_end = right.temporal.valid_to
        return (left_end is None or right.temporal.valid_from < left_end) and (
            right_end is None or left.temporal.valid_from < right_end
        )

    @staticmethod
    def _snapshot_digest(records: tuple[MemoryRecord, ...] | list[MemoryRecord]) -> str:
        return sha256_text(
            canonical_json(
                [
                    {
                        "record_id": str(record.record_id),
                        "digest": record.normalized_digest,
                        "state": record.state.value,
                        "valid_from": record.temporal.valid_from,
                        "valid_to": record.temporal.valid_to,
                        "recorded_at": record.temporal.recorded_at,
                    }
                    for record in sorted(records, key=lambda item: str(item.record_id))
                ]
            )
        )

    def conflicts(self, principal: MemoryPrincipal, namespace: str) -> ConflictReport:
        self.namespace_policy.require(principal, AuthorizationAction.READ, namespace)
        records = self.store.list_records(
            principal.tenant_id,
            namespace,
            states=(MemoryState.ACTIVE,),
        )
        structured = [
            record
            for record in records
            if record.assertion and record.assertion.is_structured
        ]
        conflicts: list[ConflictItem] = []
        for index, left in enumerate(structured):
            assert left.assertion is not None
            for right in structured[index + 1 :]:
                assert right.assertion is not None
                same_key = (
                    (left.assertion.subject or "").casefold()
                    == (right.assertion.subject or "").casefold()
                    and (left.assertion.predicate or "").casefold()
                    == (right.assertion.predicate or "").casefold()
                )
                different_value = (left.assertion.object or "").casefold() != (
                    right.assertion.object or ""
                ).casefold()
                if same_key and different_value and self._overlaps(left, right):
                    conflicts.append(
                        ConflictItem(
                            left_record_id=left.record_id,
                            right_record_id=right.record_id,
                            subject=left.assertion.subject,
                            predicate=left.assertion.predicate,
                            reason="overlapping valid-time assertions have different objects",
                        )
                    )
        return ConflictReport(
            namespace=namespace,
            conflicts=tuple(conflicts),
            checked_record_count=len(records),
            snapshot_digest=self._snapshot_digest(records),
            checked_at=self.clock.now(),
        )

    def phase_lock(
        self, principal: MemoryPrincipal, request: PhaseLockRequest
    ) -> PhaseLockReceipt:
        self.namespace_policy.require(
            principal, AuthorizationAction.WRITE, request.namespace
        )
        report = self.conflicts(principal, request.namespace)
        now = self.clock.now()
        receipt = PhaseLockReceipt(
            namespace=request.namespace,
            task_signature=request.task_signature,
            granted=report.status is OperationStatus.COMPLETE
            and not report.has_conflicts,
            conflict_report=report,
            snapshot_digest=report.snapshot_digest,
            expires_at=now + timedelta(seconds=request.ttl_seconds),
            principal_id=principal.principal_id,
            created_at=now,
        )
        self.store.save_phase_lock(receipt)
        return receipt

    def verify_phase_lock(
        self,
        principal: MemoryPrincipal,
        namespace: str,
        task_signature: str,
    ) -> PhaseLockVerification:
        self.namespace_policy.require(principal, AuthorizationAction.READ, namespace)
        now = self.clock.now()
        lock = self.store.get_phase_lock(namespace, task_signature)
        report = self.conflicts(principal, namespace)
        reasons: list[str] = []
        if lock is None:
            reasons.append("phase lock does not exist")
        else:
            if not lock.granted:
                reasons.append("phase lock was not granted")
            if lock.principal_id != principal.principal_id and not principal.is_admin:
                reasons.append("phase lock belongs to a different principal")
            if lock.expires_at <= now:
                reasons.append("phase lock expired")
            if lock.snapshot_digest != report.snapshot_digest:
                reasons.append("namespace changed after phase lock issuance")
            if report.has_conflicts:
                reasons.append("current namespace contains conflicts")
        return PhaseLockVerification(
            lock_id=lock.lock_id if lock else None,
            namespace=namespace,
            task_signature=task_signature,
            valid=not reasons,
            reasons=tuple(reasons or ["phase lock is current and conflict-free"]),
            current_snapshot_digest=report.snapshot_digest,
            verified_at=now,
        )

    def lineage(
        self,
        principal: MemoryPrincipal,
        namespace: str,
        record_id: UUID,
    ) -> LineageReplay:
        self.namespace_policy.require(principal, AuthorizationAction.READ, namespace)
        record = self.store.get_record(record_id)
        if record is None:
            raise StoreError(f"record not found: {record_id}")
        if record.tenant_id != principal.tenant_id or record.namespace != namespace:
            raise AuthorizationError(
                "record is outside the authorized tenant or namespace"
            )
        return self.lineage_replayer.replay(principal.tenant_id, namespace, record_id)

    def promote(
        self, principal: MemoryPrincipal, request: PromotionRequest
    ) -> WriteReceipt:
        record = self.get(principal, request.record_id)
        if record is None:
            raise StoreError(f"record not found: {request.record_id}")
        self.namespace_policy.require(
            principal, AuthorizationAction.PROMOTE, record.namespace
        )
        for supporting_id in request.supporting_record_ids:
            supporting = self.store.get_record(supporting_id)
            if supporting is None:
                raise StoreError(f"supporting record not found: {supporting_id}")
            if (
                supporting.tenant_id != principal.tenant_id
                or supporting.namespace != record.namespace
            ):
                raise AuthorizationError(
                    "promotion support crosses tenant or namespace boundary"
                )
        conflict_report = self.conflicts(principal, record.namespace)
        if conflict_report.has_conflicts and not request.governance_approval:
            raise AuthorizationError(
                "promotion denied while unresolved conflicts exist"
            )
        decision = self.promotion_policy.evaluate(record, request)
        if not decision.approved:
            raise AuthorizationError("promotion denied: " + "; ".join(decision.reasons))
        evidence = list(record.evidence)
        if request.governance_approval:
            evidence.append(
                EvidenceRef(
                    kind=EvidenceKind.GOVERNANCE_APPROVAL,
                    description=request.reason,
                    source_id=principal.audit_subject,
                )
            )
        provenance = Provenance(
            source="memory-promotion",
            source_id=str(record.record_id),
            source_digest=record.normalized_digest,
            source_agent_id=principal.agent_id,
            extraction_method=decision.policy_version,
        )
        write_request = MemoryWriteRequest(
            namespace=record.namespace,
            memory_class=request.target_class,
            content=record.content,
            assertion=record.assertion,
            provenance=provenance,
            evidence=tuple(evidence),
            confidence=record.confidence,
            valid_from=record.temporal.valid_from,
            valid_to=record.temporal.valid_to,
            source_observed_at=record.temporal.source_observed_at,
            tags=tuple({*record.tags, "promoted"}),
            metadata={
                **record.metadata,
                "promotion_policy": decision.policy_version,
                "promotion_reasons": list(decision.reasons),
            },
            idempotency_key=f"promotion:{record.record_id}:{request.target_class.value}",
            supersedes=(record.record_id,),
            references=tuple(
                dict.fromkeys((*request.supporting_record_ids, record.record_id))
            ),
            consent=request.consent or record.consent,
        )
        return self.write(principal, write_request)

    def apply_retention(
        self,
        principal: MemoryPrincipal,
        namespace: str,
        *,
        apply: bool,
    ) -> RetentionReceipt:
        authorization = self.namespace_policy.require(
            principal,
            AuthorizationAction.ARCHIVE if apply else AuthorizationAction.READ,
            namespace,
        )
        now = self.clock.now()
        records = tuple(
            self.store.list_records(
                principal.tenant_id,
                namespace,
                states=(MemoryState.ACTIVE, MemoryState.SUPERSEDED),
                limit=100_000,
            )
        )
        decisions = self.retention_engine.evaluate(records, now=now)
        archived_ids = tuple(
            decision.record_id for decision in decisions if decision.action == "archive"
        )
        archive_receipt = ArchiveReceipt(
            namespace=namespace,
            applied=apply,
            archived_record_ids=archived_ids,
            authorization=authorization,
            reason=f"reference-aware retention under {self.retention_policy.policy_version}",
            actor=principal.audit_subject,
            created_at=now,
        )
        if apply and archived_ids:
            by_id = {record.record_id: record for record in records}
            status_events = tuple(
                MemoryStatusEvent(
                    record_id=record_id,
                    previous_state=by_id[record_id].state,
                    new_state=MemoryState.ARCHIVED,
                    reason=archive_receipt.reason,
                    actor=principal.audit_subject,
                    occurred_at=now,
                    receipt_id=archive_receipt.receipt_id,
                )
                for record_id in archived_ids
            )
            # Archiving withdraws the record from active retrieval, so its
            # projection must be withdrawn too. This is retirement, not privacy
            # erasure: the canonical content is preserved (ADR-074).
            retire_events = (
                tuple(
                    OutboxEvent(
                        event_type="memory.record.retire",
                        aggregate_id=record_id,
                        namespace=namespace,
                        payload={
                            "record_id": str(record_id),
                            "reason": archive_receipt.reason,
                            "archive_receipt_id": str(archive_receipt.receipt_id),
                        },
                        created_at=now,
                        next_attempt_at=now,
                    )
                    for record_id in archived_ids
                )
                if self.projection.name != "none"
                else ()
            )
            self.store.commit_archive(
                archive_receipt,
                status_events=status_events,
                outbox_events=retire_events,
            )
        return RetentionReceipt(
            namespace=namespace,
            applied=apply,
            decisions=decisions,
            archive_receipt=archive_receipt,
            created_at=now,
        )

    def delete(
        self, principal: MemoryPrincipal, request: DeletionRequest
    ) -> DeletionReceipt:
        record = self.store.get_record(request.record_id)
        if record is None:
            raise StoreError(f"record not found: {request.record_id}")
        if record.tenant_id != principal.tenant_id and not principal.is_admin:
            raise AuthorizationError("deletion target belongs to a different tenant")
        authorization = self.namespace_policy.require(
            principal,
            AuthorizationAction.ADMIN,
            record.namespace,
        )
        now = self.clock.now()
        tombstone_digest = sha256_text(
            canonical_json(
                {
                    "record_id": str(record.record_id),
                    "tenant_id": record.tenant_id,
                    "namespace": record.namespace,
                    "reason_digest": sha256_text(request.reason),
                    "verification_reference_digest": sha256_text(
                        request.verification_reference
                    ),
                    "requested_by": principal.audit_subject,
                    "requested_at": now,
                }
            )
        )
        if request.dry_run:
            return DeletionReceipt(
                record_id=record.record_id,
                namespace=record.namespace,
                status=DeletionStatus.DRY_RUN,
                tombstone_digest=tombstone_digest,
                authorization=authorization,
                reason=request.reason,
                verification_reference=request.verification_reference,
                requested_by=principal.audit_subject,
                created_at=now,
            )

        projection_enabled = self.projection.name != "none"
        event = (
            OutboxEvent(
                event_type="memory.record.erase",
                aggregate_id=record.record_id,
                namespace=record.namespace,
                payload={},
                created_at=now,
                next_attempt_at=now,
            )
            if projection_enabled
            else None
        )
        status = (
            DeletionStatus.PENDING_PROJECTION
            if projection_enabled
            else DeletionStatus.COMPLETE
        )
        receipt = DeletionReceipt(
            record_id=record.record_id,
            namespace=record.namespace,
            status=status,
            tombstone_digest=tombstone_digest,
            authorization=authorization,
            reason=request.reason,
            verification_reference=request.verification_reference,
            projection_event_id=event.event_id if event else None,
            requested_by=principal.audit_subject,
            created_at=now,
            completed_at=now if not projection_enabled else None,
        )
        if event is not None:
            event = event.model_copy(
                update={
                    "payload": {
                        "record_id": str(record.record_id),
                        "deletion_receipt_id": str(receipt.receipt_id),
                    }
                }
            )
        redacted_state = (
            MemoryState.DELETION_PENDING if projection_enabled else MemoryState.DELETED
        )
        redacted_record = record.model_copy(
            update={
                "content": f"[deleted:{receipt.tombstone_id}]",
                "assertion": None,
                "provenance": Provenance(
                    source="verified-deletion",
                    extraction_method="privacy-deletion/v1",
                    source_trust=1.0,
                    transformed_at=now,
                ),
                "evidence": (),
                "confidence": Confidence(score=0.0, evidence_count=0),
                "state": redacted_state,
                "tags": ("deleted", "privacy-tombstone"),
                "metadata": {
                    "tombstone_id": str(receipt.tombstone_id),
                    "tombstone_digest": tombstone_digest,
                    "deletion_receipt_id": str(receipt.receipt_id),
                },
                "normalized_digest": tombstone_digest,
                "original_digest": tombstone_digest,
                "consent": None,
            }
        )
        self.store.commit_deletion(
            receipt,
            redacted_record,
            outbox_event=event,
        )
        return receipt

    def prune(
        self, principal: MemoryPrincipal, namespace: str, *, apply: bool
    ) -> ArchiveReceipt:
        """Compatibility surface for archive-first retention."""

        return self.apply_retention(principal, namespace, apply=apply).archive_receipt

    def health(self) -> HealthReport:
        store_health = self.store.health()
        projection_health = self.projection.health()
        degraded: list[str] = []
        if not store_health.get("healthy"):
            status = OperationStatus.FAILED
            degraded.append("canonical store is unhealthy")
        elif self.projection.name != "none" and not projection_health.get("healthy"):
            status = OperationStatus.PARTIAL
            degraded.append("projection is unhealthy")
        else:
            status = OperationStatus.COMPLETE
        return HealthReport(
            status=status,
            package_version=PACKAGE_VERSION,
            schema_version=MEMORY_SCHEMA_VERSION,
            store=store_health,
            projection=projection_health,
            outbox_backlog=self.store.outbox_backlog(),
            degraded_reasons=tuple(degraded),
            checked_at=self.clock.now(),
        )

    def stats(self) -> dict[str, object]:
        return self.store.stats()
