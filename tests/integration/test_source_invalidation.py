# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_source_invalidation.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""ADR-086: structured source invalidation archives current records atomically.

Every case runs against the in-memory, SQLite, and PostgreSQL canonical stores.
The path under test is the locked one: GeneratedDataService (adapter) ->
MemoryService.invalidate_by_source -> RecordStore.commit_source_invalidation ->
lifecycle status events + the existing outbox -> target-aware retirement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    DeletionRequest,
    HydrationRequest,
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryState,
    OutboxStatus,
    RetirementMode,
)
from l9_graphite_memory.contracts.generated_data import SourceInvalidationStatus
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.generated_data import GeneratedDataService
from l9_graphite_memory.services.outbox_worker import OutboxWorker
from tests.conftest import STORE_BACKENDS, make_store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "deployment" / "generated-data" / "fixtures"
REPOSITORY = "Quantum-L9/l9-graphiti-memory"
SERVICES_PATH = "src/l9_graphite_memory/services"


class RecordingProjection:
    name = "recording"
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
        return {"retired": True, "erased": False}

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
def projection() -> RecordingProjection:
    return RecordingProjection()


@pytest.fixture
def service(store, projection) -> MemoryService:
    service = MemoryService(store, projection)
    service.initialize()
    return service


@pytest.fixture
def generated(service) -> GeneratedDataService:
    return GeneratedDataService(service)


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="generated-data",
        tenant_id="tenant-a",
        read_namespaces=("repo-a", "repo-b"),
        write_namespaces=("repo-a", "repo-b"),
        maintain_namespaces=("repo-a", "repo-b"),
    )


def _candidate(
    candidate_id: str,
    *,
    namespace: str = "repo-a",
    conditions: list[Any] | None = None,
    statement: str | None = None,
    supersedes: list[str] | None = None,
) -> dict[str, Any]:
    payload = json.loads((FIXTURES / "governed-candidate.json").read_text(encoding="utf-8"))
    payload["candidate_id"] = candidate_id
    payload["source"]["visibility"] = "namespace_local"
    payload["source"]["namespace"] = namespace
    payload["knowledge"]["statement"] = statement or f"generated fact {candidate_id}"
    if conditions is not None:
        payload["knowledge"]["invalidation_conditions"] = conditions
    if supersedes is not None:
        payload["supersedes"] = supersedes
    return payload


def _ingest(generated, principal, candidate_id: str, **kwargs) -> UUID:
    result = generated.ingest_governed_candidate(principal, _candidate(candidate_id, **kwargs))
    assert result.status.value == "admitted", result
    assert result.record_id is not None
    return result.record_id


def _request(event_id: str = "invalidation-001", **overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "event_id": event_id,
        "event_type": "repository_path_changed",
        "repository": REPOSITORY,
        "from_sha": "1111111111111111111111111111111111111111",
        "to_sha": "2222222222222222222222222222222222222222",
        "selectors": [{"selector_type": "relevant_path_changed", "selector_value": SERVICES_PATH}],
        "delete_memory": False,
    }
    request.update(overrides)
    return request


def _states(store, *record_ids: UUID) -> list[MemoryState]:
    return [store.get_record(record_id).state for record_id in record_ids]


def _status_events(store, record_id: UUID) -> list[tuple[str | None, str]]:
    if hasattr(store, "status_events"):
        return [
            (event.previous_state.value if event.previous_state else None, event.new_state.value)
            for event in store.status_events
            if event.record_id == record_id
        ]
    if store.name == "sqlite":
        rows = (
            store._connection()
            .execute(
                "SELECT previous_state, new_state FROM memory_status_events "
                "WHERE record_id = ? ORDER BY occurred_at, rowid",
                (str(record_id),),
            )
            .fetchall()
        )
        return [(row["previous_state"], row["new_state"]) for row in rows]
    with store._cursor() as cursor:
        cursor.execute(
            "SELECT previous_state, new_state FROM memory_status_events "
            "WHERE record_id = %s ORDER BY occurred_at",
            (str(record_id),),
        )
        return [(row["previous_state"], row["new_state"]) for row in cursor.fetchall()]


def _retire_events(store, record_id: UUID) -> list[OutboxStatus]:
    if hasattr(store, "outbox"):
        return [
            event.status
            for event in store.outbox.values()
            if event.aggregate_id == record_id and event.event_type == "memory.record.retire"
        ]
    if store.name == "sqlite":
        rows = (
            store._connection()
            .execute(
                "SELECT status FROM outbox_events WHERE aggregate_id = ? AND event_type = ?",
                (str(record_id), "memory.record.retire"),
            )
            .fetchall()
        )
        return [OutboxStatus(str(row["status"])) for row in rows]
    with store._cursor() as cursor:
        cursor.execute(
            "SELECT status FROM outbox_events WHERE aggregate_id = %s AND event_type = %s",
            (str(record_id), "memory.record.retire"),
        )
        return [OutboxStatus(str(row["status"])) for row in cursor.fetchall()]


