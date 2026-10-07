# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/sqlite_store.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SQLite canonical store with bi-temporal queries, receipts, and atomic outbox."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from l9_graphite_memory.contracts import (
    LEGACY_PROVIDER_TYPE,
    ArchiveReceipt,
    ConflictLinkReceipt,
    DeletionReceipt,
    DeletionStatus,
    GraphCutoverReceipt,
    LegacyProjectionReleaseReceipt,
    LifecycleTransitionReceipt,
    MaintenanceRunReceipt,
    MemoryRecord,
    MemorySearchRequest,
    MemoryState,
    MemoryStatusEvent,
    OutboxEvent,
    OutboxStatus,
    PhaseLockReceipt,
    ProjectionLink,
    ProjectionRebuildReceipt,
    ProjectionRetirementReceipt,
    WriteReceipt,
)
from l9_graphite_memory.contracts.generated_data import (
    RevalidationRequirement,
    SourceInvalidationEvent,
    SourceSelectorRecord,
    source_selectors_for_record,
)
from l9_graphite_memory.errors import (
    IdempotencyConflict,
    PhaseLockSnapshotConflict,
    ProjectionLinkConflict,
    StoreError,
)
from l9_graphite_memory.ports.phase_lock import PhaseLockPrecondition, snapshot_digest
from l9_graphite_memory.ports.service_capability import (
    ServiceWriteCapability,
    require_service_write_capability,
)
from l9_graphite_memory.schema import schema_registry

# Register built-in migrations.
from l9_graphite_memory.schema import upcasters as _upcasters  # noqa: F401

_SCHEMA_VERSION = 9

