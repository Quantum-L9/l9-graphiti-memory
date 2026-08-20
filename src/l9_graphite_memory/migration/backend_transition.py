# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/migration/backend_transition.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Detect a canonical-store backend transition that would silently lose sight
of existing memory.

Selecting a different `store_backend` points the control plane at a different
canonical store. Nothing is destroyed -- the prior store keeps its records --
but the running system has no knowledge of them, and a freshly initialized
store reports itself healthy with zero records. An operator who switches
backends expecting their memory to follow gets a green health check and an
empty namespace.

Cross-backend data migration is deliberately out of scope (ADR-072); it needs
its own evidence and rollback contract. What is in scope is refusing to start
quietly in that state (ADR-077).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

ACKNOWLEDGEMENT_SETTING = "acknowledge_backend_transition"
ACKNOWLEDGEMENT_ENV = "L9_MEMORY_ACKNOWLEDGE_BACKEND_TRANSITION"


class PriorLedger(BaseModel):
    """A canonical store this deployment previously wrote to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backend: str
    location: str
    record_count: int = Field(ge=0)


class BackendTransitionReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    configured_backend: str
    configured_is_empty: bool
    prior_ledgers: tuple[PriorLedger, ...] = ()
    acknowledged: bool = False

    @property
    def transition_detected(self) -> bool:
        """True when the configured store is empty and another holds records."""

        return self.configured_is_empty and bool(self.prior_ledgers)

    @property
    def blocking(self) -> bool:
        return self.transition_detected and not self.acknowledged

    def describe(self) -> str:
        lines = [
            (
                f"canonical store backend {self.configured_backend!r} is empty, "
                "but this deployment has a prior canonical ledger that still "
                "holds records:"
            ),
        ]
        for ledger in self.prior_ledgers:
            lines.append(
                f"  - {ledger.backend} at {ledger.location} "
                f"({ledger.record_count} records)"
            )
        lines.extend(
            [
                "",
                "Nothing has been lost: those records are still in the prior store.",
                "This process simply cannot see them, and would report healthy while",
                "serving an empty namespace.",
                "",
                "Moving canonical data between backends is a separate, evidence-bound",
                "operation and is not performed automatically (ADR-072).",
                "",
                "If this is a deliberate fresh start on a new backend, acknowledge it:",
                f"  export {ACKNOWLEDGEMENT_ENV}=1",
            ]
        )
        return "\n".join(lines)


def _sqlite_record_count(path: Path) -> int | None:
    """Records in a SQLite ledger, or None if it is not one."""

    if not path.is_file() or path.stat().st_size == 0:
        return None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_records'"
        ).fetchone()
        if row is None:
            return None
        count = connection.execute("SELECT COUNT(*) FROM memory_records").fetchone()
        return int(count[0]) if count else 0
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def candidate_sqlite_ledgers(settings: object) -> tuple[Path, ...]:
    """SQLite ledgers this deployment may previously have written to."""

    data_dir = getattr(settings, "data_dir", None)
    candidates: list[Path] = []
    if isinstance(data_dir, Path) and data_dir.is_dir():
        candidates.extend(sorted(data_dir.glob("*.sqlite3")))
    resolved = getattr(settings, "resolved_database_path", None)
    if isinstance(resolved, Path) and resolved not in candidates:
        candidates.append(resolved)
    return tuple(dict.fromkeys(candidates))


def detect_backend_transition(settings: object, store: object) -> BackendTransitionReport:
    """Report whether the configured store is empty while a prior one is not.

    Only a local SQLite ledger can be discovered without credentials, so a
    postgres-to-postgres or postgres-to-sqlite move is not detectable here. The
    common and dangerous direction -- adopting the shared backend while a local
    ledger still holds the deployment's memory -- is.
    """

    backend = str(getattr(settings, "store_backend", getattr(store, "name", "unknown")))
    acknowledged = bool(getattr(settings, ACKNOWLEDGEMENT_SETTING, False))

    try:
        configured_count = int(store.stats().get("records", 0))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - a store that cannot report is not a transition
        return BackendTransitionReport(
            configured_backend=backend,
            configured_is_empty=False,
            acknowledged=acknowledged,
        )

    if configured_count > 0:
        return BackendTransitionReport(
            configured_backend=backend,
            configured_is_empty=False,
            acknowledged=acknowledged,
        )

    active_path = getattr(store, "path", None)
    prior: list[PriorLedger] = []
    for path in candidate_sqlite_ledgers(settings):
        if active_path is not None and Path(path) == Path(active_path):
            # This is the configured store, not a prior one.
            continue
        count = _sqlite_record_count(path)
        if count:
            prior.append(
                PriorLedger(backend="sqlite", location=str(path), record_count=count)
            )

    return BackendTransitionReport(
        configured_backend=backend,
        configured_is_empty=True,
        prior_ledgers=tuple(prior),
        acknowledged=acknowledged,
    )
