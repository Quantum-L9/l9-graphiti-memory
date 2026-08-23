# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/contracts/privacy.py
#   layer: contract
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Purpose-bound consent contract for sensitive memory classes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import MemoryClass
from .evidence import EvidenceRef
from .temporal import utc_now


class ConsentGrant(BaseModel):
    """Purpose-bound consent for identity or preference memory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    consent_id: UUID = Field(default_factory=uuid4)
    subject_id: str = Field(min_length=1, max_length=300)
    namespace: str = Field(min_length=1, max_length=300)
    allowed_classes: tuple[MemoryClass, ...] = (
        MemoryClass.IDENTITY,
        MemoryClass.PREFERENCE,
    )
    purpose: str = Field(min_length=1, max_length=1_000)
    evidence: EvidenceRef
    granted_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    def permits(
        self,
        namespace: str,
        memory_class: MemoryClass,
        *,
        at: datetime,
        subject_id: str | None = None,
    ) -> bool:
        if self.namespace != namespace or memory_class not in self.allowed_classes:
            return False
        if subject_id is not None and self.subject_id != subject_id:
            return False
        if self.granted_at > at or self.revoked_at is not None and self.revoked_at <= at:
            return False
        return self.expires_at is None or self.expires_at > at
