# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_conflict_links.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""ADR-081: contradictions are links reconciliation records on both records."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from l9_graphite_memory.adapters import NullProjection
from l9_graphite_memory.contracts import (
    ConflictItem,
    EvidenceKind,
    EvidenceRef,
    MaintenanceOperation,
    MaintenanceRequest,
    MemoryAssertion,
    MemoryPrincipal,
    MemoryState,
    MemoryWriteRequest,
    PhaseLockRequest,
    Provenance,
)
from l9_graphite_memory.errors import AdmissionError, AuthorizationError
from l9_graphite_memory.maintenance import MaintenanceService
from l9_graphite_memory.services import MemoryService
from tests.conftest import STORE_BACKENDS, make_store

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)
RECONCILE = MaintenanceRequest(namespace="repo-a", operations=(MaintenanceOperation.RECONCILE,))


@pytest.fixture(params=STORE_BACKENDS)
def store(request, tmp_path):
    store = make_store(request.param, tmp_path)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def service(store) -> MemoryService:
    service = MemoryService(store, NullProjection())
    service.initialize()
    return service


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="nightly",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
        promote_namespaces=("repo-a",),
        maintain_namespaces=("repo-a",),
    )


def _write(service, principal, content, obj, *, subject="service", valid_from=BASE, **kwargs):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace=kwargs.pop("namespace", "repo-a"),
            content=content,
            assertion=MemoryAssertion(subject=subject, predicate="region", object=obj),
            provenance=Provenance(source="test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
            valid_from=valid_from,
            **kwargs,
        ),
    ).record_id


def _link_receipts(store) -> list[dict]:
    if hasattr(store, "conflict_receipts"):
        return [item.model_dump(mode="json") for item in store.conflict_receipts.values()]
    if store.name == "sqlite":
        rows = (
            store._connection()
            .execute("SELECT receipt_json FROM operation_receipts WHERE kind = 'conflict_link'")
            .fetchall()
        )
        return [json.loads(str(row["receipt_json"])) for row in rows]
    with store._cursor() as cursor:
        cursor.execute("SELECT receipt_json FROM operation_receipts WHERE kind = 'conflict_link'")
        return [json.loads(str(row["receipt_json"])) for row in cursor.fetchall()]


def test_reconciliation_links_both_records_under_a_receipt(service, store, maintainer):
    left = _write(service, maintainer, "runs in us-east-1", "us-east-1")
    right = _write(service, maintainer, "runs in eu-west-1", "eu-west-1")
    assert not service.conflicts(maintainer, "repo-a").has_conflicts

    receipt = MaintenanceService(service).run(maintainer, RECONCILE)

    assert receipt.failures == ()
    (action,) = receipt.actions
    assert action.applied and action.details["linked"] is True
    assert store.get_record(left).conflicts_with == (right,)
    assert store.get_record(right).conflicts_with == (left,)
    (stored,) = _link_receipts(store)
    assert stored["receipt_id"] == action.details["conflict_link_receipt_id"]
    assert {stored["links"][0]["left_record_id"], stored["links"][0]["right_record_id"]} == {
        str(left),
        str(right),
    }

    report = service.conflicts(maintainer, "repo-a")
    (conflict,) = report.conflicts
    assert {conflict.left_record_id, conflict.right_record_id} == {left, right}
    assert (conflict.subject, conflict.predicate) == ("service", "region")


def test_a_rerun_writes_nothing(service, store, maintainer):
    _write(service, maintainer, "runs in us-east-1", "us-east-1")
    _write(service, maintainer, "runs in eu-west-1", "eu-west-1")
    MaintenanceService(service).run(maintainer, RECONCILE)
    again = MaintenanceService(service).run(maintainer, RECONCILE)
    assert again.actions == ()
    assert len(_link_receipts(store)) == 1
    assert len(service.conflicts(maintainer, "repo-a").conflicts) == 1


