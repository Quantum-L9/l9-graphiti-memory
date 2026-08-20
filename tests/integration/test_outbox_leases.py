# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_outbox_leases.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SP-07: abandoned outbox claims recover; no event is ever owned twice."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    OutboxStatus,
    Provenance,
    RetirementMode,
)
from l9_graphite_memory.errors import StoreError
from l9_graphite_memory.services import MemoryService
from tests.conftest import STORE_BACKENDS, make_store


class RecordingProjection:
    """Minimal projection so MemoryService emits projection outbox events."""

    name = "recording"
    capabilities: tuple[str, ...] = ()
    retirement_mode = RetirementMode.WITHDRAW

    def __init__(self) -> None:
        self.projected: list[uuid.UUID] = []

    def health(self) -> dict[str, object]:
        return {"healthy": True}

    def project(self, record) -> dict[str, object]:
        self.projected.append(record.record_id)
        return {"locator": f"episode-{record.record_id}"}

    def erase(self, record_id, namespace, *, locator=None) -> dict[str, object]:
        return {"erased": True}

    def search_strategy(self, strategy, query, namespaces, *, limit):
        return []

    def search(self, query, namespaces, *, limit):
        return []


def _seed_event(store, principal) -> uuid.UUID:
    service = MemoryService(store, RecordingProjection())
    service.initialize()
    receipt = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.SEMANTIC,
            content="record requiring projection",
            provenance=Provenance(source="lease-test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
        ),
    )
    assert receipt.outbox_event_ids
    return receipt.outbox_event_ids[0]


@pytest.fixture(params=STORE_BACKENDS)
def store(request, tmp_path):
    store = make_store(request.param, tmp_path)
    store.initialize()
    yield store
    store.close()


def test_claim_grants_a_bounded_lease(store, principal) -> None:
    event_id = _seed_event(store, principal)
    now = datetime.now(timezone.utc)

    claimed = store.claim_outbox(
        limit=10, now=now, lease_seconds=300, lease_owner="worker-a"
    )

    assert [event.event_id for event in claimed] == [event_id]
    event = claimed[0]
    assert event.status is OutboxStatus.PROCESSING
    assert event.lease_id is not None
    assert event.lease_owner == "worker-a"
    assert event.lease_expires_at == now + timedelta(seconds=300)


def test_a_live_lease_is_not_reclaimable(store, principal) -> None:
    """No event can be concurrently owned by two workers."""

    _seed_event(store, principal)
    now = datetime.now(timezone.utc)

    first = store.claim_outbox(
        limit=10, now=now, lease_seconds=300, lease_owner="worker-a"
    )
    second = store.claim_outbox(
        limit=10, now=now, lease_seconds=300, lease_owner="worker-b"
    )

    assert len(first) == 1
    assert second == []


def test_an_abandoned_claim_recovers_after_lease_expiry(store, principal) -> None:
    """A worker that dies mid-delivery does not strand the event forever."""

    event_id = _seed_event(store, principal)
    now = datetime.now(timezone.utc)

    first = store.claim_outbox(
        limit=10, now=now, lease_seconds=60, lease_owner="worker-a"
    )
    assert len(first) == 1

    # worker-a crashes here: it never calls update_outbox.
    still_held = store.claim_outbox(
        limit=10,
        now=now + timedelta(seconds=59),
        lease_seconds=60,
        lease_owner="worker-b",
    )
    assert still_held == []

    recovered = store.claim_outbox(
        limit=10,
        now=now + timedelta(seconds=61),
        lease_seconds=60,
        lease_owner="worker-b",
    )

    assert [event.event_id for event in recovered] == [event_id]
    assert recovered[0].lease_owner == "worker-b"
    assert recovered[0].lease_id != first[0].lease_id


