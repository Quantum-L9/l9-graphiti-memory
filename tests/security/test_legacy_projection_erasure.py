# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/security/test_legacy_projection_erasure.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Release-blocking: verified deletion covers copies left in a retained legacy store.

ADR-091. The GraphScopeKey migration (ADR-084) re-projects every record into a
fresh provider database and keeps the previous one for rollback. A deletion
during that window must not report COMPLETE while the previous database still
holds a copy: it stays pending until the operator releases the legacy copies
after destroying that store.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from l9_graphite_memory.adapters import GraphitiProjection, InMemoryRecordStore
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    DeletionRequest,
    MemoryAssertion,
    MemoryPrincipal,
    MemoryState,
    MemoryWriteRequest,
    ProjectionLink,
    Provenance,
)
from l9_graphite_memory.contracts.projection import legacy_copies, link_withdrawn
from l9_graphite_memory.errors import AuthorizationError, StoreError
from l9_graphite_memory.graph import GRAPH_SCOPE_SCHEME
from l9_graphite_memory.ports.service_capability import SERVICE_WRITE_CAPABILITY
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker
from tests.conftest import STORE_BACKENDS, make_store
from tests.security.test_graph_tenant_isolation import GroupedGraphitiTransport

NAMESPACE = "shared"
MAINTAINER = MemoryPrincipal(
    principal_id="tenant-a-agent",
    tenant_id="tenant-a",
    read_namespaces=(NAMESPACE,),
    write_namespaces=(NAMESPACE,),
    maintain_namespaces=(NAMESPACE,),
)
ADMIN = MemoryPrincipal(
    principal_id="admin",
    tenant_id="tenant-a",
    read_namespaces=("*",),
    write_namespaces=("*",),
    is_admin=True,
)


class Migration:
    """Canonical store shared across an old and a fresh provider database."""

    def __init__(self, store=None) -> None:
        self.store = store if store is not None else InMemoryRecordStore()
        self.old = GroupedGraphitiTransport()
        self.new = GroupedGraphitiTransport()
        self.service, self.worker = self._bind(self.old)

    def _bind(self, transport: GroupedGraphitiTransport) -> tuple[MemoryService, OutboxWorker]:
        projection = GraphitiProjection(transport)
        service = MemoryService(self.store, projection)
        service.initialize()
        worker = OutboxWorker(self.store, projection, MemorySettings(), worker_id="migration")
        return service, worker

    def write(self, content: str, **kwargs) -> UUID:
        receipt = self.service.write(
            MAINTAINER,
            MemoryWriteRequest(
                namespace=NAMESPACE,
                content=content,
                provenance=Provenance(source="migration-test"),
                **kwargs,
            ),
        )
        assert receipt.record_id is not None
        return receipt.record_id

    def drain(self) -> None:
        for _ in range(8):
            if self.worker.run_once()["claimed"] == 0:
                return

    def link(self, record_id: UUID) -> ProjectionLink | None:
        return self.store.get_projection_link(record_id, "graphiti")

    def switch_provider(self, *records: UUID) -> None:
        """Mark links as pre-ADR-084 and bind the fresh database; no rebuild yet."""

        for record_id in records:
            link = self.link(record_id)
            assert link is not None
            self.store.save_projection_link(link.model_copy(update={"metadata": {}}))
        self.service, self.worker = self._bind(self.new)

    def cut_over(self, *records: UUID) -> None:
        """Mark links as pre-ADR-084, then rebuild into the fresh database."""

        self.switch_provider(*records)
        receipt = self.service.rebuild_projection(MAINTAINER, NAMESPACE, apply=True)
        assert set(receipt.stale_scope_record_ids) == set(records)
        self.drain()


@pytest.fixture
def migration() -> Migration:
    return Migration()


def test_rebuild_records_the_superseded_copy_as_an_obligation(migration) -> None:
    record = migration.write("falcon plan")
    migration.drain()
    old_locator = migration.link(record).locator
    migration.cut_over(record)

    link = migration.link(record)
    assert link.metadata["scope_scheme"] == GRAPH_SCOPE_SCHEME
    assert not link_withdrawn(link)
    (copy,) = legacy_copies(link)
    assert copy["locator"] == old_locator and copy["scope_scheme"] is None
    assert str(record) in migration.old.episodes and str(record) in migration.new.episodes


