# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ingestion/topology_publication.py
#   layer: integration
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Governed admission of l9-constellation-topology publication plans (ADR-078).

This is a local, in-process ingestion adapter for the versioned
``l9.topology-publication-plan`` contract. It is not an inter-node router and
not a second memory control plane:

* Topology decides only that a candidate is *eligible to request* admission.
  Held, rejected, and skipped candidates never reach ``MemoryService``.
* Every attempted write goes through ``MemoryService.write`` — never a
  ``RecordStore`` method, never SQL, never a projection provider. Memory's own
  authorization, normalization, consent, admission, temporal, and atomic
  persistence pipeline stays the final authority, so an eligible candidate may
  still come back admitted, quarantined, rejected, or duplicate.
* The embedded intents are validated by this repository's canonical
  ``IngestMemoryIntent`` / ``MemoryWriteRequest`` classes. The plan envelope
  around them is a narrow, versioned adapter model — a deliberate choice over
  revalidating the producer's JSON Schema, which would add a ``jsonschema``
  runtime dependency this package does not carry. Producer schema drift
  therefore surfaces as typed validation errors at this boundary.
* Topology's explicit idempotency key is the retry identity of the requested
  effect. It is preserved exactly and never re-minted, so replaying an
  interrupted plan turns already-committed operations into duplicate receipts
  instead of new records.
* The plan and topology packet arrive as integrity-bound bundles. File content
  hashes are recomputed here (``sha256:`` over exact bytes); recomputing the
  producer's *semantic* hash is producer-owned and deliberately not
  reimplemented, so a forged semantic hash is caught by the bundle manifest
  cross-checks rather than by a second hash algorithm claiming equivalence.

The ``MemoryPrincipal`` is supplied by the caller (server or operator derived,
via runtime settings). Nothing in the plan payload can influence it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from l9_graphite_memory.contracts import MemoryPrincipal
from l9_graphite_memory.contracts.enums import WriteStatus
from l9_graphite_memory.contracts.temporal import utc_now
from l9_graphite_memory.errors import L9MemoryError
from l9_graphite_memory.integrations import GateMemoryBridge, IngestMemoryIntent
from l9_graphite_memory.services.memory_service import MemoryService

SUPPORTED_PLAN_TYPE = "l9.topology-publication-plan"
SUPPORTED_PLAN_VERSIONS = ("1.0.0",)
BATCH_RECEIPT_SCHEMA = "l9.topology-publication-batch-receipt/v1"
PLAN_DOCUMENT_NAME = "publication-plan.json"
BUNDLE_MANIFEST_NAME = "manifest.json"
_SHA_PREFIX = "sha256:"

#: Producer id fields whose values name topology entities. Resolution collects
#: the union across every payload record, so a candidate citing an id absent
#: from the bound packet fails binding.
_ENTITY_ID_KEYS = (
    "repository_id",
    "artifact_id",
    "capability_id",
    "claim_id",
    "subject_id",
    "source_id",
    "target_id",
    "edge_id",
)
_ENTITY_ID_LIST_KEYS = ("artifact_ids", "capability_ids", "projected_entity_ids")

ExecutionMode = Literal["preflight", "apply"]
CandidateExecutionStatus = Literal[
    "not_attempted_held",
    "not_attempted_rejected",
    "admitted",
    "quarantined",
    "memory_rejected",
    "duplicate",
    "failed",
]


