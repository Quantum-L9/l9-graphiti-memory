# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_retention_lineage_phase_lock.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from l9_graphite_memory.contracts import (
    MemoryClass,
    MemoryWriteRequest,
    PhaseLockRequest,
    Provenance,
)


def _write(memory_service, principal, content: str, **kwargs):
    return memory_service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            content=content,
            provenance=Provenance(source="test"),
            **kwargs,
        ),
    )


def test_lineage_replays_supersession_and_references(memory_service, principal) -> None:
    base = _write(memory_service, principal, "base fact")
    replacement = _write(
        memory_service,
        principal,
        "replacement fact",
        supersedes=(base.record_id,),
        references=(base.record_id,),
    )

    replay = memory_service.lineage(principal, "repo-a", replacement.record_id)

    assert replay.complete
    assert base.record_id in replay.ordered_record_ids
    assert (replacement.record_id, base.record_id, "supersedes") in replay.edges
    assert (replacement.record_id, base.record_id, "references") in replay.edges


def test_phase_lock_invalidates_when_namespace_changes(memory_service, principal) -> None:
    lock = memory_service.phase_lock(
        principal,
        PhaseLockRequest(namespace="repo-a", task_signature="task-signature-1"),
    )
    initial = memory_service.verify_phase_lock(principal, "repo-a", "task-signature-1")
    _write(memory_service, principal, "new record changes snapshot")
    changed = memory_service.verify_phase_lock(principal, "repo-a", "task-signature-1")

    assert lock.granted
    assert initial.valid
    assert not changed.valid
    assert "namespace changed" in " ".join(changed.reasons)


def test_reference_aware_retention_soft_expires_referenced_record(
    memory_service, principal
) -> None:
    now = datetime.now(timezone.utc)
    expired = _write(
        memory_service,
        principal,
        "expired observation",
        memory_class=MemoryClass.OBSERVATION,
        valid_from=now - timedelta(days=2),
        valid_to=now - timedelta(days=1),
    )
    _write(
        memory_service,
        principal,
        "dependent active record",
        references=(expired.record_id,),
    )

    receipt = memory_service.apply_retention(principal, "repo-a", apply=False)
    decision = next(item for item in receipt.decisions if item.record_id == expired.record_id)

    assert decision.action == "soft-expire"
    assert decision.reference_count == 1