def test_deletion_during_the_rollback_window_stays_pending(migration) -> None:
    record = migration.write("falcon plan")
    migration.drain()
    migration.cut_over(record)

    deletion = migration.service.delete(
        ADMIN,
        DeletionRequest(record_id=record, reason="subject request", verification_reference="r"),
    )
    migration.drain()

    # The reachable copy is erased; the retained legacy copy is not, so the
    # deletion is not complete.
    assert str(record) not in migration.new.episodes
    assert str(record) in migration.old.episodes
    assert migration.store.get_record(record).state is MemoryState.DELETION_PENDING
    link = migration.link(record)
    assert link_withdrawn(link) and legacy_copies(link)
    assert link.metadata["pending_deletion_receipt_id"] == str(deletion.receipt_id)

    preview = migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-1", apply=False
    )
    assert preview.completed_deletion_record_ids == (record,)
    assert migration.store.get_record(record).state is MemoryState.DELETION_PENDING

    # Operator destroys the legacy store, then releases.
    migration.old.episodes.clear()
    released = migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-1", apply=True
    )
    assert released.applied and released.released_copy_count == 1
    assert released.completed_deletion_record_ids == (record,)
    assert migration.store.get_record(record).state is MemoryState.DELETED
    assert migration.link(record) is None


def test_a_record_retired_after_cutover_keeps_its_obligation(migration) -> None:
    old = migration.write(
        "kestrel owner billing",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="billing"),
    )
    migration.drain()
    migration.cut_over(old)
    migration.write(
        "kestrel owner platform",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="platform"),
        supersedes=(old,),
    )
    migration.drain()
    assert migration.store.get_record(old).state is MemoryState.SUPERSEDED
    assert str(old) not in migration.new.episodes
    link = migration.link(old)
    assert link_withdrawn(link) and legacy_copies(link)

    migration.service.delete(
        ADMIN, DeletionRequest(record_id=old, reason="subject request", verification_reference="r")
    )
    migration.drain()
    assert migration.store.get_record(old).state is MemoryState.DELETION_PENDING

    migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-2", apply=True
    )
    assert migration.store.get_record(old).state is MemoryState.DELETED


def test_release_drops_the_obligation_of_active_records_and_keeps_their_link(migration) -> None:
    record = migration.write("falcon plan")
    migration.drain()
    migration.cut_over(record)
    receipt = migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-3", apply=True
    )
    assert receipt.released_record_ids == (record,)
    assert receipt.completed_deletion_record_ids == ()
    link = migration.link(record)
    assert link is not None and not legacy_copies(link) and not link_withdrawn(link)
    assert str(record) in migration.new.episodes


def test_release_requires_admin(migration) -> None:
    with pytest.raises(AuthorizationError):
        migration.service.release_legacy_projection_copies(
            MAINTAINER, NAMESPACE, store_destruction_reference="CHG-4", apply=True
        )


def test_deletion_without_legacy_copies_completes_as_before(migration) -> None:
    record = migration.write("falcon plan")
    migration.drain()
    migration.service.delete(
        ADMIN,
        DeletionRequest(record_id=record, reason="subject request", verification_reference="r"),
    )
    migration.drain()
    assert migration.store.get_record(record).state is MemoryState.DELETED
    assert str(record) not in migration.old.episodes


def test_deletion_before_the_rebuild_runs_keeps_the_legacy_copy_outstanding(migration) -> None:
    """Codex review: a stale-scheme link must not be erased through the new provider."""

    record = migration.write("falcon plan")
    migration.drain()
    migration.switch_provider(record)  # rebuild not run yet
    migration.service.delete(
        ADMIN,
        DeletionRequest(record_id=record, reason="subject request", verification_reference="r"),
    )
    migration.drain()
    assert migration.store.get_record(record).state is MemoryState.DELETION_PENDING
    link = migration.link(record)
    assert link_withdrawn(link)
    assert [copy["scope_scheme"] for copy in legacy_copies(link)] == [None]
    assert str(record) in migration.old.episodes  # the retained copy
    migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-5", apply=True
    )
    assert migration.store.get_record(record).state is MemoryState.DELETED


