# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/ports/__init__.py
#   layer: port
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Backend-neutral ports used by the core services."""

from .clock import Clock, SystemClock
from .constellation import (
    GateClientPort,
    GateDispatchReceipt,
    TransportPacketFactory,
    TransportPacketPort,
)
from .phase_lock import PhaseLockPrecondition, snapshot_digest
from .projection import ProjectionAdapter, ProjectionHit
from .record_store import RecordStore
from .service_capability import (
    SERVICE_WRITE_CAPABILITY,
    ServiceWriteCapability,
    require_service_write_capability,
)
from .synthesis import ProceduralSynthesizer, SynthesizedProcedure

__all__ = [
    "SERVICE_WRITE_CAPABILITY",
    "Clock",
    "GateClientPort",
    "GateDispatchReceipt",
    "PhaseLockPrecondition",
    "ProceduralSynthesizer",
    "ProjectionAdapter",
    "ProjectionHit",
    "RecordStore",
    "ServiceWriteCapability",
    "SynthesizedProcedure",
    "SystemClock",
    "TransportPacketFactory",
    "TransportPacketPort",
    "require_service_write_capability",
    "snapshot_digest",
]