class TopologyPlanError(L9MemoryError):
    """A publication plan, its bundle, or its topology binding is invalid."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TopologyProducerModel(_FrozenModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class TopologyPacketRefModel(_FrozenModel):
    packet_id: str = Field(min_length=1)
    packet_type: str = Field(min_length=1)
    packet_version: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    semantic_hash: str = Field(min_length=1)
    artifact_hash: str | None = None
    validation_status: str = Field(min_length=1)
    subject_id: str | None = None
    source_revision: str | None = None


class TopologyEligibilityModel(_FrozenModel):
    status: Literal["eligible", "held", "rejected"]
    reasons: tuple[str, ...] = ()


class TopologyLoweringModel(_FrozenModel):
    source_fields: tuple[str, ...] = ()
    resolved_evidence_ids: tuple[str, ...] = ()
    truncated_evidence_count: int = Field(default=0, ge=0)
    derivation_evidence_kind: str | None = None
    confidence_level: str
    confidence_method: str
    conflict_status: str
    observed_conflict_ids: tuple[str, ...] = ()
    observed_unknown_ids: tuple[str, ...] = ()
    owning_repository_id: str | None = None
    source_assertion_ids: tuple[str, ...] = ()
    assertion_predicate: str | None = None
    predicate_support: str | None = None


class TopologyCandidateModel(_FrozenModel):
    candidate_id: str = Field(min_length=1)
    candidate_kind: Literal["entity", "relationship", "claim"]
    source_topology_entity_ids: tuple[str, ...]
    source_evidence_ids: tuple[str, ...] = ()
    source_repository_model_packet_ids: tuple[str, ...] = ()
    eligibility: TopologyEligibilityModel
    lowering: TopologyLoweringModel
    #: Canonical validation on purpose: the producer's mirror types are not
    #: trusted here — this repository's own intent contract is.
    memory_intent: IngestMemoryIntent
    idempotency_key: str = Field(min_length=1, max_length=300)


class TopologySkippedCandidateModel(_FrozenModel):
    source_kind: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class TopologyDiagnosticModel(_FrozenModel):
    code: str
    detail: str
    count: int = Field(default=0, ge=0)


class TopologyPublicationPlanModel(_FrozenModel):
    plan_type: Literal["l9.topology-publication-plan"]
    plan_version: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    producer: TopologyProducerModel
    source_topology_packet: TopologyPacketRefModel
    source_topology_semantic_hash: str = Field(min_length=1)
    policy: dict[str, Any]
    policy_hash: str = Field(min_length=1)
    candidates: tuple[TopologyCandidateModel, ...] = ()
    skipped_candidates: tuple[TopologySkippedCandidateModel, ...] = ()
    diagnostics: tuple[TopologyDiagnosticModel, ...] = ()
    semantic_hash: str = Field(min_length=1)
    published_at: datetime


class BundleFileEntryModel(_FrozenModel):
    path: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)


class BundleManifestModel(_FrozenModel):
    manifest_version: str = Field(min_length=1)
    packet_id: str = Field(min_length=1)
    packet_type: str = Field(min_length=1)
    packet_version: str = Field(min_length=1)
    semantic_hash: str = Field(min_length=1)
    artifact_hash: str = Field(min_length=1)
    files: tuple[BundleFileEntryModel, ...]
    created_at: datetime


class VerifiedBundle(_FrozenModel):
    """An integrity-verified packet bundle, keyed by relative file path."""

    root: str
    manifest: BundleManifestModel
    documents: dict[str, Any]


class TopologyCandidateResult(_FrozenModel):
    candidate_id: str
    topology_eligibility: Literal["eligible", "held", "rejected"]
    idempotency_key: str
    attempted: bool
    execution_status: CandidateExecutionStatus
    memory_receipt_id: UUID | None = None
    memory_record_id: UUID | None = None
    #: Verbatim MemoryService WriteStatus value when a write was attempted and
    #: returned a receipt; None for unattempted or raising candidates.
    memory_admission_status: str | None = None
    #: Exception class name when execution_status is "failed". Never message
    #: text: messages could carry memory content, and the receipt must not.
    failure_kind: str | None = None


class TopologyPublicationBatchReceipt(_FrozenModel):
    #: Carries the contract's ``schema`` identity as ``schema_id``: this
    #: repository's schema-field law forbids pydantic aliases, and pydantic
    #: itself reserves the ``schema`` attribute name on BaseModel.
    schema_id: str = Field(default=BATCH_RECEIPT_SCHEMA)
    plan_id: str
    source_topology_packet_id: str
    source_topology_semantic_hash: str
    mode: ExecutionMode
    eligible_count: int = Field(ge=0)
    held_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    attempted_count: int = Field(ge=0)
    admitted_count: int = Field(ge=0)
    quarantined_count: int = Field(ge=0)
    memory_rejected_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    candidate_results: tuple[TopologyCandidateResult, ...]
    created_at: datetime = Field(default_factory=utc_now)


_PLAN_ADAPTER: TypeAdapter[TopologyPublicationPlanModel] = TypeAdapter(TopologyPublicationPlanModel)
_MANIFEST_ADAPTER: TypeAdapter[BundleManifestModel] = TypeAdapter(BundleManifestModel)


def _sha256(content: bytes) -> str:
    return _SHA_PREFIX + hashlib.sha256(content).hexdigest()


def _read_bundle_file(root: Path, relative: str) -> bytes:
    """Read one bundle file, refusing traversal and symlink escapes.

    The bundle directory is the allowed input root. A manifest path that walks
    out of it, or a symlink that resolves outside it, would let a plan cite
    files the operator never supplied — so both fail closed. Inputs are only
    ever read, never modified.
    """
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise TopologyPlanError(f"bundle path escapes the bundle root: {relative}")
    resolved_root = root.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise TopologyPlanError(f"bundle path resolves outside the bundle root: {relative}")
    if not candidate.is_file():
        raise TopologyPlanError(f"bundle file is missing: {relative}")
    return candidate.read_bytes()


def _load_json(content: bytes, *, context: str) -> Any:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TopologyPlanError(f"{context} is not valid JSON: {exc}") from exc


def load_verified_bundle(root: Path) -> VerifiedBundle:
    """Load a packet bundle and verify every manifest-listed file's integrity."""
    manifest_raw = _load_json(
        _read_bundle_file(root, BUNDLE_MANIFEST_NAME),
        context=f"{BUNDLE_MANIFEST_NAME} in {root}",
    )
    try:
        manifest = _MANIFEST_ADAPTER.validate_python(manifest_raw)
    except ValidationError as exc:
        raise TopologyPlanError(f"bundle manifest is invalid: {exc}") from exc
    documents: dict[str, Any] = {}
    for entry in manifest.files:
        content = _read_bundle_file(root, entry.path)
        digest = _sha256(content)
        if digest != entry.content_hash:
            raise TopologyPlanError(
                f"bundle file failed integrity verification: {entry.path} "
                f"(recorded {entry.content_hash}, observed {digest})"
            )
        if len(content) != entry.size_bytes:
            raise TopologyPlanError(
                f"bundle file size mismatch: {entry.path} "
                f"(recorded {entry.size_bytes}, observed {len(content)})"
            )
        if entry.media_type == "application/json":
            documents[entry.path] = _load_json(content, context=entry.path)
    return VerifiedBundle(root=str(root), manifest=manifest, documents=documents)


