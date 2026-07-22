# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/test_store_contract.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import (
    InMemoryRecordStore,
    NullProjection,
    SQLiteRecordStore,
)
from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.services import MemoryService


def stores(tmp_path: Path):
    return [InMemoryRecordStore(), SQLiteRecordStore(tmp_path / "conformance.sqlite3")]


@pytest.mark.parametrize("index", [0, 1])
def test_store_adapters_share_write_read_contract(
    tmp_path: Path, principal, index: int
) -> None:
    store = stores(tmp_path)[index]
    service = MemoryService(store, NullProjection())
    service.initialize()
    receipt = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.SEMANTIC,
            content="Adapter conformance",
            provenance=Provenance(source="test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
        ),
    )
    assert service.get(principal, receipt.record_id).content == "Adapter conformance"
    assert store.health()["healthy"]


@pytest.mark.parametrize("index", [0, 1])
def test_store_adapters_commit_archive_with_receipt(
    tmp_path: Path,
    principal,
    admin_principal,
    index: int,
) -> None:
    from datetime import datetime, timedelta, timezone

    from l9_graphite_memory.contracts import MemoryState

    store = stores(tmp_path)[index]
    service = MemoryService(store, NullProjection())
    service.initialize()
    now = datetime.now(timezone.utc)
    write = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.OBSERVATION,
            content="expired adapter record",
            provenance=Provenance(source="test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
            valid_from=now - timedelta(days=2),
            valid_to=now - timedelta(days=1),
        ),
    )
    archive = service.prune(admin_principal, "repo-a", apply=True)
    assert archive.archived_record_ids == (write.record_id,)
    assert service.get(admin_principal, write.record_id).state is MemoryState.ARCHIVED
    assert store.stats()["receipts"] == 2
    store.close()


@pytest.mark.parametrize("index", [0, 1])
def test_store_adapters_commit_verified_deletion_with_receipt(
    tmp_path: Path,
    principal,
    admin_principal,
    index: int,
) -> None:
    from l9_graphite_memory.contracts import (
        DeletionRequest,
        DeletionStatus,
        MemoryState,
    )

    store = stores(tmp_path)[index]
    service = MemoryService(store, NullProjection())
    service.initialize()
    write = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            content="delete me through canonical service",
            provenance=Provenance(source="test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
        ),
    )
    receipt = service.delete(
        admin_principal,
        DeletionRequest(
            record_id=write.record_id,
            reason="verified deletion conformance",
            verification_reference="test-ticket",
        ),
    )
    tombstone = service.get(admin_principal, write.record_id)

    assert receipt.status is DeletionStatus.COMPLETE
    assert tombstone is not None and tombstone.state is MemoryState.DELETED
    assert "delete me" not in tombstone.content
    store.close()


@pytest.mark.parametrize("store_kind", ["memory", "sqlite"])
def test_projection_link_round_trip(store_kind: str, tmp_path) -> None:

    from l9_graphite_memory.adapters import InMemoryRecordStore, SQLiteRecordStore
    from l9_graphite_memory.contracts import ProjectionLink

    store = (
        InMemoryRecordStore()
        if store_kind == "memory"
        else SQLiteRecordStore(tmp_path / "projection-links.db")
    )
    store.initialize()
    try:
        # Projection links are constrained to canonical records. Create a minimal record through fixtures.
        from l9_graphite_memory.adapters import NullProjection
        from l9_graphite_memory.contracts import (
            MemoryPrincipal,
            MemoryWriteRequest,
            Provenance,
        )
        from l9_graphite_memory.services import MemoryService

        principal = MemoryPrincipal(
            principal_id="tester",
            tenant_id="tenant",
            read_namespaces=("repo-a",),
            write_namespaces=("repo-a",),
        )
        service = MemoryService(store, NullProjection())
        receipt = service.write(
            principal,
            MemoryWriteRequest(
                namespace="repo-a",
                content="projection link target",
                provenance=Provenance(source="test"),
            ),
        )
        assert receipt.record_id is not None
        record_id = receipt.record_id
        link = ProjectionLink(
            record_id=record_id,
            namespace="repo-a",
            projection_name="graphiti",
            locator="episode-1",
        )
        store.save_projection_link(link)
        assert store.get_projection_link(record_id, "graphiti") == link
        store.delete_projection_link(record_id, "graphiti")
        assert store.get_projection_link(record_id, "graphiti") is None
    finally:
        store.close()