def test_linked_conflicts_refuse_phase_locks_and_promotion(service, store, maintainer):
    from l9_graphite_memory.contracts import MemoryClass, PromotionRequest

    left = _write(service, maintainer, "runs in us-east-1", "us-east-1")
    _write(service, maintainer, "runs in eu-west-1", "eu-west-1")
    MaintenanceService(service).run(maintainer, RECONCILE)

    lock = service.phase_lock(
        maintainer, PhaseLockRequest(namespace="repo-a", task_signature="signature-1")
    )
    assert not lock.granted
    with pytest.raises(AuthorizationError, match="unresolved conflicts"):
        service.promote(
            maintainer,
            PromotionRequest(
                record_id=left,
                target_class=MemoryClass.SEMANTIC,
                governance_approval=False,
                reason="promote a contested fact",
            ),
        )


def test_superseding_one_side_resolves_the_conflict(service, store, maintainer):
    left = _write(service, maintainer, "runs in us-east-1", "us-east-1")
    right = _write(service, maintainer, "runs in eu-west-1", "eu-west-1")
    MaintenanceService(service).run(maintainer, RECONCILE)
    assert service.conflicts(maintainer, "repo-a").has_conflicts

    _write(service, maintainer, "moved to eu-west-1", "eu-west-1", supersedes=(left,))

    assert store.get_record(left).state is MemoryState.SUPERSEDED
    # The link is history on both records; the report no longer counts it.
    assert store.get_record(right).conflicts_with == (left,)
    assert not service.conflicts(maintainer, "repo-a").has_conflicts
    lock = service.phase_lock(
        maintainer, PhaseLockRequest(namespace="repo-a", task_signature="signature-2")
    )
    assert lock.granted


def test_link_conflicts_validates_its_targets(service, store, maintainer, admin_principal):
    left = _write(service, maintainer, "runs in us-east-1", "us-east-1")
    right = _write(service, maintainer, "runs in eu-west-1", "eu-west-1")
    foreign = _write(
        service,
        admin_principal,
        "runs in ap-south-1",
        "ap-south-1",
        namespace="workspace",
    )

    def link(a, b):
        return service.link_conflicts(
            maintainer,
            "repo-a",
            links=(ConflictItem(left_record_id=a, right_record_id=b, reason="test"),),
            reason="test",
        )

    with pytest.raises(AdmissionError, match="cannot conflict with itself"):
        link(left, left)
    with pytest.raises(AuthorizationError, match="outside the authorized"):
        link(left, foreign)
    receipt = link(left, right)
    assert len(receipt.links) == 1
    repeat = link(right, left)
    assert repeat.links == ()
    assert len(_link_receipts(store)) == 1

    _write(service, maintainer, "moved", "eu-west-1", supersedes=(left,))
    third = _write(service, maintainer, "runs in sa-east-1", "sa-east-1")
    with pytest.raises(AdmissionError, match="only active records"):
        link(left, third)

    reader = maintainer.model_copy(update={"maintain_namespaces": ()})
    with pytest.raises(AuthorizationError):
        service.link_conflicts(
            reader,
            "repo-a",
            links=(ConflictItem(left_record_id=right, right_record_id=third, reason="t"),),
            reason="t",
        )


def test_linking_requires_the_service_capability(service, store, maintainer):
    left = _write(service, maintainer, "runs in us-east-1", "us-east-1")
    right = _write(service, maintainer, "runs in eu-west-1", "eu-west-1")
    from l9_graphite_memory.contracts import (
        AuthorizationAction,
        AuthorizationReceipt,
        ConflictLinkReceipt,
    )

    receipt = ConflictLinkReceipt(
        namespace="repo-a",
        links=(ConflictItem(left_record_id=left, right_record_id=right, reason="t"),),
        authorization=service.namespace_policy.require(
            maintainer, AuthorizationAction.MAINTAIN, "repo-a"
        ),
        reason="t",
        actor="attacker",
    )
    with pytest.raises(PermissionError, match="write capability"):
        store.commit_conflict_links(object(), receipt)
    assert store.get_record(left).conflicts_with == ()
    assert isinstance(receipt.authorization, AuthorizationReceipt)
