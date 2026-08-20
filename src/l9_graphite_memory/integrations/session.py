# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/integrations/session.py
#   layer: integration
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""In-process session ingestion and context restoration adapters."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    HydrationRequest,
    HydrationResult,
    MemoryClass,
    MemoryPrincipal,
    MemoryWriteRequest,
    Provenance,
    WriteReceipt,
)
from l9_graphite_memory.services import MemoryService


class SessionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1, max_length=300)
    sequence: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=64_000)
    event_type: str = Field(default="message", min_length=1, max_length=100)
    source_agent_id: str | None = Field(default=None, max_length=300)
    tags: tuple[str, ...] = ()


class SessionIngestor:
    """Admit session events as canonical memory during the ingest call.

    There is no deferred outcome: :meth:`ingest` either returns a canonical
    write receipt or raises. A caller that cannot tolerate a failed write must
    surface that failure, not record a local success.
    """

    def __init__(self, service: MemoryService) -> None:
        self.service = service

    @staticmethod
    def request(
        principal: MemoryPrincipal,
        event: SessionEvent,
        *,
        namespace: str,
        dry_run: bool = False,
    ) -> MemoryWriteRequest:
        return MemoryWriteRequest(
            namespace=namespace,
            memory_class=MemoryClass.EPISODIC,
            content=event.content,
            provenance=Provenance(
                source="session-ingestion",
                source_id=f"{event.session_id}:{event.sequence}",
                source_agent_id=event.source_agent_id or principal.agent_id,
                session_id=event.session_id,
                tool="SessionIngestor",
                extraction_method="session-event/v1",
            ),
            evidence=(
                EvidenceRef(
                    kind=EvidenceKind.EXPLICIT,
                    description=f"Session event {event.sequence} ({event.event_type})",
                    source_id=f"{event.session_id}:{event.sequence}",
                ),
            ),
            tags=tuple({*event.tags, "session", event.event_type.casefold()}),
            metadata={
                "session_id": event.session_id,
                "sequence": event.sequence,
                "event_type": event.event_type,
            },
            idempotency_key=f"session:{namespace}:{event.session_id}:{event.sequence}",
            dry_run=dry_run,
        )

    def ingest(
        self,
        principal: MemoryPrincipal,
        event: SessionEvent,
        *,
        namespace: str,
        dry_run: bool = False,
    ) -> WriteReceipt:
        return self.service.write(
            principal,
            self.request(principal, event, namespace=namespace, dry_run=dry_run),
        )


class ContextRestorer:
    def __init__(self, service: MemoryService) -> None:
        self.service = service

    def restore(
        self,
        principal: MemoryPrincipal,
        *,
        task: str,
        namespaces: tuple[str, ...],
        session_id: str | None = None,
        token_budget: int = 1_200,
    ) -> HydrationResult:
        topics = (f"session {session_id}",) if session_id else ()
        return self.service.hydrate(
            principal,
            HydrationRequest(
                task=task,
                namespaces=namespaces,
                topics=topics,
                token_budget=token_budget,
            ),
        )