def _search_ids(service, principal, *, include_archived: bool = False) -> set[UUID]:
    receipt = service.search(
        principal,
        MemorySearchRequest(
            query="generated fact",
            namespaces=("repo-a", "repo-b"),
            limit=50,
            include_archived=include_archived,
        ),
    )
    return {hit.record.record_id for hit in receipt.hits}


def _drain(worker) -> None:
    for _ in range(8):
        if worker.run_once()["claimed"] == 0:
            break


# -- selector persistence ------------------------------------------------------


def test_admission_persists_canonical_selectors(store, generated, maintainer) -> None:
    record_id = _ingest(generated, maintainer, "cand-persist")

    selectors = store.list_source_selectors(record_id)
    assert {(s.repository, s.selector_type, s.selector_value, s.active) for s in selectors} == {
        (REPOSITORY, "relevant_path_changed", SERVICES_PATH, True),
        (REPOSITORY, "architecture_owner_changed", "canonical_memory_write_boundary", True),
    }
    assert all(s.record_id == record_id and s.deactivated_at is None for s in selectors)


def test_unstructured_conditions_persist_no_selector(store, generated, maintainer) -> None:
    record_id = _ingest(
        generated,
        maintainer,
        "cand-unstructured",
        conditions=[
            {"condition_type": "relevant_path_changed", "selector": SERVICES_PATH},
            "rerun when the services directory looks different",
        ],
    )

    # All-or-nothing: one unmappable condition means no selector at all,
    # never a partial index that silently drops a condition.
    assert store.list_source_selectors(record_id) == []


# -- request forms --------------------------------------------------------------


def test_canonical_selectors_archive_matching_active_records(
    store, service, generated, maintainer
) -> None:
    first = _ingest(generated, maintainer, "cand-a", namespace="repo-a")
    second = _ingest(generated, maintainer, "cand-b", namespace="repo-b")
    untouched = _ingest(
        generated,
        maintainer,
        "cand-c",
        conditions=[{"condition_type": "relevant_path_changed", "selector": "docs"}],
    )

    receipt = generated.invalidate_by_source(maintainer, _request())

    assert receipt.status is SourceInvalidationStatus.APPLIED
    assert receipt.event_id == "invalidation-001"
    assert receipt.matched == 2 and receipt.transitioned == 2
    assert set(receipt.record_ids) == {first, second}
    assert receipt.deleted is False
    assert len(receipt.lifecycle_receipt_ids) == 2  # one per affected namespace
    assert len(receipt.revalidation_requirement_ids) == 2
    assert _states(store, first, second) == [MemoryState.ARCHIVED, MemoryState.ARCHIVED]
    assert _states(store, untouched) == [MemoryState.ACTIVE]
    for record_id in (first, second):
        assert _status_events(store, record_id)[-1] == ("active", "archived")
        selectors = store.list_source_selectors(record_id)
        assert selectors and all(not s.active and s.deactivated_at for s in selectors)
    assert all(selector.active for selector in store.list_source_selectors(untouched))


def test_legacy_singular_selector_still_works(store, generated, maintainer) -> None:
    record_id = _ingest(generated, maintainer, "cand-legacy")
    legacy = {
        "event_type": "repository_path_changed",
        "repository": REPOSITORY,
        "selector": {"condition_type": "relevant_path_changed", "selector": SERVICES_PATH},
    }

    receipt = generated.invalidate_by_source(maintainer, legacy)

    assert receipt.status is SourceInvalidationStatus.APPLIED
    assert receipt.matched == 1 and receipt.transitioned == 1
    assert receipt.record_ids == [record_id]
    # A legacy request without event_id gets a deterministic identity.
    assert receipt.event_id is not None
    assert receipt.event_id.startswith("legacy-invalidation-")
    replay = generated.invalidate_by_source(maintainer, legacy)
    assert replay == receipt
    assert _states(store, record_id) == [MemoryState.ARCHIVED]


def test_deployed_bridge_request_shape_is_accepted(store, generated, maintainer) -> None:
    record_id = _ingest(generated, maintainer, "cand-bridge")
    request = json.loads((FIXTURES / "path-invalidation.json").read_text(encoding="utf-8"))
    # Envelope fields RepositoryEventBridge.to_request() also sends.
    request["create_replacement_record"] = False
    request["metadata"] = {"producer": "Cursor-Governance"}

    receipt = generated.invalidate_by_source(maintainer, request)

    assert receipt.status is SourceInvalidationStatus.APPLIED
    assert receipt.record_ids == [record_id]
    assert receipt.event_id == request["event_id"]