def load_publication_plan(bundle: VerifiedBundle) -> TopologyPublicationPlanModel:
    """Parse the plan document out of an integrity-verified plan bundle."""
    if PLAN_DOCUMENT_NAME not in bundle.documents:
        raise TopologyPlanError(
            f"plan bundle does not list {PLAN_DOCUMENT_NAME}; an unbundled plan "
            "file is not an integrity-bound input"
        )
    try:
        plan = _PLAN_ADAPTER.validate_python(bundle.documents[PLAN_DOCUMENT_NAME])
    except ValidationError as exc:
        raise TopologyPlanError(f"publication plan is invalid: {exc}") from exc
    if plan.plan_type != SUPPORTED_PLAN_TYPE:
        raise TopologyPlanError(f"unsupported plan type: {plan.plan_type}")
    if plan.plan_version not in SUPPORTED_PLAN_VERSIONS:
        raise TopologyPlanError(
            f"unsupported plan version: {plan.plan_version}; "
            f"supported: {', '.join(SUPPORTED_PLAN_VERSIONS)}"
        )
    if bundle.manifest.packet_id != plan.plan_id:
        raise TopologyPlanError(
            "plan bundle manifest packet_id does not match plan_id: "
            f"{bundle.manifest.packet_id} != {plan.plan_id}"
        )
    if bundle.manifest.semantic_hash != plan.semantic_hash:
        raise TopologyPlanError(
            "plan bundle manifest semantic_hash does not match the plan's "
            "declared semantic_hash; recomputing the producer hash algorithm "
            "is producer-owned, so this cross-check is the integrity boundary"
        )
    _validate_plan_structure(plan)
    return plan


def _validate_plan_structure(plan: TopologyPublicationPlanModel) -> None:
    seen: set[str] = set()
    for candidate in plan.candidates:
        if candidate.candidate_id in seen:
            raise TopologyPlanError(f"duplicate candidate_id in plan: {candidate.candidate_id}")
        seen.add(candidate.candidate_id)
        request_key = candidate.memory_intent.request.idempotency_key
        if not request_key:
            raise TopologyPlanError(
                f"candidate {candidate.candidate_id}: memory intent carries no "
                "idempotency_key; topology publication requires explicit "
                "operation identity"
            )
        if request_key != candidate.idempotency_key:
            raise TopologyPlanError(
                f"candidate {candidate.candidate_id}: candidate idempotency_key "
                "does not equal the intent request idempotency_key; a re-minted "
                "retry identity invalidates the entire plan"
            )


