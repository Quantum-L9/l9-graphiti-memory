# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/postgres_store.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""PostgreSQL canonical store for shared, durable, multi-agent deployments."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from l9_graphite_memory.contracts import (
    ArchiveReceipt,
    DeletionReceipt,
    DeletionStatus,
    MaintenanceRunReceipt,
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
from l9_graphite_memory.errors import ConfigurationError, StoreError
from l9_graphite_memory.schema import schema_registry

# Register built-in migrations.
from l9_graphite_memory.schema import upcasters as _upcasters  # noqa: F401

if TYPE_CHECKING:  # pragma: no cover - typing only
    from psycopg2.extensions import connection as _Connection
else:  # pragma: no cover - runtime alias
    _Connection = Any

_SCHEMA_VERSION = 6


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _driver() -> Any:
    """Import the driver lazily so the base package stays dependency-light."""

    try:
        import psycopg2
        import psycopg2.extras
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
        raise ConfigurationError(
            "the postgres store backend requires the 'postgres' extra "
            "(pip install 'l9-graphite-memory[postgres]')"
        ) from exc
    return psycopg2


class PostgresRecordStore:
    """Shared canonical store.

    Semantics match :class:`SQLiteRecordStore` exactly -- the conformance suite
    runs both against the same contract. The difference is deployment shape: one
    PostgreSQL instance is the single canonical authority for every agent and
    worker, where a SQLite file is authoritative only for the process that can
    reach that file.
    """

    name = "postgres"

    def __init__(self, dsn: str, *, statement_timeout_ms: int = 30_000) -> None:
        if not dsn or not dsn.strip():
            raise ConfigurationError("postgres store requires a non-empty DSN")
        self.dsn = dsn
        self.statement_timeout_ms = statement_timeout_ms
        self._local = threading.local()
        self._initialized = False

    # -- connection management ------------------------------------------------

    def _connection(self) -> Any:
        connection = getattr(self._local, "connection", None)
        if connection is None or connection.closed:
            psycopg2 = _driver()
            try:
                connection = psycopg2.connect(self.dsn)
            except psycopg2.Error as exc:
                raise StoreError(f"postgres connection failed: {exc}") from exc
            connection.autocommit = False
            with connection.cursor() as cursor:
                cursor.execute(
                    "SET statement_timeout = %s", (self.statement_timeout_ms,)
                )
            connection.commit()
            self._local.connection = connection
        return connection

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        """Read cursor. Reads run in their own transaction and never leave one open."""

        psycopg2 = _driver()
        connection = self._connection()
        try:
            with connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cursor:
                yield cursor
            connection.commit()
        except psycopg2.Error as exc:
            connection.rollback()
            raise StoreError(f"postgres read failed: {exc}") from exc

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        psycopg2 = _driver()
        connection = self._connection()
        try:
            with connection.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            ) as cursor:
                yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    # -- lifecycle ------------------------------------------------------------

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL
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
                valid_from TIMESTAMPTZ NOT NULL,
                valid_to TIMESTAMPTZ,
                recorded_at TIMESTAMPTZ NOT NULL,
                source_observed_at TIMESTAMPTZ,
                superseded_at TIMESTAMPTZ,
                provenance_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                confidence_json TEXT NOT NULL,
                confidence_score DOUBLE PRECISION NOT NULL,
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
                created_at TIMESTAMPTZ NOT NULL,
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
                record_id TEXT NOT NULL REFERENCES memory_records(record_id),
                previous_state TEXT,
                new_state TEXT NOT NULL,
                reason TEXT NOT NULL,
                actor TEXT NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL,
                receipt_id TEXT,
                event_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS operation_receipts (
                receipt_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                aggregate_id TEXT,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
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
                next_attempt_at TIMESTAMPTZ NOT NULL,
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                delivered_at TIMESTAMPTZ,
                lease_id TEXT,
                lease_owner TEXT,
                lease_expires_at TIMESTAMPTZ,
                event_json TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_outbox_due ON outbox_events(status, next_attempt_at)",
            "CREATE INDEX IF NOT EXISTS idx_outbox_lease ON outbox_events(status, lease_expires_at)",
            "ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS lease_id TEXT",
            "ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS lease_owner TEXT",
            "ALTER TABLE outbox_events ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ",
            """
            CREATE TABLE IF NOT EXISTS projection_links (
                record_id TEXT NOT NULL REFERENCES memory_records(record_id),
                projection_name TEXT NOT NULL,
                namespace TEXT NOT NULL,
                locator TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                link_json TEXT NOT NULL,
                PRIMARY KEY (record_id, projection_name)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_projection_links_locator ON projection_links(projection_name, locator)",
            """
            CREATE TABLE IF NOT EXISTS maintenance_runs (
                run_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                namespace TEXT NOT NULL,
                status TEXT NOT NULL,
                applied BOOLEAN NOT NULL,
                watermark TIMESTAMPTZ NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
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
                applied BOOLEAN NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (tenant_id, namespace, action_digest)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS phase_locks (
                lock_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                task_signature TEXT NOT NULL,
                granted BOOLEAN NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                receipt_json TEXT NOT NULL,
                UNIQUE(namespace, task_signature)
            )
            """,
        ]
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                for statement in statements:
                    tx.execute(statement)
                tx.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (%s, %s) "
                    "ON CONFLICT (version) DO NOTHING",
                    (_SCHEMA_VERSION, datetime.now(timezone.utc)),
                )
        except psycopg2.Error as exc:
            raise StoreError(f"postgres schema initialization failed: {exc}") from exc
        self._initialized = True

    def close(self) -> None:
        connection = getattr(self._local, "connection", None)
        if connection is not None and not connection.closed:
            connection.close()
        self._local.connection = None
        self._initialized = False

    def health(self) -> dict[str, Any]:
        try:
            with self._cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM memory_records")
                row = cursor.fetchone()
            return {
                "name": self.name,
                "healthy": self._initialized,
                "records": int(row["count"]) if row else 0,
                "schema_version": _SCHEMA_VERSION,
            }
        except StoreError as exc:
            return {"name": self.name, "healthy": False, "error": str(exc)}

    # -- serialization --------------------------------------------------------

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
            record.temporal.valid_from,
            record.temporal.valid_to,
            record.temporal.recorded_at,
            record.temporal.source_observed_at,
            record.temporal.superseded_at,
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
            record.created_at,
            _json(payload),
        )

    @staticmethod
    def _row_to_record(row: Any) -> MemoryRecord:
        return schema_registry.read_record(json.loads(str(row["record_json"])))

    def _insert_record(self, tx: Any, record: MemoryRecord) -> None:
        tx.execute(
            """
            INSERT INTO memory_records (
                record_id, schema_version, tenant_id, namespace, memory_class, content,
                assertion_json, valid_from, valid_to, recorded_at, source_observed_at,
                superseded_at, provenance_json, evidence_json, confidence_json,
                confidence_score, state, tags_json, metadata_json, normalized_digest,
                original_digest, idempotency_key, supersedes_json, references_json,
                conflicts_with_json, created_by, created_at, record_json
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            self._record_values(record),
        )

    @staticmethod
    def _insert_operation_receipt(
        tx: Any,
        *,
        receipt_id: UUID,
        kind: str,
        aggregate_id: str | None,
        status: str,
        created_at: datetime,
        payload: dict[str, Any],
    ) -> None:
        tx.execute(
            """
            INSERT INTO operation_receipts(receipt_id, kind, aggregate_id, status, created_at, receipt_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                str(receipt_id),
                kind,
                aggregate_id,
                status,
                created_at,
                _json(payload),
            ),
        )

    def _insert_status_event(self, tx: Any, event: MemoryStatusEvent) -> None:
        tx.execute(
            "SELECT record_json FROM memory_records WHERE record_id = %s FOR UPDATE",
            (str(event.record_id),),
        )
        row = tx.fetchone()
        if row is None:
            raise StoreError(f"status transition target not found: {event.record_id}")
        record_payload = json.loads(str(row["record_json"]))
        current_state = MemoryState(str(record_payload["state"]))
        if (
            event.previous_state is not None
            and current_state is not event.previous_state
        ):
            raise StoreError(
                f"status transition expected {event.previous_state.value} "
                f"but found {current_state.value}: {event.record_id}"
            )
        record_payload["state"] = event.new_state.value
        superseded_at: datetime | None = None
        if event.new_state is MemoryState.SUPERSEDED:
            record_payload.setdefault("temporal", {})["superseded_at"] = (
                event.occurred_at.isoformat()
            )
            superseded_at = event.occurred_at
        else:
            existing = record_payload.get("temporal", {}).get("superseded_at")
            superseded_at = datetime.fromisoformat(existing) if existing else None
        tx.execute(
            """
            UPDATE memory_records
            SET state = %s, superseded_at = %s, record_json = %s
            WHERE record_id = %s
            """,
            (
                event.new_state.value,
                superseded_at,
                _json(record_payload),
                str(event.record_id),
            ),
        )
        tx.execute(
            """
            INSERT INTO memory_status_events(
                event_id, record_id, previous_state, new_state, reason, actor,
                occurred_at, receipt_id, event_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(event.event_id),
                str(event.record_id),
                event.previous_state.value if event.previous_state else None,
                event.new_state.value,
                event.reason,
                event.actor,
                event.occurred_at,
                str(event.receipt_id) if event.receipt_id else None,
                _json(event.model_dump(mode="json")),
            ),
        )

    @staticmethod
    def _insert_outbox(tx: Any, event: OutboxEvent) -> None:
        tx.execute(
            """
            INSERT INTO outbox_events(
                event_id, event_type, aggregate_id, namespace, status, attempts,
                next_attempt_at, last_error, created_at, delivered_at,
                lease_id, lease_owner, lease_expires_at, event_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(event.event_id),
                event.event_type,
                str(event.aggregate_id),
                event.namespace,
                event.status.value,
                event.attempts,
                event.next_attempt_at,
                event.last_error,
                event.created_at,
                event.delivered_at,
                str(event.lease_id) if event.lease_id else None,
                event.lease_owner,
                event.lease_expires_at,
                _json(event.model_dump(mode="json")),
            ),
        )

    # -- canonical writes -----------------------------------------------------

    def commit_write(
        self,
        record: MemoryRecord | None,
        receipt: WriteReceipt,
        *,
        outbox_events: tuple[OutboxEvent, ...] = (),
        status_events: tuple[MemoryStatusEvent, ...] = (),
    ) -> None:
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                if record is not None:
                    self._insert_record(tx, record)
                self._insert_operation_receipt(
                    tx,
                    receipt_id=receipt.receipt_id,
                    kind="write",
                    aggregate_id=str(receipt.record_id) if receipt.record_id else None,
                    status=receipt.status.value,
                    created_at=receipt.created_at,
                    payload=receipt.model_dump(mode="json"),
                )
                for status_event in status_events:
                    self._insert_status_event(tx, status_event)
                for outbox_event in outbox_events:
                    self._insert_outbox(tx, outbox_event)
        except psycopg2.IntegrityError as exc:
            raise StoreError(
                f"atomic memory write violated store constraints: {exc}"
            ) from exc
        except psycopg2.Error as exc:
            raise StoreError(f"atomic memory write failed: {exc}") from exc

    # -- reads ----------------------------------------------------------------

    def get_record(self, record_id: UUID) -> MemoryRecord | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT record_json FROM memory_records WHERE record_id = %s",
                (str(record_id),),
            )
            row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def find_by_idempotency(
        self, tenant_id: str, namespace: str, idempotency_key: str
    ) -> MemoryRecord | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT record_json FROM memory_records
                WHERE tenant_id = %s AND namespace = %s AND idempotency_key = %s
                """,
                (tenant_id, namespace, idempotency_key),
            )
            row = cursor.fetchone()
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
        params: list[Any] = [tenant_id, tuple(namespaces), tuple(states)]
        where = [
            "tenant_id = %s",
            "namespace IN %s",
            "state IN %s",
            "confidence_score >= %s",
            "valid_from <= %s",
            "(valid_to IS NULL OR valid_to > %s)",
            "recorded_at <= %s",
        ]
        params.extend(
            [
                request.min_confidence,
                request.valid_at,
                request.valid_at,
                request.recorded_before or request.valid_at,
            ]
        )
        if request.memory_classes:
            where.append("memory_class IN %s")
            params.append(tuple(item.value for item in request.memory_classes))
        params.append(request.limit * 20)
        sql = (
            "SELECT record_json FROM memory_records "
            f"WHERE {' AND '.join(where)} ORDER BY recorded_at DESC LIMIT %s"
        )
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
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
        sql = (
            "SELECT record_json FROM memory_records "
            "WHERE tenant_id = %s AND namespace = %s"
        )
        if states:
            sql += " AND state IN %s"
            params.append(tuple(item.value for item in states))
        sql += " ORDER BY recorded_at DESC LIMIT %s"
        params.append(limit)
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_expired(
        self,
        tenant_id: str,
        namespace: str,
        *,
        before: datetime,
    ) -> list[MemoryRecord]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT record_json FROM memory_records
                WHERE tenant_id = %s AND namespace = %s AND state = %s
                  AND valid_to IS NOT NULL AND valid_to <= %s
                ORDER BY valid_to ASC
                """,
                (tenant_id, namespace, MemoryState.ACTIVE.value, before),
            )
            rows = cursor.fetchall()
        return [self._row_to_record(row) for row in rows]

    def transition_state(self, event: MemoryStatusEvent) -> None:
        with self._transaction() as tx:
            self._insert_status_event(tx, event)

    # -- phase locks ----------------------------------------------------------

    def save_phase_lock(self, receipt: PhaseLockReceipt) -> None:
        with self._transaction() as tx:
            tx.execute(
                """
                INSERT INTO phase_locks(lock_id, namespace, task_signature, granted, expires_at, created_at, receipt_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(namespace, task_signature) DO UPDATE SET
                    lock_id = excluded.lock_id,
                    granted = excluded.granted,
                    expires_at = excluded.expires_at,
                    created_at = excluded.created_at,
                    receipt_json = excluded.receipt_json
                """,
                (
                    str(receipt.lock_id),
                    receipt.namespace,
                    receipt.task_signature,
                    receipt.granted,
                    receipt.expires_at,
                    receipt.created_at,
                    _json(receipt.model_dump(mode="json")),
                ),
            )

    def get_phase_lock(
        self, namespace: str, task_signature: str
    ) -> PhaseLockReceipt | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT receipt_json FROM phase_locks WHERE namespace = %s AND task_signature = %s",
                (namespace, task_signature),
            )
            row = cursor.fetchone()
        return (
            PhaseLockReceipt.model_validate_json(str(row["receipt_json"]))
            if row
            else None
        )

    # -- outbox ---------------------------------------------------------------

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
            # SKIP LOCKED makes two concurrent claim cycles disjoint: a row
            # another transaction is already claiming is passed over rather
            # than waited on, so no event can be owned twice.
            tx.execute(
                """
                SELECT event_id, event_json FROM outbox_events
                WHERE (status IN (%s, %s) AND next_attempt_at <= %s)
                   OR (status = %s AND (lease_expires_at IS NULL OR lease_expires_at <= %s))
                ORDER BY created_at ASC LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (
                    OutboxStatus.PENDING.value,
                    OutboxStatus.RETRY.value,
                    now,
                    OutboxStatus.PROCESSING.value,
                    now,
                    limit,
                ),
            )
            rows = tx.fetchall()
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
                    SET status = %s, lease_id = %s, lease_owner = %s,
                        lease_expires_at = %s, event_json = %s
                    WHERE event_id = %s
                    """,
                    (
                        OutboxStatus.PROCESSING.value,
                        str(leased.lease_id),
                        lease_owner,
                        expires_at,
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
            tx.execute(
                "SELECT event_json FROM outbox_events WHERE event_id = %s FOR UPDATE",
                (str(event_id),),
            )
            row = tx.fetchone()
            if row is None:
                raise StoreError(f"outbox event not found: {event_id}")
            event = OutboxEvent.model_validate_json(str(row["event_json"]))
            if lease_id is not None and event.lease_id != lease_id:
                raise StoreError(
                    f"outbox lease is no longer held for {event_id}; "
                    "another worker owns this event"
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
                SET status = %s, attempts = %s, next_attempt_at = %s, last_error = %s,
                    delivered_at = %s, lease_id = NULL, lease_owner = NULL,
                    lease_expires_at = NULL, event_json = %s
                WHERE event_id = %s
                """,
                (
                    status.value,
                    attempts,
                    next_attempt_at,
                    last_error,
                    delivered_at,
                    _json(updated.model_dump(mode="json")),
                    str(event_id),
                ),
            )

    def outbox_backlog(self) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM outbox_events WHERE status NOT IN (%s, %s)",
                (OutboxStatus.DELIVERED.value, OutboxStatus.DEAD.value),
            )
            row = cursor.fetchone()
        return int(row["count"]) if row else 0

    # -- projection links -----------------------------------------------------

    def save_projection_link(self, link: ProjectionLink) -> None:
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO projection_links (
                        record_id, projection_name, namespace, locator, created_at, link_json
                    ) VALUES (%s, %s, %s, %s, %s, %s)
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
                        link.created_at,
                        _json(link.model_dump(mode="json")),
                    ),
                )
        except psycopg2.Error as exc:
            raise StoreError(f"projection link persistence failed: {exc}") from exc

    def get_projection_link(
        self,
        record_id: UUID,
        projection_name: str,
    ) -> ProjectionLink | None:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT link_json FROM projection_links WHERE record_id = %s AND projection_name = %s",
                (str(record_id), projection_name),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ProjectionLink.model_validate_json(str(row["link_json"]))

    def delete_projection_link(self, record_id: UUID, projection_name: str) -> None:
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                tx.execute(
                    "DELETE FROM projection_links WHERE record_id = %s AND projection_name = %s",
                    (str(record_id), projection_name),
                )
        except psycopg2.Error as exc:
            raise StoreError(f"projection link deletion failed: {exc}") from exc

    # -- maintenance ledger ---------------------------------------------------

    def save_maintenance_run(self, receipt: MaintenanceRunReceipt) -> None:
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                tx.execute(
                    """
                    INSERT INTO maintenance_runs(
                        run_id, tenant_id, namespace, status, applied, watermark,
                        started_at, completed_at, receipt_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(receipt.run_id),
                        receipt.tenant_id,
                        receipt.namespace,
                        receipt.status.value,
                        receipt.applied,
                        receipt.watermark,
                        receipt.started_at,
                        receipt.completed_at,
                        _json(receipt.model_dump(mode="json")),
                    ),
                )
                for action in receipt.actions:
                    if not action.applied:
                        continue
                    tx.execute(
                        """
                        INSERT INTO maintenance_actions(
                            action_digest, run_id, tenant_id, namespace, operation,
                            applied, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, namespace, action_digest) DO NOTHING
                        """,
                        (
                            action.action_digest,
                            str(receipt.run_id),
                            receipt.tenant_id,
                            receipt.namespace,
                            action.operation.value,
                            True,
                            receipt.started_at,
                        ),
                    )
        except psycopg2.Error as exc:
            raise StoreError(f"maintenance run persistence failed: {exc}") from exc

    def get_maintenance_watermark(
        self, tenant_id: str, namespace: str
    ) -> datetime | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT MAX(watermark) AS watermark FROM maintenance_runs
                WHERE tenant_id = %s AND namespace = %s AND applied = TRUE
                """,
                (tenant_id, namespace),
            )
            row = cursor.fetchone()
        watermark = row["watermark"] if row else None
        return watermark if isinstance(watermark, datetime) else None

    def find_maintenance_action_digests(
        self, tenant_id: str, namespace: str
    ) -> frozenset[str]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT action_digest FROM maintenance_actions
                WHERE tenant_id = %s AND namespace = %s AND applied = TRUE
                """,
                (tenant_id, namespace),
            )
            rows = cursor.fetchall()
        return frozenset(str(row["action_digest"]) for row in rows)

    # -- statistics -----------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        with self._cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM memory_records")
            total = cursor.fetchone()
            cursor.execute("SELECT COUNT(*) AS count FROM operation_receipts")
            receipts = cursor.fetchone()
            cursor.execute(
                "SELECT state, COUNT(*) AS count FROM memory_records GROUP BY state"
            )
            state_rows = cursor.fetchall()
            cursor.execute(
                "SELECT memory_class, COUNT(*) AS count FROM memory_records GROUP BY memory_class"
            )
            class_rows = cursor.fetchall()
        return {
            "records": int(total["count"]) if total else 0,
            "receipts": int(receipts["count"]) if receipts else 0,
            "outbox_backlog": self.outbox_backlog(),
            "by_state": {str(row["state"]): int(row["count"]) for row in state_rows},
            "by_class": {
                str(row["memory_class"]): int(row["count"]) for row in class_rows
            },
        }

    # -- retention and privacy ------------------------------------------------

    def commit_archive(
        self,
        receipt: ArchiveReceipt,
        *,
        status_events: tuple[MemoryStatusEvent, ...],
        outbox_events: tuple[OutboxEvent, ...] = (),
    ) -> None:
        if not receipt.applied:
            raise StoreError("cannot persist a non-applied archive receipt")
        event_ids = {event.record_id for event in status_events}
        if event_ids != set(receipt.archived_record_ids):
            raise StoreError(
                "archive receipt and status events target different records"
            )
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                self._insert_operation_receipt(
                    tx,
                    receipt_id=receipt.receipt_id,
                    kind="archive",
                    aggregate_id=receipt.namespace,
                    status=receipt.status.value,
                    created_at=receipt.created_at,
                    payload=receipt.model_dump(mode="json"),
                )
                for event in status_events:
                    self._insert_status_event(tx, event)
                for outbox_event in outbox_events:
                    self._insert_outbox(tx, outbox_event)
        except psycopg2.IntegrityError as exc:
            raise StoreError(
                f"atomic archive violated store constraints: {exc}"
            ) from exc
        except psycopg2.Error as exc:
            raise StoreError(f"atomic archive failed: {exc}") from exc

    def commit_deletion(
        self,
        receipt: DeletionReceipt,
        redacted_record: MemoryRecord,
        *,
        outbox_event: OutboxEvent | None,
    ) -> None:
        if redacted_record.record_id != receipt.record_id:
            raise StoreError("deletion receipt and redacted record target differ")
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                tx.execute(
                    "SELECT record_id FROM memory_records WHERE record_id = %s FOR UPDATE",
                    (str(receipt.record_id),),
                )
                if tx.fetchone() is None:
                    raise StoreError(f"deletion target not found: {receipt.record_id}")
                tx.execute(
                    """
                    UPDATE memory_records SET
                        content = %s, assertion_json = %s, provenance_json = %s, evidence_json = %s,
                        confidence_json = %s, confidence_score = %s, state = %s, tags_json = %s,
                        metadata_json = %s, normalized_digest = %s, original_digest = %s,
                        supersedes_json = %s, references_json = %s, conflicts_with_json = %s,
                        record_json = %s
                    WHERE record_id = %s
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
                self._insert_operation_receipt(
                    tx,
                    receipt_id=receipt.receipt_id,
                    kind="deletion",
                    aggregate_id=str(receipt.record_id),
                    status=receipt.status.value,
                    created_at=receipt.created_at,
                    payload=receipt.model_dump(mode="json"),
                )
                if outbox_event is not None:
                    self._insert_outbox(tx, outbox_event)
        except psycopg2.IntegrityError as exc:
            raise StoreError(
                f"atomic deletion request violated store constraints: {exc}"
            ) from exc
        except psycopg2.Error as exc:
            raise StoreError(f"atomic deletion request failed: {exc}") from exc

    def complete_deletion(
        self,
        record_id: UUID,
        receipt_id: UUID,
        *,
        completed_at: datetime,
    ) -> None:
        psycopg2 = _driver()
        try:
            with self._transaction() as tx:
                tx.execute(
                    "SELECT record_json FROM memory_records WHERE record_id = %s FOR UPDATE",
                    (str(record_id),),
                )
                record_row = tx.fetchone()
                tx.execute(
                    "SELECT receipt_json FROM operation_receipts "
                    "WHERE receipt_id = %s AND kind = 'deletion' FOR UPDATE",
                    (str(receipt_id),),
                )
                receipt_row = tx.fetchone()
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
                    "UPDATE memory_records SET state = %s, record_json = %s WHERE record_id = %s",
                    (
                        MemoryState.DELETED.value,
                        _json(updated_record.model_dump(mode="json")),
                        str(record_id),
                    ),
                )
                tx.execute(
                    "UPDATE operation_receipts SET status = %s, receipt_json = %s WHERE receipt_id = %s",
                    (
                        DeletionStatus.COMPLETE.value,
                        _json(updated_receipt.model_dump(mode="json")),
                        str(receipt_id),
                    ),
                )
        except psycopg2.Error as exc:
            raise StoreError(f"deletion completion failed: {exc}") from exc
