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
from uuid import UUID

from l9_graphite_memory.config import MemorySettings, load_settings
from l9_graphite_memory.contracts import (
    MemoryState,
    OutboxEvent,
    OutboxStatus,
    ProjectionLink,
    ProjectionRetirementReceipt,
)
from l9_graphite_memory.errors import ConfigurationError, ProjectionError, StoreError
from l9_graphite_memory.observability import configure_logging, get_logger
from l9_graphite_memory.ports import Clock, ProjectionAdapter, RecordStore, SystemClock
from l9_graphite_memory.ports.projection import RenderedProjectionAdapter
from l9_graphite_memory.projections.runtime import ProjectionRuntime

log = get_logger("l9.memory.outbox")


def verify_projection_runtime(store: RecordStore, projections: ProjectionRuntime) -> None:
    """Refuse a runtime that cannot address every copy or queued event it owes.

    Target identities carry the manifest version, so a version bump, a target
    removal, or a legacy-to-manifest cutover can leave persisted links and
    pending retire or erase events naming identities the new runtime does not
    bind. Those events would fail on every retry and dead-letter, and a
    verified deletion would stay pending with no runtime able to finish it.
    Activation therefore fails first, naming the identities, so the operator
    retains the earlier manifest revision (``projection_manifest_history``)
    or drains them with the runtime that wrote them (ADR-057, ADR-084).

    The runtime itself never reads canonical state; this check happens at the
    composition boundary, where the worker holds both.
    """

    unresolved = projections.unresolved_identities(store.list_projection_target_identities())
    if unresolved:
        raise ConfigurationError(
            "projection runtime cannot address target identities that still own "
            "projection links or pending outbox events: "
            + ", ".join(unresolved)
            + "; retain the manifest revision that declares them "
            "(projection_manifest_history) or drain them with that runtime first"
        )


