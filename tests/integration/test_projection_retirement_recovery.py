# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_projection_retirement_recovery.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""ADR-076: the withdraw-only ceiling is declared, audited, and reversible."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from l9_graphite_memory.adapters import (
    GraphitiProjection,
    NullProjection,
)
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    DeletionRequest,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
    RetirementMode,
)
from l9_graphite_memory.errors import AuthorizationError, StoreError
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker
from tests.conftest import STORE_BACKENDS, make_store


class WithdrawProjection:
    """Stands in for a provider whose only removal primitive is deletion."""

    name = "withdraw-only"
    capabilities: tuple[str, ...] = ()
    retirement_mode = RetirementMode.WITHDRAW

    def __init__(self) -> None:
        self.projected: list[UUID] = []
        self.retired: list[UUID] = []
        self.erased: list[UUID] = []

    def health(self) -> dict[str, object]:
        return {"healthy": True}

    def project(self, record) -> dict[str, object]:
        self.projected.append(record.record_id)
        return {"locator": f"episode-{record.record_id}"}

    def retire(self, record_id, namespace, *, locator=None, reason="") -> dict[str, object]:
        self.retired.append(record_id)
        return {"retired": True, "erased": False, "locator": locator}

    def erase(self, record_id, namespace, *, locator=None) -> dict[str, object]:
        self.erased.append(record_id)
        return {"erased": True}

    def search_strategy(self, strategy, query, namespaces, *, limit):
        return []

    def search(self, query, namespaces, *, limit):
        return []


@pytest.fixture(params=STORE_BACKENDS)
def store(request, tmp_path):
    store = make_store(request.param, tmp_path)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def projection() -> WithdrawProjection:
    return WithdrawProjection()


@pytest.fixture
def service(store, projection) -> MemoryService:
    service = MemoryService(store, projection)
    service.initialize()
    return service


@pytest.fixture
def worker(store, projection) -> OutboxWorker:
    return OutboxWorker(store, projection, MemorySettings(), worker_id="test")


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="operator",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
        maintain_namespaces=("repo-a",),
    )


def _write(service, principal, content, **kwargs):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.OBSERVATION,
            content=content,
            provenance=Provenance(source="test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
            **kwargs,
        ),
    )


def _drain(worker) -> None:
    for _ in range(6):
        if worker.run_once()["claimed"] == 0:
            break


# -- the ceiling is declared, not implied ------------------------------------


def test_providers_declare_their_retirement_mode() -> None:
    """The ceiling is machine-readable rather than prose in an ADR."""

    assert GraphitiProjection.retirement_mode is RetirementMode.WITHDRAW
    assert NullProjection.retirement_mode is RetirementMode.NATIVE


# -- retirement stays auditable from canonical state -------------------------


def test_retirement_is_recorded_in_canonical_state(
    service, store, projection, worker, maintainer
) -> None:
    """A withdraw-only provider cannot tell retire from erase in its own log,
    so canonical state has to carry the distinction."""

    original = _write(service, maintainer, "first truth")
    _drain(worker)
    replacement = _write(service, maintainer, "revised truth", supersedes=(original.record_id,))
    _drain(worker)

    assert projection.retired == [original.record_id]
    assert projection.erased == []

    receipts = _retirement_receipts(store)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["record_id"] == str(original.record_id)
    assert receipt["retirement_mode"] == RetirementMode.WITHDRAW.value
    assert receipt["erasure"] is False
    assert receipt["rebuildable"] is True
    assert str(replacement.record_id) in receipt["reason"]
    assert receipt["locator"] == f"episode-{original.record_id}"


def test_a_retirement_receipt_cannot_claim_erasure() -> None:
    from pydantic import ValidationError

    from l9_graphite_memory.contracts import ProjectionRetirementReceipt

    with pytest.raises(ValidationError, match="cannot assert erasure"):
        ProjectionRetirementReceipt(
            record_id=UUID(int=1),
            namespace="repo-a",
            projection_name="withdraw-only",
            retirement_mode=RetirementMode.WITHDRAW,
            reason="superseded",
            erasure=True,
        )


def test_privacy_deletion_produces_no_retirement_receipt(
    service, store, projection, worker, maintainer, admin_principal
) -> None:
    """The two paths stay distinguishable in canonical state."""

    written = _write(service, maintainer, "delete me")
    _drain(worker)
    service.delete(
        admin_principal,
        DeletionRequest(
            record_id=written.record_id,
            reason="verified deletion",
            verification_reference="ticket-1",
        ),
    )
    _drain(worker)

    assert projection.erased == [written.record_id]
    assert _retirement_receipts(store) == []