def _entity_id_universe(topology: VerifiedBundle) -> tuple[set[str], set[str]]:
    """Collect entity and evidence id universes from bound topology payloads."""
    entity_ids: set[str] = set()
    evidence_ids: set[str] = set()

    def collect(record: Any) -> None:
        if not isinstance(record, dict):
            return
        for key in _ENTITY_ID_KEYS:
            value = record.get(key)
            if isinstance(value, str) and value:
                entity_ids.add(value)
        for key in _ENTITY_ID_LIST_KEYS:
            values = record.get(key)
            if isinstance(values, list):
                entity_ids.update(item for item in values if isinstance(item, str))
        value = record.get("evidence_id")
        if isinstance(value, str) and value:
            evidence_ids.add(value)

    for path, document in topology.documents.items():
        if not path.startswith("payload/"):
            continue
        if isinstance(document, list):
            for record in document:
                collect(record)
        else:
            collect(document)
    return entity_ids, evidence_ids


def _repository_model_packet_ids(topology: VerifiedBundle) -> set[str]:
    packet_document = topology.documents.get("packet.json")
    if not isinstance(packet_document, dict):
        raise TopologyPlanError("topology bundle does not carry packet.json")
    inputs = packet_document.get("inputs")
    refs = inputs.get("repository_model_packets") if isinstance(inputs, dict) else None
    if not isinstance(refs, list):
        return set()
    return {
        ref["packet_id"]
        for ref in refs
        if isinstance(ref, dict) and isinstance(ref.get("packet_id"), str)
    }


def validate_topology_binding(plan: TopologyPublicationPlanModel, topology: VerifiedBundle) -> None:
    """Bind the plan to the supplied topology packet bundle, fail-closed.

    A JSON plan is not accepted as an unauthenticated assertion that some
    topology packet existed: the packet the plan names must be the packet the
    operator supplied, hash for hash, and every candidate's citations must
    resolve inside it.
    """
    manifest = topology.manifest
    ref = plan.source_topology_packet
    if manifest.packet_id != ref.packet_id:
        raise TopologyPlanError(
            "plan cites topology packet "
            f"{ref.packet_id} but the supplied bundle is {manifest.packet_id}"
        )
    if manifest.semantic_hash != plan.source_topology_semantic_hash:
        raise TopologyPlanError(
            "plan source_topology_semantic_hash does not match the supplied topology bundle"
        )
    if ref.semantic_hash != manifest.semantic_hash:
        raise TopologyPlanError(
            "plan packet ref semantic_hash does not match the supplied topology bundle"
        )
    entity_ids, evidence_ids = _entity_id_universe(topology)
    packet_input_ids = _repository_model_packet_ids(topology)
    for candidate in plan.candidates:
        for entity_id in candidate.source_topology_entity_ids:
            if entity_id not in entity_ids:
                raise TopologyPlanError(
                    f"candidate {candidate.candidate_id} cites topology entity "
                    f"{entity_id} which does not resolve in the bound packet"
                )
        for evidence_id in candidate.source_evidence_ids:
            if evidence_id not in evidence_ids:
                raise TopologyPlanError(
                    f"candidate {candidate.candidate_id} cites topology evidence "
                    f"{evidence_id} which does not resolve in the bound packet"
                )
        for packet_id in candidate.source_repository_model_packet_ids:
            if packet_id not in packet_input_ids:
                raise TopologyPlanError(
                    f"candidate {candidate.candidate_id} cites repository model "
                    f"packet {packet_id} which is not a bound input of the "
                    "topology packet"
                )


def _validate_gate_conformance(plan: TopologyPublicationPlanModel) -> None:
    """Prove every eligible intent passes the Gate intent contract, no dispatch.

    Cross-node transport later must move these intents through Gate, so the
    Gate boundary's own validator must accept them now. This is a static
    validation only: no Gate client exists here and nothing is dispatched.
    """
    for candidate in plan.candidates:
        if candidate.eligibility.status != "eligible":
            continue
        try:
            GateMemoryBridge.validate_intent(candidate.memory_intent.model_dump(mode="python"))
        except (ValidationError, ValueError) as exc:
            raise TopologyPlanError(
                f"candidate {candidate.candidate_id}: eligible intent failed "
                f"Gate intent conformance: {exc}"
            ) from exc


