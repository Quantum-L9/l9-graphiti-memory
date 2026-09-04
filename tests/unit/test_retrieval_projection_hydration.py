# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_retrieval_projection_hydration.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""Projection hits outside the canonical recency window are hydrated, not lost.

Finding F-12 (2026-09-04 audit): graph and semantic strategies could only
re-score records the store's most-recent window already returned, so the
strategy that exists to find an older relevant record could never surface one.
The projection contributes identity; the record served is always canonical and
passes the same filters the store applied.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from l9_graphite_memory.adapters import InMemoryRecordStore
from l9_graphite_memory.contracts import (
    MemoryClass,
    MemorySearchRequest,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
    RetirementMode,
)
from l9_graphite_memory.ports import ProjectionHit
from l9_graphite_memory.services import MemoryService


class PinnedProjection:
    """Returns one graph hit for a chosen record, regardless of the query."""

    name = "pinned"
    capabilities: tuple[str, ...] = ("graph-search",)
    retirement_mode = RetirementMode.WITHDRAW

    def __init__(self) -> None:
        self.record_id: UUID | None = None

    def health(self):
        return {"healthy": True}

    def project(self, record):
        return {"locator": str(record.record_id)}

    def retire(self, record_id, namespace, *, locator=None, reason=""):
        return {"retired": True, "erased": False}

    def erase(self, record_id, namespace, *, locator=None):
        return {"erased": True}

    def search_strategy(self, strategy, query, namespaces, *, limit):
        if self.record_id is None:
            return []
        return [ProjectionHit(record_id=self.record_id, score=0.9, excerpt="graph")]

    def search(self, query, namespaces, *, limit):
        return self.search_strategy("graph-search", query, namespaces, limit=limit)


def _service():
    store = InMemoryRecordStore()
    projection = PinnedProjection()
    service = MemoryService(store, projection)
    service.initialize()
    return store, projection, service


def _write(service, principal, content, **kwargs):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a", content=content, provenance=Provenance(source="t"), **kwargs
        ),
    )


def test_projection_hit_outside_the_store_window_is_hydrated(principal, monkeypatch) -> None:
    store, projection, service = _service()
    old = _write(service, principal, "who is the owner of the billing service")
    projection.record_id = old.record_id
    # Simulate the recency window having moved past the record.
    monkeypatch.setattr(store, "search_records", lambda *args, **kwargs: [])

    receipt = service.search(
        principal, MemorySearchRequest(query="who is the owner", namespaces=("repo-a",))
    )

    assert [hit.record.record_id for hit in receipt.hits] == [old.record_id]
    assert receipt.hits[0].record.content == "who is the owner of the billing service"
    assert "projection" in receipt.hits[0].matched_by


def test_hydrated_hit_still_obeys_lifecycle_and_temporal_filters(principal, monkeypatch) -> None:
    store, projection, service = _service()
    old = _write(service, principal, "who is the owner of the billing service")
    _write(service, principal, "who is the new owner", supersedes=(old.record_id,))
    assert store.get_record(old.record_id).state is MemoryState.SUPERSEDED
    projection.record_id = old.record_id
    monkeypatch.setattr(store, "search_records", lambda *args, **kwargs: [])

    current = service.search(
        principal, MemorySearchRequest(query="who is the owner", namespaces=("repo-a",))
    )
    assert current.hits == ()

    historical = service.search(
        principal,
        MemorySearchRequest(
            query="who is the owner", namespaces=("repo-a",), include_superseded=True
        ),
    )
    assert [hit.record.record_id for hit in historical.hits] == [old.record_id]

    before_it_was_recorded = service.search(
        principal,
        MemorySearchRequest(
            query="who is the owner",
            namespaces=("repo-a",),
            include_superseded=True,
            recorded_before=datetime.now(timezone.utc) - timedelta(days=1),
        ),
    )
    assert before_it_was_recorded.hits == ()


def test_hydration_never_crosses_the_authorized_namespace(principal, monkeypatch) -> None:
    store, projection, service = _service()
    other = principal.model_copy(
        update={"read_namespaces": ("repo-b",), "write_namespaces": ("repo-b",)}
    )
    foreign = service.write(
        other,
        MemoryWriteRequest(
            namespace="repo-b",
            memory_class=MemoryClass.SEMANTIC,
            content="who is the owner of repo-b",
            provenance=Provenance(source="t"),
        ),
    )
    projection.record_id = foreign.record_id
    monkeypatch.setattr(store, "search_records", lambda *args, **kwargs: [])

    receipt = service.search(
        principal, MemorySearchRequest(query="who is the owner", namespaces=("repo-a",))
    )
    assert receipt.hits == ()
