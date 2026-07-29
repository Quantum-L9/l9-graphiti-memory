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
    """No-op `ActiveStore` used when active memory is disabled."""

    async def register(
        self, identity: AgentIdentity, lease: AgentLease
    ) -> AgentPresence:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def renew(self, lease: AgentLease) -> AgentPresence:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def unregister(self, lease: AgentLease) -> None:
        return None

    async def put_context(
        self,
        lease: AgentLease,
        expected_version: int | None,
        draft: ActiveContextDraft,
    ) -> ActiveContext:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def get_context(
        self, agent_id: str, instance_id: str | None = None
    ) -> ActiveContext | None:
        return None

    async def get_presence(
        self, agent_id: str, instance_id: str | None = None
    ) -> AgentPresence | None:
        return None

    async def list_active(
        self, scope: AgentScope, cursor: str | None, limit: int
    ) -> _NullPage:
        return _NullPage()

    async def health(self) -> _NullHealth:
        return _NullHealth()

    async def close(self) -> None:
        return None


class NullAwarenessBus:
    """No-op `AwarenessBus` used when active memory is disabled."""

    async def publish(self, event: AgentEvent) -> None:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)

    async def subscribe(self, subscription: object) -> AsyncIterator[AgentEvent]:
        raise ActiveMemoryUnavailableError(_DISABLED_MESSAGE)
        yield  # pragma: no cover - unreachable, satisfies async generator typing

    async def health(self) -> _NullHealth:
        return _NullHealth()

    async def close(self) -> None:
        return None
