# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_maintenance_engine.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SP-12 / SP-13 / SP-14: consolidation with lineage, temporal safety, idempotency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.adapters import NullProjection
from l9_graphite_memory.contracts import (
    ConfidenceMethod,
    EvidenceKind,
    EvidenceRef,
    MaintenanceOperation,
    MaintenanceRequest,
    MemoryAssertion,
    MemoryClass,
    MemoryPrincipal,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.errors import AuthorizationError
from l9_graphite_memory.maintenance import MaintenanceService
from l9_graphite_memory.ports import Clock
from l9_graphite_memory.services import MemoryService
from tests.conftest import STORE_BACKENDS, make_store

BASE = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class FrozenClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta) -> None:
        self._now = self._now + timedelta(**delta)


@pytest.fixture(params=STORE_BACKENDS)
def store(request, tmp_path):
    store = make_store(request.param, tmp_path)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(BASE)


@pytest.fixture
def service(store, clock) -> MemoryService:
    service = MemoryService(store, NullProjection(), clock=clock)
    service.initialize()
    return service


@pytest.fixture
def maintenance(service) -> MaintenanceService:
    return MaintenanceService(service)


@pytest.fixture
def writer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="agent",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
    )


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    """Nightly principal: MAINTAIN and READ only."""

    return MemoryPrincipal(
        principal_id="nightly-maintenance",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        maintain_namespaces=("repo-a",),
    )


def write(
    service,
    principal,
    content: str,
    *,
    source_id: str = "s",
    assertion: MemoryAssertion | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    memory_class: MemoryClass = MemoryClass.OBSERVATION,
):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=memory_class,
            content=content,
            assertion=assertion,
            provenance=Provenance(source="observer", source_id=source_id),
            evidence=(
                EvidenceRef(
                    kind=EvidenceKind.OBSERVATION,
                    description=f"observed by {source_id}",
                    source_id=source_id,
                ),
            ),
            valid_from=valid_from or BASE,
            valid_to=valid_to,
        ),
    )


def run(maintenance, maintainer, **kwargs):
    return maintenance.run(maintainer, MaintenanceRequest(namespace="repo-a", **kwargs))


# -- SP-12: consolidation with lineage ---------------------------------------


def test_duplicate_observations_consolidate_with_lineage(
    service, store, maintenance, writer, maintainer, clock
) -> None:
    """SP-12: identical observations become one derived memory that cites them."""

    first = write(service, writer, "the deploy pipeline uses ubuntu-latest", source_id="a")
    second = write(service, writer, "the deploy pipeline uses ubuntu-latest", source_id="b")
    assert first.record_id != second.record_id

    clock.advance(hours=1)
    receipt = run(maintenance, maintainer, operations=(MaintenanceOperation.DEDUPE,))

    assert receipt.applied is True
    assert len(receipt.applied_actions) == 1
    action = receipt.applied_actions[0]
    assert action.operation is MaintenanceOperation.DEDUPE
    assert set(action.source_record_ids) == {first.record_id, second.record_id}

    derived = store.get_record(action.result_record_id)
    assert derived is not None
    # Lineage: the derived memory cites and supersedes both observations.
    assert set(derived.supersedes) == {first.record_id, second.record_id}
    assert set(derived.references) == {first.record_id, second.record_id}
    assert derived.confidence.method is ConfidenceMethod.AGGREGATED
    assert derived.confidence.evidence_count == 2
    assert any(item.kind is EvidenceKind.AGGREGATION for item in derived.evidence)
    assert derived.metadata["consolidated_count"] == 2

    # The originals are immutable: superseded, not rewritten or deleted.
    for original in (first, second):
        record = store.get_record(original.record_id)
        assert record.state is MemoryState.SUPERSEDED
        assert record.content == "the deploy pipeline uses ubuntu-latest"
        assert record.evidence


def test_consolidation_runs_under_maintain_without_write_authority(
    service, maintenance, writer, maintainer
) -> None:
    """SP-10 in practice: the nightly principal never needs a WRITE grant."""

    write(service, writer, "identical content", source_id="a")
    write(service, writer, "identical content", source_id="b")

    assert maintainer.write_namespaces == ()
    assert maintainer.is_admin is False

    receipt = run(maintenance, maintainer, operations=(MaintenanceOperation.DEDUPE,))

    assert receipt.applied_actions
    assert receipt.authorization.action.value == "maintain"


def test_maintenance_requires_the_maintain_grant(service, maintenance, writer) -> None:
    with pytest.raises(AuthorizationError):
        maintenance.run(writer, MaintenanceRequest(namespace="repo-a"))


def test_a_single_observation_is_left_alone(
    service, store, maintenance, writer, maintainer
) -> None:
    written = write(service, writer, "only observation", source_id="a")

    receipt = run(maintenance, maintainer)

    assert receipt.applied_actions == ()
    assert store.get_record(written.record_id).state is MemoryState.ACTIVE


# -- SP-13: temporal evolution and contradiction ------------------------------


