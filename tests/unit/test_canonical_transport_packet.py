# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_canonical_transport_packet.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-21

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from l9_graphite_memory.contracts import MemorySearchRequest
from l9_graphite_memory.errors import (
    BoundaryAlignmentError,
    UnsupportedTransportPacketVersion,
)
from l9_graphite_memory.integrations.constellation import (
    GateMemoryBridge,
    SearchMemoryIntent,
)
from l9_graphite_memory.integrations.transport_packet import (
    AUTHORITATIVE_PACKAGE,
    CanonicalTransportPacketFactory,
    assert_supported_sdk_version,
)
from l9_graphite_memory.ports.constellation import GateDispatchReceipt


class _Envelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    body: str


class _LocalTransportPacket(BaseModel):
    model_config = ConfigDict(frozen=True)
    packet_id: str


class _RecordingGate:
    def __init__(self) -> None:
        self.packets: list[object] = []

    def dispatch(self, packet: object) -> GateDispatchReceipt:
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


def test_supported_version_range_is_fail_closed() -> None:
    assert assert_supported_sdk_version("1.0.1") == "1.0.1"
    with pytest.raises(UnsupportedTransportPacketVersion):
        assert_supported_sdk_version("1.1.0")
    with pytest.raises(UnsupportedTransportPacketVersion):
        assert_supported_sdk_version("0.9.0")


def test_root_and_follow_up_use_authoritative_constructor() -> None:
    pytest.importorskip("constellation_node_sdk")
    from importlib.metadata import version

    factory = CanonicalTransportPacketFactory(tenant="quantum-l9")
    assert factory.sdk_version == version(AUTHORITATIVE_PACKAGE)
    gate = _RecordingGate()
    bridge = GateMemoryBridge(packet_factory=factory, gate_client=gate)
    intent = _intent()

    root_receipt = bridge.dispatch_root(intent=intent, trace_id="trace-rp-001")
    parent = gate.packets[0]
    follow_receipt = bridge.dispatch_follow_up(parent=parent, intent=intent)
    child = gate.packets[1]

    assert parent.canonical_packet.__class__.__module__.startswith("constellation_node_sdk")
    assert child.canonical_packet.__class__.__module__.startswith("constellation_node_sdk")
    assert parent.trace_id == "trace-rp-001"
    assert child.trace_id == parent.trace_id
    assert child.packet_id != parent.packet_id
    assert parent.lineage == ()
    assert child.lineage == (parent.packet_id,)
    assert parent.canonical_packet.lineage.generation == 0
    assert child.canonical_packet.lineage.generation == 1
    assert child.canonical_packet.lineage.parent_id == parent.canonical_packet.header.packet_id
    assert root_receipt.packet_id == parent.packet_id
    assert follow_receipt.packet_id == child.packet_id
    dumped_root = parent.canonical_packet.model_dump(mode="json")
    dumped_child = child.canonical_packet.model_dump(mode="json")
    assert dumped_root["payload"]["operation"] == "memory.search"
    assert dumped_child["payload"]["request"]["query"] == "architecture"
    assert dumped_root["security"]["transport_hash"] != dumped_child["security"]["transport_hash"]


def test_serialized_fixtures_have_stable_shape_and_digests(tmp_path: Path) -> None:
    pytest.importorskip("constellation_node_sdk")
    factory = CanonicalTransportPacketFactory(tenant="quantum-l9")
    root = factory.create(payload=_intent(), trace_id="trace-fixture")
    child = root.derive_or_with_hop(payload=_intent())
    fixtures = {
        "root": root.canonical_packet.model_dump(mode="json"),
        "follow_up": child.canonical_packet.model_dump(mode="json"),
    }
    encoded = json.dumps(fixtures, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    out = tmp_path / "transport-packet-fixtures.json"
    out.write_bytes(encoded)
    assert len(digest) == 64
    assert fixtures["root"]["header"]["trace_id"] == "trace-fixture"
    assert fixtures["follow_up"]["header"]["trace_id"] == "trace-fixture"
    assert fixtures["follow_up"]["lineage"]["generation"] == 1


def test_factory_rejects_envelope_local_duplicate_and_raw_dict() -> None:
    pytest.importorskip("constellation_node_sdk")
    factory = CanonicalTransportPacketFactory(tenant="quantum-l9")
    _Envelope.__name__ = "Packet" + "Envelope"
    _LocalTransportPacket.__name__ = "TransportPacket"
    with pytest.raises(BoundaryAlignmentError, match="deprecated envelope"):
        factory.create(payload=_Envelope(body="nope"), trace_id="trace-1")
    with pytest.raises(BoundaryAlignmentError, match="local TransportPacket"):
        factory.create(payload=_LocalTransportPacket(packet_id="x"), trace_id="trace-1")
    with pytest.raises(BoundaryAlignmentError, match="raw-dict"):
        factory.create(payload={"operation": "memory.search"}, trace_id="trace-1")  # type: ignore[arg-type]


def test_no_production_transport_packet_or_envelope_definitions() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "l9_graphite_memory"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "class TransportPacket(" in text:
            offenders.append(str(path.relative_to(root)))
        if "class Packet" + "Envelope(" in text:
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
