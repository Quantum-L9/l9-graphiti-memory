# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/test_execution_modes.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Preflight/apply semantics, batch receipts, and crash-replay recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import NullProjection, SQLiteRecordStore
from l9_graphite_memory.errors import StoreError
from l9_graphite_memory.ingestion import (
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


def _inputs(tmp_path: Path, count: int = 4):
    candidates = [
        make_candidate(candidate_id=f"eligible-{index}", status="eligible")
        for index in range(count)
    ]
    plan_root = make_plan_bundle(tmp_path / "plan", candidates)
    topo_root = make_topology_bundle(tmp_path / "topo")
    return (
        load_publication_plan(load_verified_bundle(plan_root)),
        load_verified_bundle(topo_root),
    )


def _sqlite_service(tmp_path: Path) -> MemoryService:
    service = MemoryService(
        SQLiteRecordStore(tmp_path / "canonical.sqlite3"), NullProjection()
    )
    service.initialize()
    return service


def test_preflight_validates_everything_and_writes_nothing(
    tmp_path: Path, topology_principal
) -> None:
    plan, topo = _inputs(tmp_path)
    service = _sqlite_service(tmp_path)
    receipt = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="preflight",
    )
    assert receipt.mode == "preflight"
    assert receipt.attempted_count == 4
    assert receipt.admitted_count == 4
    assert service.store.stats()["records"] == 0
    assert all(r.memory_record_id is None for r in receipt.candidate_results)


def test_preflight_does_not_mutate_identity_fields(
    tmp_path: Path, topology_principal
) -> None:
    plan, topo = _inputs(tmp_path, count=1)

    captured = {}

    class CapturingService(MemoryService):
        def write(self, principal, request):  # type: ignore[override]
            captured["request"] = request
            return super().write(principal, request)

    from l9_graphite_memory.adapters import InMemoryRecordStore

    service = CapturingService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="preflight",
    )
    submitted = captured["request"]
    original = plan.candidates[0].memory_intent.request
    assert submitted.dry_run is True
    assert original.dry_run is False
    assert submitted.model_copy(update={"dry_run": False}) == original


def test_apply_then_preflight_reports_duplicates_without_new_records(
    tmp_path: Path, topology_principal
) -> None:
    plan, topo = _inputs(tmp_path)
    service = _sqlite_service(tmp_path)
    applied = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert applied.admitted_count == 4
    preflight = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="preflight",
    )
    assert preflight.duplicate_count == 4
    assert service.store.stats()["records"] == 4


def test_batch_receipt_counts_reconcile(tmp_path: Path, topology_principal) -> None:
    plan, topo = _inputs(tmp_path)
    service = _sqlite_service(tmp_path)
    receipt = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert receipt.attempted_count == (
        receipt.admitted_count
        + receipt.quarantined_count
        + receipt.memory_rejected_count
        + receipt.duplicate_count
        + receipt.failed_count
    )
    assert len(receipt.candidate_results) == len(plan.candidates)
    dumped = receipt.model_dump(mode="json")
    assert dumped["schema_id"] == "l9.topology-publication-batch-receipt/v1"
    forbidden = ("content", "assertion", "provenance")
    for result in dumped["candidate_results"]:
        for key in forbidden:
            assert key not in result


def test_candidate_execution_order_is_candidate_id_code_point_order(
    tmp_path: Path, topology_principal
) -> None:
    candidates = [
        make_candidate(candidate_id=name, status="eligible")
        for name in ("zeta", "alpha", "Mid")
    ]
    plan_root = make_plan_bundle(tmp_path / "plan", candidates)
    topo_root = make_topology_bundle(tmp_path / "topo")
    plan = load_publication_plan(load_verified_bundle(plan_root))
    topo = load_verified_bundle(topo_root)

    order: list[str] = []

    class OrderingService(MemoryService):
        def write(self, principal, request):  # type: ignore[override]
            order.append(request.idempotency_key)
            return super().write(principal, request)

    from l9_graphite_memory.adapters import InMemoryRecordStore

    service = OrderingService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert order == [
        "l9-topology-publication/v3:Mid",
        "l9-topology-publication/v3:alpha",
        "l9-topology-publication/v3:zeta",
    ]