def _retirement_receipts(store) -> list[dict]:
    """Read retirement receipts back through whatever the backend exposes."""

    import json

    if hasattr(store, "projection_retirements"):
        return [receipt.model_dump(mode="json") for receipt in store.projection_retirements]
    if store.name == "sqlite":
        rows = (
            store._connection()
            .execute(
                "SELECT receipt_json FROM operation_receipts WHERE kind = 'projection_retirement'"
            )
            .fetchall()
        )
        return [json.loads(str(row["receipt_json"])) for row in rows]
    with store._cursor() as cursor:
        cursor.execute(
            "SELECT receipt_json FROM operation_receipts WHERE kind = 'projection_retirement'"
        )
        return [json.loads(str(row["receipt_json"])) for row in cursor.fetchall()]


# -- withdrawal is reversible ------------------------------------------------


def test_rebuild_reprojects_records_whose_projection_was_withdrawn(
    service, store, projection, worker, maintainer
) -> None:
    """The headline remediation: a withdrawn projection is recoverable."""

    now = datetime.now(timezone.utc)
    written = _write(
        service,
        maintainer,
        "expired then restored",
        valid_from=now - timedelta(days=2),
        valid_to=now - timedelta(days=1),
    )
    _drain(worker)
    assert store.get_projection_link(written.record_id, "withdraw-only") is not None

    # Archive retires the projection.
    service.apply_retention(maintainer.model_copy(update={"is_admin": True}), "repo-a", apply=True)
    _drain(worker)
    assert projection.retired == [written.record_id]
    assert store.get_projection_link(written.record_id, "withdraw-only") is None

    # Governance restores the record to active through the service, which
    # commits the transition with its own projection intent (ADR-074).
    governance = maintainer.model_copy(update={"is_admin": True})
    restored = service.transition_lifecycle(
        governance,
        "repo-a",
        record_ids=(written.record_id,),
        new_state=MemoryState.ACTIVE,
        reason="governance reversed the archive decision",
    )
    assert [item.new_state for item in restored.transitions] == [MemoryState.ACTIVE]
    assert store.get_record(written.record_id).state is MemoryState.ACTIVE
    _drain(worker)
    assert projection.projected.count(written.record_id) == 2
    assert store.get_projection_link(written.record_id, "withdraw-only") is not None

    # A projection lost at the provider is recovered by rebuild, so the
    # withdrawal was not permanent.
    store.delete_projection_link(written.record_id, "withdraw-only")
    receipt = service.rebuild_projection(maintainer, "repo-a", apply=True)
    assert receipt.queued_record_ids == (written.record_id,)
    _drain(worker)

    assert projection.projected.count(written.record_id) == 3
    assert store.get_projection_link(written.record_id, "withdraw-only") is not None


def test_rebuild_dry_run_queues_nothing(service, store, projection, worker, maintainer) -> None:
    """A dry run reports what it would do without enqueueing anything."""

    written = _write(service, maintainer, "projected then withdrawn")
    _drain(worker)
    # Simulate a withdrawal: the link is gone, so the record is unprojected.
    store.delete_projection_link(written.record_id, "withdraw-only")
    projected_before = list(projection.projected)

    receipt = service.rebuild_projection(maintainer, "repo-a", apply=False)

    assert receipt.applied is False
    assert receipt.queued_record_ids == (written.record_id,)

    # Nothing was enqueued, so draining re-projects nothing.
    _drain(worker)
    assert projection.projected == projected_before
    assert store.get_projection_link(written.record_id, "withdraw-only") is None


def test_rebuild_skips_records_that_are_already_projected(
    service, store, projection, worker, maintainer
) -> None:
    _write(service, maintainer, "already projected")
    _drain(worker)

    receipt = service.rebuild_projection(maintainer, "repo-a", apply=True)

    assert receipt.queued_record_ids == ()
    assert receipt.already_projected_count == 1


def test_rebuild_requires_maintain_authority(service, store, projection) -> None:
    reader = MemoryPrincipal(
        principal_id="reader",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
    )

    with pytest.raises(AuthorizationError):
        service.rebuild_projection(reader, "repo-a", apply=True)


def test_rebuild_is_refused_when_no_projection_is_configured(store, maintainer) -> None:
    service = MemoryService(store, NullProjection())
    service.initialize()

    with pytest.raises(StoreError, match="nothing to rebuild"):
        service.rebuild_projection(maintainer, "repo-a", apply=True)
