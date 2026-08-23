# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/test_containment_and_identity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Eligibility containment, idempotency binding, and the authority boundary.

Topology eligibility means only "may attempt admission". These suites prove
held/rejected/skipped candidates produce zero MemoryService calls, that the
explicit idempotency key binding is exact or the whole plan fails, and that
Memory admission — not the adapter — decides every attempted outcome.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.ingestion import (
    TopologyPlanError,
    execute_topology_publication,
    load_publication_plan,
    load_verified_bundle,
)
from l9_graphite_memory.services import MemoryService
from tests.unit.topology_publication.conftest import (
    make_candidate,
    make_plan_bundle,
    make_topology_bundle,
)


class CountingMemoryService(MemoryService):
    """Counts write calls so containment is proven, not assumed."""

    def __init__(self) -> None:
        super().__init__(InMemoryRecordStore(), NullProjection())
        self.initialize()
        self.write_calls = 0

    def write(self, principal, request):  # type: ignore[override]
        self.write_calls += 1
        return super().write(principal, request)


def _load_inputs(tmp_path: Path, candidates, *, skipped: int = 0):
    plan_root = make_plan_bundle(tmp_path / "plan", candidates, skipped=skipped)
    topo_root = make_topology_bundle(tmp_path / "topo")
    return (
        load_publication_plan(load_verified_bundle(plan_root)),
        load_verified_bundle(topo_root),
    )


def test_adversarial_mix_calls_memory_service_exactly_for_eligible(
    tmp_path: Path, topology_principal
) -> None:
    candidates = (
        [
            make_candidate(candidate_id=f"eligible-{i}", status="eligible")
            for i in range(3)
        ]
        + [make_candidate(candidate_id=f"held-{i}", status="held") for i in range(2)]
        + [
            make_candidate(candidate_id=f"rejected-{i}", status="rejected")
            for i in range(4)
        ]
    )
    plan, topo = _load_inputs(tmp_path, candidates, skipped=5)
    service = CountingMemoryService()
    receipt = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert service.write_calls == 3
    assert receipt.eligible_count == 3
    assert receipt.held_count == 2
    assert receipt.rejected_count == 4
    assert receipt.skipped_count == 5
    assert receipt.attempted_count == 3
    statuses = {r.candidate_id: r.execution_status for r in receipt.candidate_results}
    assert statuses["held-0"] == "not_attempted_held"
    assert statuses["rejected-0"] == "not_attempted_rejected"
    unattempted = [r for r in receipt.candidate_results if not r.attempted]
    assert all(r.memory_receipt_id is None for r in unattempted)


def test_candidate_only_plan_writes_nothing(tmp_path: Path, topology_principal) -> None:
    candidates = [
        make_candidate(candidate_id=f"held-{i}", status="held") for i in range(3)
    ]
    plan, topo = _load_inputs(tmp_path, candidates)
    service = CountingMemoryService()
    receipt = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert service.write_calls == 0
    assert receipt.attempted_count == 0
    assert service.store.stats()["records"] == 0


def test_key_mismatch_fails_the_entire_plan_before_any_write(
    tmp_path: Path, topology_principal
) -> None:
    candidates = [
        make_candidate(candidate_id="good", status="eligible"),
        make_candidate(
            candidate_id="mismatched",
            status="eligible",
            idempotency_key="l9-topology-publication/v3:candidate-key",
            intent_key="l9-topology-publication/v3:different-request-key",
        ),
    ]
    plan_root = make_plan_bundle(tmp_path / "plan", candidates)
    with pytest.raises(TopologyPlanError, match="does not equal the intent request"):
        load_publication_plan(load_verified_bundle(plan_root))


def test_missing_intent_idempotency_key_fails_the_plan(tmp_path: Path) -> None:
    candidate = make_candidate(candidate_id="keyless", status="eligible")
    del candidate["memory_intent"]["request"]["idempotency_key"]
    plan_root = make_plan_bundle(tmp_path / "plan", [candidate])
    with pytest.raises(TopologyPlanError, match="no.*idempotency_key|idempotency_key"):
        load_publication_plan(load_verified_bundle(plan_root))


def test_forged_eligible_without_candidate_key_is_rejected(tmp_path: Path) -> None:
    candidate = make_candidate(candidate_id="forged", status="eligible")
    candidate["idempotency_key"] = ""
    plan_root = make_plan_bundle(tmp_path / "plan", [candidate])
    with pytest.raises(TopologyPlanError, match="publication plan is invalid"):
        load_publication_plan(load_verified_bundle(plan_root))


def test_unauthorized_namespace_is_refused_by_memory_policy(
    tmp_path: Path, topology_principal
) -> None:
    candidates = [
        make_candidate(
            candidate_id="unauthorized",
            status="eligible",
        )
    ]
    candidates[0]["memory_intent"]["request"]["namespace"] = (
        "l9.constellation/other-repo"
    )
    plan, topo = _load_inputs(tmp_path, candidates)
    service = CountingMemoryService()
    receipt = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert service.write_calls == 1
    result = receipt.candidate_results[0]
    # MemoryService refuses the unauthorized namespace with a typed REJECTED
    # receipt rather than raising, so the adapter records Memory's decision
    # verbatim — and nothing was committed.
    assert result.execution_status == "memory_rejected"
    assert result.memory_admission_status == "rejected"
    assert service.store.stats()["records"] == 0


def test_low_confidence_outcome_is_memorys_decision(
    tmp_path: Path, topology_principal
) -> None:
    candidate = make_candidate(candidate_id="low-confidence", status="eligible")
    candidate["memory_intent"]["request"]["confidence"]["score"] = 0.05
    plan, topo = _load_inputs(tmp_path, [candidate])
    service = CountingMemoryService()
    receipt = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    result = receipt.candidate_results[0]
    assert result.attempted
    assert result.memory_admission_status is not None
    assert result.execution_status in {"admitted", "quarantined", "memory_rejected"}


def test_intents_are_submitted_verbatim(tmp_path: Path, topology_principal) -> None:
    candidate = make_candidate(candidate_id="verbatim", status="eligible")
    plan, topo = _load_inputs(tmp_path, [candidate])

    captured = {}

    class CapturingService(CountingMemoryService):
        def write(self, principal, request):  # type: ignore[override]
            captured["request"] = request
            return super().write(principal, request)

    service = CapturingService()
    execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    submitted = captured["request"]
    original = plan.candidates[0].memory_intent.request
    assert submitted == original
    assert submitted.idempotency_key == plan.candidates[0].idempotency_key
    assert submitted.consent is None
