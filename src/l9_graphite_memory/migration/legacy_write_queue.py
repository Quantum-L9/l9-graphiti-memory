# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/migration/legacy_write_queue.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-08-20

"""Drain the retired deferred-ingestion queue through the canonical service.

Deferred canonical ingestion is no longer a supported write outcome: a memory
write becomes canonical during the operation or fails visibly. This module
exists only so operators who ran an earlier release can inspect and drain the
files that release left behind. It is deliberately one-way -- there is no
enqueue path, so no runtime can persist a new request for later ingestion.
"""

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

LEGACY_QUEUE_DIRNAME = "write-recovery"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LegacyQueuedWrite(BaseModel):
    """One request file written by the retired deferred-ingestion queue."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    queue_id: UUID = Field(default_factory=uuid4)
    request: dict[str, Any]
    request_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempts: int = Field(default=0, ge=0)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class LegacyDrainItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    queue_id: UUID | None
    source_path: str
    status: str
    receipt: WriteReceipt | None = None
    error: str | None = None


class LegacyDrainReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    queue_root: str
    applied: bool
    attempted: int = Field(ge=0)
    delivered: int = Field(ge=0)
    retained: int = Field(ge=0)
    unreadable: int = Field(ge=0)
    items: tuple[LegacyDrainItem, ...]
    created_at: datetime = Field(default_factory=_utc_now)

    @property
    def drained_cleanly(self) -> bool:
        return self.retained == 0 and self.unreadable == 0


class LegacyWriteQueueDrain:
    """Inspect and replay a retired queue directory; never write a new one.

    Replay always calls :meth:`MemoryService.write`, so authorization,
    admission, temporal law, and idempotency stay authoritative. Files that
    cannot be parsed or delivered are preserved and reported rather than
    dropped, so no queued write disappears silently.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.pending_dir = self.root / "pending"
        self.drained_dir = self.root / "drained"

    def exists(self) -> bool:
        return self.pending_dir.is_dir()

    def pending_paths(self) -> tuple[Path, ...]:
        if not self.pending_dir.is_dir():
            return ()
        return tuple(sorted(self.pending_dir.glob("*.json")))

    def inventory(self) -> tuple[tuple[Path, LegacyQueuedWrite | None], ...]:
        """Return every pending file with its parsed item, or None if unreadable."""

        result: list[tuple[Path, LegacyQueuedWrite | None]] = []
        for path in self.pending_paths():
            try:
                item = LegacyQueuedWrite.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                item = None
            result.append((path, item))
        return tuple(result)

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(payload, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _record_drain(self, path: Path, item: LegacyQueuedWrite, receipt: WriteReceipt) -> None:
        self.drained_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "queue": item.model_dump(mode="json"),
            "receipt": receipt.model_dump(mode="json"),
            "drained_at": _utc_now().isoformat(),
        }
        self._atomic_write(
            self.drained_dir / f"{item.queue_id}.json",
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )
        path.unlink(missing_ok=True)

    def drain(
        self,
        service: MemoryService,
        principal: MemoryPrincipal,
        *,
        apply: bool = True,
        limit: int = 100,
    ) -> LegacyDrainReport:
        items: list[LegacyDrainItem] = []
        delivered = retained = unreadable = 0
        for path, queued in self.inventory()[:limit]:
            relative = str(path)
            if queued is None:
                unreadable += 1
                items.append(
                    LegacyDrainItem(
                        queue_id=None,
                        source_path=relative,
                        status="unreadable",
                        error="queued write file could not be parsed; preserved for manual review",
                    )
                )
                continue
            try:
                request = MemoryWriteRequest.model_validate(queued.request)
                current_digest = sha256_text(canonical_json(request.model_dump(mode="json")))
                if current_digest != queued.request_digest:
                    raise ValueError("queued request digest mismatch")
                if not apply:
                    items.append(
                        LegacyDrainItem(
                            queue_id=queued.queue_id,
                            source_path=relative,
                            status="drainable",
                        )
                    )
                    continue
                receipt = service.write(principal, request)
                self._record_drain(path, queued, receipt)
                delivered += 1
                items.append(
                    LegacyDrainItem(
                        queue_id=queued.queue_id,
                        source_path=relative,
                        status="drained",
                        receipt=receipt,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                retained += 1
                items.append(
                    LegacyDrainItem(
                        queue_id=queued.queue_id,
                        source_path=relative,
                        status="retained",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
        return LegacyDrainReport(
            queue_root=str(self.root),
            applied=apply,
            attempted=len(items),
            delivered=delivered,
            retained=retained,
            unreadable=unreadable,
            items=tuple(items),
        )