def test_crash_mid_batch_recovers_by_rerunning_the_same_plan(
    tmp_path: Path, topology_principal
) -> None:
    plan, topo = _inputs(tmp_path, count=5)
    store = SQLiteRecordStore(tmp_path / "canonical.sqlite3")

    class CrashingService(MemoryService):
        def __init__(self) -> None:
            super().__init__(store, NullProjection())
            self.calls = 0

        def write(self, principal, request):  # type: ignore[override]
            self.calls += 1
            if self.calls == 3:
                raise StoreError("simulated crash mid-batch")
            return super().write(principal, request)

    crashing = CrashingService()
    crashing.initialize()
    first = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=crashing,
        mode="apply",
    )
    assert first.admitted_count == 4
    assert first.failed_count == 1
    assert store.stats()["records"] == 4

    recovered = MemoryService(store, NullProjection())
    recovered.initialize()
    second = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=recovered,
        mode="apply",
    )
    assert second.duplicate_count == 4
    assert second.admitted_count == 1
    assert second.failed_count == 0
    assert store.stats()["records"] == 5
    store.close()


def test_replayed_records_keep_their_record_ids(
    tmp_path: Path, topology_principal
) -> None:
    plan, topo = _inputs(tmp_path, count=3)
    service = _sqlite_service(tmp_path)
    first = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    second = execute_topology_publication(
        plan=plan,
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    first_ids = {r.candidate_id: r.memory_record_id for r in first.candidate_results}
    second_ids = {r.candidate_id: r.memory_record_id for r in second.candidate_results}
    assert first_ids == second_ids
    assert second.admitted_count == 0


@pytest.mark.parametrize("status", ["held", "rejected"])
def test_non_eligible_candidates_survive_replay_untouched(
    tmp_path: Path, topology_principal, status: str
) -> None:
    candidates = [
        make_candidate(candidate_id="eligible-0", status="eligible"),
        make_candidate(candidate_id=f"{status}-0", status=status),
    ]
    plan_root = make_plan_bundle(tmp_path / "plan", candidates)
    topo_root = make_topology_bundle(tmp_path / "topo")
    plan = load_publication_plan(load_verified_bundle(plan_root))
    topo = load_verified_bundle(topo_root)
    service = _sqlite_service(tmp_path)
    for _ in range(2):
        receipt = execute_topology_publication(
            plan=plan,
            topology_bundle=topo,
            principal=topology_principal,
            memory_service=service,
            mode="apply",
        )
    assert service.store.stats()["records"] == 1
    assert receipt.attempted_count == 1


def test_same_effect_key_in_a_new_plan_container_is_the_same_memory_operation(
    tmp_path: Path, topology_principal
) -> None:
    """WS16: the effect key, not the plan envelope, is the retry identity."""
    from tests.unit.topology_publication.conftest import make_plan_bundle as _mpb

    shared = make_candidate(candidate_id="stable-fact", status="eligible")
    first_root = _mpb(tmp_path / "plan-1", [shared])
    second_root = _mpb(
        tmp_path / "plan-2",
        [shared],
        plan_id="publication-plan:" + "7" * 64,
        plan_semantic_hash="sha256:" + "8" * 64,
    )
    topo = load_verified_bundle(make_topology_bundle(tmp_path / "topo"))
    service = _sqlite_service(tmp_path)

    first = execute_topology_publication(
        plan=load_publication_plan(load_verified_bundle(first_root)),
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    second = execute_topology_publication(
        plan=load_publication_plan(load_verified_bundle(second_root)),
        topology_bundle=topo,
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert first.admitted_count == 1
    assert second.admitted_count == 0
    assert second.duplicate_count == 1
    assert (
        first.candidate_results[0].memory_record_id
        == second.candidate_results[0].memory_record_id
    )
    assert service.store.stats()["records"] == 1
