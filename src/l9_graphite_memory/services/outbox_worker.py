# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/services/outbox_worker.py
#   layer: service
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Deliver committed outbox events to optional graph projections."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from datetime import datetime, timedelta

from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.contracts import OutboxEvent, OutboxStatus, ProjectionLink
from l9_graphite_memory.errors import StoreError
from l9_graphite_memory.observability import configure_logging, get_logger
from l9_graphite_memory.ports import Clock, ProjectionAdapter, RecordStore, SystemClock

log = get_logger("l9.memory.outbox")


class OutboxWorker:
    def __init__(
        self,
        store: RecordStore,
        projection: ProjectionAdapter,
        settings: MemorySettings,
        *,
        clock: Clock | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.store = store
        self.projection = projection
        self.settings = settings
        self.clock = clock or SystemClock()
        # Identifies this worker in outbox leases so an operator can see which
        # worker holds a claim and which one abandoned it.
        self.worker_id = worker_id or f"{socket.gethostname()}:{os.getpid()}"

    def _settle(
        self,
        event: OutboxEvent,
        *,
        status: OutboxStatus,
        attempts: int,
        next_attempt_at: datetime,
        last_error: str | None,
        delivered_at: datetime | None = None,
    ) -> bool:
        """Record the outcome of a leased event.

        Returns False when this worker no longer holds the lease, which means
        another worker recovered the event and owns its outcome. Writing the
        outcome anyway would overwrite that worker's result, so the caller
        drops it instead.
        """

        try:
            self.store.update_outbox(
                event.event_id,
                status=status,
                attempts=attempts,
                next_attempt_at=next_attempt_at,
                last_error=last_error,
                delivered_at=delivered_at,
                lease_id=event.lease_id,
            )
        except StoreError as exc:
            log.warning(
                "outbox_lease_lost",
                extra={
                    "event_id": str(event.event_id),
                    "worker_id": self.worker_id,
                    "error": str(exc),
                },
            )
            return False
        return True

    def run_once(self) -> dict[str, int]:
        if self.projection.name == "none":
            return {
                "claimed": 0,
                "delivered": 0,
                "retried": 0,
                "dead": 0,
                "lease_lost": 0,
            }
        now = self.clock.now()
        events = self.store.claim_outbox(
            limit=self.settings.outbox_batch_size,
            now=now,
            lease_seconds=self.settings.outbox_lease_seconds,
            lease_owner=self.worker_id,
        )
        delivered = retried = dead = lost = 0
        for event in events:
            attempts = event.attempts + 1
            try:
                if event.event_type == "memory.record.project":
                    record = self.store.get_record(event.aggregate_id)
                    if record is None:
                        raise RuntimeError(
                            f"outbox aggregate not found: {event.aggregate_id}"
                        )
                    result = self.projection.project(record)
                    locator = (
                        result.get("locator") if isinstance(result, dict) else None
                    )
                    if not isinstance(locator, str) or not locator.strip():
                        raise RuntimeError(
                            f"projection {self.projection.name} did not return a stable locator "
                            f"for record {record.record_id}"
                        )
                    self.store.save_projection_link(
                        ProjectionLink(
                            record_id=record.record_id,
                            namespace=record.namespace,
                            projection_name=self.projection.name,
                            locator=locator,
                            metadata={
                                "transport_result": result,
                                "outbox_event_id": str(event.event_id),
                            },
                            created_at=now,
                        )
                    )
                elif event.event_type == "memory.record.erase":
                    link = self.store.get_projection_link(
                        event.aggregate_id, self.projection.name
                    )
                    if link is None:
                        raise RuntimeError(
                            f"projection locator not found for {event.aggregate_id} on {self.projection.name}"
                        )
                    self.projection.erase(
                        event.aggregate_id,
                        event.namespace,
                        locator=link.locator,
                    )
                    self.store.delete_projection_link(
                        event.aggregate_id, self.projection.name
                    )
                    receipt_id = event.payload.get("deletion_receipt_id")
                    if not isinstance(receipt_id, str):
                        raise RuntimeError(
                            "deletion outbox event lacks deletion_receipt_id"
                        )
                    from uuid import UUID

                    self.store.complete_deletion(
                        event.aggregate_id,
                        UUID(receipt_id),
                        completed_at=now,
                    )
                else:
                    raise RuntimeError(
                        f"unsupported outbox event type: {event.event_type}"
                    )
                settled = self._settle(
                    event,
                    status=OutboxStatus.DELIVERED,
                    attempts=attempts,
                    next_attempt_at=now,
                    last_error=None,
                    delivered_at=now,
                )
                if settled:
                    delivered += 1
                else:
                    lost += 1
            except Exception as exc:  # noqa: BLE001
                if attempts >= self.settings.outbox_max_attempts:
                    status = OutboxStatus.DEAD
                    dead += 1
                    next_attempt = now
                else:
                    status = OutboxStatus.RETRY
                    retried += 1
                    delay = self.settings.outbox_base_delay_seconds * (
                        2 ** min(attempts - 1, 10)
                    )
                    next_attempt = now + timedelta(seconds=delay)
                if not self._settle(
                    event,
                    status=status,
                    attempts=attempts,
                    next_attempt_at=next_attempt,
                    last_error=str(exc),
                ):
                    if status is OutboxStatus.DEAD:
                        dead -= 1
                    else:
                        retried -= 1
                    lost += 1
                    continue
                log.warning(
                    "outbox_delivery_failed",
                    extra={
                        "event_id": str(event.event_id),
                        "attempts": attempts,
                        "status": status.value,
                        "error": str(exc),
                    },
                )
        return {
            "claimed": len(events),
            "delivered": delivered,
            "retried": retried,
            "dead": dead,
            "lease_lost": lost,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver L9 memory outbox events")
    parser.add_argument(
        "--once", action="store_true", help="Process one batch and exit"
    )
    parser.add_argument(
        "--interval", type=float, default=5.0, help="Polling interval in seconds"
    )
    parser.add_argument(
        "--config", default=None, help="Optional YAML configuration path"
    )
    args = parser.parse_args()

    from l9_graphite_memory.adapters import build_projection, build_store
    from l9_graphite_memory.secrets import load_secrets_sync

    load_secrets_sync()
    settings = load_settings(args.config)
    configure_logging(settings.log_level, json_output=settings.json_logs)
    store = build_store(settings)
    projection = build_projection(settings)
    worker = OutboxWorker(store, projection, settings)
    if args.once:
        sys.stdout.write(str(worker.run_once()) + "\n")
        return 0
    try:
        while True:
            worker.run_once()
            time.sleep(max(args.interval, 0.1))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
