# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/test_phase_lock_snapshot_scale.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""The service and every store digest the same namespace snapshot at any size.

Finding F-06 (2026-09-04 audit): ``MemoryService.conflicts`` listed active
records with the store's default bound of 1,000, while every adapter re-verified
the phase-lock precondition over the complete active set. Past that bound the
two digests could never agree, so every governed write in a large namespace was
refused as a snapshot conflict. Parameterized over the store backends, as
ADR-079 requires.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import NullProjection
from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemoryWriteRequest,
    PhaseLockRequest,
    Provenance,
)
from l9_graphite_memory.services import MemoryService
from tests.conftest import STORE_BACKENDS, make_store

NAMESPACE = "repo-a"
# One past the historical listing bound.
RECORD_COUNT = 1_001


def _request(content: str) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        namespace=NAMESPACE,
        memory_class=MemoryClass.OBSERVATION,
        content=content,
        provenance=Provenance(source="phase-lock-scale"),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="scale"),),
    )


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_governed_write_succeeds_beyond_the_historical_listing_bound(
    tmp_path: Path, principal: MemoryPrincipal, backend: str
) -> None:
    store = make_store(backend, tmp_path)
    service = MemoryService(store, NullProjection())
    service.initialize()
    try:
        for index in range(RECORD_COUNT):
            service.write(principal, _request(f"record {index}"))
        assert len(store.list_records(principal.tenant_id, NAMESPACE, limit=None)) == RECORD_COUNT
        assert len(store.list_records(principal.tenant_id, NAMESPACE)) == 1_000

        lock = service.phase_lock(
            principal, PhaseLockRequest(namespace=NAMESPACE, task_signature="scale-signature")
        )
        assert lock.granted
        assert lock.conflict_report.checked_record_count == RECORD_COUNT

        receipt = service.write_governed(
            principal, _request("governed at scale"), task_signature="scale-signature"
        )
        assert service.get(principal, receipt.record_id).content == "governed at scale"
    finally:
        store.close()