def test_retirement_before_the_rebuild_runs_keeps_the_legacy_copy_outstanding(migration) -> None:
    old = migration.write(
        "kestrel owner billing",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="billing"),
    )
    migration.drain()
    migration.switch_provider(old)
    migration.write(
        "kestrel owner platform",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="platform"),
        supersedes=(old,),
    )
    migration.drain()
    link = migration.link(old)
    assert link_withdrawn(link) and len(legacy_copies(link)) == 1


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_release_is_atomic_persisted_and_capability_gated(tmp_path, backend) -> None:
    """Codex review: one capability-gated transaction that records its receipt."""

    migration = Migration(make_store(backend, tmp_path))
    record = migration.write("falcon plan")
    migration.drain()
    migration.cut_over(record)
    deletion = migration.service.delete(
        ADMIN,
        DeletionRequest(record_id=record, reason="subject request", verification_reference="r"),
    )
    migration.drain()
    store = migration.store
    preview = migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-6", apply=False
    )
    assert store.list_legacy_projection_releases(NAMESPACE) == []
    applied_receipt = preview.model_copy(update={"applied": True})

    with pytest.raises(PermissionError):
        store.commit_legacy_projection_release(
            object(), applied_receipt, link_removals=((record, "graphiti"),)
        )
    # A failing completion rolls back the receipt and the link removal with it.
    with pytest.raises(StoreError):
        store.commit_legacy_projection_release(
            SERVICE_WRITE_CAPABILITY,
            applied_receipt,
            link_removals=((record, "graphiti"),),
            deletion_completions=((record, UUID(int=0)),),
        )
    assert migration.link(record) is not None
    assert store.list_legacy_projection_releases(NAMESPACE) == []
    assert store.get_record(record).state is MemoryState.DELETION_PENDING

    released = migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-6", apply=True
    )
    assert store.get_record(record).state is MemoryState.DELETED
    assert migration.link(record) is None
    (persisted,) = store.list_legacy_projection_releases(NAMESPACE)
    assert persisted.receipt_id == released.receipt_id
    assert persisted.store_destruction_reference == "CHG-6"
    assert persisted.completed_deletion_record_ids == (record,)
    assert deletion.receipt_id is not None
    store.close()


def _open_store(backend: str, tmp_path, schema: str | None = None):
    """Open (or reopen, to model a process restart) one durable store."""

    if backend == "memory":
        return InMemoryRecordStore()
    if backend == "sqlite":
        from l9_graphite_memory.adapters import SQLiteRecordStore

        return SQLiteRecordStore(tmp_path / "release.sqlite3")
    from tests.conftest import make_postgres_store

    return make_postgres_store(schema)


def _reopen(backend: str, tmp_path, store):
    if backend == "memory":
        return store  # no process boundary to cross; state is the object
    schema = getattr(store, "test_schema", None)
    store.close()
    return _open_store(backend, tmp_path, schema)


def _pending_deletion(migration: Migration) -> UUID:
    record = migration.write("falcon plan")
    migration.drain()
    migration.cut_over(record)
    migration.service.delete(
        ADMIN,
        DeletionRequest(record_id=record, reason="subject request", verification_reference="r"),
    )
    migration.drain()
    assert migration.store.get_record(record).state is MemoryState.DELETION_PENDING
    return record


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_injected_failure_mid_release_changes_nothing_and_survives_restart(
    tmp_path, backend, monkeypatch
) -> None:
    """Audit F-01: all-or-nothing under failure, durable across restart, retry idempotent."""

    migration = Migration(_open_store(backend, tmp_path))
    record = _pending_deletion(migration)
    before = migration.link(record)
    hook = "complete_deletion" if backend == "memory" else "_complete_deletion_tx"

    def fail(*args, **kwargs):
        raise RuntimeError("injected failure after receipt and link changes were staged")

    monkeypatch.setattr(migration.store, hook, fail)
    with pytest.raises(RuntimeError, match="injected failure"):
        migration.service.release_legacy_projection_copies(
            ADMIN, NAMESPACE, store_destruction_reference="CHG-7", apply=True
        )
    monkeypatch.undo()

    migration.store = _reopen(backend, tmp_path, migration.store)
    migration.service, migration.worker = migration._bind(migration.new)
    assert migration.link(record) == before
    assert migration.store.get_record(record).state is MemoryState.DELETION_PENDING
    assert migration.store.list_legacy_projection_releases(NAMESPACE) == []

    released = migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-7", apply=True
    )
    assert released.completed_deletion_record_ids == (record,)

    migration.store = _reopen(backend, tmp_path, migration.store)
    migration.service, migration.worker = migration._bind(migration.new)
    assert migration.store.get_record(record).state is MemoryState.DELETED
    assert migration.link(record) is None
    (persisted,) = migration.store.list_legacy_projection_releases(NAMESPACE)
    assert persisted.receipt_id == released.receipt_id

    again = migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-7", apply=True
    )
    assert again.released_record_ids == ()
    assert len(migration.store.list_legacy_projection_releases(NAMESPACE)) == 1
    migration.store.close()


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_release_refuses_a_plan_overtaken_by_a_concurrent_erasure(tmp_path, backend) -> None:
    """A link rewritten after the release read it must not be overwritten by the stale plan."""

    migration = Migration(_open_store(backend, tmp_path))
    record = migration.write("falcon plan")
    migration.drain()
    migration.cut_over(record)
    store = migration.store
    original = store.commit_legacy_projection_release

    def erase_first(*args, **kwargs):
        # The outbox worker erases the record between the release's read and
        # its commit, turning the live link into a pending withdrawn one.
        migration.service.delete(
            ADMIN,
            DeletionRequest(record_id=record, reason="subject request", verification_reference="r"),
        )
        migration.drain()
        return original(*args, **kwargs)

    store.commit_legacy_projection_release = erase_first  # type: ignore[method-assign]
    with pytest.raises(StoreError, match="changed since the release was planned"):
        migration.service.release_legacy_projection_copies(
            ADMIN, NAMESPACE, store_destruction_reference="CHG-8", apply=True
        )
    store.commit_legacy_projection_release = original  # type: ignore[method-assign]
    link = migration.link(record)
    assert link_withdrawn(link) and legacy_copies(link)
    assert store.get_record(record).state is MemoryState.DELETION_PENDING
    assert store.list_legacy_projection_releases(NAMESPACE) == []

    migration.service.release_legacy_projection_copies(
        ADMIN, NAMESPACE, store_destruction_reference="CHG-8", apply=True
    )
    assert store.get_record(record).state is MemoryState.DELETED
    store.close()