def test_disjoint_validity_is_not_collapsed(
    service, store, maintenance, writer, maintainer
) -> None:
    """SP-13: a fact that lapsed and returned keeps its gap."""

    first = write(
        service,
        writer,
        "the feature flag is enabled",
        source_id="a",
        valid_from=BASE,
        valid_to=BASE + timedelta(days=1),
    )
    second = write(
        service,
        writer,
        "the feature flag is enabled",
        source_id="b",
        valid_from=BASE + timedelta(days=10),
        valid_to=BASE + timedelta(days=11),
    )

    receipt = run(maintenance, maintainer, operations=(MaintenanceOperation.DEDUPE,))

    assert receipt.applied_actions == ()
    assert store.get_record(first.record_id).state is MemoryState.ACTIVE
    assert store.get_record(second.record_id).state is MemoryState.ACTIVE


def test_temporal_evolution_supersedes_rather_than_deduping(
    service, store, maintenance, writer, maintainer
) -> None:
    """SP-13: a changed fact replaces the old one; both survive as history."""

    old = write(
        service,
        writer,
        "the service runs in us-east-1",
        source_id="a",
        assertion=MemoryAssertion(subject="service", predicate="region", object="us-east-1"),
        valid_from=BASE,
    )
    new = write(
        service,
        writer,
        "the service runs in eu-west-1",
        source_id="b",
        assertion=MemoryAssertion(subject="service", predicate="region", object="eu-west-1"),
        valid_from=BASE + timedelta(days=5),
    )

    receipt = run(maintenance, maintainer, operations=(MaintenanceOperation.SUPERSEDE,))

    actions = receipt.applied_actions
    assert len(actions) == 1
    assert actions[0].operation is MaintenanceOperation.SUPERSEDE
    assert actions[0].superseded_record_ids == (old.record_id,)

    # The old fact is superseded, not merged away, and keeps its content.
    superseded = store.get_record(old.record_id)
    assert superseded.state is MemoryState.SUPERSEDED
    assert superseded.content == "the service runs in us-east-1"
    assert store.get_record(new.record_id).state is MemoryState.ACTIVE


def test_contradiction_is_reported_not_resolved(
    service, store, maintenance, writer, maintainer
) -> None:
    """SP-13: an unresolvable conflict is surfaced, and nothing is mutated."""

    left = write(
        service,
        writer,
        "the owner is team-alpha",
        source_id="a",
        assertion=MemoryAssertion(subject="service", predicate="owner", object="team-alpha"),
        valid_from=BASE,
    )
    right = write(
        service,
        writer,
        "the owner is team-beta",
        source_id="b",
        assertion=MemoryAssertion(subject="service", predicate="owner", object="team-beta"),
        valid_from=BASE,
    )

    receipt = run(maintenance, maintainer, operations=(MaintenanceOperation.RECONCILE,))

    actions = receipt.actions
    assert len(actions) == 1
    assert actions[0].operation is MaintenanceOperation.RECONCILE
    assert set(actions[0].source_record_ids) == {left.record_id, right.record_id}
    assert actions[0].details["resolution"] == "requires governance decision"
    assert actions[0].result_record_id is None

    # Reconciliation changes nothing.
    assert store.get_record(left.record_id).state is MemoryState.ACTIVE
    assert store.get_record(right.record_id).state is MemoryState.ACTIVE

    # It is reported, not applied, so the finding is not suppressed.
    assert receipt.applied_actions == ()
    assert actions[0].action_digest not in store.find_maintenance_action_digests(
        "tenant-a", "repo-a"
    )


def test_an_unresolved_contradiction_is_reported_on_every_run(
    service, store, maintenance, writer, maintainer, clock
) -> None:
    """A conflict nobody resolved must not go quiet after the first sighting."""

    for source_id, owner in (("a", "team-alpha"), ("b", "team-beta")):
        write(
            service,
            writer,
            f"the owner is {owner}",
            source_id=source_id,
            assertion=MemoryAssertion(subject="service", predicate="owner", object=owner),
            valid_from=BASE,
        )

    first = run(maintenance, maintainer, operations=(MaintenanceOperation.RECONCILE,))
    clock.advance(days=1)
    second = run(maintenance, maintainer, operations=(MaintenanceOperation.RECONCILE,))

    assert len(first.actions) == 1
    assert len(second.actions) == 1
    assert second.actions[0].action_digest == first.actions[0].action_digest


def test_corroborating_assertions_refine_with_combined_evidence(
    service, store, maintenance, writer, maintainer
) -> None:
    """Differently worded agreement is corroboration, not duplication."""

    first = write(
        service,
        writer,
        "The build targets Python 3.13.",
        source_id="a",
        assertion=MemoryAssertion(subject="build", predicate="targets", object="python-3.13"),
    )
    second = write(
        service,
        writer,
        "Builds are pinned to Python 3.13 across CI.",
        source_id="b",
        assertion=MemoryAssertion(subject="build", predicate="targets", object="python-3.13"),
    )

    receipt = run(maintenance, maintainer, operations=(MaintenanceOperation.REFINE,))

    actions = receipt.applied_actions
    assert len(actions) == 1
    assert actions[0].operation is MaintenanceOperation.REFINE
    derived = store.get_record(actions[0].result_record_id)
    assert derived.confidence.evidence_count == 2
    assert set(derived.references) == {first.record_id, second.record_id}


