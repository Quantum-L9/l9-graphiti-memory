# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_source_selector_migration.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""ADR-086 store schema 9: selector tables, the 8 -> 9 backfill, restart safety.

Each migration case builds a store at the current schema, admits governed
candidates, then rewrites the store back to the exact schema-8 shape (no
schema-9 tables, no schema-9 marker). Reopening must recreate the tables and
backfill selectors from structured metadata only: identical to what admission
wrote, none for records whose metadata does not map losslessly.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from l9_graphite_memory.adapters import NullProjection, SQLiteRecordStore
from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryPrincipal,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.generated_data import GeneratedDataService
from tests.conftest import make_postgres_store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "deployment" / "generated-data" / "fixtures"
VERIFIER = ROOT / "deployment" / "generated-data" / "verify_selector_indexes.py"
SCHEMA_9_TABLES = (
    "memory_source_selectors",
    "source_invalidation_events",
    "revalidation_requirements",
)
SELECTOR_INDEXES = {
    "idx_selector_repository_value",
    "idx_selector_record_active",
    "idx_selector_type_value",
}


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id="generated-data",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
        maintain_namespaces=("repo-a",),
    )


def _candidate(candidate_id: str, conditions: list[Any] | None = None) -> dict[str, Any]:
    payload = json.loads((FIXTURES / "governed-candidate.json").read_text(encoding="utf-8"))
    payload["candidate_id"] = candidate_id
    payload["source"]["visibility"] = "namespace_local"
    payload["source"]["namespace"] = "repo-a"
    payload["knowledge"]["statement"] = f"generated fact {candidate_id}"
    if conditions is not None:
        payload["knowledge"]["invalidation_conditions"] = conditions
    return payload


def _populate(store, principal) -> dict[str, UUID]:
    service = MemoryService(store, NullProjection())
    generated = GeneratedDataService(service)

    def ingest(candidate_id: str, conditions: list[Any] | None = None) -> UUID:
        result = generated.ingest_governed_candidate(
            principal, _candidate(candidate_id, conditions)
        )
        assert result.record_id is not None
        return result.record_id

    records = {
        "active": ingest("cand-active"),
        "archived": ingest("cand-archived"),
        "unstructured": ingest("cand-prose", ["re-check when the services change"]),
    }
    service.transition_lifecycle(
        principal,
        "repo-a",
        record_ids=(records["archived"],),
        new_state=MemoryState.ARCHIVED,
        reason="retired before schema 9",
    )
    records["plain"] = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.OBSERVATION,
            content="src/l9_graphite_memory/services is mentioned only in prose",
            provenance=Provenance(source="test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
        ),
    ).record_id
    return records


def _selector_keys(store, record_id: UUID) -> list[tuple[str, str, str, str]]:
    return [
        (s.selector_id, s.repository, s.selector_type, s.selector_value)
        for s in store.list_source_selectors(record_id)
    ]


def _assert_backfilled(store, records: dict[str, UUID], admitted: dict[str, list]) -> None:
    assert _selector_keys(store, records["active"]) == admitted["active"]
    assert all(s.active for s in store.list_source_selectors(records["active"]))
    # The archived record keeps its lossless selectors, inactive.
    assert _selector_keys(store, records["archived"]) == admitted["archived"]
    assert not any(s.active for s in store.list_source_selectors(records["archived"]))
    assert store.list_source_selectors(records["unstructured"]) == []
    assert store.list_source_selectors(records["plain"]) == []


def _invalidate_after_migration(store, principal, record_id: UUID) -> None:
    receipt = GeneratedDataService(MemoryService(store, NullProjection())).invalidate_by_source(
        principal,
        {
            "event_id": "post-migration",
            "event_type": "repository_path_changed",
            "repository": "Quantum-L9/l9-graphiti-memory",
            "selectors": [
                {
                    "selector_type": "relevant_path_changed",
                    "selector_value": "src/l9_graphite_memory/services",
                }
            ],
        },
    )
    assert receipt.status.value == "applied"
    assert receipt.record_ids == [record_id]


# -- SQLite ----------------------------------------------------------------------------


def _sqlite_downgrade_to_schema_8(store: SQLiteRecordStore) -> None:
    with store._transaction() as tx:
        for table in SCHEMA_9_TABLES:
            tx.execute(f"DROP TABLE {table}")
        tx.execute("DELETE FROM schema_migrations WHERE version >= 9")
        if not tx.execute("SELECT 1 FROM schema_migrations WHERE version = 8").fetchone():
            tx.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (8, '2026-10-01')"
            )


def _sqlite_versions(store: SQLiteRecordStore) -> set[int]:
    return {row[0] for row in store._connection().execute("SELECT version FROM schema_migrations")}


