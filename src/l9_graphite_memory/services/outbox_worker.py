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
    MemoryRecord,
    MemoryState,
    OutboxEvent,
    OutboxStatus,
    ProjectionLink,
    ProjectionRetirementReceipt,
)
from l9_graphite_memory.contracts.projection import (
    LEGACY_COPIES_KEY,
    LINK_WITHDRAWN_KEY,
    PENDING_DELETION_RECEIPT_KEY,
    legacy_copies,
    link_withdrawn,
)
from l9_graphite_memory.errors import ProjectionLinkConflict, StoreError
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

    @staticmethod
    def _carried_legacy_copies(
        previous: ProjectionLink | None, scope_scheme: object, now: datetime
    ) -> list[dict[str, object]]:
        """Legacy obligations a new link inherits from the one it replaces.

        Replacing a live link written under another provider scope scheme
        leaves that copy behind in the retained legacy store (ADR-084), so it
        becomes an obligation instead of being forgotten (ADR-091).
        """

        copies: list[dict[str, object]] = list(legacy_copies(previous))
        if (
            previous is not None
            and not link_withdrawn(previous)
            and previous.metadata.get("scope_scheme") != scope_scheme
        ):
            copies.append(
                {
                    "locator": previous.locator,
                    "scope_scheme": previous.metadata.get("scope_scheme"),
                    "superseded_at": now.isoformat(),
                }
            )
        return copies

    #: Re-derivations allowed when the link changes under the worker.
    _LINK_INSTALL_ATTEMPTS = 3

    def _install_link(
        self,
        record: MemoryRecord,
        locator: str,
        metadata: dict[str, object],
        scope_scheme: object,
        now: datetime,
    ) -> bool:
        """Install the new link, re-deriving carried obligations on conflict.

        The link's legacy obligations are derived from the link it replaces.
        A legacy release that clears them between that read and the write
        would otherwise have them re-added, so the store rejects a write whose
        predecessor changed and the worker re-derives from the current link.
        The lifecycle check and the write are one atomic store step: a
        deletion, retirement or release that landed after the provider write
        must not be followed by a live link (ADR-091).
        """

        for _ in range(self._LINK_INSTALL_ATTEMPTS):
            previous = self.store.get_projection_link(record.record_id, self.projection.name)
            link_metadata = dict(metadata)
            carried = self._carried_legacy_copies(previous, scope_scheme, now)
            if carried:
                link_metadata[LEGACY_COPIES_KEY] = carried
            try:
                return self.store.save_projection_link_if_active(
                    ProjectionLink(
                        record_id=record.record_id,
                        namespace=record.namespace,
                        projection_name=self.projection.name,
                        locator=locator,
                        metadata=link_metadata,
                        created_at=now,
                    ),
                    expected_previous=previous,
                )
            except ProjectionLinkConflict:
                continue
        # Persistent contention: withdraw the fresh copy so no unlinked copy
        # is left behind, and let the outbox retry the projection.
        self.projection.retire(
            record.record_id,
            record.namespace,
            locator=locator,
            reason="post-project-link-contention",
        )
        raise ProjectionLinkConflict(
            f"projection link for {record.record_id} kept changing during install"
        )

    def _retain_stale_link(self, link: ProjectionLink, now: datetime) -> ProjectionLink:
        """Treat a link written under another scope scheme as a legacy copy.

        Between a migration rebuild being queued and its projection event
        running, a record's link still points at the retained legacy store.
        Removing that copy through the current provider is impossible, so the
        link becomes a withdrawn legacy obligation instead (ADR-091).
        """

        scheme = getattr(self.projection, "scope_scheme", None)
        if link_withdrawn(link) or link.metadata.get("scope_scheme") == scheme:
            return link
        copies = [
            *legacy_copies(link),
            {
                "locator": link.locator,
                "scope_scheme": link.metadata.get("scope_scheme"),
                "superseded_at": now.isoformat(),
            },
        ]
        retained = link.model_copy(
            update={
                "metadata": {**link.metadata, LEGACY_COPIES_KEY: copies, LINK_WITHDRAWN_KEY: True},
                "created_at": now,
            }
        )
        self.store.save_projection_link(retained)
        return retained

    def _drop_live_copy(
        self, link: ProjectionLink, now: datetime, *, pending_receipt_id: str | None = None
    ) -> None:
        """Forget the live copy; keep the link only while legacy copies remain."""

        if not legacy_copies(link):
            self.store.delete_projection_link(link.record_id, self.projection.name)
            return
        metadata = {**link.metadata, LINK_WITHDRAWN_KEY: True}
        if pending_receipt_id is not None:
            metadata[PENDING_DELETION_RECEIPT_KEY] = pending_receipt_id
        self.store.save_projection_link(
            link.model_copy(update={"metadata": metadata, "created_at": now})
        )

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
                    else:
                        result = self.projection.project(record)
                        locator = result.get("locator") if isinstance(result, dict) else None
                        if not isinstance(locator, str) or not locator.strip():
                            raise RuntimeError(
                                f"projection {self.projection.name} did not return a stable "
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
                                },
                            )
                            self.projection.retire(
                                record.record_id,
                                record.namespace,
                                locator=locator,
                                reason="post-project-race-stale",
                            )
                        else:
                            scope_scheme = getattr(self.projection, "scope_scheme", None)
                            metadata: dict[str, object] = {
                                "transport_result": result,
                                "outbox_event_id": str(event.event_id),
                                # Provider group scheme the copy was
                                # written under (ADR-084); None for a
                                # provider without scoped groups.
                                "scope_scheme": scope_scheme,
                            }
                            installed = self._install_link(
                                record, locator, metadata, scope_scheme, now
                            )
                            if not installed:
                                log.info(
                                    "projection_link_refused_not_active",
                                    extra={
                                        "event_id": str(event.event_id),
                                        "record_id": str(record.record_id),
                                    },
                                )
                                self.projection.retire(
                                    record.record_id,
                                    record.namespace,
                                    locator=locator,
                                    reason="post-project-race-stale",
                                )
                elif event.event_type == "memory.record.retire":
                    # Withdraw a superseded or archived projection. This path
                    # must never touch canonical state: the record keeps its
                    # content and its lifecycle history, and only the derived
                    # projection is withdrawn (ADR-074).
                    link = self.store.get_projection_link(event.aggregate_id, self.projection.name)
                    current = self.store.get_record(event.aggregate_id)
                    if link is not None and (
                        current is None or current.state is not MemoryState.ACTIVE
                    ):
                        link = self._retain_stale_link(link, now)
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
                    elif link is None or link_withdrawn(link):
                        # Nothing was ever projected (or the live copy is
                        # already withdrawn), so there is nothing to withdraw.
                        # Retirement is satisfied.
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
                        result = self.projection.retire(
                            event.aggregate_id,
                            event.namespace,
                            locator=link.locator,
                            reason=reason_text,
                        )
                        self._drop_live_copy(link, now)
                        # A provider whose only removal primitive is deletion
                        # cannot distinguish this from a privacy erasure in its
                        # own logs. Record the distinction in canonical state,
                        # where it does not depend on the provider (ADR-076).
                        self.store.save_projection_retirement(
                            ProjectionRetirementReceipt(
                                record_id=event.aggregate_id,
                                namespace=event.namespace,
                                projection_name=self.projection.name,
                                retirement_mode=self.projection.retirement_mode,
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
                    link = self.store.get_projection_link(event.aggregate_id, self.projection.name)
                    if link is not None:
                        link = self._retain_stale_link(link, now)
                    complete = True
                    if link is None:
                        # No projected copy is known to canonical state: the
                        # record was never projected, or its projection was
                        # already withdrawn by retirement. The end state
                        # verified deletion requires -- no projected copy --
                        # already holds, so the deletion completes instead of
                        # retrying to DEAD and stranding the record in
                        # deletion_pending (ADR-057, ADR-074). A late project
                        # event cannot undo this: the worker never projects a
                        # record that is no longer active.
                        log.info(
                            "projection_erase_noop",
                            extra={
                                "event_id": str(event.event_id),
                                "record_id": str(event.aggregate_id),
                            },
                        )
                    else:
                        if not link_withdrawn(link):
                            self.projection.erase(
                                event.aggregate_id,
                                event.namespace,
                                locator=link.locator,
                            )
                        if legacy_copies(link):
                            # A copy survives in a retained legacy provider
                            # store this projection cannot reach. Verified
                            # deletion is not complete until an operator
                            # releases it after destroying that store (ADR-091).
                            self._drop_live_copy(link, now, pending_receipt_id=receipt_id)
                            log.info(
                                "projection_erase_waiting_on_legacy_copies",
                                extra={
                                    "event_id": str(event.event_id),
                                    "record_id": str(event.aggregate_id),
                                    "legacy_copy_count": len(legacy_copies(link)),
                                },
                            )
                            complete = False
                        else:
                            self.store.delete_projection_link(
                                event.aggregate_id, self.projection.name
                            )
                    if complete:
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