def test_a_stale_worker_cannot_settle_a_recovered_event(store, principal) -> None:
    """The crashed worker's late write must not overwrite the new owner."""

    event_id = _seed_event(store, principal)
    now = datetime.now(timezone.utc)

    stale = store.claim_outbox(
        limit=10, now=now, lease_seconds=60, lease_owner="worker-a"
    )[0]
    recovered = store.claim_outbox(
        limit=10,
        now=now + timedelta(seconds=61),
        lease_seconds=60,
        lease_owner="worker-b",
    )[0]

    with pytest.raises(StoreError, match="lease is no longer held"):
        store.update_outbox(
            event_id,
            status=OutboxStatus.DELIVERED,
            attempts=1,
            next_attempt_at=now,
            last_error=None,
            delivered_at=now,
            lease_id=stale.lease_id,
        )

    # The rightful owner still settles normally.
    store.update_outbox(
        event_id,
        status=OutboxStatus.DELIVERED,
        attempts=1,
        next_attempt_at=now,
        last_error=None,
        delivered_at=now,
        lease_id=recovered.lease_id,
    )
    assert store.outbox_backlog() == 0


def test_settling_clears_the_lease(store, principal) -> None:
    event_id = _seed_event(store, principal)
    now = datetime.now(timezone.utc)
    claimed = store.claim_outbox(
        limit=10, now=now, lease_seconds=60, lease_owner="worker-a"
    )[0]

    store.update_outbox(
        event_id,
        status=OutboxStatus.RETRY,
        attempts=1,
        next_attempt_at=now,
        last_error="provider unavailable",
        lease_id=claimed.lease_id,
    )

    requeued = store.claim_outbox(
        limit=10, now=now, lease_seconds=60, lease_owner="worker-b"
    )
    assert [event.event_id for event in requeued] == [event_id]
    assert requeued[0].attempts == 1


def test_worker_reports_lease_loss_instead_of_overwriting(
    store, principal, monkeypatch
) -> None:
    """SP-07 at the worker level: a lost lease is reported, not forced."""

    from l9_graphite_memory.config import MemorySettings
    from l9_graphite_memory.services.outbox_worker import OutboxWorker

    _seed_event(store, principal)
    projection = RecordingProjection()
    settings = MemorySettings(outbox_lease_seconds=60)
    worker = OutboxWorker(store, projection, settings, worker_id="worker-a")

    original_claim = store.claim_outbox

    def claim_then_steal(*args, **kwargs):
        events = original_claim(*args, **kwargs)
        # Another worker recovers the event between claim and settle.
        for event in events:
            original_claim(
                limit=10,
                now=kwargs["now"] + timedelta(seconds=kwargs["lease_seconds"] + 1),
                lease_seconds=60,
                lease_owner="worker-b",
            )
        return events

    monkeypatch.setattr(store, "claim_outbox", claim_then_steal)

    result = worker.run_once()

    assert result["claimed"] == 1
    assert result["delivered"] == 0
    assert result["lease_lost"] == 1


def test_concurrent_workers_never_share_an_event_on_the_shared_backend(
    principal,
) -> None:
    """SP-07 under real contention: SKIP LOCKED makes claims disjoint.

    Ten events, eight threads on independent connections, all claiming at once.
    Every event must be claimed exactly once across the whole fleet.
    """

    from concurrent.futures import ThreadPoolExecutor

    from tests.conftest import make_postgres_store

    schema = f"l9_race_{uuid.uuid4().hex}"
    seeder = make_postgres_store(schema)
    seeder.initialize()

    service = MemoryService(seeder, RecordingProjection())
    expected: set[uuid.UUID] = set()
    for index in range(10):
        receipt = service.write(
            principal,
            MemoryWriteRequest(
                namespace="repo-a",
                memory_class=MemoryClass.SEMANTIC,
                content=f"contended record {index}",
                provenance=Provenance(source="race-test"),
                evidence=(
                    EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),
                ),
            ),
        )
        expected.update(receipt.outbox_event_ids)
    assert len(expected) == 10

    now = datetime.now(timezone.utc)
    workers = [make_postgres_store(schema) for _ in range(8)]

    def claim(worker_index: int) -> list[uuid.UUID]:
        store = workers[worker_index]
        claimed = store.claim_outbox(
            limit=10,
            now=now,
            lease_seconds=300,
            lease_owner=f"worker-{worker_index}",
        )
        return [event.event_id for event in claimed]

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            batches = list(pool.map(claim, range(8)))
    finally:
        for store in workers:
            store.close()
        seeder.close()

    claimed_ids = [event_id for batch in batches for event_id in batch]

    # No event was handed to two workers, and none was stranded.
    assert len(claimed_ids) == len(set(claimed_ids))
    assert set(claimed_ids) == expected
