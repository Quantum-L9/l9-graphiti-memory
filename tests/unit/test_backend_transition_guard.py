# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_backend_transition_guard.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""ADR-077: a backend transition fails closed instead of serving an empty store."""

from __future__ import annotations

from pathlib import Path

import pytest

from l9_graphite_memory.adapters import NullProjection, build_store
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryPrincipal,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.errors import ConfigurationError
from l9_graphite_memory.migration import detect_backend_transition
from l9_graphite_memory.migration.backend_transition import ACKNOWLEDGEMENT_ENV
from l9_graphite_memory.services import MemoryService


@pytest.fixture
def principal() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="operator",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
    )


def _seed_ledger(path: Path, principal: MemoryPrincipal, *, records: int = 1) -> None:
    settings = MemorySettings(
        store_backend="sqlite",
        data_dir=path.parent,
        database_path=path,
        # Seeding a second ledger beside a populated one is exactly the
        # condition the guard blocks, so the helper states the intent.
        acknowledge_backend_transition=True,
    )
    store = build_store(settings)
    service = MemoryService(store, NullProjection())
    service.initialize()
    for index in range(records):
        service.write(
            principal,
            MemoryWriteRequest(
                namespace="repo-a",
                content=f"prior memory {index}",
                provenance=Provenance(source="test"),
                evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
            ),
        )
    store.close()


def test_switching_to_an_empty_backend_fails_closed(tmp_path, principal) -> None:
    """The footgun: a green health check over an empty store."""

    _seed_ledger(tmp_path / "memory.sqlite3", principal)

    switched = MemorySettings(
        store_backend="sqlite",
        data_dir=tmp_path,
        database_path=tmp_path / "elsewhere.sqlite3",
    )

    with pytest.raises(ConfigurationError) as excinfo:
        build_store(switched)

    message = str(excinfo.value)
    assert "memory.sqlite3" in message
    assert "1 records" in message
    assert "Nothing has been lost" in message
    assert ACKNOWLEDGEMENT_ENV in message


def test_acknowledging_the_transition_allows_startup(tmp_path, principal) -> None:
    """A deliberate fresh start is permitted once it is stated."""

    _seed_ledger(tmp_path / "memory.sqlite3", principal)

    switched = MemorySettings(
        store_backend="sqlite",
        data_dir=tmp_path,
        database_path=tmp_path / "elsewhere.sqlite3",
        acknowledge_backend_transition=True,
    )

    store = build_store(switched)
    try:
        assert store.stats()["records"] == 0
    finally:
        store.close()


def test_reopening_the_same_ledger_is_not_a_transition(tmp_path, principal) -> None:
    """The configured store is not its own prior store."""

    ledger = tmp_path / "memory.sqlite3"
    _seed_ledger(ledger, principal)

    settings = MemorySettings(
        store_backend="sqlite", data_dir=tmp_path, database_path=ledger
    )
    store = build_store(settings)
    try:
        assert store.stats()["records"] == 1
    finally:
        store.close()


def test_a_populated_backend_is_never_treated_as_a_transition(
    tmp_path, principal
) -> None:
    """Ambiguity only exists while the configured store is empty."""

    _seed_ledger(tmp_path / "memory.sqlite3", principal)
    _seed_ledger(tmp_path / "second.sqlite3", principal, records=2)

    settings = MemorySettings(
        store_backend="sqlite",
        data_dir=tmp_path,
        database_path=tmp_path / "second.sqlite3",
    )
    store = build_store(settings)
    try:
        report = detect_backend_transition(settings, store)
        assert report.configured_is_empty is False
        assert report.transition_detected is False
        assert report.blocking is False
    finally:
        store.close()


def test_a_first_run_with_no_prior_ledger_starts_normally(tmp_path) -> None:
    settings = MemorySettings(
        store_backend="sqlite",
        data_dir=tmp_path,
        database_path=tmp_path / "fresh.sqlite3",
    )
    store = build_store(settings)
    try:
        report = detect_backend_transition(settings, store)
        assert report.configured_is_empty is True
        assert report.prior_ledgers == ()
        assert report.blocking is False
    finally:
        store.close()


def test_an_empty_prior_ledger_does_not_block(tmp_path) -> None:
    """A prior store with no records has nothing to lose sight of."""

    empty_prior = MemorySettings(
        store_backend="sqlite",
        data_dir=tmp_path,
        database_path=tmp_path / "memory.sqlite3",
    )
    build_store(empty_prior).close()

    switched = MemorySettings(
        store_backend="sqlite",
        data_dir=tmp_path,
        database_path=tmp_path / "elsewhere.sqlite3",
    )
    store = build_store(switched)
    store.close()


def test_a_non_ledger_sqlite_file_is_ignored(tmp_path, principal) -> None:
    """An unrelated SQLite file must not be mistaken for canonical memory."""

    import sqlite3

    unrelated = tmp_path / "unrelated.sqlite3"
    connection = sqlite3.connect(unrelated)
    connection.execute("CREATE TABLE notes (id INTEGER)")
    connection.execute("INSERT INTO notes VALUES (1)")
    connection.commit()
    connection.close()

    settings = MemorySettings(
        store_backend="sqlite",
        data_dir=tmp_path,
        database_path=tmp_path / "fresh.sqlite3",
    )
    store = build_store(settings)
    try:
        assert detect_backend_transition(settings, store).prior_ledgers == ()
    finally:
        store.close()


def test_the_shared_backend_is_guarded_too(tmp_path, principal, monkeypatch) -> None:
    """Adopting postgres while a local ledger holds memory is the real case."""

    _seed_ledger(tmp_path / "memory.sqlite3", principal, records=3)

    settings = MemorySettings(
        store_backend="postgres",
        postgres_dsn="postgresql:///unused",
        data_dir=tmp_path,
    )

    class EmptyStore:
        name = "postgres"

        def stats(self) -> dict[str, int]:
            return {"records": 0}

        def close(self) -> None:
            pass

    report = detect_backend_transition(settings, EmptyStore())

    assert report.configured_backend == "postgres"
    assert report.blocking is True
    assert report.prior_ledgers[0].record_count == 3
    assert "3 records" in report.describe()
