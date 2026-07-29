# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/errors.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Typed error hierarchy for the active-memory subsystem.

All active-memory failures MUST raise one of these typed errors so that
external consumers (via the stable SDK) can distinguish transient
backend unavailability from contract violations, without needing to
inspect Redis-specific exception types.
"""

from __future__ import annotations


class ActiveMemoryError(Exception):
    """Base class for all active-memory subsystem errors."""


class ActiveMemoryUnavailableError(ActiveMemoryError):
    """Raised when the configured active-memory backend cannot be reached.

    This error MUST NOT be raised for canonical Graphiti memory
    operations; it is scoped strictly to the active (Redis-backed)
    layer. Per the failure/degradation policy, canonical memory
    operations must remain unaffected when active memory is optional.
    """


class ContextVersionConflictError(ActiveMemoryError):
    """Raised when an optimistic `expected_version` check fails.

    Attributes:
        expected_version: The version the caller believed was current.
        current_version: The version actually stored in the backend.
    """

    def __init__(self, expected_version: int | None, current_version: int) -> None:
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"context version conflict: expected={expected_version!r} "
            f"current={current_version!r}"
        )


class LeaseExpiredError(ActiveMemoryError):
    """Raised when an operation is attempted against an expired lease.

    Callers must re-register (obtaining a new `instance_id`) rather than
    attempt to renew an expired lease.
    """

    def __init__(self, agent_id: str, instance_id: str) -> None:
        self.agent_id = agent_id
        self.instance_id = instance_id
        super().__init__(
            f"lease expired for agent_id={agent_id!r} instance_id={instance_id!r}; "
            "re-registration with a new instance_id is required"
        )


class SchemaCompatibilityError(ActiveMemoryError):
    """Raised when a record's schema_version is not supported.

    Unknown additive (minor) schema versions must be tolerated by
    consumers; this error is reserved for unsupported major schema
    versions per the SDK compatibility policy.
    """

    def __init__(
        self, observed_version: int, supported_versions: tuple[int, ...]
    ) -> None:
        self.observed_version = observed_version
        self.supported_versions = supported_versions
        super().__init__(
            f"unsupported schema_version={observed_version!r}; "
            f"supported={supported_versions!r}"
        )
