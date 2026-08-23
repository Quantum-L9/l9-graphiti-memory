# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_canonical_gate_client.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-21

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict

from l9_graphite_memory.contracts import MemorySearchRequest
from l9_graphite_memory.contracts.enums import OperationStatus
from l9_graphite_memory.contracts.receipts import HealthReport
from l9_graphite_memory.errors import (
    BoundaryAlignmentError,
    GateDeniedError,
    GateMalformedReceiptError,
    GateRejectedError,
    GateTimeoutError,
    GateUnavailableError,
)
from l9_graphite_memory.integrations.constellation import SearchMemoryIntent
from l9_graphite_memory.integrations.gate_client import (
    CanonicalGateClient,
    attach_gate_health,
    receipt_from_response,
)
from l9_graphite_memory.integrations.transport_packet import (
    CanonicalTransportPacketFactory,
)


class _LocalPacket(BaseModel):
    model_config = ConfigDict(frozen=True)
    packet_id: str
    trace_id: str = "trace"


class _StubSdkClient:
    def __init__(self, *, response: object | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.sent: list[object] = []

    async def send_to_gate(self, packet: object) -> object:
        self.sent.append(packet)
        if self.error is not None:
            raise self.error
        return self.response

    async def health(self) -> object:
        if self.error is not None:
            raise self.error
        return {"status": "ok", "version": "1.0.1"}


def _intent() -> SearchMemoryIntent:
    return SearchMemoryIntent(
        request=MemorySearchRequest(query="architecture", namespaces=("repo",))
    )


def _node_factory() -> CanonicalTransportPacketFactory:
    return CanonicalTransportPacketFactory(tenant="quantum-l9", local_node="memory-node")


def _response_packet(request: object, *, payload: dict[str, object] | None = None) -> object:
    pytest.importorskip("constellation_node_sdk")
    from constellation_node_sdk import create_transport_packet

    return create_transport_packet(
        action="search",
        payload=payload
        or {
            "status": "accepted",
            "authorization": "allow",
            "route_reference": "gate-route-1",
        },
        tenant="quantum-l9",
        source_node="gate",
        destination_node="memory-node",
        reply_to="memory-node",
        trace_id=request.header.trace_id,
        correlation_id=request.header.correlation_id,
    )


def test_dispatch_signature_has_no_peer_url_or_destination() -> None:
    parameters = inspect.signature(CanonicalGateClient.dispatch).parameters
    assert list(parameters) == ["self", "packet"]
    assert "url" not in parameters
    assert "destination" not in parameters
    assert "peer" not in parameters


def test_static_scan_has_no_direct_peer_dispatch() -> None:
    source = Path("src/l9_graphite_memory/integrations/gate_client.py").read_text()
    assert "peer_url" not in source
    assert "destination_node=" not in source
    assert "requests." not in source
    assert "urllib" not in source
    assert "send_to_gate" in source
    assert "retry" not in source.lower() or "does not authorize" in source


def test_attach_gate_health_keeps_core_and_gate_distinct() -> None:
    core = HealthReport(
        status=OperationStatus.COMPLETE,
        package_version="2.2.0",
        schema_version="2.2.0",
        store={"name": "sqlite", "healthy": True},
        projection={"name": "none", "healthy": True},
        outbox_backlog=0,
        checked_at=datetime.now(timezone.utc),
    )
    assert core.gate == {"name": "gate", "configured": False}
    degraded = attach_gate_health(
        core, {"name": "gate", "configured": True, "healthy": False, "status": "unavailable"}
    )
    assert degraded.status == OperationStatus.PARTIAL
    assert "gate is unavailable" in degraded.degraded_reasons
    assert degraded.store["healthy"] is True


def test_production_dispatch_maps_receipt_fields() -> None:
    pytest.importorskip("constellation_node_sdk")
    factory = _node_factory()
    request = factory.create(payload=_intent(), trace_id="trace-rp-002")
    response = _response_packet(request.canonical_packet)
    stub = _StubSdkClient(response=response)
    client = CanonicalGateClient(sdk_client=stub, packet_type=type(request.canonical_packet))

    receipt = client.dispatch(request)

    assert stub.sent == [request.canonical_packet]
    assert receipt.accepted is True
    assert receipt.packet_id == request.packet_id
    assert receipt.trace_id == "trace-rp-002"
    assert receipt.status == "accepted"
    assert receipt.authorization == "allow"
    assert receipt.route_reference == "gate-route-1"
    assert receipt.correlation_id == str(request.canonical_packet.header.correlation_id)


def test_trace_mismatch_fails_closed() -> None:
    pytest.importorskip("constellation_node_sdk")
    from constellation_node_sdk import create_transport_packet

    factory = _node_factory()
    request = factory.create(payload=_intent(), trace_id="trace-rp-002")
    mismatched = create_transport_packet(
        action="search",
        payload={"status": "accepted"},
        tenant="quantum-l9",
        source_node="gate",
        destination_node="memory-node",
        trace_id="other-trace",
    )
    with pytest.raises(GateMalformedReceiptError, match="trace_id"):
        receipt_from_response(
            request_packet=request.canonical_packet, response_packet=mismatched
        )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError("slow"), GateTimeoutError),
    ],
)
def test_timeout_is_distinct(error: Exception, expected: type[Exception]) -> None:
    pytest.importorskip("constellation_node_sdk")
    factory = _node_factory()
    request = factory.create(payload=_intent(), trace_id="trace-rp-002")
    client = CanonicalGateClient(
        sdk_client=_StubSdkClient(error=error),
        packet_type=type(request.canonical_packet),
    )
    with pytest.raises(expected):
        client.dispatch(request)


