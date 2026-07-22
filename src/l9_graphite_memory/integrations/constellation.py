# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/integrations/constellation.py
#   layer: integration
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Gate-only L9 constellation bridge for memory intents.

The bridge expresses typed intent and preserves canonical packet lineage. It
contains no peer URL, node registry, destination selector, or routing logic.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from l9_graphite_memory.contracts import (
    HydrationRequest,
    MemorySearchRequest,
    MemoryWriteRequest,
    PhaseLockRequest,
)
from l9_graphite_memory.errors import BoundaryAlignmentError
from l9_graphite_memory.ports.constellation import (
    GateClientPort,
    GateDispatchReceipt,
    TransportPacketFactory,
    TransportPacketPort,
)


class IngestMemoryIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["memory.ingest"] = "memory.ingest"
    request: MemoryWriteRequest


class SearchMemoryIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["memory.search"] = "memory.search"
    request: MemorySearchRequest


class HydrateMemoryIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["memory.hydrate"] = "memory.hydrate"
    request: HydrationRequest


class PhaseLockMemoryIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operation: Literal["memory.phase_lock"] = "memory.phase_lock"
    request: PhaseLockRequest


MemoryGateIntent = Annotated[
    IngestMemoryIntent
    | SearchMemoryIntent
    | HydrateMemoryIntent
    | PhaseLockMemoryIntent,
    Field(discriminator="operation"),
]
_MEMORY_GATE_INTENT = TypeAdapter(MemoryGateIntent)


class GateMemoryBridge:
    """Create or derive canonical packets and send them only through Gate."""

    def __init__(
        self, *, packet_factory: TransportPacketFactory, gate_client: GateClientPort
    ) -> None:
        self._packet_factory = packet_factory
        self._gate_client = gate_client

    @staticmethod
    def validate_intent(value: object) -> MemoryGateIntent:
        """Validate an intent without accepting an untyped transport mapping."""

        return _MEMORY_GATE_INTENT.validate_python(value)

    def dispatch_root(
        self, *, intent: MemoryGateIntent, trace_id: str
    ) -> GateDispatchReceipt:
        """Create a root packet and let Gate resolve its destination."""

        packet = self._packet_factory.create(payload=intent, trace_id=trace_id)
        self._validate_root(packet, trace_id)
        return self._dispatch(packet)

    def dispatch_follow_up(
        self,
        *,
        parent: TransportPacketPort,
        intent: MemoryGateIntent,
    ) -> GateDispatchReceipt:
        """Derive an immutable hop from a parent and dispatch it only through Gate."""

        before_lineage = tuple(parent.lineage)
        child = parent.derive_or_with_hop(payload=intent)
        if child is parent:
            raise BoundaryAlignmentError(
                "derive_or_with_hop mutated the parent packet in place"
            )
        if parent.trace_id != child.trace_id:
            raise BoundaryAlignmentError("derived packet did not preserve trace_id")
        if tuple(parent.lineage) != before_lineage:
            raise BoundaryAlignmentError("parent packet lineage changed in place")
        if len(tuple(child.lineage)) <= len(before_lineage):
            raise BoundaryAlignmentError("derived packet did not append a lineage hop")
        return self._dispatch(child)

    @staticmethod
    def _validate_root(packet: TransportPacketPort, expected_trace_id: str) -> None:
        if not packet.packet_id:
            raise BoundaryAlignmentError("packet factory returned an empty packet_id")
        if packet.trace_id != expected_trace_id:
            raise BoundaryAlignmentError(
                "packet factory did not preserve the requested trace_id"
            )

    def _dispatch(self, packet: TransportPacketPort) -> GateDispatchReceipt:
        receipt = self._gate_client.dispatch(packet)
        if receipt.packet_id != packet.packet_id:
            raise BoundaryAlignmentError(
                "Gate receipt packet_id does not match the dispatched packet"
            )
        if receipt.trace_id != packet.trace_id:
            raise BoundaryAlignmentError(
                "Gate receipt trace_id does not match the dispatched packet"
            )
        return receipt