# Schema 9: structured source selectors, applied source invalidations, and the
# revalidation requirements they create (ADR-095).
_SOURCE_INVALIDATION_DDL = (
    """
    CREATE TABLE IF NOT EXISTS memory_source_selectors (
        selector_id TEXT PRIMARY KEY,
        record_id TEXT NOT NULL,
        repository TEXT NOT NULL,
        selector_type TEXT NOT NULL,
        selector_value TEXT NOT NULL,
        active INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        deactivated_at TEXT,
        FOREIGN KEY(record_id) REFERENCES memory_records(record_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_selector_repository_value ON memory_source_selectors(repository, selector_type, selector_value, active)",
    "CREATE INDEX IF NOT EXISTS idx_selector_record_active ON memory_source_selectors(record_id, active)",
    "CREATE INDEX IF NOT EXISTS idx_selector_type_value ON memory_source_selectors(selector_type, selector_value, active)",
    """
    CREATE TABLE IF NOT EXISTS source_invalidation_events (
        tenant_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        request_digest TEXT NOT NULL,
        event_type TEXT NOT NULL,
        repository TEXT,
        matched INTEGER NOT NULL,
        transitioned INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        event_json TEXT NOT NULL,
        PRIMARY KEY (tenant_id, event_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS revalidation_requirements (
        requirement_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        namespace TEXT NOT NULL,
        record_id TEXT NOT NULL,
        invalidation_event_id TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        requirement_json TEXT NOT NULL,
        FOREIGN KEY(record_id) REFERENCES memory_records(record_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_revalidation_record ON revalidation_requirements(record_id, status)",
)

# One row per durable provider copy, keyed by target identity (ADR-084).
_PROJECTION_LINKS_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    record_id TEXT NOT NULL,
    target_identity TEXT NOT NULL,
    projection_name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    namespace TEXT NOT NULL,
    locator TEXT NOT NULL,
    created_at TEXT NOT NULL,
    link_json TEXT NOT NULL,
    PRIMARY KEY (record_id, target_identity),
    FOREIGN KEY(record_id) REFERENCES memory_records(record_id)
)
"""


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class SQLiteRecordStore:
    name = "sqlite"

    def __init__(self, database_path: str | Path) -> None:
        self.path = Path(database_path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._write_lock = threading.RLock()
        self._initialized = False

    def _connection(self) -> sqlite3.Connection:
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            connection.execute("PRAGMA busy_timeout = 30000")
            self._local.connection = connection
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connection()
        with self._write_lock:
            try:
                connection.execute("BEGIN IMMEDIATE")
                yield connection
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def initialize(self) -> None:
        connection = self._connection()  # noqa: F841
        statements = [
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                record_id TEXT PRIMARY KEY,
                schema_version TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                memory_class TEXT NOT NULL,
                content TEXT NOT NULL,
                assertion_json TEXT,
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                recorded_at TEXT NOT NULL,
                source_observed_at TEXT,
                superseded_at TEXT,
                provenance_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                confidence_json TEXT NOT NULL,
                confidence_score REAL NOT NULL,
                state TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                normalized_digest TEXT NOT NULL,
                original_digest TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                supersedes_json TEXT NOT NULL,
                references_json TEXT NOT NULL DEFAULT '[]',
                conflicts_with_json TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                record_json TEXT NOT NULL,
                UNIQUE (tenant_id, namespace, idempotency_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_records_namespace_time ON memory_records(tenant_id, namespace, valid_from, valid_to)",
            "CREATE INDEX IF NOT EXISTS idx_records_state_class ON memory_records(state, memory_class)",
            "CREATE INDEX IF NOT EXISTS idx_records_digest ON memory_records(tenant_id, namespace, normalized_digest)",
            """
            CREATE TABLE IF NOT EXISTS memory_status_events (
                event_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                previous_state TEXT,
                new_state TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                receipt_id TEXT,
                event_json TEXT NOT NULL,
                FOREIGN KEY(record_id) REFERENCES memory_records(record_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS operation_receipts (
                receipt_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                aggregate_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                receipt_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS outbox_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT,
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                lease_id TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                event_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox_events(status, next_attempt_at)",
            "CREATE INDEX IF NOT EXISTS idx_outbox_lease ON outbox_events(status, lease_expires_at)",
            _PROJECTION_LINKS_DDL.format(table="projection_links"),
            "CREATE INDEX IF NOT EXISTS idx_projection_links_locator ON projection_links(projection_name, locator)",
            "CREATE INDEX IF NOT EXISTS idx_projection_links_target ON projection_links(target_identity, locator)",
            """
            CREATE TABLE IF NOT EXISTS maintenance_runs (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                status TEXT NOT NULL,
                applied INTEGER NOT NULL,
                watermark TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                receipt_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_maintenance_runs_namespace ON maintenance_runs(tenant_id, namespace, applied, watermark)",
            """
            CREATE TABLE IF NOT EXISTS maintenance_actions (
                action_digest TEXT NOT NULL,
                run_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                operation TEXT NOT NULL,
                applied INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, namespace, action_digest)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS phase_locks (
                lock_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                task_signature TEXT NOT NULL,
                granted INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                receipt_json TEXT NOT NULL,
                UNIQUE(tenant_id, namespace, task_signature)
            )
            """,
        ]
        with self._transaction() as tx:
            # Phase-lock tenant isolation migration: legacy databases keyed locks
            # by (namespace, task_signature) only, which lets two tenants sharing a
            # namespace/task signature collide on one lock slot. Detect the legacy
            # schema (no tenant_id column) and drop it so the tenant-scoped table
            # below is created cleanly. Outstanding legacy locks are invalidated
            # rather than assigned an invented tenant owner.
            phase_lock_columns = {
                str(row[1]) for row in tx.execute("PRAGMA table_info(phase_locks)").fetchall()
            }
            if phase_lock_columns and "tenant_id" not in phase_lock_columns:
                tx.execute("DROP TABLE phase_locks")
            self._migrate_projection_links_to_targets(tx)
            for statement in statements:
                tx.execute(statement)
            for statement in _SOURCE_INVALIDATION_DDL:
                tx.execute(statement)
            columns = {
                str(row[1]) for row in tx.execute("PRAGMA table_info(memory_records)").fetchall()
            }
            if "references_json" not in columns:
                tx.execute(
                    "ALTER TABLE memory_records ADD COLUMN references_json TEXT NOT NULL DEFAULT '[]'"
                )
            outbox_columns = {
                str(row[1]) for row in tx.execute("PRAGMA table_info(outbox_events)").fetchall()
            }
            for column in ("lease_id", "lease_owner", "lease_expires_at"):
                if column not in outbox_columns:
                    tx.execute(f"ALTER TABLE outbox_events ADD COLUMN {column} TEXT")
            self._backfill_source_selectors(tx)
            tx.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )
        self._initialized = True

    @staticmethod
    def _migrate_projection_links_to_targets(tx: sqlite3.Connection) -> None:
        """Rekey schema-7 links from projection name to target identity.

        Schema 7 keyed a link by ``(record_id, projection_name)``, so a record
        could hold one provider copy per projection name. Every existing row is
        copied unchanged, locator and link JSON included, with the projection
        name it was keyed by as its target identity; that is the identity the
        legacy runtime resolves, so no copy is orphaned. Runs only while the
        legacy table shape is present (ADR-084).
        """

        columns = {
            str(row[1]) for row in tx.execute("PRAGMA table_info(projection_links)").fetchall()
        }
        if not columns or "target_identity" in columns:
            return
        tx.execute(_PROJECTION_LINKS_DDL.format(table="projection_links_v8"))
        tx.execute(
            """
            INSERT INTO projection_links_v8 (
                record_id, target_identity, projection_name, provider_type,
                namespace, locator, created_at, link_json
            )
            SELECT record_id, projection_name, projection_name, ?,
                   namespace, locator, created_at, link_json
            FROM projection_links
            """,
            (LEGACY_PROVIDER_TYPE,),
        )
        copied = tx.execute("SELECT COUNT(*) FROM projection_links_v8").fetchone()[0]
        original = tx.execute("SELECT COUNT(*) FROM projection_links").fetchone()[0]
        if copied != original:
            raise StoreError(
                f"projection link migration copied {copied} of {original} links; aborted"
            )
        tx.execute("DROP TABLE projection_links")
        tx.execute("ALTER TABLE projection_links_v8 RENAME TO projection_links")

    def _backfill_source_selectors(self, tx: sqlite3.Connection) -> None:
        """Schema 8 -> 9: derive selectors from existing structured metadata.

        Runs only until schema 9 is recorded, inside the initialization
        transaction. Each selector comes from ``source_selectors_for_record``,
        the same lossless mapping admission uses; a record whose metadata does
        not map losslessly gets none. Selector ids are deterministic and
        inserted with ``OR IGNORE``, so a rerun after an interrupted start
        changes nothing (ADR-095).
        """

        if tx.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (_SCHEMA_VERSION,)
        ).fetchone():
            return
        now = datetime.now(timezone.utc)
        rows = tx.execute(
            "SELECT record_json FROM memory_records WHERE state NOT IN (?, ?)",
            (MemoryState.DELETED.value, MemoryState.DELETION_PENDING.value),
        ).fetchall()
        for row in rows:
            record = self._row_to_record(row)
            active = record.state is MemoryState.ACTIVE
            for selector in source_selectors_for_record(record):
                self._insert_selector(
                    tx,
                    selector.model_copy(
                        update={"active": active, "deactivated_at": None if active else now}
                    ),
                )

    @staticmethod
    def _insert_selector(tx: sqlite3.Connection, selector: SourceSelectorRecord) -> None:
        tx.execute(
            """
            INSERT OR IGNORE INTO memory_source_selectors(
                selector_id, record_id, repository, selector_type, selector_value,
                active, created_at, deactivated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                selector.selector_id,
                str(selector.record_id),
                selector.repository,
                selector.selector_type,
                selector.selector_value,
                int(selector.active),
                _dt(selector.created_at),
                _dt(selector.deactivated_at),
            ),
        )

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None
        self._initialized = False

    def health(self) -> dict[str, Any]:
        try:
            row = (
                self._connection()
                .execute("SELECT COUNT(*) AS count FROM memory_records")
                .fetchone()
            )
            return {
                "name": self.name,
                "healthy": self._initialized,
                "path": str(self.path),
                "records": int(row["count"]) if row else 0,
                "schema_version": _SCHEMA_VERSION,
            }
        except sqlite3.Error as exc:
            return {
                "name": self.name,
                "healthy": False,
                "path": str(self.path),
                "error": str(exc),
            }

    @staticmethod
    def _record_values(record: MemoryRecord) -> tuple[Any, ...]:
        payload = record.model_dump(mode="json")
        return (
            str(record.record_id),
            record.schema_version,
            record.tenant_id,
            record.namespace,
            record.memory_class.value,
            record.content,
            _json(record.assertion.model_dump(mode="json")) if record.assertion else None,
            _dt(record.temporal.valid_from),
            _dt(record.temporal.valid_to),
            _dt(record.temporal.recorded_at),
            _dt(record.temporal.source_observed_at),
            _dt(record.temporal.superseded_at),
            _json(record.provenance.model_dump(mode="json")),
            _json([item.model_dump(mode="json") for item in record.evidence]),
            _json(record.confidence.model_dump(mode="json")),
            record.confidence.score,
            record.state.value,
            _json(record.tags),
            _json(record.metadata),
            record.normalized_digest,
            record.original_digest,
            record.idempotency_key,
            _json([str(item) for item in record.supersedes]),
            _json([str(item) for item in record.references]),
            _json([str(item) for item in record.conflicts_with]),
            record.created_by,
            _dt(record.created_at),
            _json(payload),
        )

    def _insert_record(self, tx: sqlite3.Connection, record: MemoryRecord) -> None:
        tx.execute(
            """
            INSERT INTO memory_records (
                record_id, schema_version, tenant_id, namespace, memory_class, content,
                assertion_json, valid_from, valid_to, recorded_at, source_observed_at,
                superseded_at, provenance_json, evidence_json, confidence_json,
                confidence_score, state, tags_json, metadata_json, normalized_digest,
                original_digest, idempotency_key, supersedes_json, references_json, conflicts_with_json,
                created_by, created_at, record_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            self._record_values(record),
        )

    def _insert_receipt(self, tx: sqlite3.Connection, receipt: WriteReceipt) -> None:
        tx.execute(
            """
            INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(receipt.receipt_id),
                "write",
                str(receipt.record_id) if receipt.record_id else None,
                receipt.status.value,
                _dt(receipt.created_at),
                _json(receipt.model_dump(mode="json")),
            ),
        )

    def _insert_archive_receipt(self, tx: sqlite3.Connection, receipt: ArchiveReceipt) -> None:
        tx.execute(
            """
            INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(receipt.receipt_id),
                "archive",
                receipt.namespace,
                receipt.status.value,
                _dt(receipt.created_at),
                _json(receipt.model_dump(mode="json")),
            ),
        )

    def _insert_deletion_receipt(self, tx: sqlite3.Connection, receipt: DeletionReceipt) -> None:
        tx.execute(
            """
            INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(receipt.receipt_id),
                "deletion",
                str(receipt.record_id),
                receipt.status.value,
                _dt(receipt.created_at),
                _json(receipt.model_dump(mode="json")),
            ),
        )

    def _insert_status_event(self, tx: sqlite3.Connection, event: MemoryStatusEvent) -> None:
        record = tx.execute(
            "SELECT record_json FROM memory_records WHERE record_id = ?",
            (str(event.record_id),),
        ).fetchone()
        if record is None:
            raise StoreError(f"status transition target not found: {event.record_id}")
        record_payload = json.loads(str(record["record_json"]))
        current_state = MemoryState(str(record_payload["state"]))
        if event.previous_state is not None and current_state is not event.previous_state:
            raise StoreError(
                f"status transition expected {event.previous_state.value} but found {current_state.value}: {event.record_id}"
            )
        record_payload["state"] = event.new_state.value
        if event.new_state is MemoryState.SUPERSEDED:
            record_payload.setdefault("temporal", {})["superseded_at"] = _dt(event.occurred_at)
        tx.execute(
            """
            UPDATE memory_records
            SET state = ?, superseded_at = ?, record_json = ?
            WHERE record_id = ?
            """,
            (
                event.new_state.value,
                _dt(event.occurred_at)
                if event.new_state is MemoryState.SUPERSEDED
                else record_payload.get("temporal", {}).get("superseded_at"),
                _json(record_payload),
                str(event.record_id),
            ),
        )
        tx.execute(
            """
            INSERT INTO memory_status_events(
                event_id, record_id, previous_state, new_state, reason, actor,
                occurred_at, receipt_id, event_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.event_id),
                str(event.record_id),
                event.previous_state.value if event.previous_state else None,
                event.new_state.value,
                event.reason,
                event.actor,
                _dt(event.occurred_at),
                str(event.receipt_id) if event.receipt_id else None,
                _json(event.model_dump(mode="json")),
            ),
        )

    def _insert_outbox(self, tx: sqlite3.Connection, event: OutboxEvent) -> None:
        tx.execute(
            """
            INSERT INTO outbox_events(
                event_id, event_type, aggregate_id, namespace, status, attempts,
                next_attempt_at, last_error, created_at, delivered_at,
                lease_id, lease_owner, lease_expires_at, event_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.event_id),
                event.event_type,
                str(event.aggregate_id),
                event.namespace,
                event.status.value,
                event.attempts,
                _dt(event.next_attempt_at),
                event.last_error,
                _dt(event.created_at),
                _dt(event.delivered_at),
                str(event.lease_id) if event.lease_id else None,
                event.lease_owner,
                _dt(event.lease_expires_at),
                _json(event.model_dump(mode="json")),
            ),
        )

    def commit_write(
        self,
        capability: ServiceWriteCapability,
        record: MemoryRecord | None,
        receipt: WriteReceipt,
        *,
        outbox_events: tuple[OutboxEvent, ...] = (),
        status_events: tuple[MemoryStatusEvent, ...] = (),
        expected_phase_lock: PhaseLockPrecondition | None = None,
    ) -> None:
        require_service_write_capability(capability)
        try:
            with self._transaction() as tx:
                # BEGIN IMMEDIATE already holds the write lock here, so the
                # re-read below cannot be overtaken by another writer before
                # this transaction commits.
                if expected_phase_lock is not None:
                    self._require_phase_lock_snapshot(tx, expected_phase_lock)
                if record is not None:
                    self._insert_record(tx, record)
                    # Structured selectors commit with the record (ADR-095).
                    for selector in source_selectors_for_record(record):
                        self._insert_selector(tx, selector)
                self._insert_receipt(tx, receipt)
                for status_event in status_events:
                    self._insert_status_event(tx, status_event)
                for outbox_event in outbox_events:
                    self._insert_outbox(tx, outbox_event)
        except sqlite3.IntegrityError as exc:
            if "idempotency_key" in str(exc):
                raise IdempotencyConflict(
                    "operation identity already committed by a concurrent write: "
                    f"{record.idempotency_key if record else '?'}"
                ) from exc
            raise StoreError(f"atomic memory write violated store constraints: {exc}") from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic memory write failed: {exc}") from exc

    def _require_phase_lock_snapshot(
        self, tx: sqlite3.Connection, expected: PhaseLockPrecondition
    ) -> None:
        rows = tx.execute(
            "SELECT record_json FROM memory_records "
            "WHERE tenant_id = ? AND namespace = ? AND state = ?",
            (expected.tenant_id, expected.namespace, MemoryState.ACTIVE.value),
        ).fetchall()
        current = snapshot_digest([self._row_to_record(row) for row in rows])
        if current != expected.expected_snapshot_digest:
            raise PhaseLockSnapshotConflict(
                "namespace changed after phase-lock verification: "
                f"expected={expected.expected_snapshot_digest} current={current}"
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        raw = json.loads(str(row["record_json"]))
        return schema_registry.read_record(raw)

    def get_record(self, record_id: UUID) -> MemoryRecord | None:
        row = (
            self._connection()
            .execute(
                "SELECT record_json FROM memory_records WHERE record_id = ?",
                (str(record_id),),
            )
            .fetchone()
        )
        return self._row_to_record(row) if row else None

    def find_by_idempotency(
        self, tenant_id: str, namespace: str, idempotency_key: str
    ) -> MemoryRecord | None:
        row = (
            self._connection()
            .execute(
                """
            SELECT record_json FROM memory_records
            WHERE tenant_id = ? AND namespace = ? AND idempotency_key = ?
            """,
                (tenant_id, namespace, idempotency_key),
            )
            .fetchone()
        )
        return self._row_to_record(row) if row else None

    def search_records(
        self,
        tenant_id: str,
        request: MemorySearchRequest,
        namespaces: tuple[str, ...],
    ) -> list[MemoryRecord]:
        if not namespaces:
            return []
        states = [MemoryState.ACTIVE.value]
        if request.include_superseded:
            states.append(MemoryState.SUPERSEDED.value)
        if request.include_archived:
            states.append(MemoryState.ARCHIVED.value)
        namespace_marks = ",".join("?" for _ in namespaces)
        state_marks = ",".join("?" for _ in states)
        params: list[Any] = [tenant_id, *namespaces, *states]
        where = [
            "tenant_id = ?",
            f"namespace IN ({namespace_marks})",
            f"state IN ({state_marks})",
            "confidence_score >= ?",
            "valid_from <= ?",
            "(valid_to IS NULL OR valid_to > ?)",
            "recorded_at <= ?",
        ]
        params.extend(
            [
                request.min_confidence,
                _dt(request.valid_at),
                _dt(request.valid_at),
                _dt(request.recorded_before or request.valid_at),
            ]
        )
        if request.memory_classes:
            class_marks = ",".join("?" for _ in request.memory_classes)
            where.append(f"memory_class IN ({class_marks})")
            params.extend(item.value for item in request.memory_classes)
        sql = f"SELECT record_json FROM memory_records WHERE {' AND '.join(where)} ORDER BY recorded_at DESC LIMIT ?"
        params.append(request.limit * 20)
        rows = self._connection().execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_records(
        self,
        tenant_id: str,
        namespace: str,
        *,
        states: tuple[MemoryState, ...] = (),
        limit: int | None = 1_000,
    ) -> list[MemoryRecord]:
        params: list[Any] = [tenant_id, namespace]
        sql = "SELECT record_json FROM memory_records WHERE tenant_id = ? AND namespace = ?"
        if states:
            marks = ",".join("?" for _ in states)
            sql += f" AND state IN ({marks})"
            params.extend(item.value for item in states)
        sql += " ORDER BY recorded_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._connection().execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def transition_state(
        self, capability: ServiceWriteCapability, event: MemoryStatusEvent
    ) -> None:
        require_service_write_capability(capability)
        try:
            with self._transaction() as tx:
                self._insert_status_event(tx, event)
        except sqlite3.Error as exc:
            raise StoreError(f"lifecycle transition failed: {exc}") from exc

    def find_source_selector_matches(
        self,
        tenant_id: str,
        *,
        repository: str | None,
        selector_type: str,
        selector_value: str,
    ) -> tuple[UUID, ...]:
        params: list[Any] = [selector_type, selector_value]
        sql = (
            "SELECT DISTINCT s.record_id FROM memory_source_selectors AS s "
            "JOIN memory_records AS r ON r.record_id = s.record_id "
            "WHERE s.selector_type = ? AND s.selector_value = ? AND s.active = 1"
        )
        if repository is not None:
            sql += " AND s.repository = ?"
            params.append(repository)
        sql += " AND r.tenant_id = ? AND r.state = ? ORDER BY s.record_id"
        params.extend([tenant_id, MemoryState.ACTIVE.value])
        rows = self._connection().execute(sql, params).fetchall()
        return tuple(UUID(str(row[0])) for row in rows)

    def list_source_selectors(self, record_id: UUID) -> list[SourceSelectorRecord]:
        rows = (
            self._connection()
            .execute(
                "SELECT * FROM memory_source_selectors WHERE record_id = ? ORDER BY selector_id",
                (str(record_id),),
            )
            .fetchall()
        )
        return [
            SourceSelectorRecord(
                selector_id=str(row["selector_id"]),
                record_id=UUID(str(row["record_id"])),
                repository=str(row["repository"]),
                selector_type=str(row["selector_type"]),
                selector_value=str(row["selector_value"]),
                active=bool(row["active"]),
                created_at=datetime.fromisoformat(str(row["created_at"])),
                deactivated_at=_parse_dt(row["deactivated_at"]),
            )
            for row in rows
        ]

    def get_source_invalidation(
        self, tenant_id: str, event_id: str
    ) -> SourceInvalidationEvent | None:
        row = (
            self._connection()
            .execute(
                "SELECT event_json FROM source_invalidation_events "
                "WHERE tenant_id = ? AND event_id = ?",
                (tenant_id, event_id),
            )
            .fetchone()
        )
        return SourceInvalidationEvent.model_validate_json(str(row[0])) if row else None

    def list_revalidation_requirements(self, record_id: UUID) -> list[RevalidationRequirement]:
        rows = (
            self._connection()
            .execute(
                "SELECT requirement_json FROM revalidation_requirements "
                "WHERE record_id = ? ORDER BY created_at, requirement_id",
                (str(record_id),),
            )
            .fetchall()
        )
        return [RevalidationRequirement.model_validate_json(str(row[0])) for row in rows]

    def commit_source_invalidation(
        self,
        capability: ServiceWriteCapability,
        event: SourceInvalidationEvent,
        *,
        lifecycle_receipts: tuple[LifecycleTransitionReceipt, ...],
        status_events: tuple[MemoryStatusEvent, ...],
        outbox_events: tuple[OutboxEvent, ...] = (),
        revalidation_requirements: tuple[RevalidationRequirement, ...] = (),
    ) -> None:
        require_service_write_capability(capability)
        transitioned = {
            item.record_id for receipt in lifecycle_receipts for item in receipt.transitions
        }
        if {item.record_id for item in status_events} != transitioned:
            raise StoreError("invalidation receipts and status events target different records")
        try:
            with self._transaction() as tx:
                if tx.execute(
                    "SELECT 1 FROM source_invalidation_events WHERE tenant_id = ? AND event_id = ?",
                    (event.tenant_id, event.event_id),
                ).fetchone():
                    raise IdempotencyConflict(
                        f"source invalidation already committed: {event.event_id}"
                    )
                tx.execute(
                    """
                    INSERT INTO source_invalidation_events(
                        tenant_id, event_id, request_digest, event_type, repository,
                        matched, transitioned, created_at, event_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.tenant_id,
                        event.event_id,
                        event.request_digest,
                        event.event_type,
                        event.repository,
                        event.matched,
                        event.transitioned,
                        _dt(event.created_at),
                        _json(event.model_dump(mode="json")),
                    ),
                )
                for receipt in lifecycle_receipts:
                    tx.execute(
                        """
                        INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(receipt.receipt_id),
                            "lifecycle",
                            receipt.namespace,
                            receipt.status.value,
                            _dt(receipt.created_at),
                            _json(receipt.model_dump(mode="json")),
                        ),
                    )
                for status_event in status_events:
                    self._insert_status_event(tx, status_event)
                for outbox_event in outbox_events:
                    self._insert_outbox(tx, outbox_event)
                for requirement in revalidation_requirements:
                    tx.execute(
                        """
                        INSERT INTO revalidation_requirements(
                            requirement_id, tenant_id, namespace, record_id,
                            invalidation_event_id, status, created_at, requirement_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(requirement.requirement_id),
                            requirement.tenant_id,
                            requirement.namespace,
                            str(requirement.record_id),
                            requirement.invalidation_event_id,
                            requirement.status,
                            _dt(requirement.created_at),
                            _json(requirement.model_dump(mode="json")),
                        ),
                    )
                for record_id in sorted(transitioned, key=str):
                    tx.execute(
                        "UPDATE memory_source_selectors SET active = 0, deactivated_at = ? "
                        "WHERE record_id = ? AND active = 1",
                        (_dt(event.created_at), str(record_id)),
                    )
        except sqlite3.IntegrityError as exc:
            if "source_invalidation_events" in str(exc):
                raise IdempotencyConflict(
                    f"source invalidation already committed: {event.event_id}"
                ) from exc
            raise StoreError(
                f"atomic source invalidation violated store constraints: {exc}"
            ) from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic source invalidation failed: {exc}") from exc

    def commit_lifecycle(
        self,
        capability: ServiceWriteCapability,
        receipt: LifecycleTransitionReceipt,
        *,
        status_events: tuple[MemoryStatusEvent, ...],
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        require_service_write_capability(capability)
        event_ids = {event.record_id for event in status_events}
        if event_ids != {item.record_id for item in receipt.transitions}:
            raise StoreError("lifecycle receipt and status events target different records")
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(receipt.receipt_id),
                        "lifecycle",
                        receipt.namespace,
                        receipt.status.value,
                        _dt(receipt.created_at),
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
                for event in status_events:
                    self._insert_status_event(tx, event)
                for outbox_event in outbox_events:
                    self._insert_outbox(tx, outbox_event)
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                f"atomic lifecycle transition violated store constraints: {exc}"
            ) from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic lifecycle transition failed: {exc}") from exc

    def commit_conflict_links(
        self,
        capability: ServiceWriteCapability,
        receipt: ConflictLinkReceipt,
    ) -> None:
        require_service_write_capability(capability)
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(receipt.receipt_id),
                        "conflict_link",
                        receipt.namespace,
                        receipt.status.value,
                        _dt(receipt.created_at),
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
                for link in receipt.links:
                    self._add_conflict_link(tx, link.left_record_id, link.right_record_id)
                    self._add_conflict_link(tx, link.right_record_id, link.left_record_id)
        except sqlite3.IntegrityError as exc:
            raise StoreError(f"atomic conflict link violated store constraints: {exc}") from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic conflict link failed: {exc}") from exc

    @staticmethod
    def _add_conflict_link(tx: sqlite3.Connection, record_id: UUID, other_id: UUID) -> None:
        row = tx.execute(
            "SELECT record_json FROM memory_records WHERE record_id = ?", (str(record_id),)
        ).fetchone()
        if row is None:
            raise StoreError(f"conflict link target not found: {record_id}")
        payload = json.loads(str(row["record_json"]))
        links = [str(item) for item in payload.get("conflicts_with", [])]
        if str(other_id) in links:
            return
        links.append(str(other_id))
        payload["conflicts_with"] = links
        tx.execute(
            "UPDATE memory_records SET conflicts_with_json = ?, record_json = ? WHERE record_id = ?",
            (_json(links), _json(payload), str(record_id)),
        )

    def save_phase_lock(
        self, capability: ServiceWriteCapability, receipt: PhaseLockReceipt
    ) -> None:
        require_service_write_capability(capability)
        with self._transaction() as tx:
            tx.execute(
                """
                INSERT INTO phase_locks(lock_id, tenant_id, namespace, task_signature, granted, expires_at, created_at, receipt_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, namespace, task_signature) DO UPDATE SET
                    lock_id = excluded.lock_id,
                    granted = excluded.granted,
                    expires_at = excluded.expires_at,
                    created_at = excluded.created_at,
                    receipt_json = excluded.receipt_json
                """,
                (
                    str(receipt.lock_id),
                    receipt.tenant_id,
                    receipt.namespace,
                    receipt.task_signature,
                    int(receipt.granted),
                    _dt(receipt.expires_at),
                    _dt(receipt.created_at),
                    _json(receipt.model_dump(mode="json")),
                ),
            )

    def get_phase_lock(
        self, tenant_id: str, namespace: str, task_signature: str
    ) -> PhaseLockReceipt | None:
        row = (
            self._connection()
            .execute(
                "SELECT receipt_json FROM phase_locks WHERE tenant_id = ? AND namespace = ? AND task_signature = ?",
                (tenant_id, namespace, task_signature),
            )
            .fetchone()
        )
        return PhaseLockReceipt.model_validate_json(str(row["receipt_json"])) if row else None

    def claim_outbox(
        self,
        *,
        limit: int,
        now: datetime,
        lease_seconds: int = 300,
        lease_owner: str = "outbox-worker",
    ) -> list[OutboxEvent]:
        expires_at = now + timedelta(seconds=lease_seconds)
        with self._transaction() as tx:
            rows = tx.execute(
                """
                SELECT event_id, event_json FROM outbox_events
                WHERE (status IN (?, ?) AND next_attempt_at <= ?)
                   OR (status = ? AND (lease_expires_at IS NULL OR lease_expires_at <= ?))
                ORDER BY created_at ASC LIMIT ?
                """,
                (
                    OutboxStatus.PENDING.value,
                    OutboxStatus.RETRY.value,
                    _dt(now),
                    OutboxStatus.PROCESSING.value,
                    _dt(now),
                    limit,
                ),
            ).fetchall()
            events: list[OutboxEvent] = []
            for row in rows:
                event = OutboxEvent.model_validate_json(str(row["event_json"]))
                leased = event.model_copy(
                    update={
                        "status": OutboxStatus.PROCESSING,
                        "lease_id": uuid4(),
                        "lease_owner": lease_owner,
                        "lease_expires_at": expires_at,
                    }
                )
                tx.execute(
                    """
                    UPDATE outbox_events
                    SET status = ?, lease_id = ?, lease_owner = ?, lease_expires_at = ?, event_json = ?
                    WHERE event_id = ?
                    """,
                    (
                        OutboxStatus.PROCESSING.value,
                        str(leased.lease_id),
                        lease_owner,
                        _dt(expires_at),
                        _json(leased.model_dump(mode="json")),
                        str(row["event_id"]),
                    ),
                )
                events.append(leased)
            return events

    def update_outbox(
        self,
        event_id: UUID,
        *,
        status: OutboxStatus,
        attempts: int,
        next_attempt_at: datetime,
        last_error: str | None,
        delivered_at: datetime | None = None,
        lease_id: UUID | None = None,
    ) -> None:
        with self._transaction() as tx:
            row = tx.execute(
                "SELECT event_json FROM outbox_events WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
            if row is None:
                raise StoreError(f"outbox event not found: {event_id}")
            event = OutboxEvent.model_validate_json(str(row["event_json"]))
            if lease_id is not None and event.lease_id != lease_id:
                raise StoreError(
                    f"outbox lease is no longer held for {event_id}; another worker owns this event"
                )
            updated = event.model_copy(
                update={
                    "status": status,
                    "attempts": attempts,
                    "next_attempt_at": next_attempt_at,
                    "last_error": last_error,
                    "delivered_at": delivered_at,
                    "lease_id": None,
                    "lease_owner": None,
                    "lease_expires_at": None,
                }
            )
            tx.execute(
                """
                UPDATE outbox_events
                SET status = ?, attempts = ?, next_attempt_at = ?, last_error = ?, delivered_at = ?,
                    lease_id = NULL, lease_owner = NULL, lease_expires_at = NULL, event_json = ?
                WHERE event_id = ?
                """,
                (
                    status.value,
                    attempts,
                    _dt(next_attempt_at),
                    last_error,
                    _dt(delivered_at),
                    _json(updated.model_dump(mode="json")),
                    str(event_id),
                ),
            )

    def outbox_backlog(self) -> int:
        row = (
            self._connection()
            .execute(
                "SELECT COUNT(*) AS count FROM outbox_events WHERE status NOT IN (?, ?)",
                (OutboxStatus.DELIVERED.value, OutboxStatus.DEAD.value),
            )
            .fetchone()
        )
        return int(row["count"]) if row else 0

    def save_projection_link(self, link: ProjectionLink) -> None:
        try:
            with self._transaction() as tx:
                self._upsert_projection_link(tx, link)
        except sqlite3.Error as exc:
            raise StoreError(f"projection link persistence failed: {exc}") from exc

    def _upsert_projection_link(self, tx: Any, link: ProjectionLink) -> None:
        tx.execute(
            """
            INSERT INTO projection_links (
                record_id, target_identity, projection_name, provider_type,
                namespace, locator, created_at, link_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id, target_identity) DO UPDATE SET
                projection_name = excluded.projection_name,
                provider_type = excluded.provider_type,
                namespace = excluded.namespace,
                locator = excluded.locator,
                created_at = excluded.created_at,
                link_json = excluded.link_json
            """,
            (
                str(link.record_id),
                link.target_identity,
                link.projection_name,
                link.provider_type,
                link.namespace,
                link.locator,
                _dt(link.created_at),
                _json(link.model_dump(mode="json")),
            ),
        )

    def save_projection_link_if_active(
        self, link: ProjectionLink, *, expected_previous: ProjectionLink | None
    ) -> bool:
        try:
            with self._transaction() as tx:
                row = tx.execute(
                    "SELECT record_json FROM memory_records WHERE record_id = ?",
                    (str(link.record_id),),
                ).fetchone()
                if row is None:
                    return False
                record = schema_registry.read_record(json.loads(str(row["record_json"])))
                if record.state is not MemoryState.ACTIVE:
                    return False
                current_row = tx.execute(
                    "SELECT target_identity, provider_type, link_json FROM projection_links "
                    "WHERE record_id = ? AND target_identity = ?",
                    (str(link.record_id), link.target_identity),
                ).fetchone()
                current = self._row_to_link(current_row) if current_row else None
                if current != expected_previous:
                    raise ProjectionLinkConflict("projection link changed since it was read")
                self._upsert_projection_link(tx, link)
                return True
        except sqlite3.Error as exc:
            raise StoreError(f"projection link persistence failed: {exc}") from exc

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> ProjectionLink:
        # The columns are the durable key; the JSON of a migrated schema-7 row
        # predates target identity and is read under the key it is stored at.
        data = json.loads(str(row["link_json"]))
        data["target_identity"] = str(row["target_identity"])
        data["provider_type"] = str(row["provider_type"])
        return ProjectionLink.model_validate(data)

    def get_projection_link(
        self,
        record_id: UUID,
        target_identity: str,
    ) -> ProjectionLink | None:
        row = (
            self._connection()
            .execute(
                "SELECT target_identity, provider_type, link_json FROM projection_links "
                "WHERE record_id = ? AND target_identity = ?",
                (str(record_id), target_identity),
            )
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_link(row)

    def list_projection_links(self, record_id: UUID) -> list[ProjectionLink]:
        rows = (
            self._connection()
            .execute(
                "SELECT target_identity, provider_type, link_json FROM projection_links "
                "WHERE record_id = ? ORDER BY target_identity",
                (str(record_id),),
            )
            .fetchall()
        )
        return [self._row_to_link(row) for row in rows]

    def list_projection_target_identities(self) -> tuple[str, ...]:
        connection = self._connection()
        identities = {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT target_identity FROM projection_links"
            ).fetchall()
        }
        rows = connection.execute(
            "SELECT event_json FROM outbox_events WHERE status NOT IN (?, ?)",
            (OutboxStatus.DELIVERED.value, OutboxStatus.DEAD.value),
        ).fetchall()
        for row in rows:
            identity = OutboxEvent.model_validate_json(str(row[0])).payload.get("target_identity")
            if isinstance(identity, str) and identity.strip():
                identities.add(identity.strip())
        return tuple(sorted(identities))

    def delete_projection_link(self, record_id: UUID, target_identity: str) -> None:
        try:
            with self._transaction() as tx:
                tx.execute(
                    "DELETE FROM projection_links WHERE record_id = ? AND target_identity = ?",
                    (str(record_id), target_identity),
                )
        except sqlite3.Error as exc:
            raise StoreError(f"projection link deletion failed: {exc}") from exc

    def save_maintenance_run(self, receipt: MaintenanceRunReceipt) -> None:
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO maintenance_runs(
                        run_id, tenant_id, namespace, status, applied, watermark,
                        started_at, completed_at, receipt_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(receipt.run_id),
                        receipt.tenant_id,
                        receipt.namespace,
                        receipt.status.value,
                        int(receipt.applied),
                        _dt(receipt.watermark),
                        _dt(receipt.started_at),
                        _dt(receipt.completed_at),
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
                for action in receipt.actions:
                    if not action.applied:
                        continue
                    tx.execute(
                        """
                        INSERT OR IGNORE INTO maintenance_actions(
                            action_digest, run_id, tenant_id, namespace, operation,
                            applied, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            action.action_digest,
                            str(receipt.run_id),
                            receipt.tenant_id,
                            receipt.namespace,
                            action.operation.value,
                            1,
                            _dt(receipt.started_at),
                        ),
                    )
        except sqlite3.Error as exc:
            raise StoreError(f"maintenance run persistence failed: {exc}") from exc

    def get_maintenance_watermark(self, tenant_id: str, namespace: str) -> datetime | None:
        row = (
            self._connection()
            .execute(
                """
                SELECT MAX(watermark) AS watermark FROM maintenance_runs
                WHERE tenant_id = ? AND namespace = ? AND applied = 1
                """,
                (tenant_id, namespace),
            )
            .fetchone()
        )
        return _parse_dt(str(row["watermark"])) if row and row["watermark"] else None

    def find_maintenance_action_digests(self, tenant_id: str, namespace: str) -> frozenset[str]:
        rows = (
            self._connection()
            .execute(
                """
                SELECT action_digest FROM maintenance_actions
                WHERE tenant_id = ? AND namespace = ? AND applied = 1
                """,
                (tenant_id, namespace),
            )
            .fetchall()
        )
        return frozenset(str(row["action_digest"]) for row in rows)

    def save_projection_retirement(self, receipt: ProjectionRetirementReceipt) -> None:
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(receipt.receipt_id),
                        "projection_retirement",
                        str(receipt.record_id),
                        receipt.retirement_mode.value,
                        _dt(receipt.retired_at),
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(f"projection retirement receipt failed: {exc}") from exc

    def list_unprojected_records(
        self,
        tenant_id: str,
        namespace: str,
        target_identity: str,
        *,
        limit: int = 1_000,
    ) -> list[MemoryRecord]:
        rows = (
            self._connection()
            .execute(
                """
                SELECT r.record_json FROM memory_records AS r
                LEFT JOIN projection_links AS l
                  ON l.record_id = r.record_id AND l.target_identity = ?
                WHERE r.tenant_id = ? AND r.namespace = ? AND r.state = ?
                  AND l.record_id IS NULL
                ORDER BY r.recorded_at ASC LIMIT ?
                """,
                (
                    target_identity,
                    tenant_id,
                    namespace,
                    MemoryState.ACTIVE.value,
                    limit,
                ),
            )
            .fetchall()
        )
        return [self._row_to_record(row) for row in rows]

    def commit_projection_rebuild(
        self,
        capability: ServiceWriteCapability,
        receipt: ProjectionRebuildReceipt,
        *,
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        require_service_write_capability(capability)
        if not receipt.applied:
            raise StoreError("cannot persist a non-applied rebuild receipt")
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(receipt.receipt_id),
                        "projection_rebuild",
                        receipt.namespace,
                        "applied",
                        _dt(receipt.created_at),
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
                for event in outbox_events:
                    self._insert_outbox(tx, event)
        except sqlite3.Error as exc:
            raise StoreError(f"projection rebuild failed: {exc}") from exc

    def commit_legacy_projection_release(
        self,
        capability: ServiceWriteCapability,
        receipt: LegacyProjectionReleaseReceipt,
        *,
        link_updates: tuple[ProjectionLink, ...] = (),
        link_removals: tuple[tuple[UUID, str], ...] = (),
        deletion_completions: tuple[tuple[UUID, UUID], ...] = (),
        expected_links: tuple[ProjectionLink, ...] = (),
    ) -> None:
        require_service_write_capability(capability)
        if not receipt.applied:
            raise StoreError("cannot persist a non-applied legacy projection release")
        try:
            with self._transaction() as tx:
                for expected in expected_links:
                    row = tx.execute(
                        "SELECT target_identity, provider_type, link_json FROM projection_links "
                        "WHERE record_id = ? AND target_identity = ?",
                        (str(expected.record_id), expected.target_identity),
                    ).fetchone()
                    current = self._row_to_link(row) if row else None
                    if current != expected:
                        raise StoreError("projection link changed since the release was planned")
                tx.execute(
                    """
                    INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(receipt.receipt_id),
                        "legacy_projection_release",
                        receipt.namespace,
                        "applied",
                        _dt(receipt.created_at),
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
                for link in link_updates:
                    tx.execute(
                        "UPDATE projection_links SET locator = ?, created_at = ?, link_json = ? "
                        "WHERE record_id = ? AND target_identity = ?",
                        (
                            link.locator,
                            _dt(link.created_at),
                            _json(link.model_dump(mode="json")),
                            str(link.record_id),
                            link.target_identity,
                        ),
                    )
                for record_id, target_identity in link_removals:
                    tx.execute(
                        "DELETE FROM projection_links WHERE record_id = ? AND target_identity = ?",
                        (str(record_id), target_identity),
                    )
                for record_id, receipt_id in deletion_completions:
                    self._complete_deletion_tx(
                        tx,
                        record_id,
                        receipt_id,
                        receipt.created_at,
                        f"memory.legacy-release:{receipt.actor}",
                    )
        except sqlite3.Error as exc:
            raise StoreError(f"legacy projection release failed: {exc}") from exc

    def commit_graph_cutover(
        self, capability: ServiceWriteCapability, receipt: GraphCutoverReceipt
    ) -> None:
        require_service_write_capability(capability)
        if not receipt.applied:
            raise StoreError("cannot persist a non-applied graph cutover")
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(receipt.receipt_id),
                        "graph_cutover",
                        receipt.namespace,
                        "applied",
                        _dt(receipt.created_at),
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(f"graph cutover record failed: {exc}") from exc

    def list_graph_cutovers(self, tenant_id: str, namespace: str) -> list[GraphCutoverReceipt]:
        rows = (
            self._connection()
            .execute(
                "SELECT receipt_json FROM operation_receipts "
                "WHERE kind = 'graph_cutover' AND aggregate_id = ? "
                "ORDER BY created_at, receipt_id",
                (namespace,),
            )
            .fetchall()
        )
        receipts = [
            GraphCutoverReceipt.model_validate_json(str(row["receipt_json"])) for row in rows
        ]
        # aggregate_id is the namespace; the tenant is part of the receipt.
        return [receipt for receipt in receipts if receipt.tenant_id == tenant_id]

    def list_legacy_projection_releases(
        self, namespace: str
    ) -> list[LegacyProjectionReleaseReceipt]:
        rows = (
            self._connection()
            .execute(
                "SELECT receipt_json FROM operation_receipts "
                "WHERE kind = 'legacy_projection_release' AND aggregate_id = ? "
                "ORDER BY created_at, receipt_id",
                (namespace,),
            )
            .fetchall()
        )
        return [
            LegacyProjectionReleaseReceipt.model_validate_json(str(row["receipt_json"]))
            for row in rows
        ]

    def stats(self) -> dict[str, Any]:
        connection = self._connection()
        total = connection.execute("SELECT COUNT(*) AS count FROM memory_records").fetchone()
        receipts = connection.execute("SELECT COUNT(*) AS count FROM operation_receipts").fetchone()
        state_rows = connection.execute(
            "SELECT state, COUNT(*) AS count FROM memory_records GROUP BY state"
        ).fetchall()
        class_rows = connection.execute(
            "SELECT memory_class, COUNT(*) AS count FROM memory_records GROUP BY memory_class"
        ).fetchall()
        return {
            "records": int(total["count"]) if total else 0,
            "receipts": int(receipts["count"]) if receipts else 0,
            "outbox_backlog": self.outbox_backlog(),
            "by_state": {str(row["state"]): int(row["count"]) for row in state_rows},
            "by_class": {str(row["memory_class"]): int(row["count"]) for row in class_rows},
        }

    def list_expired(
        self,
        tenant_id: str,
        namespace: str,
        *,
        before: datetime,
    ) -> list[MemoryRecord]:
        rows = (
            self._connection()
            .execute(
                """
            SELECT record_json FROM memory_records
            WHERE tenant_id = ? AND namespace = ? AND state = ?
              AND valid_to IS NOT NULL AND valid_to <= ?
            ORDER BY valid_to ASC
            """,
                (tenant_id, namespace, MemoryState.ACTIVE.value, _dt(before)),
            )
            .fetchall()
        )
        return [self._row_to_record(row) for row in rows]

    def commit_archive(
        self,
        capability: ServiceWriteCapability,
        receipt: ArchiveReceipt,
        *,
        status_events: tuple[MemoryStatusEvent, ...],
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        require_service_write_capability(capability)
        if not receipt.applied:
            raise StoreError("cannot persist a non-applied archive receipt")
        event_ids = {event.record_id for event in status_events}
        if event_ids != set(receipt.archived_record_ids):
            raise StoreError("archive receipt and status events target different records")
        try:
            with self._transaction() as tx:
                self._insert_archive_receipt(tx, receipt)
                for event in status_events:
                    self._insert_status_event(tx, event)
                for outbox_event in outbox_events:
                    self._insert_outbox(tx, outbox_event)
        except sqlite3.IntegrityError as exc:
            raise StoreError(f"atomic archive violated store constraints: {exc}") from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic archive failed: {exc}") from exc

    def commit_deletion(
        self,
        capability: ServiceWriteCapability,
        receipt: DeletionReceipt,
        redacted_record: MemoryRecord,
        *,
        outbox_event: OutboxEvent | None = None,
        outbox_events: tuple[OutboxEvent, ...] = (),
        status_event: MemoryStatusEvent,
    ) -> None:
        require_service_write_capability(capability)
        if redacted_record.record_id != receipt.record_id:
            raise StoreError("deletion receipt and redacted record target differ")
        if (
            status_event.record_id != receipt.record_id
            or status_event.new_state is not redacted_record.state
        ):
            raise StoreError("deletion status event does not describe the tombstone transition")
        try:
            with self._transaction() as tx:
                existing = tx.execute(
                    "SELECT record_id FROM memory_records WHERE record_id = ?",
                    (str(receipt.record_id),),
                ).fetchone()
                if existing is None:
                    raise StoreError(f"deletion target not found: {receipt.record_id}")
                # The lifecycle event is verified against the pre-redaction
                # state; the redaction below then replaces the whole row.
                self._insert_status_event(tx, status_event)
                # Selectors are derived from the metadata the tombstone
                # redacts, so they go with it (ADR-095).
                tx.execute(
                    "DELETE FROM memory_source_selectors WHERE record_id = ?",
                    (str(receipt.record_id),),
                )
                tx.execute(
                    """
                    UPDATE memory_records SET
                        content = ?, assertion_json = ?, provenance_json = ?, evidence_json = ?,
                        confidence_json = ?, confidence_score = ?, state = ?, tags_json = ?,
                        metadata_json = ?, normalized_digest = ?, original_digest = ?,
                        supersedes_json = ?, references_json = ?, conflicts_with_json = ?,
                        record_json = ?
                    WHERE record_id = ?
                    """,
                    (
                        redacted_record.content,
                        None,
                        _json(redacted_record.provenance.model_dump(mode="json")),
                        _json([]),
                        _json(redacted_record.confidence.model_dump(mode="json")),
                        redacted_record.confidence.score,
                        redacted_record.state.value,
                        _json(redacted_record.tags),
                        _json(redacted_record.metadata),
                        redacted_record.normalized_digest,
                        redacted_record.original_digest,
                        _json([str(item) for item in redacted_record.supersedes]),
                        _json([str(item) for item in redacted_record.references]),
                        _json([str(item) for item in redacted_record.conflicts_with]),
                        _json(redacted_record.model_dump(mode="json")),
                        str(receipt.record_id),
                    ),
                )
                self._insert_deletion_receipt(tx, receipt)
                for event in (
                    *((outbox_event,) if outbox_event is not None else ()),
                    *outbox_events,
                ):
                    self._insert_outbox(tx, event)
        except sqlite3.IntegrityError as exc:
            raise StoreError(f"atomic deletion request violated store constraints: {exc}") from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic deletion request failed: {exc}") from exc

    def complete_deletion(
        self,
        record_id: UUID,
        receipt_id: UUID,
        *,
        completed_at: datetime,
        actor: str = "memory.outbox-worker",
    ) -> None:
        try:
            with self._transaction() as tx:
                self._complete_deletion_tx(tx, record_id, receipt_id, completed_at, actor)
        except sqlite3.Error as exc:
            raise StoreError(f"deletion completion failed: {exc}") from exc

    def _complete_deletion_tx(
        self,
        tx: Any,
        record_id: UUID,
        receipt_id: UUID,
        completed_at: datetime,
        actor: str,
    ) -> None:
        """Mark one verified deletion complete inside the caller's transaction."""

        record_row = tx.execute(
            "SELECT record_json FROM memory_records WHERE record_id = ?",
            (str(record_id),),
        ).fetchone()
        receipt_row = tx.execute(
            "SELECT receipt_json FROM operation_receipts WHERE receipt_id = ? AND kind = 'deletion'",
            (str(receipt_id),),
        ).fetchone()
        if record_row is None or receipt_row is None:
            raise StoreError("deletion record or receipt not found")
        # Verified deletion completes only once no target holds a copy
        # (ADR-084), including a withdrawn link still carrying legacy copies.
        remaining = tx.execute(
            "SELECT COUNT(*) FROM projection_links WHERE record_id = ?",
            (str(record_id),),
        ).fetchone()[0]
        if remaining:
            raise StoreError(
                f"deletion of {record_id} cannot complete while {remaining} "
                "projection link(s) remain unerased"
            )
        record = schema_registry.read_record(json.loads(str(record_row["record_json"])))
        receipt = DeletionReceipt.model_validate_json(str(receipt_row["receipt_json"]))
        updated_receipt = receipt.model_copy(
            update={
                "status": DeletionStatus.COMPLETE,
                "completed_at": completed_at,
            }
        )
        if record.state is not MemoryState.DELETED:
            self._insert_status_event(
                tx,
                MemoryStatusEvent(
                    record_id=record_id,
                    previous_state=record.state,
                    new_state=MemoryState.DELETED,
                    reason="projection erasure confirmed; verified deletion complete",
                    actor=actor,
                    occurred_at=completed_at,
                    receipt_id=receipt_id,
                ),
            )
        tx.execute(
            "UPDATE operation_receipts SET status = ?, receipt_json = ? WHERE receipt_id = ?",
            (
                DeletionStatus.COMPLETE.value,
                _json(updated_receipt.model_dump(mode="json")),
                str(receipt_id),
            ),
        )