class OutboxWorker:
    """Deliver one canonical outbox event to exactly one projection target.

    Each event names the target it addresses. The worker resolves that one
    target, performs one provider operation, persists or deletes that target's
    link, and settles that event, so retries and dead letters are independent
    per target (ADR-084).
    """

    def __init__(
        self,
        store: RecordStore,
        projection: ProjectionAdapter | ProjectionRuntime,
        settings: MemorySettings,
        *,
        clock: Clock | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.store = store
        self.projections = ProjectionRuntime.coerce(projection)
        # A worker that cannot resolve an identity canonical state still owes
        # work to must not start: it would retry that event until it died.
        verify_projection_runtime(store, self.projections)
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
        if not self.projections.targets:
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
                target = self.projections.resolve_event_target(event.payload.get("target_identity"))
                if event.event_type == "memory.record.project":
                    record = self.store.get_record(event.aggregate_id)
                    if record is None:
                        raise RuntimeError(f"outbox aggregate not found: {event.aggregate_id}")
                    if record.state is not MemoryState.ACTIVE:
                        # The intent was recorded while the record was current;
                        # canonical state has moved on since (superseded,
                        # archived, tombstoned). Projecting now would put stale
                        # or deleted content back into the provider under a
                        # fresh link, after the retirement or erasure that
                        # withdrew it. The provider must reflect current
                        # canonical state, so this event is satisfied by doing
                        # nothing (ADR-074).
                        log.info(
                            "projection_project_skipped_not_active",
                            extra={
                                "event_id": str(event.event_id),
                                "record_id": str(record.record_id),
                                "state": record.state.value,
                            },
                        )
                    elif not target.delivers:
                        # The target was disabled after this intent was queued.
                        # A disabled target receives nothing new.
                        log.info(
                            "projection_project_skipped_target_disabled",
                            extra={
                                "event_id": str(event.event_id),
                                "record_id": str(record.record_id),
                                "target_identity": target.identity,
                            },
                        )
                    else:
                        adapter = self.projections.adapter_for(target.identity)
                        # Manifest mode delivers the compiled rendering, the
                        # one the link's digest attests; legacy mode has no
                        # contract and the adapter delivers as it always has.
                        rendered = self.projections.render(record)
                        if rendered is None:
                            result = adapter.project(record)
                        elif isinstance(adapter, RenderedProjectionAdapter):
                            result = adapter.project_rendered(record, rendered)
                        else:
                            raise ProjectionError(
                                f"projection target {target.identity} adapter cannot deliver "
                                "a compiled render contract"
                            )
                        locator = result.get("locator") if isinstance(result, dict) else None
                        if not isinstance(locator, str) or not locator.strip():
                            raise RuntimeError(
                                f"projection target {target.identity} did not return a stable "
                                f"locator for record {record.record_id}"
                            )
                        # Re-read canonical state after the external provider
                        # call to close the concurrent-deletion race: another
                        # worker may have deleted or superseded the record
                        # while the projection was being written (ADR-074).
                        fresh = self.store.get_record(record.record_id)
                        if fresh is None or fresh.state is not MemoryState.ACTIVE:
                            log.info(
                                "projection_post_project_stale",
                                extra={
                                    "event_id": str(event.event_id),
                                    "record_id": str(record.record_id),
                                    "fresh_state": (
                                        fresh.state.value if fresh is not None else "deleted"
                                    ),
                                    "target_identity": target.identity,
                                },
                            )
                            adapter.retire(
                                record.record_id,
                                record.namespace,
                                locator=locator,
                                reason="post-project-race-stale",
                            )
                        else:
                            link_metadata: dict[str, object] = {
                                "transport_result": result,
                                "outbox_event_id": str(event.event_id),
                            }
                            if rendered is not None:
                                link_metadata["render_content_digest"] = rendered.content_digest
                            self.store.save_projection_link(
                                ProjectionLink(
                                    record_id=record.record_id,
                                    namespace=record.namespace,
                                    projection_name=target.projection_name,
                                    target_identity=target.identity,
                                    projection_version=target.projection_version,
                                    provider_type=target.provider_type,
                                    locator=locator,
                                    manifest_digest=target.manifest_digest,
                                    # The digest of the contract that produced
                                    # the delivered bytes, not merely the one
                                    # the target was bound with.
                                    render_contract_digest=(
                                        None if rendered is None else rendered.template_digest
                                    ),
                                    metadata=link_metadata,
                                    created_at=now,
                                )
                            )
                elif event.event_type == "memory.record.retire":
                    # Withdraw a superseded or archived projection. This path
                    # must never touch canonical state: the record keeps its
                    # content and its lifecycle history, and only the derived
                    # projection is withdrawn (ADR-074).
                    link = self.store.get_projection_link(event.aggregate_id, target.identity)
                    current = self.store.get_record(event.aggregate_id)
                    if current is not None and current.state is MemoryState.ACTIVE:
                        # Governance restored the record after this retirement
                        # was queued (or the retirement is a late retry); it is
                        # current again and its projection must stay. The
                        # reactivation carries its own project event.
                        log.info(
                            "projection_retire_skipped_active",
                            extra={
                                "event_id": str(event.event_id),
                                "record_id": str(event.aggregate_id),
                            },
                        )
                    elif link is None:
                        # Nothing was ever projected, so there is nothing to
                        # withdraw. Retirement is satisfied.
                        log.info(
                            "projection_retire_noop",
                            extra={
                                "event_id": str(event.event_id),
                                "record_id": str(event.aggregate_id),
                            },
                        )
                    else:
                        reason = event.payload.get("reason")
                        reason_text = reason if isinstance(reason, str) else "retired"
                        adapter = self.projections.adapter_for(target.identity)
                        result = adapter.retire(
                            event.aggregate_id,
                            event.namespace,
                            locator=link.locator,
                            reason=reason_text,
                        )
                        self.store.delete_projection_link(event.aggregate_id, target.identity)
                        # A provider whose only removal primitive is deletion
                        # cannot distinguish this from a privacy erasure in its
                        # own logs. Record the distinction in canonical state,
                        # where it does not depend on the provider (ADR-076).
                        self.store.save_projection_retirement(
                            ProjectionRetirementReceipt(
                                record_id=event.aggregate_id,
                                namespace=event.namespace,
                                projection_name=target.projection_name,
                                target_identity=target.identity,
                                provider_type=target.provider_type,
                                retirement_mode=adapter.retirement_mode,
                                locator=link.locator,
                                reason=reason_text,
                                rebuildable=True,
                                outbox_event_id=event.event_id,
                                provider_result=result if isinstance(result, dict) else {},
                                retired_at=now,
                            )
                        )
                elif event.event_type == "memory.record.erase":
                    receipt_id = event.payload.get("deletion_receipt_id")
                    if not isinstance(receipt_id, str):
                        raise RuntimeError("deletion outbox event lacks deletion_receipt_id")
                    link = self.store.get_projection_link(event.aggregate_id, target.identity)
                    if link is None:
                        # No copy in this target is known to canonical state:
                        # the record was never projected there, or that copy
                        # was already withdrawn by retirement. This target's
                        # share of the erasure already holds (ADR-057,
                        # ADR-074). A late project event cannot undo this: the
                        # worker never projects a record that is no longer
                        # active.
                        log.info(
                            "projection_erase_noop",
                            extra={
                                "event_id": str(event.event_id),
                                "record_id": str(event.aggregate_id),
                                "target_identity": target.identity,
                            },
                        )
                    else:
                        # Erase even when the target is disabled: a copy it
                        # holds is still part of the record's erasure set.
                        self.projections.adapter_for(target.identity).erase(
                            event.aggregate_id,
                            event.namespace,
                            locator=link.locator,
                        )
                        self.store.delete_projection_link(event.aggregate_id, target.identity)
                    # The deletion completes only once no durable copy remains
                    # in any target; until then the other targets' erase events
                    # are still owed (ADR-084).
                    remaining = self.store.list_projection_links(event.aggregate_id)
                    if remaining:
                        log.info(
                            "projection_erase_awaiting_targets",
                            extra={
                                "event_id": str(event.event_id),
                                "record_id": str(event.aggregate_id),
                                "remaining_targets": [item.target_identity for item in remaining],
                            },
                        )
                    else:
                        self.store.complete_deletion(
                            event.aggregate_id,
                            UUID(receipt_id),
                            completed_at=now,
                            actor=f"memory.outbox-worker:{self.worker_id}",
                        )
                else:
                    raise RuntimeError(f"unsupported outbox event type: {event.event_type}")
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
                    delay = self.settings.outbox_base_delay_seconds * (2 ** min(attempts - 1, 10))
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
                        "target_identity": event.payload.get("target_identity"),
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
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    parser.add_argument("--interval", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--config", default=None, help="Optional YAML configuration path")
    args = parser.parse_args()

    from l9_graphite_memory.adapters import build_store
    from l9_graphite_memory.adapters.factory import build_projection_runtime
    from l9_graphite_memory.secrets import load_secrets_sync

    load_secrets_sync()
    settings = load_settings(args.config)
    configure_logging(settings.log_level, json_output=settings.json_logs)
    store = build_store(settings)
    worker = OutboxWorker(store, build_projection_runtime(settings), settings)
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