def validate_publication_inputs(
    plan: TopologyPublicationPlanModel, topology: VerifiedBundle
) -> None:
    """Run the complete pre-execution validation phase for one plan."""
    _validate_plan_structure(plan)
    validate_topology_binding(plan, topology)
    _validate_gate_conformance(plan)


_STATUS_BY_WRITE_STATUS: dict[WriteStatus, CandidateExecutionStatus] = {
    WriteStatus.ADMITTED: "admitted",
    WriteStatus.QUARANTINED: "quarantined",
    WriteStatus.REJECTED: "memory_rejected",
    WriteStatus.DUPLICATE: "duplicate",
}


def execute_topology_publication(
    *,
    plan: TopologyPublicationPlanModel,
    topology_bundle: VerifiedBundle,
    principal: MemoryPrincipal,
    memory_service: MemoryService,
    mode: ExecutionMode,
) -> TopologyPublicationBatchReceipt:
    """Validate a plan, then run its eligible candidates through MemoryService.

    The batch is per-operation atomic, never plan-atomic: MemoryService commits
    each admitted operation durably on its own, so an interruption leaves a
    prefix of committed operations. Recovery is rerunning the same plan —
    Topology's explicit idempotency keys turn committed operations into
    duplicate receipts while the remainder proceeds. No write-ahead log or
    second transaction manager exists here by design.

    ``preflight`` calls MemoryService with an execution copy of each request
    whose only change is ``dry_run=True`` — identity-bearing fields are never
    touched — and commits nothing. ``apply`` submits the request exactly as
    the producer emitted it.
    """
    validate_publication_inputs(plan, topology_bundle)
    ordered = sorted(plan.candidates, key=lambda item: item.candidate_id)
    results: list[TopologyCandidateResult] = []
    counters = {
        "attempted": 0,
        "admitted": 0,
        "quarantined": 0,
        "memory_rejected": 0,
        "duplicate": 0,
        "failed": 0,
    }
    for candidate in ordered:
        status = candidate.eligibility.status
        if status != "eligible":
            results.append(
                TopologyCandidateResult(
                    candidate_id=candidate.candidate_id,
                    topology_eligibility=status,
                    idempotency_key=candidate.idempotency_key,
                    attempted=False,
                    execution_status=(
                        "not_attempted_held" if status == "held" else "not_attempted_rejected"
                    ),
                )
            )
            continue
        request = candidate.memory_intent.request
        if mode == "preflight":
            request = request.model_copy(update={"dry_run": True})
        counters["attempted"] += 1
        try:
            receipt = memory_service.write(principal, request)
        except L9MemoryError as exc:
            counters["failed"] += 1
            results.append(
                TopologyCandidateResult(
                    candidate_id=candidate.candidate_id,
                    topology_eligibility=status,
                    idempotency_key=candidate.idempotency_key,
                    attempted=True,
                    execution_status="failed",
                    failure_kind=type(exc).__name__,
                )
            )
            continue
        execution_status = _STATUS_BY_WRITE_STATUS.get(receipt.status, "failed")
        counters[execution_status] += 1
        results.append(
            TopologyCandidateResult(
                candidate_id=candidate.candidate_id,
                topology_eligibility=status,
                idempotency_key=candidate.idempotency_key,
                attempted=True,
                execution_status=execution_status,
                memory_receipt_id=receipt.receipt_id,
                # A dry-run write receipt carries the record id the operation
                # WOULD create, but preflight commits nothing — reporting that
                # id would let a consumer read the batch receipt as durable.
                memory_record_id=None if mode == "preflight" else receipt.record_id,
                memory_admission_status=receipt.status.value,
            )
        )
    return TopologyPublicationBatchReceipt(
        plan_id=plan.plan_id,
        source_topology_packet_id=plan.source_topology_packet.packet_id,
        source_topology_semantic_hash=plan.source_topology_semantic_hash,
        mode=mode,
        eligible_count=sum(1 for item in plan.candidates if item.eligibility.status == "eligible"),
        held_count=sum(1 for item in plan.candidates if item.eligibility.status == "held"),
        rejected_count=sum(1 for item in plan.candidates if item.eligibility.status == "rejected"),
        skipped_count=len(plan.skipped_candidates),
        attempted_count=counters["attempted"],
        admitted_count=counters["admitted"],
        quarantined_count=counters["quarantined"],
        memory_rejected_count=counters["memory_rejected"],
        duplicate_count=counters["duplicate"],
        failed_count=counters["failed"],
        candidate_results=tuple(results),
    )
