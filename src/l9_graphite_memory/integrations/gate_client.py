# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/integrations/gate_client.py
#   layer: integration
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-21

"""Production GateClientPort bound to constellation-node-sdk.GateClient.

This module does not select a destination, store a node registry, or expose a
peer URL to callers. Authentication and node identity come from the hosting
runtime config (env), never from request payloads. Retry and circuit-breaking
are omitted because GateClient.send_to_gate does not authorize them.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping
from importlib import import_module
from typing import Any, NoReturn, TypeVar

_T = TypeVar("_T")

from l9_graphite_memory.contracts.enums import OperationStatus
from l9_graphite_memory.contracts.receipts import HealthReport
from l9_graphite_memory.errors import (
    BoundaryAlignmentError,
    GateDeniedError,
    GateMalformedReceiptError,
    GateRejectedError,
    GateTimeoutError,
    GateUnavailableError,
    UnsupportedTransportPacketVersion,
)
from l9_graphite_memory.integrations.transport_packet import (
    load_authoritative_transport,
)
from l9_graphite_memory.ports.constellation import (
    GateDispatchReceipt,
    TransportPacketPort,
)

_DENIED_STATUS = frozenset({"denied", "forbidden", "unauthorized"})
_REJECTED_STATUS = frozenset({"rejected", "invalid", "malformed"})
_ACCEPTED_STATUS = frozenset({"accepted", "ok", "allowed", "admitted", "complete"})


def _httpx() -> Any | None:
    try:
        return import_module("httpx")
    except ImportError:
        return None


def _sdk_transport_errors() -> tuple[type[BaseException], ...]:
    types: list[type[BaseException]] = [TimeoutError, ValueError, TypeError]
    httpx = _httpx()
    if httpx is not None:
        types.extend(
            (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.HTTPStatusError,
                httpx.RequestError,
            )
        )
    return tuple(types)


def _raise_mapped(exc: BaseException) -> NoReturn:
    httpx = _httpx()
    if httpx is not None:
        if isinstance(exc, httpx.TimeoutException):
            raise GateTimeoutError("gate request timed out") from exc
        if isinstance(exc, httpx.ConnectError):
            raise GateUnavailableError("gate is unavailable") from exc
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            if code in {401, 403}:
                raise GateDeniedError(f"gate denied dispatch ({code})") from exc
            if code in {400, 409, 422}:
                raise GateRejectedError(f"gate rejected dispatch ({code})") from exc
            if code in {502, 503, 504}:
                raise GateUnavailableError(f"gate is unavailable ({code})") from exc
            raise GateUnavailableError(f"gate dispatch failed ({code})") from exc
    if isinstance(exc, TimeoutError):
        raise GateTimeoutError("gate request timed out") from exc
    if isinstance(exc, (ValueError, TypeError)):
        raise GateMalformedReceiptError(str(exc) or "gate receipt was malformed") from exc
    raise GateUnavailableError(f"gate dispatch failed: {type(exc).__name__}") from exc


def _payload_mapping(payload: Any) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    return {}


def _status_of(payload: Mapping[str, Any]) -> str:
    raw = payload.get("status") or payload.get("decision") or "accepted"
    status = str(raw).strip().lower()
    if not status:
        return "accepted"
    return status


def receipt_from_response(*, request_packet: Any, response_packet: Any) -> GateDispatchReceipt:
    """Validate a production Gate response packet against the dispatched packet."""
    request_trace = str(request_packet.header.trace_id)
    response_trace = str(response_packet.header.trace_id)
    if response_trace != request_trace:
        raise GateMalformedReceiptError("receipt trace_id does not match the dispatched packet")
    payload = _payload_mapping(response_packet.payload)
    status = _status_of(payload)
    if status in _DENIED_STATUS:
        raise GateDeniedError(f"gate denied dispatch ({status})")
    if status in _REJECTED_STATUS:
        raise GateRejectedError(f"gate rejected dispatch ({status})")
    accepted = status in _ACCEPTED_STATUS or payload.get("accepted") is True
    authorization = payload.get("authorization") or payload.get("authorization_decision")
    route = payload.get("route_reference") or payload.get("route")
    warnings = payload.get("warnings") or ()
    warning_tuple: tuple[str, ...]
    if isinstance(warnings, str):
        warning_tuple = (warnings,)
    else:
        warning_tuple = tuple(str(item) for item in warnings)
    return GateDispatchReceipt(
        accepted=accepted,
        packet_id=str(request_packet.header.packet_id),
        trace_id=request_trace,
        route_reference=str(route) if route else None,
        warnings=warning_tuple,
        status=status,
        authorization=str(authorization) if authorization is not None else None,
        correlation_id=str(response_packet.header.correlation_id),
    )


def attach_gate_health(report: HealthReport, gate: dict[str, Any]) -> HealthReport:
    """Keep memory-core status distinct from Gate availability."""
    degraded = list(report.degraded_reasons)
    status = report.status
    if gate.get("configured") and not gate.get("healthy"):
        if "gate is unavailable" not in degraded:
            degraded.append("gate is unavailable")
        if status == OperationStatus.COMPLETE:
            status = OperationStatus.PARTIAL
    return report.model_copy(
        update={"gate": gate, "status": status, "degraded_reasons": tuple(degraded)}
    )


class CanonicalGateClient:
    """GateClientPort adapter around constellation-node-sdk.GateClient."""

    def __init__(self, *, sdk_client: Any, packet_type: type[Any]) -> None:
        if sdk_client is None:
            raise UnsupportedTransportPacketVersion(
                "production Gate adapter requires constellation-node-sdk.GateClient"
            )
        self._client = sdk_client
        self._packet_type = packet_type

    @classmethod
    def from_env(cls) -> CanonicalGateClient:
        packet_type, _create, _installed = load_authoritative_transport()
        sdk = import_module("constellation_node_sdk")
        config = sdk.get_gate_client_config_from_env()
        return cls(sdk_client=sdk.GateClient(config), packet_type=packet_type)

    def dispatch(self, packet: TransportPacketPort) -> GateDispatchReceipt:
        return self._run(self.adispatch(packet))

    async def adispatch(self, packet: TransportPacketPort) -> GateDispatchReceipt:
        raw = getattr(packet, "canonical_packet", None)
        if raw is None or not isinstance(raw, self._packet_type):
            raise BoundaryAlignmentError(
                "production Gate adapter requires an authoritative TransportPacket"
            )
        try:
            response = await self._client.send_to_gate(raw)
        except _sdk_transport_errors() as exc:
            _raise_mapped(exc)
        if not isinstance(response, self._packet_type):
            raise GateMalformedReceiptError(
                "gate response was not a constellation-node-sdk TransportPacket"
            )
        return receipt_from_response(request_packet=raw, response_packet=response)

    def health(self) -> dict[str, Any]:
        return self._run(self.ahealth())

    async def ahealth(self) -> dict[str, Any]:
        try:
            body = await self._client.health()
        except _sdk_transport_errors() as exc:
            try:
                _raise_mapped(exc)
            except GateTimeoutError:
                return {
                    "name": "gate",
                    "configured": True,
                    "healthy": False,
                    "status": "unavailable",
                    "error": "timeout",
                }
            except GateDeniedError:
                return {
                    "name": "gate",
                    "configured": True,
                    "healthy": False,
                    "status": "denied",
                    "error": "denied",
                }
            except (GateUnavailableError, GateRejectedError, GateMalformedReceiptError):
                return {
                    "name": "gate",
                    "configured": True,
                    "healthy": False,
                    "status": "unavailable",
                    "error": type(exc).__name__,
                }
        if not isinstance(body, dict):
            return {
                "name": "gate",
                "configured": True,
                "healthy": False,
                "status": "unavailable",
                "error": "malformed-health",
            }
        return {
            "name": "gate",
            "configured": True,
            "healthy": True,
            "status": "available",
            "detail": {key: body[key] for key in body if key in {"status", "ok", "version"}},
        }

    def _run(self, coro: Coroutine[Any, Any, _T]) -> _T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise BoundaryAlignmentError(
            "CanonicalGateClient.dispatch cannot nest in a running loop; use adispatch"
        )
