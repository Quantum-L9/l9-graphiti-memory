# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/errors.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Typed failures for the memory substrate."""

from __future__ import annotations


class L9MemoryError(RuntimeError):
    """Base class for all operational memory failures."""


class ConfigurationError(L9MemoryError):
    """Configuration is missing, invalid, or contradictory."""


class AuthenticationError(L9MemoryError):
    """Caller authentication failed."""


class AuthorizationError(L9MemoryError):
    """Caller is authenticated but not authorized for the requested operation."""


class AdmissionError(L9MemoryError):
    """A memory candidate could not enter the governed write pipeline."""


class StoreError(L9MemoryError):
    """The canonical record store failed."""


class IdempotencyConflict(StoreError):
    """A concurrent write already committed this operation identity.

    Raised by a store when the unique ``(tenant_id, namespace,
    idempotency_key)`` constraint rejects an insert. The duplicate lookup runs
    before the transaction, so two retries of one operation racing each other
    can both miss it; the constraint is what actually decides, and the service
    resolves this into a DUPLICATE receipt rather than a failed write (ADR-008).
    """


class PhaseLockSnapshotConflict(StoreError):
    """A governed write lost its phase-lock snapshot race.

    The store re-verified the phase-lock snapshot inside the committing
    transaction and found the namespace had changed since the lock was
    verified, so the write was refused rather than admitted against a stale
    authorization (ADR-079).
    """


class ProjectionError(L9MemoryError):
    """A graph or semantic projection failed."""


class UnsupportedSchemaVersion(L9MemoryError):
    """No safe migration path exists for a persisted schema version."""


class ConflictDetected(L9MemoryError):
    """Conflicting active memories block the requested phase lock."""


class BoundaryAlignmentError(L9MemoryError):
    """An L9 constellation boundary violated transport or Gate invariants."""


class UnsupportedTransportPacketVersion(BoundaryAlignmentError):
    """The installed constellation-node-sdk version is missing or unsupported."""


class GateDispatchError(BoundaryAlignmentError):
    """A production Gate dispatch failed with a typed, evidence-bearing outcome."""


class GateDeniedError(GateDispatchError):
    """Gate denied the packet (authorization or admission)."""


class GateRejectedError(GateDispatchError):
    """Gate rejected the packet as invalid or policy-violating."""


class GateUnavailableError(GateDispatchError):
    """Gate could not be reached or is not ready."""


class GateTimeoutError(GateDispatchError):
    """The Gate request exceeded the configured timeout."""


class GateMalformedReceiptError(GateDispatchError):
    """Gate returned a body that is not a valid dispatch receipt."""
