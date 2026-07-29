"""Storage and awareness ports for the active-memory subsystem.

Implements the port definitions from the build plan Phase 1/2. These
are `Protocol` definitions with no implementation; concrete adapters
(in-memory reference, Redis, null) live in
`l9_graphite_memory.active.adapters` and MUST all pass the shared
conformance suite in `tests/conformance/active/`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from l9_graphite_memory.active.models import (
    ActiveContext,
    ActiveContextDraft,
    AgentEvent,
    AgentIdentity,
    AgentLease,
    AgentPresence,
    AgentScope,
    AgentSubscription,
)


class ActiveStoreHealth(Protocol):
    """Structural health-check result for an `ActiveStore` backend."""

    backend: str
    connectivity: str
    authentication: str


class ActiveAgentPage(Protocol):
    """One page of active-agent discovery results."""

    items: tuple[AgentPresence, ...]
    next_cursor: str | None


class ActiveStore(Protocol):
    """Storage port for agent presence, leases, and active context.

    All methods are async. Implementations MUST enforce deployment
    isolation transparently (callers never supply deployment_id
    directly to these methods; it is bound at construction time).
    """

    async def register(
        self, identity: AgentIdentity, lease: AgentLease
    ) -> AgentPresence:
        """Register a new agent instance and store its initial presence.

        Raises:
            ActiveMemoryUnavailableError: if the backend cannot be reached.
        """
        ...

    async def renew(self, lease: AgentLease) -> AgentPresence:
        """Renew an existing lease's heartbeat and expiry.

        Raises:
            LeaseExpiredError: if the lease has already expired.
            ActiveMemoryUnavailableError: if the backend cannot be reached.
        """
        ...

    async def unregister(self, lease: AgentLease) -> None:
        """Gracefully remove presence and context for this instance.

        Must be idempotent: unregistering an already-unregistered or
        expired lease must not raise.
        """
        ...

    async def put_context(
        self,
        lease: AgentLease,
        expected_version: int | None,
        draft: ActiveContextDraft,
    ) -> ActiveContext:
        """Atomically replace the current context with `draft`.

        Raises:
            ContextVersionConflictError: if `expected_version` is
                supplied and does not match the current stored version.
            LeaseExpiredError: if the lease has expired.
            ActiveMemoryUnavailableError: if the backend cannot be reached.
        """
        ...

    async def get_context(
        self, agent_id: str, instance_id: str | None = None
    ) -> ActiveContext | None:
        """Return the current context, or None if absent/expired."""
        ...

    async def get_presence(
        self, agent_id: str, instance_id: str | None = None
    ) -> AgentPresence | None:
        """Return the current presence record, or None if absent/expired."""
        ...

    async def list_active(
        self, scope: AgentScope, cursor: str | None, limit: int
    ) -> ActiveAgentPage:
        """Return one page of active agents matching `scope`.

        Implementations MUST discard expired presence records rather
        than relying solely on backend TTL propagation timing.
        """
        ...

    async def health(self) -> ActiveStoreHealth:
        """Return a structural health snapshot of this store backend."""
        ...

    async def close(self) -> None:
        """Release any held connections/resources. Must be idempotent."""
        ...


class AwarenessHealth(Protocol):
    """Structural health-check result for an `AwarenessBus` backend."""

    backend: str
    connectivity: str


class AwarenessBus(Protocol):
    """Best-effort, at-most-once notification port.

    Implementations MUST treat delivery as lossy: a publish failure or
    a disconnected subscriber must never be treated as a correctness
    failure of the active-memory subsystem. Current truth always lives
    in `ActiveStore`, never in the awareness bus.
    """

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event. Must not raise on "no subscribers"."""
        ...

    def subscribe(self, subscription: AgentSubscription) -> AsyncIterator[AgentEvent]:
        """Return an async iterator yielding events matching the scope.

        Implementations MUST support safe reconnection: if the
        underlying transport disconnects, the iterator must either
        raise a typed error the caller can catch to trigger
        resynchronization, or transparently reconnect and yield a
        catch-up marker event — but MUST NOT silently fabricate missed
        events.
        """
        ...

    async def health(self) -> AwarenessHealth:
        """Return a structural health snapshot of this bus backend."""
        ...

    async def close(self) -> None:
        """Release any held connections/resources. Must be idempotent."""
        ...
