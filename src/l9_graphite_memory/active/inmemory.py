"""In-memory reference adapters for `ActiveStore` and `AwarenessBus`.

These adapters are the deterministic reference implementation used by
the shared conformance suite (`tests/conformance/active/`) and by
consumer unit tests that need active-memory behavior without a real
Redis instance. Behavior here MUST match the Redis adapter's documented
semantics exactly (TTL expiry, optimistic version conflicts, deployment
isolation) so that the conformance suite is meaningful.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from l9_graphite_memory.active.deployment import ActiveDeployment
from l9_graphite_memory.active.errors import (
    ActiveMemoryUnavailableError,
    ContextVersionConflictError,
    LeaseExpiredError,
)
from l9_graphite_memory.active.models import (
    ActiveContext,
    ActiveContextDraft,
    AgentEvent,
    AgentIdentity,
    AgentLease,
    AgentPresence,
    AgentScope,
    AgentStatus,
    AgentSubscription,
)

Clock = Callable[[], datetime]


@dataclass(slots=True)
class _InMemoryStoreHealth:
    backend: str = "in_memory"
    connectivity: str = "healthy"
    authentication: str = "not_applicable"


@dataclass(slots=True)
class _InMemoryAgentPage:
    items: tuple[AgentPresence, ...]
    next_cursor: str | None


@dataclass(slots=True)
class _InMemoryAwarenessHealth:
    backend: str = "in_memory"
    connectivity: str = "healthy"


class InMemoryActiveStore:
    """Deterministic in-memory `ActiveStore` implementation.

    Args:
        deployment: The immutable deployment identity this store
            instance is bound to. All operations are implicitly scoped
            to this deployment; there is no cross-deployment access.
        clock: Callable returning the current UTC `datetime`. Injectable
            for deterministic testing (e.g. a fake clock).
        context_ttl_seconds: TTL applied to every committed context.
        presence_ttl_seconds: TTL applied to every presence record.
        simulate_unavailable: If True, all operations raise
            `ActiveMemoryUnavailableError`. Used by degradation tests.
    """

    def __init__(
        self,
        deployment: ActiveDeployment,
        *,
        clock: Clock,
        context_ttl_seconds: int = 60,
        presence_ttl_seconds: int = 30,
        simulate_unavailable: bool = False,
    ) -> None:
        self._deployment = deployment
        self._clock = clock
        self._context_ttl_seconds = context_ttl_seconds
        self._presence_ttl_seconds = presence_ttl_seconds
        self._simulate_unavailable = simulate_unavailable
        self._presences: dict[tuple[str, str], AgentPresence] = {}
        self._contexts: dict[tuple[str, str], ActiveContext] = {}
        self._leases: dict[tuple[str, str], AgentLease] = {}
        self._presence_version_counter = itertools.count(start=1)
        self._context_version_counter: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    def set_unavailable(self, value: bool) -> None:
        """Toggle simulated backend unavailability for outage tests."""
        self._simulate_unavailable = value

    def _check_available(self) -> None:
        if self._simulate_unavailable:
            raise ActiveMemoryUnavailableError(
                f"in-memory active store for deployment "
                f"{self._deployment.deployment_id!r} is simulated unavailable"
            )

    async def register(
        self, identity: AgentIdentity, lease: AgentLease
    ) -> AgentPresence:
        self._check_available()
        async with self._lock:
            key = (identity.agent_id, identity.instance_id)
            now = self._clock()
            presence = AgentPresence(
                identity=identity,
                status=AgentStatus.STARTING,
                deployment_id=self._deployment.deployment_id,
                started_at=now,
                heartbeat_at=now,
                expires_at=now + timedelta(seconds=self._presence_ttl_seconds),
                presence_version=next(self._presence_version_counter),
            )
            self._presences[key] = presence
            self._leases[key] = lease
            return presence

    async def renew(self, lease: AgentLease) -> AgentPresence:
        self._check_available()
        async with self._lock:
            key = (lease.agent_id, lease.instance_id)
            now = self._clock()
            stored_lease = self._leases.get(key)
            if stored_lease is None or stored_lease.is_expired(now):
                raise LeaseExpiredError(lease.agent_id, lease.instance_id)
            existing = self._presences.get(key)
            if existing is None or existing.is_expired(now):
                raise LeaseExpiredError(lease.agent_id, lease.instance_id)
            renewed = AgentPresence(
                identity=existing.identity,
                status=existing.status,
                deployment_id=existing.deployment_id,
                started_at=existing.started_at,
                heartbeat_at=now,
                expires_at=now + timedelta(seconds=self._presence_ttl_seconds),
                presence_version=next(self._presence_version_counter),
            )
            self._presences[key] = renewed
            return renewed

    async def unregister(self, lease: AgentLease) -> None:
        self._check_available()
        async with self._lock:
            key = (lease.agent_id, lease.instance_id)
            self._presences.pop(key, None)
            self._contexts.pop(key, None)
            self._leases.pop(key, None)

    async def put_context(
        self,
        lease: AgentLease,
        expected_version: int | None,
        draft: ActiveContextDraft,
    ) -> ActiveContext:
        self._check_available()
        async with self._lock:
            key = (lease.agent_id, lease.instance_id)
            now = self._clock()
            stored_lease = self._leases.get(key)
            if stored_lease is None or stored_lease.is_expired(now):
                raise LeaseExpiredError(lease.agent_id, lease.instance_id)
            presence = self._presences.get(key)
            if presence is None:
                raise LeaseExpiredError(lease.agent_id, lease.instance_id)

            current_version = self._context_version_counter.get(key, 0)
            if expected_version is not None and expected_version != current_version:
                raise ContextVersionConflictError(expected_version, current_version)

            new_version = current_version + 1
            self._context_version_counter[key] = new_version

            group_id = (
                presence.identity.memory_group_ids[0]
                if presence.identity.memory_group_ids
                else "default"
            )
            context = ActiveContext(
                agent_id=lease.agent_id,
                instance_id=lease.instance_id,
                role=presence.identity.role,
                deployment_id=self._deployment.deployment_id,
                group_id=group_id,
                draft=draft,
                version=new_version,
                updated_at=now,
                expires_at=now + timedelta(seconds=self._context_ttl_seconds),
            )
            self._contexts[key] = context
            return context

    async def get_context(
        self, agent_id: str, instance_id: str | None = None
    ) -> ActiveContext | None:
        self._check_available()
        async with self._lock:
            now = self._clock()
            if instance_id is not None:
                context = self._contexts.get((agent_id, instance_id))
                if context is None or context.is_expired(now):
                    return None
                return context
            candidates = [
                ctx
                for (aid, _iid), ctx in self._contexts.items()
                if aid == agent_id and not ctx.is_expired(now)
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda c: c.updated_at)

    async def get_presence(
        self, agent_id: str, instance_id: str | None = None
    ) -> AgentPresence | None:
        self._check_available()
        async with self._lock:
            now = self._clock()
            if instance_id is not None:
                presence = self._presences.get((agent_id, instance_id))
                if presence is None or presence.is_expired(now):
                    return None
                return presence
            candidates = [
                p
                for (aid, _iid), p in self._presences.items()
                if aid == agent_id and not p.is_expired(now)
            ]
            if not candidates:
                return None
            return max(candidates, key=lambda p: p.heartbeat_at)

    async def list_active(
        self, scope: AgentScope, cursor: str | None, limit: int
    ) -> _InMemoryAgentPage:
        self._check_available()
        async with self._lock:
            now = self._clock()
            matches = []
            for presence in self._presences.values():
                if presence.is_expired(now):
                    continue
                if presence.deployment_id != scope.deployment_id:
                    continue
                if scope.role is not None and presence.identity.role != scope.role:
                    continue
                if (
                    scope.group_id is not None
                    and scope.group_id not in presence.identity.memory_group_ids
                ):
                    continue
                matches.append(presence)
            matches.sort(key=lambda p: (p.identity.agent_id, p.identity.instance_id))

            start_index = 0
            if cursor is not None:
                for idx, presence in enumerate(matches):
                    token = (
                        f"{presence.identity.agent_id}:{presence.identity.instance_id}"
                    )
                    if token == cursor:
                        start_index = idx + 1
                        break

            page_items = tuple(matches[start_index : start_index + limit])
            next_cursor = None
            if start_index + limit < len(matches):
                last = page_items[-1]
                next_cursor = f"{last.identity.agent_id}:{last.identity.instance_id}"
            return _InMemoryAgentPage(items=page_items, next_cursor=next_cursor)

    async def health(self) -> _InMemoryStoreHealth:
        if self._simulate_unavailable:
            return _InMemoryStoreHealth(connectivity="unavailable")
        return _InMemoryStoreHealth()

    async def close(self) -> None:
        return None


class InMemoryAwarenessBus:
    """Deterministic in-memory `AwarenessBus` implementation.

    Uses one `asyncio.Queue` per active subscription. Publishing to a
    scope with no active subscriptions is a no-op success, matching
    the at-most-once, fire-and-forget semantics of the Redis adapter.
    """

    def __init__(
        self,
        deployment: ActiveDeployment,
        *,
        simulate_unavailable: bool = False,
        max_queue_size: int = 1000,
    ) -> None:
        self._deployment = deployment
        self._simulate_unavailable = simulate_unavailable
        self._max_queue_size = max_queue_size
        self._subscribers: list[tuple[AgentScope, asyncio.Queue[AgentEvent]]] = []
        self._lock = asyncio.Lock()

    def set_unavailable(self, value: bool) -> None:
        """Toggle simulated backend unavailability for outage tests."""
        self._simulate_unavailable = value

    def _matches(self, scope: AgentScope, event: AgentEvent) -> bool:
        if event.deployment_id != scope.deployment_id:
            return False
        if scope.role is not None and event.role != scope.role:
            return False
        if scope.group_id is not None and event.group_id != scope.group_id:  # noqa: SIM103
            return False
        return True

    async def publish(self, event: AgentEvent) -> None:
        if self._simulate_unavailable:
            raise ActiveMemoryUnavailableError(
                f"in-memory awareness bus for deployment "
                f"{self._deployment.deployment_id!r} is simulated unavailable"
            )
        async with self._lock:
            for scope, queue in self._subscribers:
                if self._matches(scope, event):
                    if queue.full():
                        # At-most-once semantics: drop rather than block or
                        # raise. This mirrors Redis Pub/Sub's lossy behavior
                        # under slow-consumer backpressure.
                        continue
                    queue.put_nowait(event)

    async def subscribe(
        self, subscription: AgentSubscription
    ) -> AsyncIterator[AgentEvent]:
        if self._simulate_unavailable:
            raise ActiveMemoryUnavailableError(
                f"in-memory awareness bus for deployment "
                f"{self._deployment.deployment_id!r} is simulated unavailable"
            )
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=self._max_queue_size)
        entry = (subscription.scope, queue)
        async with self._lock:
            self._subscribers.append(entry)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                if entry in self._subscribers:
                    self._subscribers.remove(entry)

    async def health(self) -> _InMemoryAwarenessHealth:
        if self._simulate_unavailable:
            return _InMemoryAwarenessHealth(connectivity="unavailable")
        return _InMemoryAwarenessHealth()

    async def close(self) -> None:
        async with self._lock:
            self._subscribers.clear()
