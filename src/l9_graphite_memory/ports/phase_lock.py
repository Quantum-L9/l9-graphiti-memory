# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/phase_lock.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-08-27

"""Phase-lock write preconditions shared by the service and every record store.

``MemoryService.write_governed`` verifies a phase lock and then commits. Those
two steps are sound only when the store re-checks the namespace snapshot inside
the same transaction that admits the record (ADR-079). Verifying in the service
and committing in the store leaves a time-of-check/time-of-use window in which a
concurrent writer -- another governed request, another server process, or a
canonical write from an unrelated path -- can change the namespace after the
lock was judged current.

``snapshot_digest`` lives here rather than on the service so that all three
adapters compute the identical value without importing a service. This module
depends only on ``contracts`` and on the dependency-free normalization helpers,
so it introduces no layering cycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.contracts import MemoryRecord


def snapshot_digest(records: Sequence[MemoryRecord]) -> str:
    """Digest a namespace's records, stable under store iteration order.

    Sorting by ``record_id`` keeps the value independent of the order a given
    backend happens to return rows in, so the service and every adapter agree.
    """

    return sha256_text(
        canonical_json(
            [
                {
                    "record_id": str(record.record_id),
                    "digest": record.normalized_digest,
                    "state": record.state.value,
                    "valid_from": record.temporal.valid_from,
                    "valid_to": record.temporal.valid_to,
                    "recorded_at": record.temporal.recorded_at,
                }
                for record in sorted(records, key=lambda item: str(item.record_id))
            ]
        )
    )


@dataclass(frozen=True)
class PhaseLockPrecondition:
    """The namespace snapshot a governed write was authorized against.

    A store that receives this must re-verify ``expected_snapshot_digest``
    against the namespace's live active records inside the transaction that
    commits the write, and raise ``PhaseLockSnapshotConflict`` when it no
    longer matches. This mirrors the ``expected_version`` precondition the
    active-memory ``put_context`` contract already uses.
    """

    tenant_id: str
    namespace: str
    expected_snapshot_digest: str
