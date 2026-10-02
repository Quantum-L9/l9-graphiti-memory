# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_projection_targets.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-10-01
"""ADR-084: one record, many provider targets, each with its own lifecycle.

Graphiti is the active target and Zep the shadow target of ``facts-v8``. Each
target receives its own outbox intent, holds its own link, fails and retries
on its own, and is erased on its own. A deletion completes only once every
durable copy is gone.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import yaml

from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    DeletionRequest,
    DeletionStatus,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryState,
    MemoryWriteRequest,
    OperationStatus,
    Provenance,
    RetirementMode,
)
from l9_graphite_memory.errors import ProjectionError, StoreError
from l9_graphite_memory.ports import ProjectionHit
from l9_graphite_memory.projections import (
    ProjectionRuntime,
    compile_projection,
    parse_projection_manifest_data,
)
from l9_graphite_memory.retrieval import RetrievalPlanner
from l9_graphite_memory.services import MemoryService, OutboxWorker
from tests.conftest import STORE_BACKENDS, make_store

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config" / "projections" / "facts-v8.yaml"
GRAPHITI = "facts:v8:graphiti_mcp:primary"
ZEP = "facts:v8:zep:primary"


class FakeProvider:
    """One provider dialect with switchable failures."""

    capabilities: tuple[str, ...] = ("graph-search", "semantic-search")
    retirement_mode = RetirementMode.WITHDRAW

    def __init__(self, name: str) -> None:
        self.name = name
        self.fail_project = False
        self.fail_erase = False
        self.fail_search = False
        self.projected: list[UUID] = []
        self.retired: list[UUID] = []
        self.erased: list[UUID] = []
        self.search_hits: list[UUID] = []

    def health(self) -> dict[str, Any]:
        return {"name": self.name, "healthy": True}

    def project(self, record) -> dict[str, Any]:
        self.projected.append(record.record_id)
        if self.fail_project:
            raise ProjectionError(f"{self.name} unavailable")
        return {"locator": f"{self.name}-{record.record_id}"}

    def retire(self, record_id, namespace, *, locator=None, reason="") -> dict[str, Any]:
        self.retired.append(record_id)
        return {"retired": True, "erased": False, "locator": locator}

    def erase(self, record_id, namespace, *, locator=None) -> dict[str, Any]:
        if self.fail_erase:
            raise ProjectionError(f"{self.name} erase unavailable")
        assert locator == f"{self.name}-{record_id}"
        self.erased.append(record_id)
        return {"erased": True, "locator": locator}

    def search_strategy(self, strategy, query, namespaces, *, limit) -> list[ProjectionHit]:
        if self.fail_search:
            raise ProjectionError(f"{self.name} search unavailable")
        return [ProjectionHit(record_id=item, score=0.9) for item in self.search_hits]

    def search(self, query, namespaces, *, limit) -> list[ProjectionHit]:
        return self.search_strategy("graph-search", query, namespaces, limit=limit)


class Clock:
    def __init__(self) -> None:
        self.current = datetime.now(timezone.utc)

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def build_runtime(
    graphiti: FakeProvider | None,
    zep: FakeProvider | None,
    *,
    graphiti_mode: str = "active",
    zep_mode: str = "shadow",
) -> ProjectionRuntime:
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    data["spec"]["providers"][0]["mode"] = graphiti_mode
    data["spec"]["providers"][1]["mode"] = zep_mode
    compiled = compile_projection(parse_projection_manifest_data(data))
    return ProjectionRuntime.from_compiled(compiled, {GRAPHITI: graphiti, ZEP: zep})


class Harness:
    def __init__(self, store, runtime: ProjectionRuntime, clock: Clock, tmp_path: Path) -> None:
        self.store = store
        self.clock = clock
        self.tmp_path = tmp_path
        self.rebind(runtime)

    def rebind(self, runtime: ProjectionRuntime, **planner: Any) -> None:
        """Compose a new service and worker over the same canonical store."""

        self.runtime = runtime
        retrieval = RetrievalPlanner(self.store, runtime, **planner) if planner else None
        self.service = MemoryService(self.store, runtime, clock=self.clock, retrieval=retrieval)
        self.worker = OutboxWorker(
            self.store,
            runtime,
            MemorySettings(
                data_dir=self.tmp_path / "data",
                state_dir=self.tmp_path / "state",
                outbox_base_delay_seconds=1,
            ),
            clock=self.clock,
            worker_id="test",
        )

    def run(self) -> dict[str, int]:
        result = self.worker.run_once()
        # Every retry delay in these tests is under a minute.
        self.clock.advance(60)
        return result

    def links(self, record_id: UUID) -> dict[str, str]:
        return {
            link.target_identity: link.locator
            for link in self.store.list_projection_links(record_id)
        }


@pytest.fixture(params=STORE_BACKENDS)
def store(request, tmp_path):
    store = make_store(request.param, tmp_path)
    store.initialize()
    yield store
    store.close()


@pytest.fixture
def graphiti() -> FakeProvider:
    return FakeProvider("graphiti")


@pytest.fixture
def zep() -> FakeProvider:
    return FakeProvider("zep")


@pytest.fixture
def harness(store, graphiti, zep, tmp_path) -> Harness:
    return Harness(store, build_runtime(graphiti, zep), Clock(), tmp_path)


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="operator",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
        maintain_namespaces=("repo-a",),
    )


def _write(harness: Harness, principal, content: str, **kwargs: Any):
    return harness.service.write(
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


def _delete(harness: Harness, admin, record_id: UUID):
    return harness.service.delete(
        admin,
        DeletionRequest(
            record_id=record_id,
            reason="verified subject deletion",
            verification_reference="ticket-084",
        ),
    )


# -- T-03 multiple links ------------------------------------------------------


def test_one_record_holds_one_link_per_target(harness, principal) -> None:
    written = _write(harness, principal, "projected into two targets")
    assert len(written.outbox_event_ids) == 2

    assert harness.run()["delivered"] == 2

    assert harness.links(written.record_id) == {
        GRAPHITI: f"graphiti-{written.record_id}",
        ZEP: f"zep-{written.record_id}",
    }
    link = harness.store.get_projection_link(written.record_id, ZEP)
    assert link is not None
    assert (link.projection_name, link.projection_version, link.provider_type) == (
        "facts",
        8,
        "zep",
    )
    assert link.manifest_digest == harness.runtime.compiled.manifest_digest
    assert link.render_contract_digest == harness.runtime.compiled.render_contract_digest


# -- T-04 independent delivery ----------------------------------------------


def test_zep_failure_does_not_erase_graphiti_success(harness, principal, graphiti, zep) -> None:
    zep.fail_project = True
    written = _write(harness, principal, "zep is down")

    result = harness.run()

    assert (result["delivered"], result["retried"]) == (1, 1)
    assert set(harness.links(written.record_id)) == {GRAPHITI}
    assert harness.store.outbox_backlog() == 1

    zep.fail_project = False
    assert harness.run()["delivered"] == 1
    assert set(harness.links(written.record_id)) == {GRAPHITI, ZEP}
    # The healthy target was delivered once and never replayed.
    assert graphiti.projected == [written.record_id]


def test_graphiti_failure_does_not_settle_zep_falsely(harness, principal, graphiti, zep) -> None:
    graphiti.fail_project = True
    written = _write(harness, principal, "graphiti is down")

    result = harness.run()

    assert (result["delivered"], result["retried"]) == (1, 1)
    assert set(harness.links(written.record_id)) == {ZEP}
    assert harness.store.outbox_backlog() == 1


# -- T-05 target-specific retirement ----------------------------------------


def test_supersession_retires_every_persisted_target(harness, principal, graphiti, zep) -> None:
    original = _write(harness, principal, "original fact")
    harness.run()
    replacement = _write(harness, principal, "replacement fact", supersedes=(original.record_id,))

    harness.run()

    assert harness.links(original.record_id) == {}
    assert set(harness.links(replacement.record_id)) == {GRAPHITI, ZEP}
    assert graphiti.retired == [original.record_id]
    assert zep.retired == [original.record_id]
    if hasattr(harness.store, "projection_retirements"):
        evidence = {
            receipt.target_identity: receipt for receipt in harness.store.projection_retirements
        }
        assert set(evidence) == {GRAPHITI, ZEP}
        assert evidence[ZEP].provider_type == "zep"
        assert evidence[ZEP].locator == f"zep-{original.record_id}"
        assert all(not receipt.erasure for receipt in evidence.values())


# -- T-06 reactivation --------------------------------------------------------


def test_reactivation_restores_every_target(harness, principal, maintainer, admin_principal):
    written = _write(harness, principal, "archived then restored")
    harness.run()
    harness.service.transition_lifecycle(
        maintainer,
        "repo-a",
        record_ids=(written.record_id,),
        new_state=MemoryState.ARCHIVED,
        reason="archived",
    )
    harness.run()
    assert harness.links(written.record_id) == {}

    restored = harness.service.transition_lifecycle(
        admin_principal,
        "repo-a",
        record_ids=(written.record_id,),
        new_state=MemoryState.ACTIVE,
        reason="restored by governance",
    )
    assert len(restored.outbox_event_ids) == 2
    harness.run()

    assert set(harness.links(written.record_id)) == {GRAPHITI, ZEP}


# -- T-07 stale delayed event -------------------------------------------------


def test_delayed_project_retry_cannot_resurrect_an_inactive_record(
    harness, principal, maintainer, graphiti, zep
) -> None:
    zep.fail_project = True
    written = _write(harness, principal, "zep retry outlives the record")
    harness.run()
    assert set(harness.links(written.record_id)) == {GRAPHITI}

    harness.service.transition_lifecycle(
        maintainer,
        "repo-a",
        record_ids=(written.record_id,),
        new_state=MemoryState.ARCHIVED,
        reason="archived before zep recovered",
    )
    zep.fail_project = False
    harness.run()
    harness.run()

    assert harness.links(written.record_id) == {}
    # Zep was only ever attempted once, by the delivery that failed.
    assert zep.projected == [written.record_id]
    assert harness.store.outbox_backlog() == 0


# -- T-11 / T-12 / T-13 deletion --------------------------------------------


def test_deletion_completes_when_every_target_is_erased(
    harness, principal, admin_principal, graphiti, zep
) -> None:
    written = _write(harness, principal, "erase me everywhere")
    harness.run()

    receipt = _delete(harness, admin_principal, written.record_id)

    assert receipt.status is DeletionStatus.PENDING_PROJECTION
    assert set(receipt.projection_targets) == {GRAPHITI, ZEP}
    assert len(receipt.projection_event_ids) == 2
    assert receipt.projection_event_id == receipt.projection_event_ids[0]
    harness.run()
    assert graphiti.erased == [written.record_id] and zep.erased == [written.record_id]
    assert harness.links(written.record_id) == {}
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETED


def test_partial_erasure_keeps_the_deletion_pending_and_retryable(
    harness, principal, admin_principal, graphiti, zep
) -> None:
    written = _write(harness, principal, "zep cannot erase yet")
    harness.run()
    zep.fail_erase = True
    _delete(harness, admin_principal, written.record_id)

    result = harness.run()

    assert (result["delivered"], result["retried"]) == (1, 1)
    # Graphiti's link went only after its own verified erase; Zep's stays.
    assert harness.links(written.record_id) == {ZEP: f"zep-{written.record_id}"}
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETION_PENDING
    with pytest.raises(StoreError, match="remain unerased"):
        harness.store.complete_deletion(
            written.record_id,
            UUID(harness.store.get_record(written.record_id).metadata["deletion_receipt_id"]),
            completed_at=harness.clock.now(),
        )

    zep.fail_erase = False
    harness.run()
    assert harness.links(written.record_id) == {}
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETED


def test_disabled_target_with_a_link_is_still_erased(
    harness, principal, admin_principal, graphiti, zep
) -> None:
    written = _write(harness, principal, "zep disabled after projection")
    harness.run()
    harness.rebind(build_runtime(graphiti, zep, zep_mode="disabled"))
    assert harness.runtime.target(ZEP).delivers is False

    receipt = _delete(harness, admin_principal, written.record_id)
    harness.run()

    assert ZEP in receipt.projection_targets
    assert zep.erased == [written.record_id]
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETED


def test_unconfigured_disabled_target_blocks_completion_until_reconfigured(
    harness, principal, admin_principal, graphiti, zep
) -> None:
    written = _write(harness, principal, "zep removed from configuration")
    harness.run()
    harness.rebind(build_runtime(graphiti, None, zep_mode="disabled"))

    _delete(harness, admin_principal, written.record_id)
    harness.run()

    assert harness.links(written.record_id) == {ZEP: f"zep-{written.record_id}"}
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETION_PENDING

    harness.rebind(build_runtime(graphiti, zep, zep_mode="disabled"))
    harness.run()
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETED


def test_legacy_link_after_cutover_fails_closed_until_a_legacy_runtime_erases_it(
    harness, principal, admin_principal, graphiti, zep
) -> None:
    legacy = FakeProvider("graphiti")
    harness.rebind(ProjectionRuntime.legacy(legacy))
    written = _write(harness, principal, "projected before cutover")
    harness.run()
    assert harness.links(written.record_id) == {"graphiti": f"graphiti-{written.record_id}"}

    harness.rebind(build_runtime(graphiti, zep))
    receipt = _delete(harness, admin_principal, written.record_id)
    harness.run()
    harness.run()

    assert "graphiti" in receipt.projection_targets
    assert harness.links(written.record_id) == {"graphiti": f"graphiti-{written.record_id}"}
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETION_PENDING

    harness.rebind(ProjectionRuntime.legacy(legacy))
    harness.run()
    assert legacy.erased == [written.record_id]
    assert harness.store.get_record(written.record_id).state is MemoryState.DELETED


# -- T-15 rebuild targeting ---------------------------------------------------


def test_rebuild_restores_only_the_missing_target(
    harness, principal, maintainer, graphiti, zep
) -> None:
    written = _write(harness, principal, "zep copy lost")
    harness.run()
    graphiti_link = harness.store.get_projection_link(written.record_id, GRAPHITI)
    harness.store.delete_projection_link(written.record_id, ZEP)

    plan = harness.service.rebuild_projection(maintainer, "repo-a", apply=False)
    assert plan.target_identities == (GRAPHITI, ZEP)
    assert plan.queued_by_target == {GRAPHITI: (), ZEP: (written.record_id,)}

    applied = harness.service.rebuild_projection(maintainer, "repo-a", apply=True, target=ZEP)
    assert applied.target_identities == (ZEP,)
    assert len(applied.outbox_event_ids) == 1
    harness.run()

    assert set(harness.links(written.record_id)) == {GRAPHITI, ZEP}
    assert harness.store.get_projection_link(written.record_id, GRAPHITI) == graphiti_link
    assert graphiti.projected == [written.record_id]
    assert zep.projected == [written.record_id, written.record_id]


def test_rebuild_rejects_unknown_and_disabled_targets(harness, maintainer, graphiti, zep):
    with pytest.raises(ProjectionError, match="unknown projection target"):
        harness.service.rebuild_projection(
            maintainer, "repo-a", apply=False, target="facts:v8:zep:secondary"
        )
    harness.rebind(build_runtime(graphiti, zep, zep_mode="disabled"))
    with pytest.raises(StoreError, match="receives no deliveries"):
        harness.service.rebuild_projection(maintainer, "repo-a", apply=False, target=ZEP)


# -- T-08 / T-09 / T-10 retrieval ------------------------------------------


def _search(harness: Harness, principal):
    return harness.service.search(
        principal, MemorySearchRequest(query="who is the owner", namespaces=("repo-a",))
    )


@pytest.fixture
def retrieval(harness, principal, graphiti, zep, monkeypatch):
    graphiti_record = _write(harness, principal, "who is the owner of billing")
    zep_record = _write(harness, principal, "who is the owner of payments")
    graphiti.search_hits = [graphiti_record.record_id]
    zep.search_hits = [zep_record.record_id]
    # Only a projection hit can surface either record.
    monkeypatch.setattr(harness.store, "search_records", lambda *args, **kwargs: [])
    return graphiti_record.record_id, zep_record.record_id


def test_active_target_contributes_to_retrieval(harness, principal, retrieval) -> None:
    graphiti_id, _ = retrieval
    receipt = _search(harness, principal)

    assert [hit.record.record_id for hit in receipt.hits] == [graphiti_id]
    assert "projection" in receipt.hits[0].matched_by
    assert receipt.status is OperationStatus.COMPLETE
    assert f"{GRAPHITI}:graph-search" in receipt.stores_succeeded
    (evidence,) = receipt.projection_evidence
    assert (evidence.target_identity, evidence.mode, evidence.strategy) == (
        GRAPHITI,
        "active",
        "graph-search",
    )
    assert evidence.succeeded and evidence.hit_count == 1 and evidence.contributed == 1


def test_shadow_results_never_alter_returned_results(harness, principal, retrieval, zep) -> None:
    graphiti_id, _ = retrieval
    baseline = _search(harness, principal)

    harness.rebind(harness.runtime, shadow_measurement=True)
    measured = _search(harness, principal)
    zep.fail_search = True
    failing_shadow = _search(harness, principal)

    for receipt in (measured, failing_shadow):
        assert [hit.record.record_id for hit in receipt.hits] == [graphiti_id]
        assert [hit.score for hit in receipt.hits] == [hit.score for hit in baseline.hits]
        assert receipt.status is OperationStatus.COMPLETE
        assert receipt.stores_attempted == baseline.stores_attempted
        assert not any(label.startswith(ZEP) for label in receipt.stores_attempted)
    shadow = [item for item in measured.projection_evidence if item.target_identity == ZEP]
    assert [(item.mode, item.hit_count, item.contributed) for item in shadow] == [("shadow", 1, 0)]
    failed = [item for item in failing_shadow.projection_evidence if item.target_identity == ZEP]
    assert [(item.succeeded, item.contributed) for item in failed] == [(False, 0)]


def test_disabled_target_is_never_queried(harness, principal, retrieval, graphiti, zep) -> None:
    harness.rebind(build_runtime(graphiti, zep, zep_mode="disabled"), shadow_measurement=True)
    zep.fail_search = True

    receipt = _search(harness, principal)

    assert all(item.target_identity == GRAPHITI for item in receipt.projection_evidence)
    assert receipt.status is OperationStatus.COMPLETE


def test_active_provider_failure_is_a_failed_strategy_not_an_empty_success(
    harness, principal, retrieval, graphiti
) -> None:
    graphiti.fail_search = True

    receipt = _search(harness, principal)

    assert receipt.status is OperationStatus.PARTIAL
    assert f"{GRAPHITI}:graph-search" in receipt.stores_failed
    assert "graph-search" in receipt.strategies_failed
    assert "graph-search" not in receipt.strategies_succeeded
    (evidence,) = receipt.projection_evidence
    assert not evidence.succeeded and evidence.error and evidence.hit_count == 0
    # Canonical retrieval stays available.
    assert harness.store.name not in receipt.stores_failed
