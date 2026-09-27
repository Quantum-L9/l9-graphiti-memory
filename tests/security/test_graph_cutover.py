# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/security/test_graph_cutover.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Release-blocking: graph cutover receipt and rollback window (GI-090, ADR-092).

The previous projection store must not be destroyed before the cutover is
recorded, nor while its rollback window is open. ``release-legacy-projection``
is the assertion that it was destroyed, so it refuses to apply until a cutover
receipt exists for the namespace and its window has ended.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.contracts import DeletionRequest, MemoryState
from l9_graphite_memory.errors import AuthorizationError, CutoverNotReady, StoreError
from l9_graphite_memory.ports.service_capability import SERVICE_WRITE_CAPABILITY
from l9_graphite_memory.services import MemoryService
from tests.conftest import STORE_BACKENDS
from tests.security.test_legacy_projection_erasure import (
    ADMIN,
    MAINTAINER,
    NAMESPACE,
    Migration,
    _open_store,
    _reopen,
)


class SteppedClock:
    """Starts at the real time (the outbox worker uses the system clock) and steps."""

    def __init__(self) -> None:
        self.current = datetime.now(timezone.utc)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def _migration(store=None) -> tuple[Migration, SteppedClock]:
    migration = Migration(store)
    clock = SteppedClock()
    migration.service = MemoryService(migration.store, migration.service.projection, clock=clock)
    migration.service.initialize()
    return migration, clock


def _record(migration: Migration, *, window=timedelta(hours=72), apply=True, **overrides):
    values = {
        "previous_binding": "neo4j://retained/graphiti-v0",
        "new_binding": "neo4j://fresh/graphiti-v1",
        "change_reference": "CHG-42",
        "rollback_window": window,
        "apply": apply,
    }
    values.update(overrides)
    return migration.service.record_graph_cutover(ADMIN, NAMESPACE, **values)


def _switched_and_rebuilt(migration: Migration, *, drain: bool):
    record = migration.write("falcon plan")
    migration.drain()
    migration.switch_provider(record)
    migration.service.rebuild_projection(MAINTAINER, NAMESPACE, apply=True)
    if drain:
        migration.drain()
    return record


def _rebind(migration: Migration, clock: SteppedClock) -> None:
    migration.service = MemoryService(migration.store, migration.service.projection, clock=clock)
    migration.service.initialize()


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_cutover_is_refused_until_the_projection_is_complete(tmp_path, backend) -> None:
    migration, clock = _migration(_open_store(backend, tmp_path))
    _, migration.worker = migration._bind(migration.new)
    _rebind(migration, clock)
    record = _switched_and_rebuilt(migration, drain=False)

    check = _record(migration, apply=False)
    assert check.ready is False and check.applied is False
    assert check.unprojected_record_ids == (record,)
    assert check.outbox_backlog >= 1
    with pytest.raises(CutoverNotReady, match="not projected"):
        _record(migration)
    assert migration.store.list_graph_cutovers(NAMESPACE) == []
    migration.store.close()


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_cutover_is_recorded_persisted_and_capability_gated(tmp_path, backend) -> None:
    migration, clock = _migration(_open_store(backend, tmp_path))
    _switched_and_rebuilt(migration, drain=True)
    _rebind(migration, clock)

    receipt = _record(migration, window=timedelta(hours=72))
    assert receipt.applied and receipt.ready
    assert receipt.active_record_count == receipt.projected_record_count == 1
    assert receipt.rollback_window_ends_at == clock.now() + timedelta(hours=72)
    assert receipt.scope_scheme is not None

    with pytest.raises(PermissionError):
        migration.store.commit_graph_cutover(object(), receipt)
    with pytest.raises(StoreError, match="non-applied"):
        migration.store.commit_graph_cutover(
            SERVICE_WRITE_CAPABILITY, receipt.model_copy(update={"applied": False})
        )

    migration.store = _reopen(backend, tmp_path, migration.store)
    (persisted,) = migration.store.list_graph_cutovers(NAMESPACE)
    assert persisted == receipt
    migration.store.close()


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_release_waits_for_the_receipt_and_the_end_of_the_window(tmp_path, backend) -> None:
    migration, clock = _migration(_open_store(backend, tmp_path))
    record = _switched_and_rebuilt(migration, drain=True)
    _rebind(migration, clock)
    migration.service.delete(
        ADMIN,
        DeletionRequest(record_id=record, reason="subject request", verification_reference="r"),
    )
    migration.drain()
    assert migration.store.get_record(record).state is MemoryState.DELETION_PENDING

    def release(apply=True):
        return migration.service.release_legacy_projection_copies(
            ADMIN, NAMESPACE, store_destruction_reference="CHG-DESTROY", apply=apply
        )

    # No cutover recorded: the previous store may not be declared destroyed.
    with pytest.raises(CutoverNotReady, match="no graph cutover"):
        release()
    cutover = _record(migration, window=timedelta(hours=72))

    # Window open: still refused; a preview is allowed and names the cutover.
    clock.advance(timedelta(hours=71))
    with pytest.raises(CutoverNotReady, match="rollback window"):
        release()
    preview = release(apply=False)
    assert preview.cutover_receipt_id == cutover.receipt_id
    assert migration.store.get_record(record).state is MemoryState.DELETION_PENDING
    assert migration.store.list_legacy_projection_releases(NAMESPACE) == []

    # Window ended: the release applies and records which cutover authorized it.
    clock.advance(timedelta(hours=1))
    released = release()
    assert released.applied and released.cutover_receipt_id == cutover.receipt_id
    assert migration.store.get_record(record).state is MemoryState.DELETED
    (persisted,) = migration.store.list_legacy_projection_releases(NAMESPACE)
    assert persisted.cutover_receipt_id == cutover.receipt_id
    migration.store.close()


def test_the_latest_cutover_governs_and_earlier_ones_are_kept() -> None:
    migration, clock = _migration()
    _switched_and_rebuilt(migration, drain=True)
    _rebind(migration, clock)
    first = _record(migration, window=timedelta(0))
    clock.advance(timedelta(minutes=5))
    second = _record(migration, window=timedelta(days=7), change_reference="CHG-43")
    assert [r.receipt_id for r in migration.store.list_graph_cutovers(NAMESPACE)] == [
        first.receipt_id,
        second.receipt_id,
    ]
    with pytest.raises(CutoverNotReady, match="rollback window"):
        migration.service.release_legacy_projection_copies(
            ADMIN, NAMESPACE, store_destruction_reference="CHG-DESTROY", apply=True
        )


def test_cutover_requires_admin_distinct_bindings_and_a_non_negative_window() -> None:
    migration, _clock = _migration()
    with pytest.raises(AuthorizationError):
        migration.service.record_graph_cutover(
            MAINTAINER,
            NAMESPACE,
            previous_binding="a",
            new_binding="b",
            change_reference="CHG",
            rollback_window=timedelta(0),
            apply=True,
        )
    with pytest.raises(CutoverNotReady, match="differ"):
        _record(migration, previous_binding="neo4j://same", new_binding="neo4j://same")
    with pytest.raises(CutoverNotReady, match="negative"):
        _record(migration, window=timedelta(hours=-1))
