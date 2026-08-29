# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ingestion/publication_identity.py
#   layer: integration
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-29

"""Consumer-side recomputation of topology publication identity (ADR-078).

A publication plan declares two identities per candidate: ``candidate_id``, the
logical fact, and ``idempotency_key``, the exact durable admission requested.
Both are pure functions of data the plan and its bound topology packet already
carry. Until this module existed the consumer took both on trust, and the only
integrity check between them and the payload was that
``manifest.semantic_hash`` equalled ``plan.semantic_hash`` — two fields that
live in two files an editor of the bundle controls together. A coordinated edit
that left that pair alone and repaired only the per-file ``content_hash``
therefore admitted arbitrary content, at arbitrary confidence, under an
arbitrary retry identity.

So this module recomputes both identities from the payload and refuses the whole
plan on any mismatch. A candidate whose declared identity does not describe its
own content is not a candidate this repository will hand to ``MemoryService``.

**What this closes, and what it does not.** Any hash the consumer can recompute,
a forger can also recompute. This binds the declared identities to the payload,
which is what makes the manifest cross-check meaningful instead of circular, and
it closes every edit that does not reimplement the producer's canonicalization —
partial writes, truncation, merge damage, a tampering tool, a buggy regenerator.
It does not, and cannot without a secret, defend against a party that implements
the algorithm below and emits a self-consistent forgery. That threat is answered
by signing the bundle, which is a contract decision this module deliberately
does not pre-empt; see ``docs/decisions`` before adding one.

**Why the algorithm is duplicated rather than imported.** This package does not
depend on ``l9-constellation-topology`` and must not: the consumer validating a
producer's claim with the producer's own code proves only that the code is
self-consistent. The two implementations are held together instead by the golden
vectors in ``tests/fixtures/publication_identity/golden-vectors.json``, which are
generated from the producer and asserted by both repositories. A drift in either
canonicalization breaks those vectors before it can break a plan.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from l9_graphite_memory.errors import L9MemoryError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from l9_graphite_memory.ingestion.topology_publication import (
        TopologyCandidateModel,
        TopologyPublicationPlanModel,
        VerifiedBundle,
    )

_SHA_PREFIX = "sha256:"
_BARE_SHA256 = re.compile(r"^[a-f0-9]{64}$")

#: Effect-identity algorithm versions this consumer can recompute. The version
#: is read from the declared key's own prefix rather than assumed, so a producer
#: that moves to v4 is rejected by name instead of silently mis-verified.
SUPPORTED_IDEMPOTENCY_ALGORITHMS: frozenset[str] = frozenset({"v3"})

#: Lowering contract versions this consumer can recompute. Read from the
#: intent's own metadata: the contract that lowered a fact participates in its
#: effect identity, so recomputing under the wrong one produces a false mismatch.
#:
#: Both are supported, and older plans are not deprecated by the newer contract.
#: The version is a property of the plan that was generated, not of the consumer
#: reading it: a plan produced under v1 has v1 keys and verifies correctly under
#: v1 forever. Dropping v1 here would refuse a plan that is still entirely
#: honest about itself.
SUPPORTED_LOWERING_CONTRACTS: frozenset[str] = frozenset({"lowering/v1", "lowering/v2"})

IDEMPOTENCY_NAMESPACE = "l9-topology-publication"
_EFFECT_IDENTITY_DOMAIN_BY_VERSION: dict[str, str] = {"v3": "l9.memory-effect-id/v3"}

#: Volatile fields stripped before hashing, matching the producer's
#: ``PUBLICATION_EXCLUDED_FIELDS`` exactly. None of them occurs inside an
#: identity view today; they are applied anyway because the producer applies
#: them, and an identity function that differs only on inputs neither side
#: currently produces is a latent divergence rather than an equivalent one.
_EXCLUDED_FIELDS: frozenset[str] = frozenset(
    {
        "created_at",
        "checked_at",
        "generated_at",
        "committed_at",
        "frozen_at",
        "run_id",
        "stage_id",
        "trace_id",
        "workflow_id",
        "artifact_hash",
        "semantic_hash",
        "packet_id",
        "receipt_id",
        "calibrated_at",
        "observed_at",
        "published_at",
        "source_observed_at",
        "transformed_at",
        "valid_from",
        "plan_id",
    }
)

#: Default ceiling on lowered evidence references per candidate, used only when
#: the plan's embedded policy does not state one.
_DEFAULT_MAX_EVIDENCE_REFS = 32


class PublicationIdentityError(L9MemoryError):
    """A declared publication identity does not describe its own payload."""


def _canonical(value: Any) -> Any:
    """Reduce a value to deterministic JSON-compatible data.

    Mirrors the producer's ``canonical_data``. Pydantic models are not expected
    here — every input is already plain JSON data — but datetimes are normalized
    the producer's way so that a future identity field carrying one cannot make
    the two implementations disagree.
    """
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonical(item) for item in value), key=_canonical_json)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _strip_excluded(value: Any) -> Any:
    value = _canonical(value)
    if isinstance(value, dict):
        return {
            key: _strip_excluded(item) for key, item in value.items() if key not in _EXCLUDED_FIELDS
        }
    if isinstance(value, list):
        return [_strip_excluded(item) for item in value]
    return value


def publication_semantic_hash(value: Any) -> str:
    """Hash identity data the producer's way, volatile fields removed."""
    payload = _canonical_json(_strip_excluded(value)).encode("utf-8")
    return _SHA_PREFIX + hashlib.sha256(payload).hexdigest()


