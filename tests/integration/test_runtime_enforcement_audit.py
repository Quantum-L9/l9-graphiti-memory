# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_runtime_enforcement_audit.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-13

"""Adversarial regression tests for the runtime-enforcement audit findings.

These cover the three confirmed bypasses from the 2026-08-13 runtime enforcement
audit:

* F-002 (T1) cross-tenant admin get/delete,
* F-003 (T2) cross-tenant phase-lock collision,
* F-001 (T2) direct lower-level canonical persistence below MemoryService.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import NullProjection
from l9_graphite_memory.adapters.in_memory_store import InMemoryRecordStore
from l9_graphite_memory.adapters.sqlite_store import SQLiteRecordStore
from l9_graphite_memory.contracts import (
    DeletionRequest,
    MemoryClass,
    MemoryPrincipal,
    MemoryWriteRequest,
    PhaseLockRequest,
    Provenance,
    WriteStatus,
)
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.services import MemoryService


def _service(store) -> MemoryService:
    service = MemoryService(store, NullProjection())
    service.initialize()
    return service


def _tenant_a_writer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="writer-a",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
        promote_namespaces=("repo-a",),
    )


def _tenant_b_admin() -> MemoryPrincipal:
    """Administrator of tenant B. Admin *within* its tenant, not across tenants."""

    return MemoryPrincipal(
        principal_id="admin-b",
        tenant_id="tenant-b",
        read_namespaces=("*",),
        write_namespaces=("*",),
        promote_namespaces=("*",),
        is_admin=True,
    )


def _global_admin(tenant_id: str = "tenant-b") -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="global-admin",
        tenant_id=tenant_id,
        read_namespaces=("*",),
        write_namespaces=("*",),
        promote_namespaces=("*",),
        is_admin=True,
        is_global_admin=True,
    )


def _write(service: MemoryService, principal: MemoryPrincipal, content: str):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.SEMANTIC,
            content=content,
            provenance=Provenance(source="test"),
        ),
    )


# --------------------------------------------------------------------------- #
# F-002: cross-tenant admin get / delete
# --------------------------------------------------------------------------- #


def test_tenant_b_admin_cannot_get_tenant_a_record() -> None:
    service = _service(InMemoryRecordStore())
    record = _write(service, _tenant_a_writer(), "tenant-a secret")

    with pytest.raises(AuthorizationError, match="different tenant"):
        service.get(_tenant_b_admin(), record.record_id)


def test_tenant_b_admin_cannot_delete_tenant_a_record() -> None:
    service = _service(InMemoryRecordStore())
    record = _write(service, _tenant_a_writer(), "tenant-a secret")

    with pytest.raises(AuthorizationError, match="different tenant"):
        service.delete(
            _tenant_b_admin(),
            DeletionRequest(
                record_id=record.record_id,
                reason="cross-tenant deletion attempt",
                verification_reference="attacker-ticket",
            ),
        )

    # The record remains readable by its own tenant, unmodified.
    assert service.get(_tenant_a_writer(), record.record_id).content == "tenant-a secret"


def test_same_tenant_admin_still_reaches_record() -> None:
    service = _service(InMemoryRecordStore())
    writer = _tenant_a_writer()
    record = _write(service, writer, "tenant-a data")
    same_tenant_admin = writer.model_copy(update={"is_admin": True})

    assert service.get(same_tenant_admin, record.record_id).content == "tenant-a data"


def test_global_admin_may_cross_tenant_by_explicit_claim() -> None:
    service = _service(InMemoryRecordStore())
    record = _write(service, _tenant_a_writer(), "tenant-a data")

    fetched = service.get(_global_admin(), record.record_id)
    assert fetched is not None and fetched.content == "tenant-a data"


# --------------------------------------------------------------------------- #
# F-003: cross-tenant phase-lock collision
# --------------------------------------------------------------------------- #


@pytest.fixture(params=["memory", "sqlite"])
def dual_tenant_stores(request, tmp_path: Path):
    if request.param == "memory":
        return InMemoryRecordStore()
    return SQLiteRecordStore(tmp_path / "phase-lock.sqlite3")


def test_phase_locks_are_isolated_across_tenants(dual_tenant_stores) -> None:
    service = _service(dual_tenant_stores)
    principal_a = MemoryPrincipal(
        principal_id="p-a",
        tenant_id="tenant-a",
        read_namespaces=("shared-ns",),
        write_namespaces=("shared-ns",),
    )
    principal_b = MemoryPrincipal(
        principal_id="p-b",
        tenant_id="tenant-b",
        read_namespaces=("shared-ns",),
        write_namespaces=("shared-ns",),
    )
    request = PhaseLockRequest(
        namespace="shared-ns", task_signature="identical-task-signature"
    )

    lock_a = service.phase_lock(principal_a, request)
    lock_b = service.phase_lock(principal_b, request)

    # Distinct receipts, distinct tenants — no overwrite collision.
    assert lock_a.tenant_id == "tenant-a"
    assert lock_b.tenant_id == "tenant-b"
    assert lock_a.lock_id != lock_b.lock_id

    # Tenant A still verifies against its own lock, unaffected by tenant B.
    verification_a = service.verify_phase_lock(
        principal_a, "shared-ns", "identical-task-signature"
    )
    verification_b = service.verify_phase_lock(
        principal_b, "shared-ns", "identical-task-signature"
    )
    assert verification_a.valid
    assert verification_b.valid
    assert verification_a.lock_id == lock_a.lock_id
    assert verification_b.lock_id == lock_b.lock_id


def test_phase_lock_not_visible_to_other_tenant(dual_tenant_stores) -> None:
    service = _service(dual_tenant_stores)
    principal_a = MemoryPrincipal(
        principal_id="p-a",
        tenant_id="tenant-a",
        read_namespaces=("shared-ns",),
        write_namespaces=("shared-ns",),
    )
    principal_b = MemoryPrincipal(
        principal_id="p-b",
        tenant_id="tenant-b",
        read_namespaces=("shared-ns",),
        write_namespaces=("shared-ns",),
    )
    service.phase_lock(
        principal_a,
        PhaseLockRequest(namespace="shared-ns", task_signature="task-signature-x"),
    )

    # Tenant B has issued no lock; it must not see tenant A's lock slot.
    verification_b = service.verify_phase_lock(
        principal_b, "shared-ns", "task-signature-x"
    )
    assert not verification_b.valid
    assert "does not exist" in " ".join(verification_b.reasons)


# --------------------------------------------------------------------------- #
# F-001: direct lower-level canonical persistence requires the service capability
# --------------------------------------------------------------------------- #


def test_direct_in_memory_commit_write_requires_capability() -> None:
    store = InMemoryRecordStore()
    store.initialize()
    service = _service(InMemoryRecordStore())
    receipt = _write(service, _tenant_a_writer(), "legit content")

    # An in-process consumer holding the concrete store cannot forge a canonical
    # write: the capability is required and cannot be supplied from here.
    with pytest.raises(PermissionError, match="write capability"):
        store.commit_write(None, None, receipt)

    with pytest.raises(PermissionError, match="write capability"):
        store.commit_write(object(), None, receipt)


def test_direct_sqlite_commit_write_requires_capability(tmp_path: Path) -> None:
    store = SQLiteRecordStore(tmp_path / "bypass.sqlite3")
    store.initialize()
    service = _service(SQLiteRecordStore(tmp_path / "legit.sqlite3"))
    receipt = _write(service, _tenant_a_writer(), "legit content")

    with pytest.raises(PermissionError, match="write capability"):
        store.commit_write(None, None, receipt)


def test_service_write_capability_is_not_publicly_exported() -> None:
    from l9_graphite_memory import adapters

    assert "InMemoryRecordStore" not in adapters.__all__
    assert "SQLiteRecordStore" not in adapters.__all__


def test_capability_backed_write_still_succeeds_through_service() -> None:
    service = _service(InMemoryRecordStore())
    receipt = _write(service, _tenant_a_writer(), "content through service")
    assert receipt.status is WriteStatus.ADMITTED
    assert service.get(_tenant_a_writer(), receipt.record_id) is not None
