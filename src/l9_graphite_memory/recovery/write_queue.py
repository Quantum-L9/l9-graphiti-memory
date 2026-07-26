# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/recovery/write_queue.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Durable ingress recovery queue that replays only through MemoryService."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.contracts import (
    MemoryPrincipal,
    MemoryWriteRequest,
    WriteReceipt,
)
from l9_graphite_memory.services import MemoryService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class QueuedWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    queue_id: UUID = Field(default_factory=uuid4)
    request: dict[str, Any]
    request_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempts: int = Field(default=0, ge=0)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class RecoveryReplayItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    queue_id: UUID
    status: str
    receipt: WriteReceipt | None = None
    error: str | None = None


class RecoveryReplayReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    attempted: int = Field(ge=0)
    delivered: int = Field(ge=0)
    retained: int = Field(ge=0)
    items: tuple[RecoveryReplayItem, ...]
    created_at: datetime = Field(default_factory=_utc_now)


class FileWriteRecoveryQueue:
    """Persist canonical requests when the primary local ledger cannot commit.

    The queue never writes memory records directly. Replays always call
    ``MemoryService.write`` so authorization, admission, temporal law, and
    idempotency remain authoritative.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.pending_dir = self.root / "pending"
        self.delivered_dir = self.root / "delivered"
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.delivered_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _pending_path(self, queue_id: UUID) -> Path:
        return self.pending_dir / f"{queue_id}.json"

    def enqueue(
        self, request: MemoryWriteRequest, *, error: str | None = None
    ) -> QueuedWrite:
        request_payload = request.model_dump(mode="json")
        digest = sha256_text(canonical_json(request_payload))
        item = QueuedWrite(
            request=request_payload,
            request_digest=digest,
            last_error=error,
        )
        self._atomic_write(
            self._pending_path(item.queue_id),
            item.model_dump_json(indent=2) + "\n",
        )
        return item

    def list_pending(self) -> tuple[QueuedWrite, ...]:
        items: list[QueuedWrite] = []
        for path in sorted(self.pending_dir.glob("*.json")):
            items.append(
                QueuedWrite.model_validate_json(path.read_text(encoding="utf-8"))
            )
        return tuple(items)

    def _record_failure(self, item: QueuedWrite, error: str) -> None:
        updated = item.model_copy(
            update={
                "attempts": item.attempts + 1,
                "last_error": error,
                "updated_at": _utc_now(),
            }
        )
        self._atomic_write(
            self._pending_path(item.queue_id),
            updated.model_dump_json(indent=2) + "\n",
        )

    def _record_delivery(self, item: QueuedWrite, receipt: WriteReceipt) -> None:
        payload = {
            "queue": item.model_dump(mode="json"),
            "receipt": receipt.model_dump(mode="json"),
            "delivered_at": _utc_now().isoformat(),
        }
        delivered_path = self.delivered_dir / f"{item.queue_id}.json"
        self._atomic_write(
            delivered_path, json.dumps(payload, indent=2, sort_keys=True) + "\n"
        )
        self._pending_path(item.queue_id).unlink(missing_ok=True)

    def replay(
        self,
        service: MemoryService,
        principal: MemoryPrincipal,
        *,
        limit: int = 100,
    ) -> RecoveryReplayReport:
        results: list[RecoveryReplayItem] = []
        for item in self.list_pending()[:limit]:
            try:
                request = MemoryWriteRequest.model_validate(item.request)
                current_digest = sha256_text(
                    canonical_json(request.model_dump(mode="json"))
                )
                if current_digest != item.request_digest:
                    raise ValueError("queued request digest mismatch")
                receipt = service.write(principal, request)
                self._record_delivery(item, receipt)
                results.append(
                    RecoveryReplayItem(
                        queue_id=item.queue_id,
                        status="delivered",
                        receipt=receipt,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                self._record_failure(item, error)
                results.append(
                    RecoveryReplayItem(
                        queue_id=item.queue_id,
                        status="retained",
                        error=error,
                    )
                )
        delivered = sum(result.status == "delivered" for result in results)
        return RecoveryReplayReport(
            attempted=len(results),
            delivered=delivered,
            retained=len(results) - delivered,
            items=tuple(results),
        )
