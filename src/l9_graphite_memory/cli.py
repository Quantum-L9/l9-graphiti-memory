# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/cli.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Operator CLI. Every command delegates to the canonical MemoryService."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from l9_graphite_memory.client_config import (
    ClientConfigStatus,
    CursorClientConfigurator,
    probe_generated_server,
)
from l9_graphite_memory.contracts import (
    ALL_MAINTENANCE_OPERATIONS,
    Confidence,
    ConsentGrant,
    DeletionRequest,
    EvidenceKind,
    EvidenceRef,
    HydrationRequest,
    MaintenanceOperation,
    MaintenanceRequest,
    MemoryAssertion,
    MemoryClass,
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryWriteRequest,
    PhaseLockReceipt,
    PhaseLockRequest,
    PromotionRequest,
    Provenance,
)
from l9_graphite_memory.curation.procedural import (
    PatternProceduralSynthesizer,
    ProceduralSynthesisWorker,
)
from l9_graphite_memory.errors import L9MemoryError
from l9_graphite_memory.extraction import SourceDistiller
from l9_graphite_memory.group_resolver import GroupResolution, resolve_group
from l9_graphite_memory.ingestion import (
    DocumentIngestor,
    RepositoryBootstrapper,
    execute_topology_publication,
    load_publication_plan,
    load_verified_bundle,
)
from l9_graphite_memory.maintenance import MaintenanceService
from l9_graphite_memory.memory_guard import GuardEvidence
from l9_graphite_memory.migration import LEGACY_QUEUE_DIRNAME, LegacyWriteQueueDrain
from l9_graphite_memory.runtime import (
    MemoryRuntime,
    build_runtime,
    local_principal_for_resolution,
)
from l9_graphite_memory.secrets import load_secrets_sync
from l9_graphite_memory.services import GeneratedDataService, OutboxWorker

_LEGACY_KIND_MAP = {
    "lesson": MemoryClass.PROCEDURAL,
    "decision": MemoryClass.DECISION,
    "preference": MemoryClass.PREFERENCE,
    "constraint": MemoryClass.CONSTRAINT,
    "manifest": MemoryClass.META,
    "session": MemoryClass.EPISODIC,
    "session_summary": MemoryClass.EPISODIC,
    "observation": MemoryClass.OBSERVATION,
    "insight": MemoryClass.INSIGHT,
    "fact": MemoryClass.SEMANTIC,
}


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def _print(value: Any) -> None:
    sys.stdout.write(_json(value) + "\n")


def _parse_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _memory_class(value: str) -> MemoryClass:
    try:
        return MemoryClass(value)
    except ValueError:
        mapped = _LEGACY_KIND_MAP.get(value)
        if mapped is None:
            allowed = ", ".join(item.value for item in MemoryClass)
            raise argparse.ArgumentTypeError(
                f"unknown memory class {value!r}; choose from {allowed}"
            ) from None
        return mapped


def _runtime(args: argparse.Namespace) -> MemoryRuntime:
    load_secrets_sync()
    return build_runtime(getattr(args, "config", None))


def _context(
    runtime: MemoryRuntime,
    args: argparse.Namespace,
    *,
    cwd: Path | None = None,
) -> tuple[GroupResolution, MemoryPrincipal]:
    resolution = resolve_group(
        cwd or Path.cwd(),
        explicit=getattr(args, "group_id", None),
        settings=runtime.settings,
    )
    principal = local_principal_for_resolution(runtime.settings, resolution)
    return resolution, principal


def _consent_from_args(
    args: argparse.Namespace,
    *,
    namespace: str,
    memory_class: MemoryClass,
    principal: MemoryPrincipal,
) -> ConsentGrant | None:
    subject_id = getattr(args, "consent_subject_id", None)
    purpose = getattr(args, "consent_purpose", None)
    description = getattr(args, "consent_evidence", None)
    supplied = [bool(subject_id), bool(purpose), bool(description)]
    if any(supplied) and not all(supplied):
        raise L9MemoryError(
            "consent-subject-id, consent-purpose, and consent-evidence must be supplied together"
        )
    if not any(supplied):
        return None
    return ConsentGrant(
        subject_id=str(subject_id),
        namespace=namespace,
        allowed_classes=(memory_class,),
        purpose=str(purpose),
        evidence=EvidenceRef(
            kind=EvidenceKind.EXPLICIT,
            description=str(description),
            source_id=getattr(args, "consent_source_id", None) or principal.audit_subject,
        ),
        expires_at=_parse_datetime(getattr(args, "consent_expires_at", None)),
    )