def test_http_denied_rejected_unavailable() -> None:
    pytest.importorskip("constellation_node_sdk")
    httpx = pytest.importorskip("httpx")
    factory = _node_factory()
    request = factory.create(payload=_intent(), trace_id="trace-rp-002")
    packet_type = type(request.canonical_packet)

    def _status(code: int) -> httpx.HTTPStatusError:
        req = httpx.Request("POST", "http://gate.example/v1/execute")
        resp = httpx.Response(code, request=req)
        return httpx.HTTPStatusError("gate", request=req, response=resp)

    cases = (
        (_status(403), GateDeniedError),
        (_status(422), GateRejectedError),
        (_status(503), GateUnavailableError),
        (httpx.TimeoutException("slow"), GateTimeoutError),
        (ValueError("Gate response body must be a JSON object"), GateMalformedReceiptError),
    )
    for error, expected in cases:
        client = CanonicalGateClient(
            sdk_client=_StubSdkClient(error=error), packet_type=packet_type
        )
        with pytest.raises(expected):
            client.dispatch(request)


def test_payload_denied_and_rejected_are_distinct() -> None:
    pytest.importorskip("constellation_node_sdk")
    factory = _node_factory()
    request = factory.create(payload=_intent(), trace_id="trace-rp-002")
    packet_type = type(request.canonical_packet)

    denied = CanonicalGateClient(
        sdk_client=_StubSdkClient(
            response=_response_packet(request.canonical_packet, payload={"status": "denied"})
        ),
        packet_type=packet_type,
    )
    with pytest.raises(GateDeniedError):
        denied.dispatch(request)

    rejected = CanonicalGateClient(
        sdk_client=_StubSdkClient(
            response=_response_packet(request.canonical_packet, payload={"status": "rejected"})
        ),
        packet_type=packet_type,
    )
    with pytest.raises(GateRejectedError):
        rejected.dispatch(request)


def test_local_duplicate_packet_is_rejected() -> None:
    pytest.importorskip("constellation_node_sdk")
    from constellation_node_sdk import TransportPacket

    client = CanonicalGateClient(sdk_client=_StubSdkClient(response=object()), packet_type=TransportPacket)
    with pytest.raises(BoundaryAlignmentError, match="authoritative TransportPacket"):
        client.dispatch(_LocalPacket(packet_id=str(uuid4())))


def test_node_factory_sets_runtime_source() -> None:
    pytest.importorskip("constellation_node_sdk")
    factory = _node_factory()
    packet = factory.create(payload=_intent(), trace_id="trace-rp-002")
    assert packet.canonical_packet.address.source_node == "memory-node"
    assert packet.canonical_packet.address.destination_node == "gate"
    assert packet.canonical_packet.provenance.origin_kind == "node"