def test_zero_match_applies_without_transition(store, generated, maintainer) -> None:
    record_id = _ingest(generated, maintainer, "cand-zero")
    receipt = generated.invalidate_by_source(
        maintainer,
        _request(selectors=[{"selector_type": "relevant_path_changed", "selector_value": "x"}]),
    )

    assert receipt.status is SourceInvalidationStatus.APPLIED
    assert receipt.matched == 0 and receipt.transitioned == 0 and receipt.record_ids == []
    assert _states(store, record_id) == [MemoryState.ACTIVE]


# -- retrieval, evidence, lineage, deletion ---------------------------------------


def test_ordinary_retrieval_excludes_and_history_retrieves(
    store, service, generated, maintainer
) -> None:
    record_id = _ingest(generated, maintainer, "cand-retrieval")
    assert record_id in _search_ids(service, maintainer)

    generated.invalidate_by_source(maintainer, _request())

    assert record_id not in _search_ids(service, maintainer)
    hydration = service.hydrate(
        maintainer,
        HydrationRequest(task="generated fact", namespaces=("repo-a",), max_records=50),
    )
    assert record_id not in {rid for section in hydration.sections for rid in section.record_ids}
    context = generated.hydrate_context(
        maintainer, {"namespace": "repo-a", "query": "generated fact"}
    )
    assert str(record_id) not in {item["record_id"] for item in context["records"]}

    assert record_id in _search_ids(service, maintainer, include_archived=True)
    historical = generated.search_context(
        maintainer,
        {"namespace": "repo-a", "query": "generated fact", "include_invalidated": True},
    )
    (item,) = [c for c in historical["candidates"] if c["record_id"] == str(record_id)]
    assert item["state"] == "archived" and item["invalidated"] is True


def test_evidence_and_lineage_survive_without_deletion(
    store, service, generated, maintainer
) -> None:
    prior = _ingest(generated, maintainer, "cand-prior", statement="generated fact v1")
    current = _ingest(
        generated,
        maintainer,
        "cand-current",
        statement="generated fact v2",
        supersedes=[str(prior)],
    )
    before = store.get_record(current)

    receipt = generated.invalidate_by_source(maintainer, _request())

    # Only the current record is invalidated; the superseded one is history.
    assert receipt.record_ids == [current]
    after = store.get_record(current)
    assert after.state is MemoryState.ARCHIVED
    assert after.content == before.content
    assert after.evidence == before.evidence
    assert after.provenance == before.provenance
    assert after.metadata == before.metadata
    assert after.supersedes == (prior,)
    assert store.get_record(prior).state is MemoryState.SUPERSEDED
    lineage = service.lineage(maintainer, "repo-a", current)
    assert lineage.complete and prior in lineage.ordered_record_ids
    for record_id in (prior, current):
        assert store.get_record(record_id).state not in {
            MemoryState.DELETED,
            MemoryState.DELETION_PENDING,
        }


def test_revalidation_requirement_is_durable(store, generated, maintainer) -> None:
    record_id = _ingest(generated, maintainer, "cand-reval")
    receipt = generated.invalidate_by_source(maintainer, _request())

    (requirement,) = store.list_revalidation_requirements(record_id)
    assert requirement.requirement_id in receipt.revalidation_requirement_ids
    assert requirement.invalidation_event_id == "invalidation-001"
    assert requirement.namespace == "repo-a" and requirement.status == "open"
    stored = store.get_source_invalidation("tenant-a", "invalidation-001")
    assert stored is not None and stored.record_ids == (record_id,)

    if store.name == "sqlite":
        reopened = type(store)(store.path)
        reopened.initialize()
        try:
            assert reopened.list_revalidation_requirements(record_id) == [requirement]
            assert reopened.get_source_invalidation("tenant-a", "invalidation-001") == stored
        finally:
            reopened.close()


def test_projection_retirement_flows_through_existing_outbox(
    store, service, generated, maintainer, projection
) -> None:
    worker = OutboxWorker(
        store, projection, MemorySettings(outbox_max_attempts=3), worker_id="test-worker"
    )
    record_id = _ingest(generated, maintainer, "cand-projected")
    _drain(worker)
    assert projection.projected == [record_id]
    assert store.list_projection_links(record_id)

    generated.invalidate_by_source(maintainer, _request())

    assert _retire_events(store, record_id) == [OutboxStatus.PENDING]
    _drain(worker)
    assert projection.retired == [record_id]
    assert _retire_events(store, record_id) == [OutboxStatus.DELIVERED]
    assert store.list_projection_links(record_id) == []
    assert projection.erased == []


