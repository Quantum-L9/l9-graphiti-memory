# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_projection_link_migration.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-10-01
"""ADR-084 schema 8: legacy links are rekeyed by target identity, never lost.

Each test builds a store, projects one record through the legacy runtime, then
rewrites ``projection_links`` back to the exact schema-7 shape, keyed by
``(record_id, projection_name)`` with link JSON that predates target fields.
Reopening the store must migrate the row in place: same locator, the projection
name as its target identity, the ``legacy`` provider type, and a legacy erase
that still finds and removes the copy.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from l9_graphite_memory.adapters import SQLiteRecordStore
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    LEGACY_PROVIDER_TYPE,
    DeletionRequest,
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
    RetirementMode,
)
from l9_graphite_memory.services import MemoryService, OutboxWorker
from tests.conftest import make_postgres_store

_TARGET_FIELDS = (
    "target_identity",
    "projection_version",
    "provider_type",
    "manifest_digest",
    "render_contract_digest",
)

_SQLITE_V7_DDL = """
CREATE TABLE projection_links_v7 (
    record_id TEXT NOT NULL,
    projection_name TEXT NOT NULL,
    namespace TEXT NOT NULL,
    locator TEXT NOT NULL,
    created_at TEXT NOT NULL,
    link_json TEXT NOT NULL,
    PRIMARY KEY (record_id, projection_name),
    FOREIGN KEY(record_id) REFERENCES memory_records(record_id)
)
"""


class LegacyProjection:
    name = "graphiti"
    capabilities: tuple[str, ...] = ()
    retirement_mode = RetirementMode.WITHDRAW

    def __init__(self) -> None:
        self.erased: list[tuple[UUID, str | None]] = []

    def health(self) -> dict[str, Any]:
        return {"name": self.name, "healthy": True}

    def project(self, record) -> dict[str, Any]:
        return {"locator": f"episode-{record.record_id}"}

    def retire(self, record_id, namespace, *, locator=None, reason="") -> dict[str, Any]:
        return {"retired": True, "erased": False, "locator": locator}

    def erase(self, record_id, namespace, *, locator=None) -> dict[str, Any]:
        self.erased.append((record_id, locator))
        return {"erased": True, "locator": locator}

    def search(self, query, namespaces, *, limit):
        return []


def _worker(store, projection, tmp_path) -> OutboxWorker:
    settings = MemorySettings(data_dir=tmp_path / "data", state_dir=tmp_path / "state")
    return OutboxWorker(store, projection, settings, worker_id="test")


def _project_one(store, projection, principal, tmp_path) -> UUID:
    service = MemoryService(store, projection)
    written = service.write(
        principal,
        MemoryWriteRequest(
            namespace="repo-a",
            memory_class=MemoryClass.OBSERVATION,
            content="projected before schema 8",
            provenance=Provenance(source="test"),
            evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
        ),
    )
    assert _worker(store, projection, tmp_path).run_once()["delivered"] == 1
    return written.record_id


def _v7_link_json(link_json: str) -> str:
    data = json.loads(link_json)
    for field in _TARGET_FIELDS:
        data.pop(field, None)
    return json.dumps(data)


def _assert_migrated_and_erasable(store, projection, record_id, admin, tmp_path) -> None:
    (link,) = store.list_projection_links(record_id)
    assert link.locator == f"episode-{record_id}"
    assert link.target_identity == "graphiti"
    assert link.projection_name == "graphiti"
    assert link.provider_type == LEGACY_PROVIDER_TYPE
    assert store.get_projection_link(record_id, "graphiti") == link

    service = MemoryService(store, projection)
    receipt = service.delete(
        admin,
        DeletionRequest(
            record_id=record_id,
            reason="post-migration deletion",
            verification_reference="ticket-084",
        ),
    )
    assert receipt.projection_targets == ("graphiti",)
    _worker(store, projection, tmp_path).run_once()

    assert projection.erased == [(record_id, f"episode-{record_id}")]
    assert store.list_projection_links(record_id) == []
    assert store.get_record(record_id).state is MemoryState.DELETED


def test_sqlite_schema_7_links_migrate_in_place(principal, admin_principal, tmp_path) -> None:
    database = tmp_path / "memory.sqlite3"
    projection = LegacyProjection()
    store = SQLiteRecordStore(database)
    store.initialize()
    record_id = _project_one(store, projection, principal, tmp_path)
    with store._transaction() as tx:
        tx.execute(_SQLITE_V7_DDL)
        for row in tx.execute(
            "SELECT record_id, projection_name, namespace, locator, created_at, link_json "
            "FROM projection_links"
        ).fetchall():
            tx.execute(
                "INSERT INTO projection_links_v7 VALUES (?, ?, ?, ?, ?, ?)",
                (*tuple(row)[:5], _v7_link_json(row[5])),
            )
        tx.execute("DROP TABLE projection_links")
        tx.execute("ALTER TABLE projection_links_v7 RENAME TO projection_links")
        tx.execute("DELETE FROM schema_migrations WHERE version = 8")
    legacy_columns = {
        row[1] for row in store._connection().execute("PRAGMA table_info(projection_links)")
    }
    assert "target_identity" not in legacy_columns
    store.close()

    for _attempt in range(2):
        reopened = SQLiteRecordStore(database)
        reopened.initialize()
        columns = [
            row[1] for row in reopened._connection().execute("PRAGMA table_info(projection_links)")
        ]
        assert "target_identity" in columns and "provider_type" in columns
        primary = [
            row[1]
            for row in sorted(
                reopened._connection().execute("PRAGMA table_info(projection_links)"),
                key=lambda row: row[5],
            )
            if row[5]
        ]
        assert primary == ["record_id", "target_identity"]
        versions = {
            row[0]
            for row in reopened._connection().execute("SELECT version FROM schema_migrations")
        }
        assert 8 in versions
        assert len(reopened.list_projection_links(record_id)) == 1
        reopened.close()

    migrated = SQLiteRecordStore(database)
    migrated.initialize()
    try:
        _assert_migrated_and_erasable(migrated, projection, record_id, admin_principal, tmp_path)
    finally:
        migrated.close()


def test_postgres_schema_7_links_migrate_in_place(principal, admin_principal, tmp_path) -> None:
    projection = LegacyProjection()
    store = make_postgres_store()
    schema = store.test_schema
    store.initialize()
    record_id = _project_one(store, projection, principal, tmp_path)
    with store._transaction() as tx:
        tx.execute("SELECT record_id, link_json FROM projection_links")
        rows = tx.fetchall()
        tx.execute("ALTER TABLE projection_links DROP CONSTRAINT projection_links_pkey")
        tx.execute("ALTER TABLE projection_links DROP COLUMN target_identity")
        tx.execute("ALTER TABLE projection_links DROP COLUMN provider_type")
        tx.execute("ALTER TABLE projection_links ADD PRIMARY KEY (record_id, projection_name)")
        for row in rows:
            tx.execute(
                "UPDATE projection_links SET link_json = %s WHERE record_id = %s",
                (_v7_link_json(row["link_json"]), row["record_id"]),
            )
        tx.execute("DELETE FROM schema_migrations WHERE version = 8")
    with store._cursor() as cursor:
        assert "target_identity" not in store._projection_link_columns(cursor)
    store.close()

    for _attempt in range(2):
        reopened = make_postgres_store(schema)
        reopened.initialize()
        with reopened._cursor() as cursor:
            cursor.execute(
                "SELECT a.attname FROM pg_index i "
                "JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
                "WHERE i.indrelid = 'projection_links'::regclass AND i.indisprimary "
                "ORDER BY array_position(i.indkey, a.attnum)"
            )
            assert [row["attname"] for row in cursor.fetchall()] == [
                "record_id",
                "target_identity",
            ]
            cursor.execute("SELECT version FROM schema_migrations")
            assert 8 in {row["version"] for row in cursor.fetchall()}
        assert len(reopened.list_projection_links(record_id)) == 1
        reopened.close()

    migrated = make_postgres_store(schema)
    migrated.initialize()
    try:
        _assert_migrated_and_erasable(migrated, projection, record_id, admin_principal, tmp_path)
    finally:
        migrated.close()


def test_fresh_sqlite_store_creates_the_target_keyed_table(tmp_path) -> None:
    store = SQLiteRecordStore(tmp_path / "fresh.sqlite3")
    store.initialize()
    columns = {row[1] for row in store._connection().execute("PRAGMA table_info(projection_links)")}
    assert {"target_identity", "provider_type", "projection_name"} <= columns
    store.close()
