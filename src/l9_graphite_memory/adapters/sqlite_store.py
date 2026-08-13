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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from l9_graphite_memory.contracts import (
    ArchiveReceipt,
    DeletionReceipt,
    DeletionStatus,
    MemoryRecord,
    MemorySearchRequest,
    MemoryState,
    MemoryStatusEvent,
    OutboxEvent,
    OutboxStatus,
    PhaseLockReceipt,
    ProjectionLink,
    WriteReceipt,
)
from l9_graphite_memory.errors import StoreError
from l9_graphite_memory.ports.service_capability import (
    ServiceWriteCapability,
    require_service_write_capability,
)
from l9_graphite_memory.schema import schema_registry

# Register built-in migrations.
from l9_graphite_memory.schema import upcasters as _upcasters  # noqa: F401

_SCHEMA_VERSION = 5


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
                event_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox_events(status, next_attempt_at)",
            """
            CREATE TABLE IF NOT EXISTS projection_links (
                record_id TEXT NOT NULL,
                projection_name TEXT NOT NULL,
                namespace TEXT NOT NULL,
                locator TEXT NOT NULL,
                created_at TEXT NOT NULL,
                link_json TEXT NOT NULL,
                PRIMARY KEY (record_id, projection_name),
                FOREIGN KEY(record_id) REFERENCES memory_records(record_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_projection_links_locator ON projection_links(projection_name, locator)",
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
                str(row[1])
                for row in tx.execute("PRAGMA table_info(phase_locks)").fetchall()
            }
            if phase_lock_columns and "tenant_id" not in phase_lock_columns:
                tx.execute("DROP TABLE phase_locks")
            for statement in statements:
                tx.execute(statement)
            columns = {
                str(row[1])
                for row in tx.execute("PRAGMA table_info(memory_records)").fetchall()
            }
            if "references_json" not in columns:
                tx.execute(
                    "ALTER TABLE memory_records ADD COLUMN references_json TEXT NOT NULL DEFAULT '[]'"
                )
            tx.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )
        self._initialized = True

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
            _json(record.assertion.model_dump(mode="json"))
            if record.assertion
            else None,
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

    def _insert_archive_receipt(
        self, tx: sqlite3.Connection, receipt: ArchiveReceipt
    ) -> None:
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

    def _insert_deletion_receipt(
        self, tx: sqlite3.Connection, receipt: DeletionReceipt
    ) -> None:
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

    def _insert_status_event(
        self, tx: sqlite3.Connection, event: MemoryStatusEvent
    ) -> None:
        record = tx.execute(
            "SELECT record_json FROM memory_records WHERE record_id = ?",
            (str(event.record_id),),
        ).fetchone()
        if record is None:
            raise StoreError(f"status transition target not found: {event.record_id}")
        record_payload = json.loads(str(record["record_json"]))
        current_state = MemoryState(str(record_payload["state"]))
        if (
            event.previous_state is not None
            and current_state is not event.previous_state
        ):
            raise StoreError(
                f"status transition expected {event.previous_state.value} but found {current_state.value}: {event.record_id}"
            )
        record_payload["state"] = event.new_state.value
        if event.new_state is MemoryState.SUPERSEDED:
            record_payload.setdefault("temporal", {})["superseded_at"] = _dt(
                event.occurred_at
            )
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
                next_attempt_at, last_error, created_at, delivered_at, event_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    ) -> None:
        require_service_write_capability(capability)
        try:
            with self._transaction() as tx:
                if record is not None:
                    self._insert_record(tx, record)
                self._insert_receipt(tx, receipt)
                for status_event in status_events:
                    self._insert_status_event(tx, status_event)
                for outbox_event in outbox_events:
                    self._insert_outbox(tx, outbox_event)
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                f"atomic memory write violated store constraints: {exc}"
            ) from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic memory write failed: {exc}") from exc

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
        limit: int = 1_000,
    ) -> list[MemoryRecord]:
        params: list[Any] = [tenant_id, namespace]
        sql = "SELECT record_json FROM memory_records WHERE tenant_id = ? AND namespace = ?"
        if states:
            marks = ",".join("?" for _ in states)
            sql += f" AND state IN ({marks})"
            params.extend(item.value for item in states)
        sql += " ORDER BY recorded_at DESC LIMIT ?"
        params.append(limit)
        rows = self._connection().execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def transition_state(self, event: MemoryStatusEvent) -> None:
        with self._transaction() as tx:
            self._insert_status_event(tx, event)

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
        return (
            PhaseLockReceipt.model_validate_json(str(row["receipt_json"]))
            if row
            else None
        )

    def claim_outbox(self, *, limit: int, now: datetime) -> list[OutboxEvent]:
        with self._transaction() as tx:
            rows = tx.execute(
                """
                SELECT event_id, event_json FROM outbox_events
                WHERE status IN (?, ?) AND next_attempt_at <= ?
                ORDER BY created_at ASC LIMIT ?
                """,
                (OutboxStatus.PENDING.value, OutboxStatus.RETRY.value, _dt(now), limit),
            ).fetchall()
            event_ids = [str(row["event_id"]) for row in rows]
            for event_id in event_ids:
                tx.execute(
                    "UPDATE outbox_events SET status = ? WHERE event_id = ?",
                    (OutboxStatus.PROCESSING.value, event_id),
                )
            events: list[OutboxEvent] = []
            for row in rows:
                event = OutboxEvent.model_validate_json(str(row["event_json"]))
                events.append(
                    event.model_copy(update={"status": OutboxStatus.PROCESSING})
                )
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
    ) -> None:
        with self._transaction() as tx:
            row = tx.execute(
                "SELECT event_json FROM outbox_events WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
            if row is None:
                raise StoreError(f"outbox event not found: {event_id}")
            event = OutboxEvent.model_validate_json(str(row["event_json"]))
            updated = event.model_copy(
                update={
                    "status": status,
                    "attempts": attempts,
                    "next_attempt_at": next_attempt_at,
                    "last_error": last_error,
                    "delivered_at": delivered_at,
                }
            )
            tx.execute(
                """
                UPDATE outbox_events
                SET status = ?, attempts = ?, next_attempt_at = ?, last_error = ?, delivered_at = ?, event_json = ?
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
                tx.execute(
                    """
                    INSERT INTO projection_links (
                        record_id, projection_name, namespace, locator, created_at, link_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id, projection_name) DO UPDATE SET
                        namespace = excluded.namespace,
                        locator = excluded.locator,
                        created_at = excluded.created_at,
                        link_json = excluded.link_json
                    """,
                    (
                        str(link.record_id),
                        link.projection_name,
                        link.namespace,
                        link.locator,
                        _dt(link.created_at),
                        _json(link.model_dump(mode="json")),
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(f"projection link persistence failed: {exc}") from exc

    def get_projection_link(
        self,
        record_id: UUID,
        projection_name: str,
    ) -> ProjectionLink | None:
        row = (
            self._connection()
            .execute(
                "SELECT link_json FROM projection_links WHERE record_id = ? AND projection_name = ?",
                (str(record_id), projection_name),
            )
            .fetchone()
        )
        if row is None:
            return None
        return ProjectionLink.model_validate_json(str(row["link_json"]))

    def delete_projection_link(self, record_id: UUID, projection_name: str) -> None:
        try:
            with self._transaction() as tx:
                tx.execute(
                    "DELETE FROM projection_links WHERE record_id = ? AND projection_name = ?",
                    (str(record_id), projection_name),
                )
        except sqlite3.Error as exc:
            raise StoreError(f"projection link deletion failed: {exc}") from exc

    def stats(self) -> dict[str, Any]:
        connection = self._connection()
        total = connection.execute(
            "SELECT COUNT(*) AS count FROM memory_records"
        ).fetchone()
        receipts = connection.execute(
            "SELECT COUNT(*) AS count FROM operation_receipts"
        ).fetchone()
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
            "by_class": {
                str(row["memory_class"]): int(row["count"]) for row in class_rows
            },
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
    ) -> None:
        require_service_write_capability(capability)
        if not receipt.applied:
            raise StoreError("cannot persist a non-applied archive receipt")
        event_ids = {event.record_id for event in status_events}
        if event_ids != set(receipt.archived_record_ids):
            raise StoreError(
                "archive receipt and status events target different records"
            )
        try:
            with self._transaction() as tx:
                self._insert_archive_receipt(tx, receipt)
                for event in status_events:
                    self._insert_status_event(tx, event)
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                f"atomic archive violated store constraints: {exc}"
            ) from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic archive failed: {exc}") from exc

    def commit_deletion(
        self,
        capability: ServiceWriteCapability,
        receipt: DeletionReceipt,
        redacted_record: MemoryRecord,
        *,
        outbox_event: OutboxEvent | None,
    ) -> None:
        require_service_write_capability(capability)
        if redacted_record.record_id != receipt.record_id:
            raise StoreError("deletion receipt and redacted record target differ")
        try:
            with self._transaction() as tx:
                existing = tx.execute(
                    "SELECT record_id FROM memory_records WHERE record_id = ?",
                    (str(receipt.record_id),),
                ).fetchone()
                if existing is None:
                    raise StoreError(f"deletion target not found: {receipt.record_id}")
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
                if outbox_event is not None:
                    self._insert_outbox(tx, outbox_event)
        except sqlite3.IntegrityError as exc:
            raise StoreError(
                f"atomic deletion request violated store constraints: {exc}"
            ) from exc
        except sqlite3.Error as exc:
            raise StoreError(f"atomic deletion request failed: {exc}") from exc

    def complete_deletion(
        self,
        record_id: UUID,
        receipt_id: UUID,
        *,
        completed_at: datetime,
    ) -> None:
        try:
            with self._transaction() as tx:
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
                record = schema_registry.read_record(
                    json.loads(str(record_row["record_json"]))
                )
                receipt = DeletionReceipt.model_validate_json(
                    str(receipt_row["receipt_json"])
                )
                updated_record = record.model_copy(
                    update={"state": MemoryState.DELETED}
                )
                updated_receipt = receipt.model_copy(
                    update={
                        "status": DeletionStatus.COMPLETE,
                        "completed_at": completed_at,
                    }
                )
                tx.execute(
                    "UPDATE memory_records SET state = ?, record_json = ? WHERE record_id = ?",
                    (
                        MemoryState.DELETED.value,
                        _json(updated_record.model_dump(mode="json")),
                        str(record_id),
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
        except sqlite3.Error as exc:
            raise StoreError(f"deletion completion failed: {exc}") from exc