def test_in_memory_link_writers_wait_for_an_in_flight_release(monkeypatch) -> None:
    """Codex review on #73: link writes cannot interleave with the release's plan check."""

    import threading

    migration = Migration()
    record = _pending_deletion(migration)
    store = migration.store
    inside, proceed = threading.Event(), threading.Event()
    real_complete = store.complete_deletion

    def paused_complete(*args, **kwargs):
        inside.set()
        proceed.wait(5)
        return real_complete(*args, **kwargs)

    late = migration.link(record).model_copy(update={"locator": "written-during-release"})
    monkeypatch.setattr(store, "complete_deletion", paused_complete)
    release = threading.Thread(
        target=migration.service.release_legacy_projection_copies,
        args=(ADMIN, NAMESPACE),
        kwargs={"store_destruction_reference": "CHG-9", "apply": True},
    )
    release.start()
    assert inside.wait(5)
    outcome: list[bool] = []
    # The outbox worker's link write is lifecycle-conditional.
    writer = threading.Thread(
        target=lambda: outcome.append(store.save_projection_link_if_active(late))
    )
    writer.start()
    writer.join(0.2)
    assert writer.is_alive(), "link write must block while the release holds the store"
    proceed.set()
    release.join(5)
    writer.join(5)
    assert store.get_record(record).state is MemoryState.DELETED
    # Third audit F-01: once deletion is complete, a late link write is refused;
    # a DELETED record never regains a projection link.
    assert outcome == [False]
    assert migration.link(record) is None


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_projection_losing_the_race_to_deletion_withdraws_its_fresh_copy(tmp_path, backend) -> None:
    """Third audit F-01: rebuild/project, provider write, pause, delete, release, resume.

    The projection worker has written the fresh provider copy and seen the
    record ACTIVE; before it installs the link, the record is deleted, its
    legacy copy erased-and-released, and deletion completes. On resuming, the
    worker must withdraw the fresh copy and must not install a link.
    """

    migration = Migration(_open_store(backend, tmp_path))
    record = migration.write("falcon plan")
    migration.drain()
    migration.switch_provider(record)
    migration.service.rebuild_projection(MAINTAINER, NAMESPACE, apply=True)
    store = migration.store
    real_get = store.get_record
    reads = {"count": 0}

    def get_record_then_race(record_id):
        current = real_get(record_id)
        if record_id == record:
            reads["count"] += 1
            if reads["count"] == 2:
                # The worker's post-provider-write lifecycle check has just
                # read ACTIVE. Everything below lands before its link write.
                store.get_record = real_get
                racer = Migration(store)
                racer.old, racer.new = migration.old, migration.new
                racer.service, racer.worker = racer._bind(migration.new)
                racer.service.delete(
                    ADMIN,
                    DeletionRequest(
                        record_id=record, reason="subject request", verification_reference="r"
                    ),
                )
                racer.drain()
                racer.service.release_legacy_projection_copies(
                    ADMIN, NAMESPACE, store_destruction_reference="CHG-10", apply=True
                )
                assert real_get(record).state is MemoryState.DELETED
        return current

    store.get_record = get_record_then_race
    try:
        migration.drain()
    finally:
        store.get_record = real_get
    assert reads["count"] >= 2, "the race window was not reached"
    assert store.get_record(record).state is MemoryState.DELETED
    assert migration.link(record) is None
    assert str(record) not in migration.new.episodes  # fresh copy withdrawn
    store.close()
