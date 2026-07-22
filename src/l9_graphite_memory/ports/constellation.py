# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/constellation.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Protocols for the optional L9 constellation boundary.

This module intentionally does not define the canonical TransportPacket model.
The owning constellation package injects that model and the Gate client.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class GateDispatchReceipt(BaseModel):
    """Evidence returned by Gate after resolving and admitting one intent packet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    packet_id: str = Field(min_length=1, max_length=300)
    trace_id: str = Field(min_length=1, max_length=300)
    route_reference: str | None = Field(default=None, max_length=500)
    warnings: tuple[str, ...] = ()


@runtime_checkable
class TransportPacketPort(Protocol):
    """Minimum immutable behavior required from the canonical transport model."""

    @property
    def packet_id(self) -> str: ...

    @property
    def trace_id(self) -> str: ...

    @property
    def lineage(self) -> tuple[str, ...]: ...

    def derive_or_with_hop(self, *, payload: BaseModel) -> TransportPacketPort: ...


@runtime_checkable
class TransportPacketFactory(Protocol):
    """Create a root canonical packet without reimplementing its model here."""

    def create(self, *, payload: BaseModel, trace_id: str) -> TransportPacketPort: ...


@runtime_checkable
class GateClientPort(Protocol):
    """Dispatch an intent packet to Gate, which alone resolves its destination."""

    def dispatch(self, packet: TransportPacketPort) -> GateDispatchReceipt: ...
