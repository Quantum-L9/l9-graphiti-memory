# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_constellation_bridge.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from l9_graphite_memory.contracts import MemorySearchRequest
from l9_graphite_memory.errors import BoundaryAlignmentError
from l9_graphite_memory.integrations.constellation import (
    GateMemoryBridge,
    SearchMemoryIntent,
)
from l9_graphite_memory.ports.constellation import GateDispatchReceipt


@dataclass(frozen=True)
class FakePacket:
    packet_id: str
    trace_id: str
    lineage: tuple[str, ...]
    payload: BaseModel
    mutate: bool = False
    break_trace: bool = False

    def derive_or_with_hop(self, *, payload: BaseModel) -> FakePacket:
        if self.mutate:
            return self
        return FakePacket(
            packet_id=f"{self.packet_id}.1",
            trace_id="changed" if self.break_trace else self.trace_id,
            lineage=(*self.lineage, self.packet_id),
            payload=payload,
        )


class FakeFactory:
    def create(self, *, payload: BaseModel, trace_id: str) -> FakePacket:
        return FakePacket(
            packet_id="packet-1", trace_id=trace_id, lineage=(), payload=payload
        )


class FakeGate:
    def __init__(self) -> None:
        self.packets: list[FakePacket] = []

    def dispatch(self, packet: FakePacket) -> GateDispatchReceipt:
        self.packets.append(packet)
        return GateDispatchReceipt(
            accepted=True,
            packet_id=packet.packet_id,
            trace_id=packet.trace_id,
            route_reference="gate-route-1",
        )


def _intent() -> SearchMemoryIntent:
    return SearchMemoryIntent(
        request=MemorySearchRequest(query="architecture", namespaces=("repo",))
    )


def test_root_intent_uses_gate_without_destination() -> None:
    gate = FakeGate()
    bridge = GateMemoryBridge(packet_factory=FakeFactory(), gate_client=gate)

    receipt = bridge.dispatch_root(intent=_intent(), trace_id="trace-1")

    assert receipt.accepted
    assert receipt.route_reference == "gate-route-1"
    assert len(gate.packets) == 1
    assert "destination" not in SearchMemoryIntent.model_fields


def test_follow_up_preserves_trace_and_appends_lineage() -> None:
    gate = FakeGate()
    bridge = GateMemoryBridge(packet_factory=FakeFactory(), gate_client=gate)
    parent = FakePacket(
        packet_id="parent", trace_id="trace-1", lineage=("root",), payload=_intent()
    )

    receipt = bridge.dispatch_follow_up(parent=parent, intent=_intent())

    assert receipt.trace_id == parent.trace_id
    assert gate.packets[0].lineage == ("root", "parent")
    assert parent.lineage == ("root",)


def test_follow_up_rejects_in_place_mutation() -> None:
    bridge = GateMemoryBridge(packet_factory=FakeFactory(), gate_client=FakeGate())
    parent = FakePacket(
        packet_id="parent",
        trace_id="trace-1",
        lineage=(),
        payload=_intent(),
        mutate=True,
    )

    with pytest.raises(BoundaryAlignmentError, match="in place"):
        bridge.dispatch_follow_up(parent=parent, intent=_intent())


def test_follow_up_rejects_trace_drift() -> None:
    bridge = GateMemoryBridge(packet_factory=FakeFactory(), gate_client=FakeGate())
    parent = FakePacket(
        packet_id="parent",
        trace_id="trace-1",
        lineage=(),
        payload=_intent(),
        break_trace=True,
    )

    with pytest.raises(BoundaryAlignmentError, match="trace_id"):
        bridge.dispatch_follow_up(parent=parent, intent=_intent())