def bare_digest(value: str | None) -> str | None:
    """Return a bare lowercase sha256 hex digest, or ``None`` when unavailable."""
    if value is None:
        return None
    candidate = value.removeprefix(_SHA_PREFIX).strip().lower()
    return candidate if _BARE_SHA256.match(candidate) else None


def candidate_identity(
    *,
    operation: str,
    candidate_kind: str,
    namespace: str,
    memory_class: str,
    content: str,
    assertion: dict[str, Any] | None,
    source_topology_entity_ids: tuple[str, ...],
) -> dict[str, Any]:
    """Return the canonical semantic identity of one publication fact."""
    return {
        "operation": operation,
        "candidate_kind": candidate_kind,
        "namespace": namespace,
        "memory_class": memory_class,
        "content": content,
        "assertion": assertion,
        "source_topology_entity_ids": tuple(source_topology_entity_ids),
    }


def candidate_id(identity: dict[str, Any]) -> str:
    """Return the stable identifier of a semantic fact."""
    return "publication-candidate:" + publication_semantic_hash(identity).removeprefix(_SHA_PREFIX)


def confidence_semantics(
    *, score: float, method: str, evidence_count: int, confidence_policy_version: str
) -> dict[str, Any]:
    """Return the confidence claim a write is making."""
    return {
        "score": score,
        "method": method,
        "evidence_count": evidence_count,
        "confidence_policy_version": confidence_policy_version,
    }


def evidence_semantics(
    *,
    evidence_kind: str,
    source_content_digest: str | None,
    stable_source_locator: str | None,
) -> dict[str, Any]:
    """Return one supporting evidence item as it bears on the requested write."""
    return {
        "evidence_kind": evidence_kind,
        "source_content_digest": source_content_digest,
        "stable_source_locator": stable_source_locator,
    }


def effect_identity(
    identity: dict[str, Any],
    *,
    algorithm_version: str,
    lowering_contract_version: str,
    local_evidence: tuple[dict[str, Any], ...],
    confidence: dict[str, Any],
    derivation_kind: str | None,
) -> dict[str, Any]:
    """Return the canonical identity of the exact durable admission requested."""
    domain = _EFFECT_IDENTITY_DOMAIN_BY_VERSION[algorithm_version]
    return {
        "domain": domain,
        "candidate_id": candidate_id(identity),
        "lowering_contract_version": lowering_contract_version,
        "local_evidence_semantics": sorted(local_evidence, key=publication_semantic_hash),
        "derivation_kind": derivation_kind,
        "confidence_semantics": confidence,
    }


