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
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.graph import GRAPH_SCOPE_SCHEME
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker
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

    def __init__(self) -> None:
        self.store = InMemoryRecordStore()
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

    def cut_over(self, *records: UUID) -> None:
        """Mark links as pre-ADR-084, then rebuild into the fresh database."""

        for record_id in records:
            link = self.link(record_id)
            assert link is not None
            self.store.save_projection_link(link.model_copy(update={"metadata": {}}))
        self.service, self.worker = self._bind(self.new)
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