def cmd_health(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        report = runtime.service.health()
        _print(report)
        return 0 if report.status.value == "complete" else 1
    finally:
        runtime.close()


def cmd_resolve(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution = resolve_group(
            Path.cwd(),
            explicit=getattr(args, "group_id", None),
            settings=runtime.settings,
        )
        _print(resolution)
        return 0 if resolution.group_id else 2
    finally:
        runtime.close()


def cmd_write(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        if not resolution.group_id:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        assertion = None
        if any((args.subject, args.predicate, args.object)):
            if not all((args.subject, args.predicate, args.object)):
                raise L9MemoryError("subject, predicate, and object must be provided together")
            assertion = MemoryAssertion(
                subject=args.subject, predicate=args.predicate, object=args.object
            )
        evidence = EvidenceRef(
            kind=EvidenceKind.EXPLICIT,
            description="operator supplied through l9-memory CLI",
            source_id=args.source_id,
        )
        request = MemoryWriteRequest(
            namespace=resolution.group_id,
            memory_class=args.kind,
            content=args.body,
            assertion=assertion,
            provenance=Provenance(
                source=args.source,
                source_id=args.source_id,
                source_agent_id=principal.agent_id,
                session_id=os.environ.get("CURSOR_CONVERSATION_ID")
                or os.environ.get("L9_SESSION_ID"),
                tool="l9-memory write",
                extraction_method="direct-cli/v1",
                source_trust=args.source_trust,
            ),
            evidence=(evidence,),
            confidence=Confidence(score=args.confidence, evidence_count=1),
            valid_from=_parse_datetime(args.valid_from) or datetime.now(timezone.utc),
            valid_to=_parse_datetime(args.valid_to),
            tags=tuple(args.tag),
            idempotency_key=args.idempotency_key,
            supersedes=tuple(UUID(value) for value in args.supersedes),
            references=tuple(UUID(value) for value in args.references),
            consent=_consent_from_args(
                args,
                namespace=resolution.group_id,
                memory_class=args.kind,
                principal=principal,
            ),
            dry_run=args.dry_run,
        )
        receipt = runtime.service.write(principal, request)
        _print(receipt)
        return 0 if receipt.status.value not in {"rejected"} else 2
    finally:
        runtime.close()


def cmd_search(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        if not resolution.group_id:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        namespaces = tuple(args.namespace) if args.namespace else (resolution.group_id,)
        if args.include_workspace and runtime.settings.workspace_namespace not in namespaces:
            namespaces = (*namespaces, runtime.settings.workspace_namespace)
        request = MemorySearchRequest(
            query=args.query,
            namespaces=namespaces,
            memory_classes=tuple(args.memory_class),
            valid_at=_parse_datetime(args.valid_at) or datetime.now(timezone.utc),
            recorded_before=_parse_datetime(args.recorded_before),
            include_superseded=args.include_superseded,
            include_archived=args.include_archived,
            min_confidence=args.min_confidence,
            limit=args.limit,
            token_budget=args.token_budget,
        )
        receipt = runtime.service.search(principal, request)
        _print(receipt)
        return 0 if receipt.status.value != "failed" else 1
    finally:
        runtime.close()


def cmd_hydrate(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        if not resolution.group_id:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        namespaces = tuple(args.namespace) if args.namespace else (resolution.group_id,)
        result = runtime.service.hydrate(
            principal,
            HydrationRequest(
                task=args.task,
                namespaces=namespaces,
                entities=tuple(args.entity),
                topics=tuple(args.topic),
                memory_classes=tuple(args.memory_class),
                token_budget=args.token_budget,
                max_records=args.max_records,
            ),
        )
        _print(result)
        return 0 if result.status.value != "failed" else 1
    finally:
        runtime.close()


def cmd_get(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        record = runtime.service.get(principal, UUID(args.record_id))
        if record is None:
            _print({"found": False, "record_id": args.record_id})
            return 2
        _print(record)
        return 0
    finally:
        runtime.close()


def cmd_stats(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _print(runtime.service.stats())
        return 0
    finally:
        runtime.close()


def cmd_conflicts(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        report = runtime.service.conflicts(principal, namespace)
        _print(report)
        return 2 if report.has_conflicts else 0
    finally:
        runtime.close()


def cmd_phase_lock(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        signature = (
            args.task_signature or hashlib.sha256(args.task.encode("utf-8")).hexdigest()[:32]
        )
        receipt = runtime.service.phase_lock(
            principal,
            PhaseLockRequest(
                namespace=namespace,
                task_signature=signature,
                ttl_seconds=args.ttl_seconds,
            ),
        )
        state_file = _mark_phase_lock_state(runtime, receipt)
        payload = receipt.model_dump(mode="json")
        payload["state_file"] = str(state_file)
        _print(payload)
        return 0 if receipt.granted else 2
    finally:
        runtime.close()


def cmd_verify_phase_lock(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        verification = runtime.service.verify_phase_lock(
            principal,
            namespace,
            args.task_signature,
        )
        _print(verification)
        return 0 if verification.valid else 2
    finally:
        runtime.close()


def cmd_lineage(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        replay = runtime.service.lineage(principal, namespace, UUID(args.record_id))
        _print(replay)
        return 0 if not replay.issues else 2
    finally:
        runtime.close()


def cmd_bootstrap(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        repo = Path(args.repo).expanduser().resolve()
        resolution, principal = _context(runtime, args, cwd=repo)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        bootstrapper = RepositoryBootstrapper(runtime.service)
        receipts = bootstrapper.bootstrap(
            principal,
            repo,
            namespace=namespace,
            dry_run=args.dry_run,
        )
        _print(
            {
                "namespace": namespace,
                "repo": str(repo),
                "dry_run": args.dry_run,
                "receipt_count": len(receipts),
                "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
            }
        )
        return 0
    finally:
        runtime.close()


def cmd_import(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        ingestor = DocumentIngestor()
        requests = ingestor.requests(
            args.path,
            namespace=namespace,
            memory_class=args.memory_class,
            repository=args.repository,
            tags=tuple(args.tag),
            dry_run=args.dry_run,
        )
        receipts = [runtime.service.write(principal, request) for request in requests]
        _print(
            {
                "path": str(Path(args.path).expanduser().resolve()),
                "namespace": namespace,
                "chunks": len(requests),
                "dry_run": args.dry_run,
                "receipts": [receipt.model_dump(mode="json") for receipt in receipts],
            }
        )
        return 0
    finally:
        runtime.close()


def cmd_distill(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        source = Path(args.path).expanduser().resolve()
        resolution, principal = _context(runtime, args, cwd=source.parent)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        receipt = SourceDistiller(runtime.service).distill_path(
            principal,
            source,
            namespace=namespace,
            repository=args.repository,
            dry_run=args.dry_run,
        )
        _print(receipt)
        return 0 if receipt.status.value != "failed" else 2
    finally:
        runtime.close()


def _state_path(runtime: MemoryRuntime) -> Path:
    conversation = (
        os.environ.get("CURSOR_CONVERSATION_ID") or os.environ.get("L9_SESSION_ID") or "default"
    )
    return runtime.settings.state_dir / f"{conversation}.json"


def _read_state(path: Path) -> GuardEvidence | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return GuardEvidence.model_validate(value)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _write_state(path: Path, state: GuardEvidence) -> None:
    """Atomically persist an ephemeral verification receipt cache."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _mark_phase_lock_state(runtime: MemoryRuntime, receipt: PhaseLockReceipt) -> Path:
    """Mirror a durable phase-lock receipt into the local verification cache."""

    path = _state_path(runtime)
    current = _read_state(path) or GuardEvidence(namespace=receipt.namespace)
    state = current.model_copy(
        update={
            "schema_version": 3,
            "namespace": receipt.namespace,
            "task_signature": receipt.task_signature,
            "phase_lock_granted": receipt.granted,
            "phase_lock_task_signature": receipt.task_signature,
            "phase_lock_expires_at": receipt.expires_at,
        }
    )
    _write_state(path, state)
    return path


def cmd_inject(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        if not resolution.group_id:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        result = runtime.service.hydrate(
            principal,
            HydrationRequest(
                task=args.task,
                namespaces=(resolution.group_id,),
                token_budget=args.token_budget,
                max_records=args.max_records,
            ),
        )
        task_signature = hashlib.sha256(args.task.encode("utf-8")).hexdigest()[:32]
        path = _state_path(runtime)
        state = GuardEvidence(
            namespace=resolution.group_id,
            hydrated_at=result.created_at,
            hydration_digest=result.result_digest,
            hydration_status=result.status.value,
            task_signature=task_signature,
            verified_task_signatures=(task_signature,) if result.status.value != "failed" else (),
            ttl_minutes=runtime.settings.gate_ttl_minutes,
        )
        _write_state(path, state)
        _print({"state_file": str(path), "hydration": result.model_dump(mode="json")})
        return 0 if result.status.value != "failed" else 1
    finally:
        runtime.close()


def cmd_autoseed_check(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            return 2
        receipt = runtime.service.search(
            principal,
            MemorySearchRequest(
                query="repository architecture manifest",
                namespaces=(namespace,),
                limit=5,
            ),
        )
        seeded = any("bootstrap" in hit.record.tags for hit in receipt.hits)
        _print(
            {
                "seeded": seeded,
                "namespace": namespace,
                "matching_records": len(receipt.hits),
            }
        )
        return 0 if seeded else 2
    finally:
        runtime.close()


def cmd_prune(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        # --dry-run always wins over --apply: a preview flag must never archive.
        receipt = runtime.service.apply_retention(
            principal, namespace, apply=args.apply and not args.dry_run
        )
        _print(receipt)
        return 0
    finally:
        runtime.close()


def cmd_rebuild_projection(args: argparse.Namespace) -> int:
    """Re-project active records that have no live projection link."""

    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        receipt = runtime.service.rebuild_projection(
            principal,
            namespace,
            apply=args.apply,
            limit=args.limit,
            reason=args.reason,
        )
        _print(receipt)
        return 0
    finally:
        runtime.close()


def cmd_maintain(args: argparse.Namespace) -> int:
    """Run scheduled canonical-memory maintenance for one namespace."""

    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        operations = (
            tuple(MaintenanceOperation(value) for value in args.operation)
            if args.operation
            else ALL_MAINTENANCE_OPERATIONS
        )
        request = MaintenanceRequest(
            namespace=namespace,
            operations=operations,
            max_records=args.max_records,
            max_actions=args.max_actions,
            dry_run=not args.apply,
            reason=args.reason,
        )
        receipt = MaintenanceService(runtime.service).run(principal, request)
        _print(receipt)
        return 0 if not receipt.failures else 2
    finally:
        runtime.close()


def cmd_synthesize_procedures(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        namespace = args.group_id or resolution.group_id
        if not namespace:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        worker = ProceduralSynthesisWorker(
            runtime.service,
            PatternProceduralSynthesizer(
                runtime.service.store,
                minimum_support=args.minimum_support,
            ),
        )
        report = worker.run(
            principal,
            namespace=namespace,
            source_record_ids=tuple(UUID(value) for value in args.source_record_id),
            dry_run=args.dry_run,
        )
        _print(report)
        return 0
    finally:
        runtime.close()


def cmd_promote(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        record_id = UUID(args.record_id)
        record = runtime.service.get(principal, record_id)
        if record is None:
            raise L9MemoryError(f"record not found: {record_id}")
        receipt = runtime.service.promote(
            principal,
            PromotionRequest(
                record_id=record_id,
                target_class=args.target_class,
                explicit_confirmation=args.explicit_confirmation,
                governance_approval=args.governance_approval,
                test_success_count=args.test_success_count,
                supporting_record_ids=tuple(UUID(value) for value in args.supporting_record_id),
                consent=_consent_from_args(
                    args,
                    namespace=record.namespace,
                    memory_class=args.target_class,
                    principal=principal,
                ),
                reason=args.reason,
            ),
        )
        _print(receipt)
        return 0
    finally:
        runtime.close()


def cmd_delete(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        receipt = runtime.service.delete(
            principal,
            DeletionRequest(
                record_id=UUID(args.record_id),
                reason=args.reason,
                verification_reference=args.verification_reference,
                dry_run=args.dry_run,
            ),
        )
        _print(receipt)
        return 0 if receipt.status.value in {"complete", "pending_projection"} else 2
    finally:
        runtime.close()


def cmd_outbox_run(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        worker = OutboxWorker(runtime.service.store, runtime.service.projection, runtime.settings)
        _print(worker.run_once())
        return 0
    finally:
        runtime.close()


def cmd_drain_legacy_write_queue(args: argparse.Namespace) -> int:
    """Drain a queue left behind by the retired deferred-ingestion release."""

    runtime = _runtime(args)
    try:
        resolution, principal = _context(runtime, args)
        if not resolution.group_id:
            raise L9MemoryError(resolution.error or "namespace is unresolved")
        drain = LegacyWriteQueueDrain(runtime.settings.state_dir / LEGACY_QUEUE_DIRNAME)
        report = drain.drain(
            runtime.service,
            principal,
            apply=not args.dry_run,
            limit=args.limit,
        )
        _print(report)
        return 0 if report.drained_cleanly else 2
    finally:
        runtime.close()


def cmd_client(args: argparse.Namespace) -> int:
    if args.client_target != "cursor":
        raise ValueError(f"unsupported client target: {args.client_target}")
    path = Path(args.path) if args.path else None
    configurator = CursorClientConfigurator(path, interpreter=args.interpreter)
    action = args.cursor_action
    if action == "inspect":
        _print(configurator.inspect())
        return 0
    if action == "install":
        receipt = configurator.install(dry_run=args.dry_run)
        _print(receipt)
        return 0 if receipt.status != ClientConfigStatus.BLOCKED else 1
    if action == "uninstall":
        restore = Path(args.restore_backup) if args.restore_backup else None
        receipt = configurator.uninstall(dry_run=args.dry_run, restore_backup=restore)
        _print(receipt)
        return 0 if receipt.status != ClientConfigStatus.BLOCKED else 1
    if action == "status":
        receipt = configurator.status()
        _print(receipt)
        return 0 if receipt.status != ClientConfigStatus.BLOCKED else 1
    if action == "verify":
        probe = probe_generated_server(interpreter=args.interpreter, timeout_seconds=args.timeout)
        _print(probe)
        return 0 if probe.status == ClientConfigStatus.COMPLETE else 1
    raise ValueError(f"unsupported cursor action: {action}")


def _read_json_payload(args: argparse.Namespace) -> dict[str, Any]:
    if getattr(args, "file", None):
        value = json.loads(Path(args.file).read_text(encoding="utf-8"))
    else:
        raw = sys.stdin.read()
        if not raw.strip():
            raise L9MemoryError("JSON payload required on stdin or --file")
        value = json.loads(raw)
    if not isinstance(value, dict):
        raise L9MemoryError("JSON payload must be an object")
    return value


def cmd_ingest_governed_candidate(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        result = GeneratedDataService(runtime.service).ingest_governed_candidate(
            principal, _read_json_payload(args)
        )
        _print(result)
        return 0 if result.status.value != "rejected" else 7
    finally:
        runtime.close()


def cmd_record_reuse(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        result = GeneratedDataService(runtime.service).record_reuse(
            principal, _read_json_payload(args)
        )
        _print(result)
        return 0 if result.status.value != "rejected" else 7
    finally:
        runtime.close()


def cmd_invalidate_source(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        result = GeneratedDataService(runtime.service).invalidate_by_source(
            principal, _read_json_payload(args)
        )
        _print(result)
        return 0 if result.status.value != "rejected" else 7
    finally:
        runtime.close()


def cmd_generated_data_capabilities(args: argparse.Namespace) -> int:
    del args
    _print(GeneratedDataService.generated_data_capabilities())
    return 0


def cmd_ingest_topology_plan(args: argparse.Namespace) -> int:
    """Admit an l9-constellation-topology publication plan through MemoryService.

    Preflight is the default: the whole plan and its topology binding are
    validated and every eligible candidate runs through MemoryService with
    ``dry_run=True``, committing nothing. ``--apply`` executes the eligible
    candidates for real. The principal comes from this runtime's configured
    settings — never from the plan payload.
    """
    plan_path = Path(args.plan)
    plan_bundle_root = plan_path if plan_path.is_dir() else plan_path.parent
    plan_bundle = load_verified_bundle(plan_bundle_root)
    plan = load_publication_plan(plan_bundle)
    topology_bundle = load_verified_bundle(Path(args.topology_bundle))
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        receipt = execute_topology_publication(
            plan=plan,
            topology_bundle=topology_bundle,
            principal=principal,
            memory_service=runtime.service,
            mode="apply" if args.apply else "preflight",
        )
        sys.stdout.write(
            json.dumps(
                receipt.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return 0
    finally:
        runtime.close()


def cmd_search_context(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        result = GeneratedDataService(runtime.service).search_context(
            principal, _read_json_payload(args)
        )
        _print(result)
        return 0 if result.get("available") else 1
    finally:
        runtime.close()


def cmd_hydrate_context(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    try:
        _, principal = _context(runtime, args)
        result = GeneratedDataService(runtime.service).hydrate_context(
            principal, _read_json_payload(args)
        )
        _print(result)
        return 0 if result.get("available") else 1
    finally:
        runtime.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="L9 contract-governed memory")
    parser.add_argument("--config", default=None, help="Optional YAML settings file")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health")
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--group-id", default=None)

    write = sub.add_parser("write")
    write.add_argument("body")
    write.add_argument("--kind", type=_memory_class, default=MemoryClass.OBSERVATION)
    write.add_argument("--group-id", default=None)
    write.add_argument("--subject", default=None)
    write.add_argument("--predicate", default=None)
    write.add_argument("--object", default=None)
    write.add_argument("--source", default="cli")
    write.add_argument("--source-id", default=None)
    write.add_argument("--source-trust", type=float, default=1.0)
    write.add_argument("--confidence", type=float, default=1.0)
    write.add_argument("--valid-from", default=None)
    write.add_argument("--valid-to", default=None)
    write.add_argument("--idempotency-key", default=None)
    write.add_argument("--supersedes", action="append", default=[])
    write.add_argument("--references", action="append", default=[])
    write.add_argument("--tag", action="append", default=[])
    write.add_argument("--consent-subject-id", default=None)
    write.add_argument("--consent-purpose", default=None)
    write.add_argument("--consent-evidence", default=None)
    write.add_argument("--consent-source-id", default=None)
    write.add_argument("--consent-expires-at", default=None)
    write.add_argument("--dry-run", action="store_true")

    search = sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--group-id", default=None)
    search.add_argument("--namespace", action="append", default=[])
    search.add_argument("--memory-class", type=_memory_class, action="append", default=[])
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--token-budget", type=int, default=None)
    search.add_argument("--valid-at", default=None)
    search.add_argument("--recorded-before", default=None)
    search.add_argument("--min-confidence", type=float, default=0.0)
    search.add_argument("--include-superseded", action="store_true")
    search.add_argument("--include-archived", action="store_true")
    search.add_argument("--include-workspace", action="store_true")

    hydrate = sub.add_parser("hydrate")
    hydrate.add_argument("task")
    hydrate.add_argument("--group-id", default=None)
    hydrate.add_argument("--namespace", action="append", default=[])
    hydrate.add_argument("--entity", action="append", default=[])
    hydrate.add_argument("--topic", action="append", default=[])
    hydrate.add_argument("--memory-class", type=_memory_class, action="append", default=[])
    hydrate.add_argument("--token-budget", type=int, default=1_200)
    hydrate.add_argument("--max-records", type=int, default=40)

    get_record = sub.add_parser("get")
    get_record.add_argument("record_id")
    get_record.add_argument("--group-id", default=None)

    sub.add_parser("stats")

    conflicts = sub.add_parser("conflicts")
    conflicts.add_argument("--group-id", default=None)

    phase_lock = sub.add_parser("phase-lock")
    phase_lock.add_argument("task", nargs="?", default="phase lock")
    phase_lock.add_argument("--group-id", default=None)
    phase_lock.add_argument("--task-signature", default=None)
    phase_lock.add_argument("--ttl-seconds", type=int, default=1_800)

    verify_lock = sub.add_parser("verify-phase-lock")
    verify_lock.add_argument("task_signature")
    verify_lock.add_argument("--group-id", default=None)

    lineage = sub.add_parser("lineage")
    lineage.add_argument("record_id")
    lineage.add_argument("--group-id", default=None)

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--repo", default=".")
    bootstrap.add_argument("--group-id", default=None)
    bootstrap.add_argument("--dry-run", action="store_true")

    import_parser = sub.add_parser("import")
    import_parser.add_argument("path")
    import_parser.add_argument("--group-id", default=None)
    import_parser.add_argument(
        "--memory-class", type=_memory_class, default=MemoryClass.OBSERVATION
    )
    import_parser.add_argument("--repository", default=None)
    import_parser.add_argument("--tag", action="append", default=[])
    import_parser.add_argument("--dry-run", action="store_true")

    distill = sub.add_parser("distill")
    distill.add_argument("path")
    distill.add_argument("--group-id", default=None)
    distill.add_argument("--repository", default=None)
    distill.add_argument("--dry-run", action="store_true")

    inject = sub.add_parser("inject")
    inject.add_argument("task", nargs="?", default="session start")
    inject.add_argument("--group-id", default=None)
    inject.add_argument("--token-budget", type=int, default=1_200)
    inject.add_argument("--max-records", type=int, default=40)

    autoseed = sub.add_parser("autoseed-check")
    autoseed.add_argument("--group-id", default=None)

    prune = sub.add_parser("prune")
    prune.add_argument("--group-id", default=None)
    prune.add_argument("--apply", action="store_true")
    prune.add_argument("--dry-run", action="store_true")

    promote = sub.add_parser("promote")
    promote.add_argument("record_id")
    promote.add_argument("target_class", type=_memory_class)
    promote.add_argument("reason")
    promote.add_argument("--group-id", default=None)
    promote.add_argument("--explicit-confirmation", action="store_true")
    promote.add_argument("--governance-approval", action="store_true")
    promote.add_argument("--test-success-count", type=int, default=0)
    promote.add_argument("--supporting-record-id", action="append", default=[])
    promote.add_argument("--consent-subject-id", default=None)
    promote.add_argument("--consent-purpose", default=None)
    promote.add_argument("--consent-evidence", default=None)
    promote.add_argument("--consent-source-id", default=None)
    promote.add_argument("--consent-expires-at", default=None)

    delete = sub.add_parser("delete")
    delete.add_argument("record_id")
    delete.add_argument("reason")
    delete.add_argument("verification_reference")
    delete.add_argument("--group-id", default=None)
    delete.add_argument("--dry-run", action="store_true")

    synthesize = sub.add_parser("synthesize-procedures")
    synthesize.add_argument("--group-id", default=None)
    synthesize.add_argument("--source-record-id", action="append", required=True)
    synthesize.add_argument("--minimum-support", type=int, default=3)
    synthesize.add_argument("--dry-run", action="store_true")

    maintain = sub.add_parser("maintain")
    maintain.add_argument("--group-id", default=None)
    maintain.add_argument(
        "--operation",
        action="append",
        choices=[item.value for item in MaintenanceOperation],
        default=None,
        help="restrict the run to specific operations (repeatable)",
    )
    maintain.add_argument("--max-records", type=int, default=5_000)
    maintain.add_argument("--max-actions", type=int, default=500)
    maintain.add_argument("--reason", default="scheduled maintenance")
    maintain.add_argument(
        "--apply",
        action="store_true",
        help="apply the plan; without it the run is a dry run",
    )

    rebuild = sub.add_parser("rebuild-projection")
    rebuild.add_argument("--group-id", default=None)
    rebuild.add_argument("--limit", type=int, default=1_000)
    rebuild.add_argument("--reason", default="projection rebuild")
    rebuild.add_argument(
        "--apply",
        action="store_true",
        help="queue the projection events; without it the run is a dry run",
    )

    sub.add_parser("outbox-run")
    drain_legacy = sub.add_parser("drain-legacy-write-queue")
    drain_legacy.add_argument("--group-id", default=None)
    drain_legacy.add_argument("--limit", type=int, default=100)
    drain_legacy.add_argument("--dry-run", action="store_true")

    client = sub.add_parser("client")
    client_sub = client.add_subparsers(dest="client_target", required=True)
    cursor = client_sub.add_parser("cursor")
    cursor_sub = cursor.add_subparsers(dest="cursor_action", required=True)
    cursor_inspect = cursor_sub.add_parser("inspect")
    cursor_inspect.add_argument("--path", default=None)
    cursor_inspect.add_argument("--interpreter", default=None)
    cursor_install = cursor_sub.add_parser("install")
    cursor_install.add_argument("--path", default=None)
    cursor_install.add_argument("--interpreter", default=None)
    cursor_install.add_argument("--dry-run", action="store_true")
    cursor_verify = cursor_sub.add_parser("verify")
    cursor_verify.add_argument("--path", default=None)
    cursor_verify.add_argument("--interpreter", default=None)
    cursor_verify.add_argument("--timeout", type=float, default=30.0)
    cursor_status = cursor_sub.add_parser("status")
    cursor_status.add_argument("--path", default=None)
    cursor_status.add_argument("--interpreter", default=None)
    cursor_uninstall = cursor_sub.add_parser("uninstall")
    cursor_uninstall.add_argument("--path", default=None)
    cursor_uninstall.add_argument("--interpreter", default=None)
    cursor_uninstall.add_argument("--dry-run", action="store_true")
    cursor_uninstall.add_argument("--restore-backup", default=None)
    ingest_topology = sub.add_parser("ingest-topology-plan")
    ingest_topology.add_argument(
        "--plan",
        required=True,
        help="Publication-plan bundle directory, or the publication-plan.json inside it",
    )
    ingest_topology.add_argument(
        "--topology-bundle",
        required=True,
        help="Integrity-bound topology packet bundle the plan cites",
    )
    ingest_topology.add_argument(
        "--apply",
        action="store_true",
        help="Execute eligible candidates; the default is a zero-write preflight",
    )
    ingest_topology.add_argument("--group-id", default=None)
    ingest_gd = sub.add_parser("ingest-governed-candidate")
    ingest_gd.add_argument("--file", default=None)
    search_gd = sub.add_parser("search-context")
    search_gd.add_argument("--file", default=None)
    hydrate_gd = sub.add_parser("hydrate-context")
    hydrate_gd.add_argument("--file", default=None)
    reuse_gd = sub.add_parser("record-reuse")
    reuse_gd.add_argument("--file", default=None)
    invalidate_gd = sub.add_parser("invalidate-source")
    invalidate_gd.add_argument("--file", default=None)
    sub.add_parser("generated-data-capabilities")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "health": cmd_health,
        "resolve": cmd_resolve,
        "write": cmd_write,
        "search": cmd_search,
        "hydrate": cmd_hydrate,
        "get": cmd_get,
        "stats": cmd_stats,
        "conflicts": cmd_conflicts,
        "phase-lock": cmd_phase_lock,
        "verify-phase-lock": cmd_verify_phase_lock,
        "lineage": cmd_lineage,
        "bootstrap": cmd_bootstrap,
        "import": cmd_import,
        "distill": cmd_distill,
        "inject": cmd_inject,
        "autoseed-check": cmd_autoseed_check,
        "prune": cmd_prune,
        "promote": cmd_promote,
        "delete": cmd_delete,
        "synthesize-procedures": cmd_synthesize_procedures,
        "maintain": cmd_maintain,
        "rebuild-projection": cmd_rebuild_projection,
        "outbox-run": cmd_outbox_run,
        "drain-legacy-write-queue": cmd_drain_legacy_write_queue,
        "client": cmd_client,
        "ingest-topology-plan": cmd_ingest_topology_plan,
        "ingest-governed-candidate": cmd_ingest_governed_candidate,
        "search-context": cmd_search_context,
        "hydrate-context": cmd_hydrate_context,
        "record-reuse": cmd_record_reuse,
        "invalidate-source": cmd_invalidate_source,
        "generated-data-capabilities": cmd_generated_data_capabilities,
    }
    try:
        return handlers[args.command](args)
    except (L9MemoryError, ValueError, OSError) as exc:
        sys.stderr.write(_json({"error": type(exc).__name__, "message": str(exc)}) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
