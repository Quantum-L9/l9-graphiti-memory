# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_outbox.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from typing import Any

from l9_graphite_memory.adapters import InMemoryRecordStore
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.ports import ProjectionHit
from l9_graphite_memory.services import MemoryService, OutboxWorker


class Projection:
    name = "test-projection"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.projected: list[str] = []

    def health(self) -> dict[str, Any]:
        return {"healthy": not self.fail}

    def project(self, record):
        if self.fail:
            raise RuntimeError("projection down")
        self.projected.append(str(record.record_id))
        return {"projected": True, "locator": f"episode-{record.record_id}"}

    def search(
        self, query: str, namespaces: tuple[str, ...], *, limit: int
    ) -> list[ProjectionHit]:
        if self.fail:
            raise RuntimeError("projection down")
        return []


def write_request() -> MemoryWriteRequest:
    return MemoryWriteRequest(
        namespace="repo-a",
        memory_class=MemoryClass.OBSERVATION,
        content="project me",
        provenance=Provenance(source="test"),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
    )


def test_outbox_delivers_after_canonical_commit(principal) -> None:
    store = InMemoryRecordStore()
    projection = Projection()
    service = MemoryService(store, projection)
    service.initialize()
    receipt = service.write(principal, write_request())
    assert receipt.outbox_event_ids
    result = OutboxWorker(store, projection, MemorySettings()).run_once()
    assert result["delivered"] == 1
    assert projection.projected == [str(receipt.record_id)]


def test_projection_failure_retries_without_losing_record(principal) -> None:
    store = InMemoryRecordStore()
    projection = Projection(fail=True)
    service = MemoryService(store, projection)
    service.initialize()
    receipt = service.write(principal, write_request())
    result = OutboxWorker(
        store, projection, MemorySettings(outbox_max_attempts=2)
    ).run_once()
    assert result["retried"] == 1
    assert store.get_record(receipt.record_id) is not None