def test_privacy_deletion_removes_derived_selectors(store, service, generated, maintainer) -> None:
    admin = maintainer.model_copy(update={"is_admin": True})
    record_id = _ingest(generated, maintainer, "cand-delete")
    assert store.list_source_selectors(record_id)

    service.delete(
        admin,
        DeletionRequest(
            record_id=record_id, reason="privacy request", verification_reference="ticket-086"
        ),
    )

    assert store.list_source_selectors(record_id) == []


# -- idempotency and conflicts -------------------------------------------------------


def test_same_event_is_idempotent(store, generated, maintainer) -> None:
    record_id = _ingest(generated, maintainer, "cand-idem")
    first = generated.invalidate_by_source(maintainer, _request())
    events_after_first = _status_events(store, record_id)
    retire_after_first = _retire_events(store, record_id)

    second = generated.invalidate_by_source(maintainer, _request())

    assert second == first
    assert _status_events(store, record_id) == events_after_first
    assert _retire_events(store, record_id) == retire_after_first
    assert len(store.list_revalidation_requirements(record_id)) == 1


def test_same_event_with_changed_body_conflicts(store, generated, maintainer) -> None:
    record_id = _ingest(generated, maintainer, "cand-conflict")
    other = _ingest(
        generated,
        maintainer,
        "cand-conflict-other",
        conditions=[{"condition_type": "relevant_path_changed", "selector": "docs"}],
    )
    generated.invalidate_by_source(maintainer, _request())

    changed = generated.invalidate_by_source(
        maintainer,
        _request(selectors=[{"selector_type": "relevant_path_changed", "selector_value": "docs"}]),
    )

    assert changed.status is SourceInvalidationStatus.REJECTED
    assert "different request body" in (changed.reason or "")
    assert changed.transitioned == 0
    assert _states(store, record_id, other) == [MemoryState.ARCHIVED, MemoryState.ACTIVE]


# -- authorization and atomicity -------------------------------------------------------


def test_authorization_failure_causes_zero_lifecycle_mutation(store, generated, maintainer) -> None:
    first = _ingest(generated, maintainer, "cand-auth-a", namespace="repo-a")
    second = _ingest(generated, maintainer, "cand-auth-b", namespace="repo-b")
    partial = maintainer.model_copy(update={"maintain_namespaces": ("repo-a",)})
    events_before = [_status_events(store, first), _status_events(store, second)]

    receipt = generated.invalidate_by_source(partial, _request())

    assert receipt.status is SourceInvalidationStatus.REJECTED
    assert "repo-b" in (receipt.reason or "")
    assert receipt.matched == 2 and receipt.transitioned == 0 and receipt.record_ids == []
    # Not even the namespace the principal could archive was touched.
    assert _states(store, first, second) == [MemoryState.ACTIVE, MemoryState.ACTIVE]
    assert [_status_events(store, first), _status_events(store, second)] == events_before
    assert store.get_source_invalidation("tenant-a", "invalidation-001") is None
    assert store.list_revalidation_requirements(first) == []
    assert all(selector.active for selector in store.list_source_selectors(first))

    # The rejection is not durable: the same operation applies once authorized.
    applied = generated.invalidate_by_source(maintainer, _request())
    assert applied.status is SourceInvalidationStatus.APPLIED and applied.transitioned == 2


def test_multiple_matches_invalidate_atomically(
    store, service, generated, maintainer, monkeypatch
) -> None:
    first = _ingest(generated, maintainer, "cand-atomic-a", namespace="repo-a")
    second = _ingest(generated, maintainer, "cand-atomic-b", namespace="repo-b")
    real_commit = store.commit_source_invalidation

    def commit_after_concurrent_change(*args: Any, **kwargs: Any) -> None:
        # Another governed path archives one matched record between
        # resolution and commit: that transition's expected previous state no
        # longer holds, so the whole operation must fail with nothing applied.
        service.transition_lifecycle(
            maintainer,
            "repo-b",
            record_ids=(second,),
            new_state=MemoryState.ARCHIVED,
            reason="concurrent maintenance",
        )
        real_commit(*args, **kwargs)

    monkeypatch.setattr(store, "commit_source_invalidation", commit_after_concurrent_change)
    receipt = generated.invalidate_by_source(maintainer, _request())

    assert receipt.status is SourceInvalidationStatus.REJECTED
    assert receipt.transitioned == 0 and receipt.record_ids == []
    assert _states(store, first) == [MemoryState.ACTIVE]
    assert _status_events(store, first) == [(None, "active")]
    assert store.get_source_invalidation("tenant-a", "invalidation-001") is None
    assert store.list_revalidation_requirements(first) == []
    assert _retire_events(store, first) == []
    assert all(selector.active for selector in store.list_source_selectors(first))