def idempotency_key(
    identity: dict[str, Any],
    *,
    algorithm_version: str,
    lowering_contract_version: str,
    local_evidence: tuple[dict[str, Any], ...],
    confidence: dict[str, Any],
    derivation_kind: str | None,
) -> str:
    """Return the identity of the exact durable write an intent requests."""
    digest = publication_semantic_hash(
        effect_identity(
            identity,
            algorithm_version=algorithm_version,
            lowering_contract_version=lowering_contract_version,
            local_evidence=local_evidence,
            confidence=confidence,
            derivation_kind=derivation_kind,
        )
    ).removeprefix(_SHA_PREFIX)
    return f"{IDEMPOTENCY_NAMESPACE}/{algorithm_version}:{digest}"


# --------------------------------------------------------------------------
# Binding the algorithm above to an actual plan
# --------------------------------------------------------------------------


def _algorithm_version(candidate: TopologyCandidateModel) -> str:
    """Read the effect-identity algorithm version out of the declared key."""
    declared = candidate.idempotency_key
    prefix = f"{IDEMPOTENCY_NAMESPACE}/"
    if not declared.startswith(prefix) or ":" not in declared:
        raise PublicationIdentityError(
            f"candidate {candidate.candidate_id}: idempotency key does not carry a "
            f"recognised {IDEMPOTENCY_NAMESPACE} algorithm prefix"
        )
    version = declared[len(prefix) :].split(":", 1)[0]
    if version not in SUPPORTED_IDEMPOTENCY_ALGORITHMS:
        raise PublicationIdentityError(
            f"candidate {candidate.candidate_id}: unsupported effect-identity "
            f"algorithm {version!r}; supported: "
            f"{', '.join(sorted(SUPPORTED_IDEMPOTENCY_ALGORITHMS))}"
        )
    return version


def _lowering_contract_version(candidate: TopologyCandidateModel) -> str:
    """Read the lowering contract version the producer recorded on the intent."""
    value = candidate.memory_intent.request.metadata.get("lowering_contract_version")
    if not isinstance(value, str) or not value:
        raise PublicationIdentityError(
            f"candidate {candidate.candidate_id}: intent metadata carries no "
            "lowering_contract_version, so its effect identity cannot be recomputed"
        )
    if value not in SUPPORTED_LOWERING_CONTRACTS:
        raise PublicationIdentityError(
            f"candidate {candidate.candidate_id}: unsupported lowering contract "
            f"{value!r}; supported: {', '.join(sorted(SUPPORTED_LOWERING_CONTRACTS))}"
        )
    return value


def _topology_evidence_index(topology: VerifiedBundle) -> dict[str, dict[str, Any]]:
    """Index the bound topology packet's evidence records by evidence id."""
    index: dict[str, dict[str, Any]] = {}
    for path, document in topology.documents.items():
        if not path.startswith("payload/"):
            continue
        records = document if isinstance(document, list) else [document]
        for record in records:
            if not isinstance(record, dict):
                continue
            evidence_id = record.get("evidence_id")
            if isinstance(evidence_id, str) and evidence_id and "source_ref" in record:
                index[evidence_id] = record
    return index


def _evidence_kind_map(plan: TopologyPublicationPlanModel) -> dict[str, str]:
    mapping = plan.policy.get("evidence_kind_by_class")
    if not isinstance(mapping, dict) or not mapping:
        raise PublicationIdentityError(
            "publication policy carries no evidence_kind_by_class mapping, so "
            "evidence semantics cannot be recomputed"
        )
    return {str(key): str(value) for key, value in mapping.items()}


def _max_evidence_refs(plan: TopologyPublicationPlanModel) -> int:
    value = plan.policy.get("maximum_evidence_refs_per_candidate", _DEFAULT_MAX_EVIDENCE_REFS)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PublicationIdentityError(
            "publication policy carries an invalid maximum_evidence_refs_per_candidate"
        )
    return value