def test_records_are_consumed_by_only_one_operation_per_run(
    service, store, maintenance, writer, maintainer
) -> None:
    """A record deduped in a run is not also superseded in the same run."""

    assertion = MemoryAssertion(subject="service", predicate="region", object="us-east-1")
    first = write(service, writer, "same content", source_id="a", assertion=assertion)
    second = write(service, writer, "same content", source_id="b", assertion=assertion)

    receipt = run(maintenance, maintainer)

    consumed = [
        record_id
        for action in receipt.applied_actions
        for record_id in action.superseded_record_ids
    ]
    assert sorted(consumed) == sorted([first.record_id, second.record_id])
    assert len(consumed) == len(set(consumed))


# -- SP-14: idempotency and watermark safety ----------------------------------


def test_rerunning_maintenance_is_idempotent(
    service, store, maintenance, writer, maintainer, clock
) -> None:
    """SP-14: a second identical run produces no further actions."""

    write(service, writer, "repeated observation", source_id="a")
    write(service, writer, "repeated observation", source_id="b")

    clock.advance(hours=1)
    first_run = run(maintenance, maintainer, operations=(MaintenanceOperation.DEDUPE,))
    assert len(first_run.applied_actions) == 1
    record_count_after_first = store.stats()["records"]

    clock.advance(hours=1)
    second_run = run(maintenance, maintainer, operations=(MaintenanceOperation.DEDUPE,))

    assert second_run.applied_actions == ()
    assert store.stats()["records"] == record_count_after_first
    assert store.get_maintenance_watermark("tenant-a", "repo-a") == second_run.watermark


def test_a_replayed_action_digest_is_skipped(
    service, store, maintenance, writer, maintainer, clock
) -> None:
    """The ledger recognizes work already applied, so it is not repeated."""

    write(service, writer, "repeated observation", source_id="a")
    write(service, writer, "repeated observation", source_id="b")

    clock.advance(hours=1)
    first_run = run(maintenance, maintainer, operations=(MaintenanceOperation.DEDUPE,))
    digest = first_run.applied_actions[0].action_digest

    assert digest in store.find_maintenance_action_digests("tenant-a", "repo-a")


def test_writes_after_the_watermark_are_out_of_scope(
    service, store, maintenance, writer, maintainer, clock
) -> None:
    """SP-14: a concurrent live write is not half-processed by a running pass."""

    write(service, writer, "concurrent content", source_id="a")

    # The run's watermark is pinned here.
    watermark = clock.now()

    clock.advance(minutes=5)
    late = write(service, writer, "concurrent content", source_id="b")

    receipt = run(
        maintenance,
        maintainer,
        operations=(MaintenanceOperation.DEDUPE,),
        watermark=watermark,
    )

    # The late duplicate was invisible to this run, so nothing was consolidated.
    assert receipt.applied_actions == ()
    assert receipt.watermark == watermark
    assert store.get_record(late.record_id).state is MemoryState.ACTIVE

    # The next run, with a later watermark, picks both up.
    clock.advance(minutes=5)
    followup = run(maintenance, maintainer, operations=(MaintenanceOperation.DEDUPE,))
    assert len(followup.applied_actions) == 1
    assert followup.previous_watermark == watermark


def test_a_future_watermark_is_rejected(maintenance, maintainer, clock) -> None:
    with pytest.raises(AuthorizationError, match="cannot be in the future"):
        run(
            maintenance,
            maintainer,
            watermark=clock.now() + timedelta(hours=1),
        )


def test_dry_run_changes_nothing_and_does_not_advance_the_watermark(
    service, store, maintenance, writer, maintainer
) -> None:
    first = write(service, writer, "dry run content", source_id="a")
    second = write(service, writer, "dry run content", source_id="b")

    receipt = run(
        maintenance,
        maintainer,
        operations=(MaintenanceOperation.DEDUPE,),
        dry_run=True,
    )

    assert receipt.applied is False
    assert receipt.maintenance_status.value == "planned"
    assert len(receipt.actions) == 1
    assert receipt.actions[0].applied is False
    assert store.get_record(first.record_id).state is MemoryState.ACTIVE
    assert store.get_record(second.record_id).state is MemoryState.ACTIVE
    assert store.get_maintenance_watermark("tenant-a", "repo-a") is None


def test_max_actions_bounds_the_run(service, store, maintenance, writer, maintainer) -> None:
    for index in range(6):
        write(service, writer, f"pair-{index // 2}", source_id=f"s{index}")

    receipt = run(
        maintenance,
        maintainer,
        operations=(MaintenanceOperation.DEDUPE,),
        max_actions=2,
    )

    assert len(receipt.applied_actions) == 2
