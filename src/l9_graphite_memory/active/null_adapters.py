# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/active/null_adapters.py
#   layer: package
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Null-object adapters used when active memory is disabled.

When `active_memory.enabled = false`, the runtime factory MUST wire
these adapters instead of `InMemoryActiveStore`/`InMemoryAwarenessBus`
or a Redis adapter. Every operation raises `ActiveMemoryUnavailableError`
so that callers using the stable SDK degrade predictably rather than
silently succeeding with fabricated state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from l9_graphite_memory.active.errors import ActiveMemoryUnavailableError
from l9_graphite_memory.active.models import (
    ActiveContext,
    ActiveContextDraft,
    AgentEvent,
    AgentIdentity,
    AgentLease,
    AgentPresence,
    AgentScope,
)

_DISABLED_MESSAGE = (
    "active memory is disabled for this deployment; enable "
    "active_memory.enabled to use presence, context, or awareness features"
)


class _NullHealth:
    backend: str = "null"
    connectivity: str = "disabled"
    authentication: str = "not_applicable"


class _NullPage:
    items: tuple[AgentPresence, ...] = ()
    next_cursor: str | None = None


class NullActiveStore:
    """No-op `ActiveStore` used when active memory is disabled.

    Every method below intentionally ignores its arguments and (for the
    read/lifecycle methods) contains no `await`: this class exists purely
    to satisfy the `ActiveStore` port's async call signature while active
    memory is disabled, so parameter names and `async` are load-bearing
    for Liskov compatibility, not incidental.
    """

    async def register(self, _identity: AgentIdentity, _lease: AgentLease) -> AgentPresence:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def renew(self, _lease: AgentLease) -> AgentPresence:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def unregister(self, _lease: AgentLease) -> None:  # NOSONAR(S7503)
        return None

    async def put_context(
        self,
        _lease: AgentLease,
        _expected_version: int | None,
        _draft: ActiveContextDraft,
    ) -> ActiveContext:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def get_context(
        self, _agent_id: str, _instance_id: str | None = None
    ) -> ActiveContext | None:  # NOSONAR(S7503)
        return None

    async def get_presence(
        self, _agent_id: str, _instance_id: str | None = None
    ) -> AgentPresence | None:  # NOSONAR(S7503)
        return None

    async def list_active(
        self, _scope: AgentScope, _cursor: str | None, _limit: int
    ) -> _NullPage:  # NOSONAR(S7503)
        return _NullPage()

    async def health(self) -> _NullHealth:  # NOSONAR(S7503)
        return _NullHealth()

    async def close(self) -> None:  # NOSONAR(S7503)
        return None


class NullAwarenessBus:
    """No-op `AwarenessBus` used when active memory is disabled.

    See `NullActiveStore` for why unused parameters and `async` are kept.
    """

    async def publish(self, _event: AgentEvent) -> None:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def subscribe(self, _subscription: object) -> AsyncIterator[AgentEvent]:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)
        yield  # NOSONAR(S1763) - unreachable; makes this an async generator to match AwarenessBus.subscribe

    async def health(self) -> _NullHealth:  # NOSONAR(S7503)
        return _NullHealth()

    async def close(self) -> None:  # NOSONAR(S7503)
        return None