def test_fresh_sqlite_store_is_schema_9_with_selector_indexes(tmp_path) -> None:
    database = tmp_path / "fresh.sqlite3"
    store = SQLiteRecordStore(database)
    store.initialize()
    try:
        assert _sqlite_versions(store) == {9}
        assert store.health()["schema_version"] == 9
        connection = store._connection()
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert set(SCHEMA_9_TABLES) <= tables
        indexes = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        assert SELECTOR_INDEXES <= indexes
        plan = " ".join(
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT record_id FROM memory_source_selectors "
                "WHERE repository = ? AND selector_type = ? AND selector_value = ? AND active = 1",
                ("r", "t", "v"),
            )
        )
        assert "idx_selector_repository_value" in plan
        plan_any_repo = " ".join(
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN SELECT record_id FROM memory_source_selectors "
                "WHERE selector_type = ? AND selector_value = ? AND active = 1",
                ("t", "v"),
            )
        )
        assert "idx_selector_type_value" in plan_any_repo
    finally:
        store.close()

    completed = subprocess.run(
        [sys.executable, str(VERIFIER), "--database", str(database)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
    assert json.loads(completed.stdout)["passed"] is True


def test_sqlite_schema_8_migrates_to_9_with_lossless_backfill(maintainer, tmp_path) -> None:
    database = tmp_path / "memory.sqlite3"
    store = SQLiteRecordStore(database)
    store.initialize()
    records = _populate(store, maintainer)
    admitted = {name: _selector_keys(store, records[name]) for name in ("active", "archived")}
    assert admitted["active"] and admitted["archived"]
    _sqlite_downgrade_to_schema_8(store)
    assert _sqlite_versions(store) == {8}
    store.close()

    for _restart in range(2):
        reopened = SQLiteRecordStore(database)
        reopened.initialize()
        assert 9 in _sqlite_versions(reopened)
        _assert_backfilled(reopened, records, admitted)
        reopened.close()

    migrated = SQLiteRecordStore(database)
    migrated.initialize()
    try:
        _invalidate_after_migration(migrated, maintainer, records["active"])
    finally:
        migrated.close()


def test_interrupted_sqlite_migration_restarts_cleanly(maintainer, tmp_path, monkeypatch) -> None:
    database = tmp_path / "memory.sqlite3"
    store = SQLiteRecordStore(database)
    store.initialize()
    records = _populate(store, maintainer)
    admitted = {name: _selector_keys(store, records[name]) for name in ("active", "archived")}
    _sqlite_downgrade_to_schema_8(store)
    store.close()

    calls = {"count": 0}
    real_insert = SQLiteRecordStore._insert_selector

    def crash_mid_backfill(tx, selector) -> None:
        calls["count"] += 1
        if calls["count"] > 1:
            raise RuntimeError("process killed during backfill")
        real_insert(tx, selector)

    monkeypatch.setattr(SQLiteRecordStore, "_insert_selector", staticmethod(crash_mid_backfill))
    interrupted = SQLiteRecordStore(database)
    with pytest.raises(RuntimeError, match="killed"):
        interrupted.initialize()
    interrupted.close()
    monkeypatch.undo()

    # The whole initialization rolled back: still exactly schema 8.
    probe = SQLiteRecordStore(database)
    connection = probe._connection()
    assert {row[0] for row in connection.execute("SELECT version FROM schema_migrations")} == {8}
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert not set(SCHEMA_9_TABLES) & tables
    probe.close()

    restarted = SQLiteRecordStore(database)
    restarted.initialize()
    try:
        assert 9 in _sqlite_versions(restarted)
        _assert_backfilled(restarted, records, admitted)
    finally:
        restarted.close()


# -- PostgreSQL ----------------------------------------------------------------------------


def _pg_downgrade_to_schema_8(store) -> None:
    with store._transaction() as tx:
        for table in SCHEMA_9_TABLES:
            tx.execute(f"DROP TABLE {table}")
        tx.execute("DELETE FROM schema_migrations WHERE version >= 9")
        tx.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (8, now()) "
            "ON CONFLICT (version) DO NOTHING"
        )


def _pg_versions(store) -> set[int]:
    with store._cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations")
        return {row["version"] for row in cursor.fetchall()}


def test_fresh_postgres_store_is_schema_9_with_selector_indexes() -> None:
    store = make_postgres_store()
    store.initialize()
    try:
        assert _pg_versions(store) == {9}
        assert store.health()["schema_version"] == 9
        with store._cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()"
            )
            assert set(SCHEMA_9_TABLES) <= {row["table_name"] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
                "AND tablename = 'memory_source_selectors'"
            )
            indexes = {row["indexname"]: row["indexdef"] for row in cursor.fetchall()}
        assert SELECTOR_INDEXES <= set(indexes)
        assert (
            "(repository, selector_type, selector_value, active)"
            in (indexes["idx_selector_repository_value"])
        )
    finally:
        store.close()


def test_postgres_schema_8_migrates_to_9_with_lossless_backfill(maintainer) -> None:
    store = make_postgres_store()
    schema = store.test_schema
    store.initialize()
    records = _populate(store, maintainer)
    admitted = {name: _selector_keys(store, records[name]) for name in ("active", "archived")}
    assert admitted["active"] and admitted["archived"]
    _pg_downgrade_to_schema_8(store)
    assert _pg_versions(store) == {8}
    store.close()

    for _restart in range(2):
        reopened = make_postgres_store(schema)
        reopened.initialize()
        assert 9 in _pg_versions(reopened)
        _assert_backfilled(reopened, records, admitted)
        reopened.close()

    migrated = make_postgres_store(schema)
    migrated.initialize()
    try:
        _invalidate_after_migration(migrated, maintainer, records["active"])
    finally:
        migrated.close()