def _local_evidence_semantics(
    candidate: TopologyCandidateModel,
    *,
    evidence_index: dict[str, dict[str, Any]],
    evidence_kinds: dict[str, str],
    ceiling: int,
) -> tuple[dict[str, Any], ...]:
    """Rebuild the evidence semantics the producer keyed this write on.

    The producer resolved evidence ids, sorted them, truncated at the policy
    ceiling, and derived three fields per kept record. The lowering receipt
    preserves that resolved order, so it is read rather than re-derived: a
    consumer that re-sorted would silently repair a producer that had not.
    """
    kept = candidate.lowering.resolved_evidence_ids[:ceiling]
    semantics: list[dict[str, Any]] = []
    for evidence_id in kept:
        record = evidence_index.get(evidence_id)
        if record is None:
            raise PublicationIdentityError(
                f"candidate {candidate.candidate_id}: lowering cites evidence "
                f"{evidence_id} which is not present in the bound topology packet"
            )
        evidence_class = record.get("evidence_class")
        kind = evidence_kinds.get(str(evidence_class))
        if kind is None:
            raise PublicationIdentityError(
                f"candidate {candidate.candidate_id}: publication policy has no "
                f"evidence kind for class {evidence_class!r}"
            )
        source_ref = record.get("source_ref")
        source_ref = source_ref if isinstance(source_ref, dict) else {}
        semantics.append(
            evidence_semantics(
                evidence_kind=kind,
                source_content_digest=bare_digest(source_ref.get("content_hash")),
                stable_source_locator=source_ref.get("source_path") or source_ref.get("uri"),
            )
        )
    return tuple(semantics)


def _declared_identity(candidate: TopologyCandidateModel) -> dict[str, Any]:
    """Build the identity view from the candidate's own admitted payload."""
    request = candidate.memory_intent.request
    assertion = request.assertion.model_dump(mode="json") if request.assertion else None
    return candidate_identity(
        operation=candidate.memory_intent.operation,
        candidate_kind=candidate.candidate_kind,
        namespace=request.namespace,
        memory_class=request.memory_class.value,
        content=request.content,
        assertion=assertion,
        source_topology_entity_ids=candidate.source_topology_entity_ids,
    )


def verify_publication_identity(
    plan: TopologyPublicationPlanModel, topology: VerifiedBundle
) -> None:
    """Recompute every candidate's declared identities and refuse any mismatch.

    Both identities are checked for every candidate, not only the eligible ones:
    a held candidate is still a statement the plan makes about topology truth,
    and a plan that misdescribes any of its own candidates is not one whose
    eligible remainder deserves trust.
    """
    evidence_index = _topology_evidence_index(topology)
    evidence_kinds = _evidence_kind_map(plan)
    ceiling = _max_evidence_refs(plan)

    for candidate in plan.candidates:
        identity = _declared_identity(candidate)
        recomputed_candidate_id = candidate_id(identity)
        if recomputed_candidate_id != candidate.candidate_id:
            raise PublicationIdentityError(
                f"candidate {candidate.candidate_id}: declared candidate_id does not "
                "describe its own payload; the plan asserts an identity for content, "
                "assertion, namespace, or memory class it does not carry "
                f"(recomputed {recomputed_candidate_id})"
            )

        algorithm_version = _algorithm_version(candidate)
        recomputed_key = idempotency_key(
            identity,
            algorithm_version=algorithm_version,
            lowering_contract_version=_lowering_contract_version(candidate),
            local_evidence=_local_evidence_semantics(
                candidate,
                evidence_index=evidence_index,
                evidence_kinds=evidence_kinds,
                ceiling=ceiling,
            ),
            confidence=confidence_semantics(
                score=candidate.memory_intent.request.confidence.score,
                method=candidate.memory_intent.request.confidence.method.value,
                evidence_count=candidate.memory_intent.request.confidence.evidence_count,
                confidence_policy_version=(
                    candidate.memory_intent.request.confidence.policy_version
                ),
            ),
            derivation_kind=candidate.lowering.derivation_evidence_kind,
        )
        if recomputed_key != candidate.idempotency_key:
            raise PublicationIdentityError(
                f"candidate {candidate.candidate_id}: declared idempotency_key does not "
                "describe the durable write it requests; the plan asserts a retry "
                "identity for confidence or supporting evidence it does not carry "
                f"(recomputed {recomputed_key})"
            )
