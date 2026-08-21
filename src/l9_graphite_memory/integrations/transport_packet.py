# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/integrations/transport_packet.py
#   layer: integration
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-21

"""Production TransportPacket factory bound to constellation-node-sdk.

This module does not define TransportPacket. It loads the authoritative
`create_transport_packet` / `derive` APIs and adapts them to the memory
bridge ports. Destination selection stays at the SDK default (`gate`).
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pydantic import BaseModel

from l9_graphite_memory.errors import (
    BoundaryAlignmentError,
    UnsupportedTransportPacketVersion,
)
from l9_graphite_memory.integrations.constellation import (
    GateMemoryBridge,
    MemoryGateIntent,
)
from l9_graphite_memory.ports.constellation import TransportPacketPort

AUTHORITATIVE_PACKAGE = "constellation-node-sdk"
AUTHORITATIVE_REPO = "Quantum-L9/Gate_SDK"
SUPPORTED_VERSION_RANGE = ">=1.0.1,<1.1.0"
_SUPPORTED_MAJOR = 1
_SUPPORTED_MINOR = 0
_SUPPORTED_MIN_PATCH = 1


def _parse_version(value: str) -> tuple[int, int, int]:
    core = value.split("+", 1)[0].split("-", 1)[0]
    parts = core.split(".")
    if len(parts) < 2:
        raise UnsupportedTransportPacketVersion(
            f"unsupported {AUTHORITATIVE_PACKAGE} version {value!r}"
        )
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError as exc:
        raise UnsupportedTransportPacketVersion(
            f"unsupported {AUTHORITATIVE_PACKAGE} version {value!r}"
        ) from exc
    return major, minor, patch


def assert_supported_sdk_version(installed: str) -> str:
    """Fail closed when the shared package is outside the supported 1.0.x range."""

    major, minor, patch = _parse_version(installed)
    if (
        major != _SUPPORTED_MAJOR
        or minor != _SUPPORTED_MINOR
        or patch < _SUPPORTED_MIN_PATCH
    ):
        raise UnsupportedTransportPacketVersion(
            f"{AUTHORITATIVE_PACKAGE} {installed} is outside {SUPPORTED_VERSION_RANGE}"
        )
    return installed


def load_authoritative_transport() -> tuple[Any, Any, str]:
    """Import the published SDK and reject unsupported versions."""

    try:
        installed = version(AUTHORITATIVE_PACKAGE)
    except PackageNotFoundError as exc:
        raise UnsupportedTransportPacketVersion(
            f"{AUTHORITATIVE_PACKAGE} is not installed; pin {AUTHORITATIVE_REPO} "
            f"{SUPPORTED_VERSION_RANGE}"
        ) from exc
    assert_supported_sdk_version(installed)
    try:
        module = import_module("constellation_node_sdk")
    except ImportError as exc:
        raise UnsupportedTransportPacketVersion(
            f"{AUTHORITATIVE_PACKAGE} {installed} could not be imported"
        ) from exc
    packet_type = getattr(module, "TransportPacket", None)
    create = getattr(module, "create_transport_packet", None)
    if packet_type is None or create is None:
        raise UnsupportedTransportPacketVersion(
            f"{AUTHORITATIVE_PACKAGE} {installed} is missing TransportPacket "
            "or create_transport_packet"
        )
    return packet_type, create, installed


def _reject_forbidden_payload(payload: object) -> None:
    name = type(payload).__name__
    module = getattr(type(payload), "__module__", "")
    if name == "Packet" + "Envelope" or "packet_envelope" in module:
        raise BoundaryAlignmentError(
            "deprecated envelope types are rejected at the constellation boundary"
        )
    if name == "TransportPacket" and not module.startswith("constellation_node_sdk"):
        raise BoundaryAlignmentError("local TransportPacket duplicates are rejected")
    if isinstance(payload, dict):
        raise BoundaryAlignmentError("raw-dict transport payloads are rejected")


def _intent_payload(intent: MemoryGateIntent) -> dict[str, Any]:
    """Map a typed memory intent onto the canonical packet payload fields."""

    return {
        "operation": intent.operation,
        "request": intent.request.model_dump(mode="json"),
    }


class CanonicalTransportPacket:
    """Port adapter over an authoritative TransportPacket instance."""

    def __init__(self, packet: Any, *, lineage: tuple[str, ...] = ()) -> None:
        self._packet = packet
        self._lineage = lineage

    @property
    def packet_id(self) -> str:
        return str(self._packet.header.packet_id)

    @property
    def trace_id(self) -> str:
        return str(self._packet.header.trace_id)

    @property
    def lineage(self) -> tuple[str, ...]:
        return self._lineage

    @property
    def canonical_packet(self) -> Any:
        return self._packet

    def derive_or_with_hop(self, *, payload: BaseModel) -> TransportPacketPort:
        _reject_forbidden_payload(payload)
        intent = GateMemoryBridge.validate_intent(payload)
        parent_id = self.packet_id
        parent_trace = self.trace_id
        child = self._packet.derive(
            action=intent.operation,
            payload=_intent_payload(intent),
        )
        if child is self._packet:
            raise BoundaryAlignmentError("canonical derive mutated the parent packet")
        adapted = CanonicalTransportPacket(
            child, lineage=(*self._lineage, parent_id)
        )
        if adapted.trace_id != parent_trace:
            raise BoundaryAlignmentError("canonical derive did not preserve trace_id")
        return adapted


class CanonicalTransportPacketFactory:
    """Create root packets through constellation-node-sdk.create_transport_packet."""

    def __init__(self, *, tenant: str, local_node: str | None = None) -> None:
        if not tenant or not tenant.strip():
            raise BoundaryAlignmentError("canonical packet factory requires a tenant")
        self._tenant = tenant.strip()
        self._local_node = local_node.strip().lower() if local_node else None
        if local_node is not None and not self._local_node:
            raise BoundaryAlignmentError("canonical packet factory local_node must not be blank")
        packet_type, create, installed = load_authoritative_transport()
        self._packet_type = packet_type
        self._create = create
        self.sdk_version = installed

    def create(self, *, payload: BaseModel, trace_id: str) -> TransportPacketPort:
        _reject_forbidden_payload(payload)
        if not trace_id or not trace_id.strip():
            raise BoundaryAlignmentError("canonical packet factory requires a trace_id")
        intent = GateMemoryBridge.validate_intent(payload)
        create_kwargs: dict[str, Any] = {
            "action": intent.operation,
            "payload": _intent_payload(intent),
            "tenant": self._tenant,
            "trace_id": trace_id.strip(),
        }
        if self._local_node:
            create_kwargs["source_node"] = self._local_node
            create_kwargs["reply_to"] = self._local_node
        packet = self._create(**create_kwargs)
        if not isinstance(packet, self._packet_type):
            raise BoundaryAlignmentError(
                "canonical constructor did not return constellation_node_sdk.TransportPacket"
            )
        adapted = CanonicalTransportPacket(packet)
        if adapted.trace_id != trace_id.strip():
            raise BoundaryAlignmentError(
                "canonical constructor did not preserve the requested trace_id"
            )
        return adapted
