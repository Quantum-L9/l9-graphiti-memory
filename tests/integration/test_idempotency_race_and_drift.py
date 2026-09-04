# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_idempotency_race_and_drift.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""Explicit retry identity survives both payload drift and concurrent retries.

Findings F-09 and F-10 (2026-09-04 audit): a replay carrying a different
payload under the same key returned DUPLICATE with no signal, and two retries
racing between the duplicate lookup and the commit surfaced the unique index
violation as a generic store failure instead of the DUPLICATE receipt ADR-008
promises.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest

from l9_graphite_memory.adapters import NullProjection, SQLiteRecordStore
from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    Provenance,
    WriteStatus,
)
from l9_graphite_memory.errors import IdempotencyConflict
from l9_graphite_memory.ports import SERVICE_WRITE_CAPABILITY  # test-only introspection
from l9_graphite_memory.services import MemoryService


def _request(content: str, *, key: str, memory_class: MemoryClass = MemoryClass.OBSERVATION):
    return MemoryWriteRequest(
        namespace="repo-a",
        memory_class=memory_class,
        content=content,
        provenance=Provenance(source="test"),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
        idempotency_key=key,
    )


def test_replay_with_a_different_payload_is_flagged(memory_service, principal) -> None:
    first = memory_service.write(principal, _request("first payload", key="op-1"))
    drifted = memory_service.write(principal, _request("DIFFERENT payload", key="op-1"))

    assert drifted.status is WriteStatus.DUPLICATE
    assert drifted.record_id == first.record_id
    assert any("payload differs" in warning for warning in drifted.warnings)
    assert memory_service.get(principal, first.record_id).content == "first payload"


def test_exact_replay_carries_no_drift_warning(memory_service, principal) -> None:
    memory_service.write(principal, _request("same payload", key="op-2"))
    replay = memory_service.write(principal, _request("same payload", key="op-2"))

    assert replay.status is WriteStatus.DUPLICATE
    assert not any("payload differs" in warning for warning in replay.warnings)


def test_class_drift_under_one_key_is_flagged(memory_service, principal) -> None:
    memory_service.write(principal, _request("content", key="op-3"))
    drifted = memory_service.write(
        principal, _request("content", key="op-3", memory_class=MemoryClass.SEMANTIC)
    )
    assert drifted.status is WriteStatus.DUPLICATE
    assert any("payload differs" in warning for warning in drifted.warnings)


def test_lost_race_between_lookup_and_commit_is_a_duplicate_receipt(
    memory_service, principal, monkeypatch
) -> None:
    """Deterministic form of the race: the lookup misses, the index decides."""

    first = memory_service.write(principal, _request("racing", key="op-race"))
    store = memory_service.store
    original_lookup = store.find_by_idempotency
    calls = {"count": 0}

    def lookup_that_misses_once(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return None
        return original_lookup(*args, **kwargs)

    monkeypatch.setattr(store, "find_by_idempotency", lookup_that_misses_once)
    second = memory_service.write(principal, _request("racing", key="op-race"))

    assert second.status is WriteStatus.DUPLICATE
    assert second.record_id == first.record_id
    assert store.stats()["records"] == 1


def test_store_raises_the_typed_conflict_for_a_duplicate_key(memory_service, principal) -> None:
    first = memory_service.write(principal, _request("typed", key="op-typed"))
    record = memory_service.get(principal, first.record_id)
    clone = record.model_copy(update={"record_id": uuid4()})
    with pytest.raises(IdempotencyConflict):
        memory_service.store.commit_write(
            SERVICE_WRITE_CAPABILITY,
            clone,
            first.model_copy(update={"record_id": clone.record_id}),
        )


def test_concurrent_retries_on_sqlite_resolve_to_one_record(tmp_path: Path, principal) -> None:
    """Eight threads retry one operation; the store admits it exactly once."""

    store = SQLiteRecordStore(tmp_path / "race.sqlite3")
    service = MemoryService(store, NullProjection())
    service.initialize()
    try:

        def attempt(index: int):
            return service.write(principal, _request("contended", key="op-concurrent"))

        with ThreadPoolExecutor(max_workers=8) as pool:
            receipts = list(pool.map(attempt, range(8)))
    finally:
        store.close()

    statuses = [receipt.status for receipt in receipts]
    assert statuses.count(WriteStatus.ADMITTED) == 1
    assert statuses.count(WriteStatus.DUPLICATE) == 7
    assert len({receipt.record_id for receipt in receipts}) == 1
