# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/test_phase_lock_write_atomicity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-08-27

"""Governed writes must re-verify the phase lock inside the committing store.

``MemoryService.write_governed`` verifies a phase lock and then commits through
a separate call. Verifying up front is not enough on its own: a concurrent
writer sharing the store can change the namespace in between, so two governed
requests could both verify against the same snapshot and both admit records
(ADR-079).

These cases drive a competing canonical write into exactly that window. They
fail against an implementation that only checks before the transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

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
from l9_graphite_memory.errors import PhaseLockSnapshotConflict
from l9_graphite_memory.services import MemoryService
from tests.conftest import STORE_BACKENDS, make_store

NAMESPACE = "repo-a"


def _request(content: str) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        namespace=NAMESPACE,
        memory_class=MemoryClass.SEMANTIC,
        content=content,
        provenance=Provenance(source="phase-lock-atomicity"),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="test"),),
    )


class _RacingStore:
    """Delegate to a real store, firing one armed write before committing.

    The armed callback runs *before* the inner store opens its transaction, so
    it models a competitor that committed after this request verified its phase
    lock but before this request's write reached the store.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._armed: Callable[[], None] | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def arm(self, callback: Callable[[], None]) -> None:
        self._armed = callback

    def commit_write(self, *args: Any, **kwargs: Any) -> Any:
        armed, self._armed = self._armed, None
        if armed is not None:
            armed()
        return self._inner.commit_write(*args, **kwargs)


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_governed_write_refuses_a_snapshot_that_moved_before_commit(
    tmp_path: Path,
    principal: MemoryPrincipal,
    backend: str,
) -> None:
    inner = make_store(backend, tmp_path)
    racing = _RacingStore(inner)
    service = MemoryService(racing, NullProjection())
    service.initialize()
    try:
        competitor = MemoryService(inner, NullProjection())
        lock = service.phase_lock(
            principal, PhaseLockRequest(namespace=NAMESPACE, task_signature="task-signature-1")
        )
        assert lock.granted

        # Land a competing canonical write in the check-to-commit window.
        racing.arm(lambda: competitor.write(principal, _request("competing write")))

        # Built outside the block so the raise is provably the governed write's,
        # not the request construction's.
        governed = _request("governed write")
        with pytest.raises(PhaseLockSnapshotConflict):
            service.write_governed(principal, governed, task_signature="task-signature-1")

        # The refused write left nothing behind; only the competitor landed.
        remaining = inner.list_records(principal.tenant_id, NAMESPACE)
        assert [item.content for item in remaining] == ["competing write"]
    finally:
        inner.close()


@pytest.mark.parametrize("backend", STORE_BACKENDS)
def test_governed_write_commits_when_the_namespace_is_unchanged(
    tmp_path: Path,
    principal: MemoryPrincipal,
    backend: str,
) -> None:
    store = make_store(backend, tmp_path)
    service = MemoryService(store, NullProjection())
    service.initialize()
    try:
        lock = service.phase_lock(
            principal, PhaseLockRequest(namespace=NAMESPACE, task_signature="task-signature-1")
        )
        assert lock.granted
        receipt = service.write_governed(
            principal, _request("governed write"), task_signature="task-signature-1"
        )
        assert service.get(principal, receipt.record_id).content == "governed write"
    finally:
        store.close()
